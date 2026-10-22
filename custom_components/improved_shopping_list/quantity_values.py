"""Purchase quantity validation, independent of catalog and pantry storage."""

from decimal import Decimal, InvalidOperation

DEFAULT_PURCHASE = {"purchase_unit": "uds", "unit_quantity": 1, "quantity_step": 1}


def positive_quantity(value):
    if type(value) not in (int, float):
        raise ValueError("Indica una cantidad numérica positiva.")
    try:
        number = Decimal(str(value))
        if not number.is_finite() or not 0 < number <= 1000000 or number != number.quantize(Decimal("0.001")):
            raise InvalidOperation
        return int(number) if number == number.to_integral_value() else float(number)
    except InvalidOperation:
        raise ValueError("La cantidad debe ser mayor que cero y como máximo 1000000, con hasta tres decimales.") from None


def purchase_defaults(product=None):
    return {key: (product or {}).get(key, default) for key, default in DEFAULT_PURCHASE.items()}


def normalize_purchase(data):
    result = purchase_defaults(data)
    unit = result["purchase_unit"]
    if not isinstance(unit, str) or not unit.strip() or len(unit.strip()) > 32 or any(ord(c) < 32 for c in unit):
        raise ValueError("Indica unas unidades de hasta 32 caracteres.")
    result["purchase_unit"] = unit.strip()
    for key in ("unit_quantity", "quantity_step"):
        result[key] = positive_quantity(result[key])
    return result
