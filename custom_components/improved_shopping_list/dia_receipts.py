"""Validate DIA account receipts, without customer or payment data."""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import json
import re

from homeassistant.util import dt as dt_util
from .catalog import CatalogError
from .receipt_parser import _identify_receipt

PARAMS = ("ticket", "begin", "business", "country", "pos", "store")


def reference_params(value):
    if not isinstance(value,dict) or set(value)!=set(PARAMS):
        raise CatalogError("DIA no ha devuelto una referencia completa del ticket.","dia_ticket_reference")
    result={}
    for key in PARAMS:
        raw=value[key]
        if type(raw) not in (str,int):
            raise CatalogError("La referencia de DIA no es válida.","dia_ticket_reference")
        item=str(raw)
        if not re.fullmatch(r"[A-Z]{2}" if key=="country" else r"[0-9]{1,16}",item):
            raise CatalogError("La referencia de DIA no es válida.","dia_ticket_reference")
        result[key]=item
    return result


def reference_id(params):
    return json.dumps(reference_params(params),sort_keys=True,separators=(",",":"))


def decimal_value(value, *, signed=False):
    if type(value) not in (int,float,str) or isinstance(value,bool):
        raise CatalogError("DIA ha devuelto un importe o cantidad no válido.","dia_ticket_amount")
    try:
        amount=Decimal(str(value))
    except InvalidOperation as err:
        raise CatalogError("DIA ha devuelto un importe o cantidad no válido.","dia_ticket_amount") from err
    if not amount.is_finite() or abs(amount)>1000000 or not signed and amount<0:
        raise CatalogError("DIA ha devuelto un importe o cantidad no válido.","dia_ticket_amount")
    return amount


def checked_date(value):
    if not isinstance(value,str) or len(value)>80:
        raise CatalogError("La fecha del ticket de DIA no es válida.","dia_ticket_date")
    when=dt_util.parse_datetime(value)
    if when is None:
        raise CatalogError("La fecha del ticket de DIA no es válida.","dia_ticket_date")
    return when if when.tzinfo else when.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)


def summary(purchase):
    if not isinstance(purchase,dict):
        raise CatalogError("DIA ha devuelto un historial no reconocido.","dia_history_format")
    params=reference_params(purchase.get("detail_params"))
    when=checked_date(purchase.get("submitted_date"))
    total=decimal_value(purchase.get("total_amount"))
    if abs(Decimal(str(when.timestamp()*1000))-Decimal(params["begin"]))>1000:
        raise CatalogError("La fecha y referencia del ticket de DIA no coinciden.","dia_ticket_identity")
    return {"reference":reference_id(params),"params":params,"amount":float(total),
        "purchased_at":dt_util.as_local(when).replace(tzinfo=None).isoformat(),
        "supported":not purchase.get("return") and not purchase.get("void"),
        "online":bool(purchase.get("online"))}


def extract_dia_account_ticket(detail, params, expected_total):
    params=reference_params(params)
    if not isinstance(detail,dict) or detail.get("currency") not in ("EUR","€"):
        raise CatalogError("DIA no ha devuelto un ticket en EUR.","dia_ticket_format")
    header=detail.get("header")
    amounts=detail.get("amount")
    corporate=detail.get("corporate")
    if not all(isinstance(value,dict) for value in (header,amounts,corporate)):
        raise CatalogError("La estructura del ticket de DIA no se reconoce.","dia_ticket_format")
    if (str(header.get("code"))!=params["ticket"] or str(header.get("store_code"))!=params["store"] or str(header.get("pos"))!=params["pos"]):
        raise CatalogError("DIA ha devuelto el detalle de otra compra.","dia_ticket_identity")
    when=checked_date(header.get("submitted_date"))
    if abs(when.timestamp()*1000-int(params["begin"]))>1000:
        raise CatalogError("La fecha y referencia del ticket de DIA no coinciden.","dia_ticket_identity")
    if detail.get("return") or detail.get("void"):
        raise CatalogError("Los tickets de devolución o anulados de DIA todavía no se pueden importar.","dia_ticket_return")
    rows=corporate.get("items")
    if not isinstance(rows,list) or not 1<=len(rows)<=300:
        raise CatalogError("DIA no ha devuelto artículos reconocibles.","dia_ticket_format")
    lines=[];gross_sum=Decimal(0);discount_sum=Decimal(0)
    for row in rows:
        if not isinstance(row,dict):
            raise CatalogError("DIA ha devuelto una línea no reconocida.","dia_ticket_format")
        if row.get("cancel"):
            continue
        name=row.get("name")
        code=row.get("code")
        if not isinstance(name,str) or not 1<=len(name.strip())<=500 or type(code) not in (int,str) or not re.fullmatch(r"[0-9]{1,16}",str(code)):
            raise CatalogError("No se reconoce el artículo de DIA.","dia_ticket_format")
        gross=decimal_value(row.get("amount"));unit=decimal_value(row.get("price_per_unit"))
        weighted=row.get("variable_weight") is True
        count=Decimal(1) if weighted else decimal_value(row.get("quantity"))
        weight=decimal_value(row.get("weight")) if weighted else None
        multiplier=weight if weighted else count
        if not multiplier or count!=int(count) or count>10000 or abs((unit*multiplier).quantize(Decimal("0.01"),rounding=ROUND_HALF_UP)-gross)>Decimal("0.02"):
            raise CatalogError("Las cantidades y el importe del artículo de DIA no coinciden.","dia_ticket_amount")
        discounts=row.get("discounts",[])
        if not isinstance(discounts,list) or len(discounts)>100 or any(not isinstance(d,dict) for d in discounts):
            raise CatalogError("Los descuentos de DIA no son válidos.","dia_ticket_amount")
        line_discount=sum((decimal_value(d.get("amount"),signed=True) for d in discounts),Decimal(0))
        net=gross+line_discount
        if net<0 or line_discount>0:
            raise CatalogError("El descuento del artículo de DIA no es válido.","dia_ticket_amount")
        pack=re.search(r"\b(\d+(?:[,.]\d+)?)\s*(KG|GRS?|G|ML|CL|LITROS?|L)\b",name,re.I)
        lines.append({"id":str(len(lines)),"description":name.strip(),"count":int(count),
            "unit_price":float((net/count).quantize(Decimal("0.0001"),rounding=ROUND_HALF_UP)),"amount":float(net),
            "gross_amount":float(gross),"line_discount":float(-line_discount),"reference_id":str(code),"ean":"",
            "pack_quantity":float(weight) if weighted else float(pack[1].replace(",",".")) if pack else None,
            "pack_unit":"kg" if weighted else {"gr":"g","grs":"g","litro":"l","litros":"l"}.get(pack[2].lower(),pack[2].lower()) if pack else ""})
        gross_sum+=gross;discount_sum+=line_discount
    if not lines:
        raise CatalogError("El ticket de DIA no contiene artículos comprados.","dia_ticket_format")
    total=decimal_value(amounts.get("total_amount"));expected=decimal_value(expected_total)
    shipping=decimal_value(amounts.get("shipping_amount",0))
    reported_gross=decimal_value(amounts.get("total_amount_without_discounts"))
    reported_discount=decimal_value(amounts.get("total_discounts"),signed=True)
    subtotal=gross_sum+discount_sum
    general_discount=subtotal+shipping-total
    if (abs(total-expected)>Decimal("0.02") or abs(gross_sum+shipping-reported_gross)>Decimal("0.02") or
        abs(reported_gross+reported_discount-total)>Decimal("0.02") or general_discount<Decimal("-0.02") or
        abs(decimal_value(corporate.get("amount"))+shipping-total)>Decimal("0.02")):
        raise CatalogError("Los artículos y descuentos no coinciden con el total de DIA.","dia_ticket_amount")
    receipt={"store":"dia","store_name":"DIA","identity":reference_id(params),
        "purchased_at":dt_util.as_local(when).replace(tzinfo=None).isoformat(),"currency":"EUR",
        "subtotal":float(subtotal),"discount":float(max(Decimal(0),general_discount)),"shipping":float(shipping),
        "total":float(total),"article_count":sum(line["count"] for line in lines),"lines":lines}
    return _identify_receipt(receipt,json.dumps(receipt,ensure_ascii=False,sort_keys=True).encode())
