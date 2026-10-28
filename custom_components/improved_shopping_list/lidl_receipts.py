"""Lidl printed HTML receipts: extract data only, never render provider HTML."""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from html.parser import HTMLParser
import json
import re

from homeassistant.util import dt as dt_util
from .catalog import CatalogError
from .receipt_parser import _identify_receipt


def amount(value):
    if type(value) not in (str, int, float):
        raise CatalogError("Lidl ha devuelto un importe no válido.", "lidl_ticket_format")
    try:
        text = str(value).strip().replace("€", "").strip()
        if "," in text:
            text = text.replace(".", "").replace(",", ".")
        result = Decimal(text)
    except InvalidOperation as err:
        raise CatalogError("Lidl ha devuelto un importe no válido.", "lidl_ticket_format") from err
    if not result.is_finite() or not 0 <= result <= 1000000:
        raise CatalogError("El importe de Lidl está fuera de rango.", "lidl_ticket_format")
    return result


def ticket_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_~.:%+=/-]{1,512}", value):
        raise CatalogError("La referencia del ticket de Lidl no es válida.", "lidl_ticket_identity")
    return value


def summary(raw):
    if not isinstance(raw, dict):
        raise CatalogError("Lidl ha devuelto un historial no reconocido.", "lidl_history_format")
    reference = ticket_id(raw.get("id"))
    date = raw.get("date")
    when = dt_util.parse_datetime(date) if isinstance(date, str) and len(date) <= 80 else None
    if when is None:
        raise CatalogError("La fecha de compra de Lidl no es válida.", "lidl_history_format")
    if when.tzinfo is None:
        when = when.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
    return {"reference": reference, "purchased_at": dt_util.as_local(when).isoformat(),
            "amount": float(amount(raw.get("totalAmount"))), "supported": not raw.get("isDeleted", False)}


class PrintedReceipt(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.articles, self.text, self._row, self._depth = [], [], None, 0

    def handle_starttag(self, tag, attrs):
        data = dict(attrs)
        if tag == "span":
            if self._row is not None:
                self._depth += 1
            elif "article" in data.get("class", "").split():
                self._row = {"attributes": data, "text": ""}
                self.articles.append(self._row)
                self._depth = 1
        if tag in ("br", "div", "p"):
            self.text.append("\n")

    def handle_endtag(self, tag):
        if tag == "span" and self._row is not None:
            self._depth -= 1
            if self._depth == 0:
                self._row = None

    def handle_data(self, data):
        self.text.append(data)
        if self._row is not None:
            self._row["text"] += data


def extract_lidl_ticket(detail, reference, expected_total, expected_date):
    if not isinstance(detail, dict) or detail.get("id") != ticket_id(reference) or detail.get("isDeleted"):
        raise CatalogError("El detalle de Lidl no corresponde a la compra.", "lidl_ticket_identity")
    parsed = summary({**detail, "totalAmount": expected_total})
    expected = dt_util.parse_datetime(expected_date)
    if expected is not None and expected.tzinfo is None:
        expected = expected.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
    if expected is None or abs(dt_util.parse_datetime(parsed["purchased_at"]).timestamp() - expected.timestamp()) > 60:
        raise CatalogError("La fecha del ticket de Lidl no coincide.", "lidl_ticket_identity")
    html = detail.get("htmlPrintedReceipt")
    if not isinstance(html, str) or not 1 <= len(html) <= 1500000:
        raise CatalogError("Lidl no ha devuelto un ticket HTML reconocido.", "lidl_ticket_format")
    parser = PrintedReceipt(); parser.feed(html)
    if not 1 <= len(parser.articles) <= 600:
        raise CatalogError("No se reconocen los artículos de Lidl.", "lidl_ticket_format")
    lines = []; previous = None
    for index, row in enumerate(parser.articles):
        attrs, text = row["attributes"], row["text"]
        code, name = attrs.get("data-art-id", ""), attrs.get("data-art-description", "").strip()
        if not re.fullmatch(r"[0-9]{1,16}", code) or not 1 <= len(name) <= 500:
            raise CatalogError("No se reconoce una línea de Lidl.", "lidl_ticket_format")
        signature = tuple(attrs.get(k) for k in ("data-art-id", "data-art-description", "data-unit-price", "data-art-quantity"))
        # Weighted items have a second article span explaining kg × price/kg.
        if previous == signature and re.match(r"^\s*\d+(?:[.,]\d+)?\s*(?:kg|g|uds?)\s*[x×*]", text, re.I):
            continue
        previous = signature
        quantity, price = amount(attrs.get("data-art-quantity", "1")), amount(attrs.get("data-unit-price"))
        amounts = re.findall(r"(?<![\d.,])-?\d+[.,]\d{2}(?!\d)", text)
        if not amounts or not quantity or quantity > 10000:
            raise CatalogError("No se reconocen las cantidades de Lidl.", "lidl_ticket_format")
        total = amount(amounts[-1])
        if abs((quantity * price).quantize(Decimal(".01"), rounding=ROUND_HALF_UP) - total) > Decimal(".02"):
            raise CatalogError("La cantidad y el precio de Lidl no coinciden.", "lidl_ticket_amount")
        following = parser.articles[index+1] if index+1 < len(parser.articles) else None
        weighted = quantity != int(quantity) or bool(following and following["attributes"].get("data-art-id") == code and re.search(r"\bkg\b", following["text"], re.I))
        count = 1 if weighted else int(quantity)
        pack = re.search(r"\b(\d+(?:[,.]\d+)?)\s*(kg|g|ml|cl|l)\b", name, re.I)
        lines.append({"id": str(len(lines)), "description": name, "count": count,
            "unit_price": float(total / count), "amount": float(total), "reference_id": code, "ean": "",
            "pack_quantity": float(quantity) if weighted else float(pack[1].replace(",", ".")) if pack else None,
            "pack_unit": "kg" if weighted else pack[2].lower() if pack else ""})
    text = "".join(parser.text)
    totals = re.findall(r"(?:^|\n)\s*TOTAL\s+(\d+[.,]\d{2})(?:\s|$)", text, re.I)
    total = amount(expected_total); subtotal = sum((Decimal(str(line["amount"])) for line in lines), Decimal(0))
    if not totals or abs(amount(totals[-1]) - total) > Decimal(".02") or abs(subtotal-total) > Decimal(".02"):
        # Unknown discount/return layouts need a dedicated parser, never guessed prices.
        raise CatalogError("Los artículos no coinciden con el total de Lidl; se conserva la compra sin revisar.", "lidl_ticket_amount")
    receipt = {"store": "lidl", "store_name": "Lidl", "identity": reference, "purchased_at": parsed["purchased_at"],
        "currency": "EUR", "subtotal": float(subtotal), "discount": 0, "shipping": 0, "total": float(total),
        "article_count": sum(line["count"] for line in lines), "lines": lines}
    return _identify_receipt(receipt, json.dumps(receipt, ensure_ascii=False, sort_keys=True).encode())
