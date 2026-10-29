"""Purchase quantities and reusable prices per measure are distinct values."""
import math
from decimal import Decimal, ROUND_HALF_UP

SCALES = {"kg":("kg",1), "g":("kg",.001), "l":("l",1), "cl":("l",.01), "ml":("l",.001), "uds":("uds",1)}


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
    if previous and ref.get("content_confirmed") and ref.get("content_quantity"):
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
