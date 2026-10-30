"""Explicit package facts shared by all shops for the same EAN; no prices."""
from datetime import datetime
import math
import re
from unicodedata import normalize, combining
from urllib.parse import urlsplit

FIELDS=("brand","content_quantity","content_unit","pack_count")
SCALES={"g":("kg",.001),"kg":("kg",1),"ml":("l",.001),"cl":("l",.01),"l":("l",1),"uds":("uds",1)}


def positive(value):
    try:
        number=float(value)
        return number if not isinstance(value,bool) and math.isfinite(number) and 0<number<=1000000 else None
    except (ValueError,TypeError):return None


def brand(value):
    if not isinstance(value,str):return ""
    value=" ".join(value.split())[:160]
    for i,char in enumerate(value):
        if char.isalpha():return value[:i]+char.upper()+value[i+1:]
    return value


def brand_key(value):
    return "".join(c for c in normalize("NFKD",value) if not combining(c)).casefold()


def content_key(quantity,unit):
    if not isinstance(unit,str):return None
    scale=SCALES.get(unit)
    q=positive(quantity)
    return (scale[0],round(q*scale[1],9)) if q and scale and (unit!="uds" or q==int(q)) else None


def extract(record):
    details=record.get("details") if isinstance(record.get("details"),dict) else {}
    prices=record.get("price_instructions") if isinstance(record.get("price_instructions"),dict) else {}
    result={}
    if value:=brand(record.get("brand") or details.get("brand")):result["brand"]=value
    count=positive(prices.get("total_units"))
    if prices.get("is_pack") is True and count and count==int(count):result["pack_count"]=int(count)
    if record.get("is_variable_weight") or record.get("is_bulk") or prices.get("approx_size"):return result
    quantity=positive(prices.get("unit_size"))
    unit=str(prices.get("size_format") or "").lower().strip()
    unit={"ud":"uds","unidad":"uds","unidades":"uds"}.get(unit,unit)
    if not content_key(quantity,unit):return result
    individual=positive(prices.get("pack_size"))
    if individual and result.get("pack_count") and not math.isclose(individual*result["pack_count"],quantity,rel_tol=.01,abs_tol=.000001):
        result["conflicts"]=["content"]
    else:result.update(content_quantity=quantity,content_unit=unit)
    return result


def consensus(records):
    values=[extract(record) for record in records]
    result={};conflicts=set()
    for field,key in (("brand",brand_key),("pack_count",lambda value:value)):
        choices={key(row[field]):row[field] for row in values if field in row}
        if len(choices)==1:result[field]=next(iter(choices.values()))
        elif choices:conflicts.add(field)
    choices={content_key(row["content_quantity"],row["content_unit"]):(row["content_quantity"],row["content_unit"])
        for row in values if row.get("content_quantity")}
    if len(choices)>1 or any("content" in row.get("conflicts",[]) for row in values):conflicts.add("content")
    elif choices:
        result["content_quantity"],result["content_unit"]=next(iter(choices.values()))
    if conflicts:result["conflicts"]=sorted(conflicts)
    return result


def validate(value):
    if not isinstance(value,dict) or set(value)-{*FIELDS,"conflicts"}:raise ValueError("Invalid common EAN data")
    result=dict(value)
    if "brand" in value:
        if not isinstance(value["brand"],str) or not value["brand"].strip() or len(value["brand"])>160 or any(ord(c)<32 for c in value["brand"]):raise ValueError("Invalid EAN brand")
        result["brand"]=brand(value["brand"])
    if "content_quantity" in value or "content_unit" in value:
        if type(value.get("content_quantity")) not in (int,float) or not content_key(value.get("content_quantity"),value.get("content_unit")):raise ValueError("Invalid EAN content")
    if "pack_count" in value and (type(value["pack_count"]) is not int or not 1<=value["pack_count"]<=1000000):raise ValueError("Invalid EAN pack count")
    conflicts=value.get("conflicts",[])
    if not isinstance(conflicts,list) or len(conflicts)>3 or any(c not in ("brand","content","pack_count") for c in conflicts):raise ValueError("Invalid EAN conflicts")
    for field in conflicts:
        if field=="content":
            result.pop("content_quantity",None);result.pop("content_unit",None)
        else:result.pop(field,None)
    return result


def observed_at(value):
    if not isinstance(value,str):raise ValueError("Missing common EAN source date")
    stamp=datetime.fromisoformat(value.replace("Z","+00:00"))
    if stamp.tzinfo is None or stamp.timestamp()<=0:raise ValueError("Invalid common EAN source date")
    return int(stamp.timestamp())


def source(value):
    if not isinstance(value,dict) or set(value)!={"store","url","revision","observed_at"}:raise ValueError("Invalid common EAN provenance")
    url=value.get("url")
    if not isinstance(url,str) or len(url)>2048 or any(ord(c)<32 for c in url):raise ValueError("Invalid common EAN source URL")
    parsed=urlsplit(url)
    if parsed.scheme!="https" or not parsed.hostname or parsed.username or parsed.password:raise ValueError("Invalid common EAN source URL")
    if not isinstance(value["store"],str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,39}",value["store"]):raise ValueError("Invalid common EAN source")
    if not isinstance(value["revision"],str) or not re.fullmatch(r"[a-f0-9]{40}",value["revision"]):raise ValueError("Invalid common EAN revision")
    if type(value["observed_at"]) not in (int,float) or not math.isfinite(value["observed_at"]) or value["observed_at"]<=0:raise ValueError("Invalid common EAN date")
    return dict(value)
