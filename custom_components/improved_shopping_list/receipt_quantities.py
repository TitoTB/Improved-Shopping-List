"""Purchase quantities and reusable prices per measure are distinct values."""
import math
from decimal import Decimal, ROUND_HALF_UP

SCALES = {"kg":("kg",1), "g":("kg",.001), "l":("l",1), "cl":("l",.01), "ml":("l",.001), "uds":("uds",1)}


def stock_quantity(quantity,source_unit,target_unit):
    """Sum compatible quantities, never treating a weight as a unit count."""
    source_unit,target_unit=source_unit.strip().casefold(),target_unit.strip().casefold()
    if source_unit==target_unit:return quantity
    source,target=SCALES.get(source_unit),SCALES.get(target_unit)
    return round(quantity*source[1]/target[1],3) if source and target and source[0]==target[0] else None


def lookup_paused(diagnostics):
    """Detect an access/rate pause, including a partially recovered product."""
    if not isinstance(diagnostics,dict):return False
    retry=diagnostics.get("retry_seconds")
    if (diagnostics.get("http_status") in (403,429,503)
            or diagnostics.get("response_class") in ("access_denied","rate_limited")
            or type(retry) in (int,float) and retry>0):return True
    attempts=diagnostics.get("attempts",[])
    return isinstance(attempts,list) and any(lookup_paused(attempt) for attempt in attempts)


def weight_format(reference):
    """A known weight unit with no fixed package size describes sale by weight."""
    return bool(reference and reference.get("sale_mode")!="package" and reference.get("content_quantity") in (None, "") and reference.get("content_unit") in ("g", "kg"))


def weight_purchase(line, reference=None):
    rate = line.get("ticket_measure_price") or {}
    return bool((line.get("manual_measure_price") or {}).get("unit")=="kg" or weight_format(reference) or rate.get("unit") in ("g", "kg") and line.get("purchased_quantity") is not None
        or line.get("quantity_estimated") and line.get("purchased_unit") in ("g", "kg") and not (reference or {}).get("content_quantity")
        or line.get("format_confirmed") and line.get("pack_quantity") is None and line.get("pack_unit") in ("g", "kg"))


def receipt_catalog_price(line, reference=None):
    """Never interpret the paid amount for a weighed purchase as a price per kg."""
    if weight_purchase(line, reference):
        rate = line.get("manual_measure_price") or line.get("ticket_measure_price")
        return measure_price(rate)["price"] if rate else None
    return line.get("unit_price")


def measure_price(raw):
    if not isinstance(raw,dict) or set(raw)-{"price","quantity","unit","currency","checked_at","source"}:
        raise ValueError("El precio por unidad de medida no es válido.")
    price, quantity = raw.get("price"), raw.get("quantity",1)
    if not isinstance(raw.get("unit"),str):
        raise ValueError("La unidad de medida no es válida.")
    unit, scale = SCALES.get(raw.get("unit"), (None,None))
    at = raw.get("checked_at")
    if (type(price) not in (int,float) or not math.isfinite(price) or not 0<price<=1000000
        or type(quantity) not in (int,float) or not math.isfinite(quantity) or not 0<quantity<=1000000
        or not unit or raw.get("currency")!="EUR" or type(at) not in (int,float) or not math.isfinite(at) or at<=0):
        raise ValueError("Indica un precio positivo y su unidad de medida.")
    rate=round(price/(quantity*scale),6)
    if not 0<rate<=1000000:
        raise ValueError("El precio por unidad de medida está fuera de rango.")
    source=raw.get("source","catalog")
    if source not in ("catalog","web","ticket","manual"):
        raise ValueError("La fuente del precio por unidad de medida no es válida.")
    return {"price":rate,"quantity":1,"unit":unit,"currency":"EUR","checked_at":at,"source":source}


def price_from_option(ref):
    if ref.get("measure_price"):
        return measure_price(ref["measure_price"])
    previous=ref.get("last_price")
    if previous and previous.get("price",0)>0 and (ref.get("content_confirmed") or weight_format(ref)):
        if weight_format(ref):
            return measure_price({**previous,"quantity":1,"unit":"kg","source":"catalog"})
        if ref.get("content_quantity"):
            return measure_price({**previous,"quantity":ref["content_quantity"],"unit":ref["content_unit"],"source":"catalog"})
    return None


def purchase_quantity(line):
    quantity,unit=line.get("purchased_quantity"),line.get("purchased_unit")
    if type(quantity) in (int,float) and math.isfinite(quantity) and quantity>0 and unit in SCALES:
        return quantity,unit
    quantity,unit=line.get("pack_quantity"),line.get("pack_unit")
    if type(quantity) in (int,float) and math.isfinite(quantity) and quantity>0 and unit in SCALES:
        return round(quantity*line["count"],3),unit
    return None,""


def estimated_quantity(line, price):
    rate=measure_price(price)
    # Use the amount before any known line promotion, never prorate basket coupons.
    amount=line.get("gross_amount",line.get("amount"))
    if type(amount) not in (int,float) or not math.isfinite(amount) or amount<=0:
        return None
    quantity=float((Decimal(str(amount))/Decimal(str(rate["price"]))).quantize(Decimal(".001"),rounding=ROUND_HALF_UP))
    if not 0<quantity<=1000000:
        return None
    return {"quantity":quantity,"unit":rate["unit"],"estimated":True,"measure_price":rate}
