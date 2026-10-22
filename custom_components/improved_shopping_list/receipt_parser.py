"""Local receipt extraction. Only recognized formats produce importable purchases."""

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from hashlib import sha256
from io import BytesIO
import re
import math
import json

from pypdf import PdfReader

from .catalog import CatalogError

MAX_PDF_BYTES = 2 * 1024 * 1024
MONEY = r"\d+(?:\.\d{3})*,\d{2}"


def money(value):
    return float(Decimal(value.replace(".", "").replace(",", ".")))


def parse_carrefour(text):
    """Carrefour electronic till receipts, retaining coupon and pack distinctions."""
    if "CARREFOUR" not in text.upper():
        raise CatalogError("Este formato de ticket todavía no está disponible. Empieza con un ticket PDF de Carrefour.")
    lines, items, pending = text.splitlines(), [], ""
    subtotal = total = None
    for raw in lines:
        line = re.sub(r"\s+", " ", raw).strip()
        if match := re.fullmatch(rf"SUBTOTAL\s+({MONEY})", line, re.I):
            subtotal = money(match[1])
            break
        if re.match(r"[=═]{3,}", line):
            continue
        if match := re.fullmatch(rf"(\d+)\s*[xX×]\s*\(\s*({MONEY})\s*\)\s*({MONEY})", line):
            if not pending:
                raise CatalogError("No se ha podido identificar el producto de una línea con varias unidades.")
            count, unit_price, amount = int(match[1]), money(match[2]), money(match[3])
            if count < 1 or abs(round(count * unit_price, 2) - amount) > .01:
                raise CatalogError("Las cantidades y el importe de una línea del ticket no coinciden.")
            items.append({"description": pending, "count": count, "unit_price": unit_price, "amount": amount})
            pending = ""
            continue
        if match := re.fullmatch(rf"(.+?)\s+({MONEY})", line):
            description = match[1].strip()
            if description.upper().startswith(("CIF", "TEL", "TOTAL", "DTO", "DESCUENTO")):
                continue
            items.append({"description": description, "count": 1, "unit_price": money(match[2]), "amount": money(match[2])})
            pending = ""
        elif line and not re.search(r"CARREFOUR|CIF:|TEL[FÉE]|\*{3}", line, re.I):
            pending = line
    if not items or subtotal is None or len(items) > 300:
        raise CatalogError("No se han podido identificar las líneas de compra de este ticket.", "receipt_unrecognized_lines")
    if abs(round(sum(item["amount"] for item in items), 2) - subtotal) > .02:
        raise CatalogError("El detalle extraído no coincide con el subtotal. No se ha importado el ticket.")
    match = re.search(rf"(\d+)\s+ART\.\s+TOTAL A PAGAR\s*:\s*({MONEY})", text, re.I)
    if not match or int(match[1]) != sum(item["count"] for item in items):
        raise CatalogError("No se ha podido comprobar el número de artículos del ticket.")
    total = money(match[2])
    date_match = re.search(r"\b(\d{2})/(\d{2})/(\d{2,4})\s+(\d{2}:\d{2}(?::\d{2})?)", text)
    if not date_match:
        raise CatalogError("No se ha podido identificar la fecha de compra.")
    day, month, year, hour = date_match.groups()
    year = "20" + year if len(year) == 2 else year
    try:
        purchased_at = datetime.fromisoformat(f"{year}-{month}-{day}T{hour}").isoformat()
    except ValueError as err:
        raise CatalogError("La fecha del ticket no es válida.") from err
    identity = re.search(r"\bNRF:\s*([A-Z0-9]+)", text)
    for index, item in enumerate(items):
        item["id"] = str(index)
        # Numbers without an explicit unit (e.g. ANACARDO CRUDO 200) are not weights.
        pack = re.search(r"\b(\d+(?:[,.]\d+)?)\s*(KG|GRS?|G|ML|CL|LITROS?|L)\b", item["description"], re.I)
        item["pack_quantity"] = float(pack[1].replace(",", ".")) if pack else None
        item["pack_unit"] = ({"gr":"g", "grs":"g", "litro":"l", "litros":"l"}.get(pack[2].lower(), pack[2].lower()) if pack else "")
    return {"store": "carrefour", "store_name": "Carrefour", "purchased_at": purchased_at,
        "identity": identity[1] if identity else "", "currency": "EUR", "subtotal": subtotal,
        "discount": round(subtotal - total, 2), "total": total, "article_count": int(match[1]), "lines": items}



def parse_carrefour_invoice(text):
    """Online Carrefour invoices: PVP is the line total before promotions."""
    if not re.search(r"C\.?C\.?\s+CARREFOUR|CARREFOUR", text, re.I) or not re.search(r"EAN\s+DESCRIPCI[ÓO]N\s+CANTIDAD\s+PVP", text, re.I):
        raise CatalogError("No se reconoce el formato de esta factura de Carrefour.")
    identity = re.search(r"\bFACTURA\s+N[º°OÚU]?[:.]?\s*([A-Z0-9][A-Z0-9/-]{2,60})", text, re.I)
    date_match = re.search(r"FECHA\s+FACTURA\s*:\s*(\d{2}/\d{2}/\d{4})", text, re.I)
    if not identity or not date_match:
        raise CatalogError("No se han podido identificar el número y la fecha de la factura.")
    try:
        purchased_at = datetime.strptime(date_match[1], "%d/%m/%Y").isoformat()
    except ValueError as err:
        raise CatalogError("La fecha de la factura no es válida.") from err
    def decimal(value):
        return Decimal(value.replace(".", "").replace(",", "."))
    def summary(label, *, optional=False):
        matches = re.findall(rf"(?m)^\s*{label}\s+(-?{MONEY})\s+EUR\s*$", text, re.I)
        if len(matches) != 1:
            if optional and not matches:
                return Decimal(0)
            raise CatalogError("No se han podido comprobar los totales de la factura.")
        return decimal(matches[0])
    items = []
    row_pattern = re.compile(rf"^(\d{{8}}|\d{{12,14}})\s+(.+?)\s+(\d+(?:\.\d{{3}})*,\d{{3}})\s+({MONEY})\s+(-?{MONEY})\s+({MONEY})\s+({MONEY})\s+({MONEY})$")
    for raw in text.splitlines():
        line = re.sub(r"\s+", " ", raw).strip()
        if not re.match(r"^\d{8,14}\s", line):
            continue
        match = row_pattern.fullmatch(line)
        if not match:
            raise CatalogError("Hay una línea de factura cuyo EAN, cantidad o precio no se ha podido leer.")
        ean, description, count_text, gross_text, discount_text, net_text, base_text, tax_text = match.groups()
        check = sum(int(digit) * (3 if index % 2 == 0 else 1) for index, digit in enumerate(reversed(ean[:-1])))
        if (10 - check % 10) % 10 != int(ean[-1]):
            raise CatalogError("Hay un EAN no válido en la factura. No se ha importado.")
        count, gross, adjustment, net = map(decimal, (count_text, gross_text, discount_text, net_text))
        if count <= 0 or count > 1000000 or net > gross or abs(gross + adjustment - net) > Decimal("0.01"):
            raise CatalogError("Las cantidades, descuentos e importes de la factura no coinciden.")
        # Prices remain before promotions; a free item must not overwrite its price with zero.
        unit_price = (gross / count).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        pack = re.search(r"\b(\d+(?:[,.]\d+)?)\s*(KG|GRS?|G|ML|CL|LITROS?|L)\b", description, re.I)
        items.append({"id":str(len(items)), "description":description, "ean":ean,
            "count":float(count), "unit_price":float(unit_price), "amount":float(net),
            "gross_amount":float(gross), "line_discount":float(gross-net),
            "pack_quantity":float(pack[1].replace(",", ".")) if pack else None,
            "pack_unit":({"gr":"g", "grs":"g", "litro":"l", "litros":"l"}.get(pack[2].lower(), pack[2].lower()) if pack else "")})
    if not 1 <= len(items) <= 300:
        raise CatalogError("No se han podido identificar las líneas de productos de la factura.")
    subtotal = summary("TOTAL IMPUESTOS INCLUIDOS")
    shipping = summary("TOTAL GASTOS DE ENV[ÍI]O", optional=True)
    discount = summary(r"OTROS DESCUENTOS/BONIF\. FACTURA", optional=True)
    total = summary("TOTAL FACTURA")
    if min(subtotal,shipping,discount,total) < 0 or abs(sum(Decimal(str(item["amount"])) for item in items)-subtotal) > Decimal("0.02") or abs(subtotal+shipping-discount-total) > Decimal("0.02"):
        raise CatalogError("El detalle, los gastos de envío y el total de la factura no coinciden. No se ha importado.")
    return {"store":"carrefour", "store_name":"Carrefour", "document_type":"invoice",
        "purchased_at":purchased_at, "identity":"invoice:"+identity[1].upper(), "currency":"EUR",
        "subtotal":float(subtotal), "shipping":float(shipping), "discount":float(discount),
        "total":float(total), "article_count":sum(item["count"] for item in items), "lines":items}


def extract_receipt(content):
    """Run in an executor; never retain the PDF's payment/loyalty/customer data."""
    if not content.startswith(b"%PDF-") or not 0 < len(content) <= MAX_PDF_BYTES:
        raise CatalogError("Sube un PDF de hasta 2 MB.")
    try:
        reader = PdfReader(BytesIO(content))
        if reader.is_encrypted or not 1 <= len(reader.pages) <= 10:
            raise CatalogError("El PDF debe tener entre 1 y 10 páginas y no estar protegido.")
        parts = []
        for page in reader.pages:
            stream = page.get_contents()
            if stream and len(stream.get_data()) > 4 * 1024 * 1024:
                raise CatalogError("El contenido del PDF es demasiado grande para procesarlo.")
            parts.append(page.extract_text(extraction_mode="layout", layout_mode_space_vertically=False))
        text = "\n".join(parts)
        if len(text) > 100000:
            raise CatalogError("El ticket contiene demasiado texto.")
        if len(text.strip()) < 20:
            raise CatalogError("El PDF no contiene texto legible. Los tickets escaneados requieren OCR y todavía no están disponibles.")
        invoice = bool(re.search(r"FECHA\s+FACTURA\s*:", text, re.I))
        receipt = parse_carrefour_invoice(text) if invoice else parse_carrefour(text)
    except CatalogError:
        raise
    except Exception as err:
        raise CatalogError("No se ha podido leer el PDF. Comprueba que sea un ticket electrónico válido.") from err
    return _identify_receipt(receipt, content)


def _identify_receipt(receipt, content):
    receipt["digest"] = sha256(content).hexdigest()
    receipt["id"] = sha256((receipt["store"] + ":" + (receipt["identity"] or receipt["purchased_at"] + ":" + str(receipt["total"]) + ":" + str(receipt["lines"]))).encode()).hexdigest()
    return receipt


def _carrefour_account_items(detail):
    """Read the observed item schema, independently of the printable till layout."""
    rows = detail.get("items")
    if rows is None or rows == []:
        return None
    if not isinstance(rows, list) or not 1 <= len(rows) <= 300:
        raise CatalogError("Carrefour ha devuelto artículos con una estructura no reconocida.", "receipt_detail_format")
    header = detail.get("header")
    if not isinstance(header, dict):
        raise CatalogError("No se han podido comprobar los totales del detalle de Carrefour.")

    def number(value):
        if type(value) not in (int, float) or not math.isfinite(value) or abs(value) > 1000000:
            raise CatalogError("Hay una cantidad o un importe no válido en el detalle de Carrefour.")
        return Decimal(str(value))

    total = number(header.get("netAmount"))
    adjustment = number(detail.get("totalDiscount", 0))
    if total < 0 or adjustment > 0:
        raise CatalogError("Este ticket contiene devoluciones o ajustes que todavía no se admiten.")
    date = detail.get("date")
    try:
        if not isinstance(date, str) or len(date) > 40 or not re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", date):
            raise ValueError
        purchased_at = datetime.fromisoformat(date).isoformat()
    except ValueError as err:
        raise CatalogError("La fecha del detalle de Carrefour no es válida.") from err
    items, subtotal, count = [], Decimal(0), 0
    for row in rows:
        if not isinstance(row, dict) or not all(key in row for key in ("description", "numberUnits", "netAmount")):
            raise CatalogError("Carrefour ha devuelto artículos con una estructura no reconocida.", "receipt_detail_format")
        description = row["description"]
        if not isinstance(description, str) or not description.strip() or len(description) > 500:
            raise CatalogError("La descripción de un artículo de Carrefour no es válida.")
        description = re.sub(r"\s+", " ", description).strip()
        quantity, amount = number(row["numberUnits"]), number(row["netAmount"])
        if quantity <= 0 or amount < 0:
            raise CatalogError("Los tickets con devoluciones todavía no se admiten.")
        if quantity != quantity.to_integral_value():
            raise CatalogError("Carrefour ha devuelto una cantidad cuyo formato todavía no se reconoce.", "receipt_detail_format")
        quantity = int(quantity)
        pack = re.search(r"\b(\d+(?:[,.]\d+)?)\s*(KG|GRS?|G|ML|CL|LITROS?|L)\b", description, re.I)
        item = {"id":str(len(items)), "description":description.strip(), "count":quantity,
            "amount":float(amount), "unit_price":float((amount/quantity).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
            "pack_quantity":float(pack[1].replace(",", ".")) if pack else None,
            "pack_unit":({"gr":"g", "grs":"g", "litro":"l", "litros":"l"}.get(pack[2].lower(), pack[2].lower()) if pack else "")}
        code = row.get("code")
        if isinstance(code, str) and re.fullmatch(r"\d{8}|\d{12,14}", code, flags=re.ASCII) and not (len(code) == 13 and code.startswith("2")):
            check = sum(int(digit)*(3 if index%2 == 0 else 1) for index, digit in enumerate(reversed(code[:-1])))
            if (10-check%10)%10 == int(code[-1]):
                item["ean"] = code
        items.append(item)
        subtotal += amount
        count += quantity
    reported_count = number(header.get("numberItems"))
    if reported_count != count:
        raise CatalogError("El número de artículos no coincide con el detalle de Carrefour.")
    if "numberLinesItems" in header and number(header["numberLinesItems"]) != len(items):
        raise CatalogError("El número de líneas no coincide con el detalle de Carrefour.")
    if abs(subtotal+adjustment-total) > Decimal("0.02"):
        raise CatalogError("Los artículos, descuentos y total del detalle de Carrefour no coinciden.")
    # Only the receipt number is used from printable lines; never customer/payment data.
    lines = detail.get("lines")
    text = "\n".join(lines) if isinstance(lines, list) and len(lines) <= 2000 and all(isinstance(line, str) and len(line) <= 2000 for line in lines) else ""
    identity = re.search(r"\bNRF:\s*([A-Z0-9]{1,60})\b", text[:100000])
    receipt = {"store":"carrefour", "store_name":"Carrefour", "purchased_at":purchased_at,
        "identity":identity[1] if identity else "", "currency":"EUR", "subtotal":float(subtotal),
        "discount":float(-adjustment), "total":float(total), "article_count":count, "lines":items}
    return receipt


def extract_carrefour_account_ticket(detail, reference, expected_total):
    """Validate structured items or legacy printable lines, without customer/payment fields."""
    if not isinstance(detail, dict) or detail.get("ticketId") != reference:
        raise CatalogError("El detalle de Carrefour no corresponde al ticket seleccionado.")
    receipt = None
    try:
        receipt = _carrefour_account_items(detail)
    except CatalogError as err:
        # Keep legacy text as an alternative only for an unknown schema, not mismatched amounts.
        if err.code != "receipt_detail_format":
            raise
    header = detail.get("header")
    if receipt is None:
        lines = detail.get("lines")
        if (not isinstance(lines, list) or not 1 <= len(lines) <= 2000 or
                any(not isinstance(line, str) or len(line) > 2000 for line in lines)):
            raise CatalogError("Carrefour no ha devuelto un detalle de ticket válido.", "receipt_detail_format")
        text = "\n".join(lines)
        if len(text) > 100000:
            raise CatalogError("El ticket contiene demasiado texto.")
        receipt = parse_carrefour(text)
    else:
        text = json.dumps(receipt, ensure_ascii=False, sort_keys=True)
    reported_total = header.get("netAmount") if isinstance(header, dict) else None
    for amount in (reported_total, expected_total):
        if type(amount) not in (int, float) or not math.isfinite(amount) or abs(receipt["total"] - amount) > .02:
            raise CatalogError("El detalle extraído no coincide con el importe de la compra de Carrefour.")
    return _identify_receipt(receipt, text.encode("utf-8"))
