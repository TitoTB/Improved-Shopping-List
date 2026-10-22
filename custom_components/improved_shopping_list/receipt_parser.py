"""Local receipt extraction. Only recognized formats produce importable purchases."""

from datetime import datetime
from decimal import Decimal
from hashlib import sha256
from io import BytesIO
import re

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
        raise CatalogError("No se han podido identificar las líneas de compra de este ticket.")
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
        receipt = parse_carrefour(text)
    except CatalogError:
        raise
    except Exception as err:
        raise CatalogError("No se ha podido leer el PDF. Comprueba que sea un ticket electrónico válido.") from err
    receipt["digest"] = sha256(content).hexdigest()
    receipt["id"] = sha256((receipt["store"] + ":" + (receipt["identity"] or receipt["purchased_at"] + ":" + str(receipt["total"]) + ":" + str(receipt["lines"]))).encode()).hexdigest()
    return receipt
