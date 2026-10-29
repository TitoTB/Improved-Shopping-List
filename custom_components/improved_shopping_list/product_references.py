"""Commercial packages, independent of shopping quantities and pantry refills."""
from copy import deepcopy
from hashlib import sha256
import math
import re
from unicodedata import normalize, combining
from urllib.parse import urlsplit
from .receipt_quantities import measure_price

UNITS = {"uds", "g", "kg", "ml", "cl", "l"}
SCALES = {"uds":("uds",1), "g":("kg",.001), "kg":("kg",1), "ml":("l",.001), "cl":("l",.01), "l":("l",1)}


def brand_name(value):
    """Uppercase the first letter without changing the brand's remaining casing."""
    value = value.strip() if isinstance(value, str) else ""
    for index, char in enumerate(value):
        if char.isalpha():
            return value[:index] + char.upper() + value[index + 1:]
    return value


def reference_image(value):
    """Keep only plain HTTPS image references, never credentials or script URLs."""
    if not isinstance(value, str) or len(value)>2048 or "\\" in value or any(ord(c)<32 for c in value):
        return ""
    try:
        parsed=urlsplit(value)
        return value if parsed.scheme=="https" and parsed.hostname and not parsed.username and not parsed.password else ""
    except ValueError:
        return ""


def name_key(value):
    return " ".join("".join(c for c in normalize("NFKD", value) if not combining(c)).casefold().split())


def gtin(value):
    if not isinstance(value, str) or not re.fullmatch(r"(?:\d{8}|\d{12,14})", value, re.ASCII):
        return ""
    total = sum(int(char)*(3 if i%2==0 else 1) for i,char in enumerate(value[-2::-1]))
    return value.zfill(14) if (10-total%10)%10 == int(value[-1]) and not (len(value)==13 and value.startswith("2")) else ""


def reference_key(store, line):
    if store == "lidl" and line.get("ticket_reference_id"):
        return sha256((store+":ref:"+line["ticket_reference_id"]).encode()).hexdigest()[:32]
    identity = "ref:"+line["reference_id"] if line.get("reference_id") else "ean:"+gtin(line.get("ean")) if gtin(line.get("ean")) else "name:"+name_key(line.get("name") or line.get("description", ""))
    return sha256((store+":"+identity).encode()).hexdigest()[:32]


def content(quantity, unit):
    if quantity in (None, "") and unit in (None, ""):
        return None, ""
    if type(quantity) not in (int, float) or not math.isfinite(quantity) or not 0 < quantity <= 1000000 or unit not in UNITS:
        raise ValueError("Indica el contenido de un envase y sus unidades, o deja ambos vacíos.")
    if unit == "uds" and quantity != int(quantity):
        raise ValueError("El número de unidades de un envase debe ser entero.")
    return quantity, unit


def inferred_content(line):
    name = line.get("name") or line.get("description", "")
    multiple = re.search(r"\b(\d+)\s*[x×]\s*(\d+(?:[.,]\d+)?)\s*(kg|grs?|g|ml|cl|l|uds?|unidades)\b",name,re.I)
    if multiple:
        unit={"gr":"g","grs":"g","ud":"uds","unidades":"uds"}.get(multiple[3].lower(),multiple[3].lower())
        return int(multiple[1])*float(multiple[2].replace(",",".")),unit
    quantity, unit = line.get("pack_quantity"), line.get("pack_unit", "")
    if type(quantity) in (int, float) and quantity > 0 and unit in UNITS:
        return quantity, unit
    match = re.search(r"\b(\d+(?:[.,]\d+)?)\s*(kg|grs?|g|ml|cl|litros?|l|uds?\.?|unidades|huevos)\b", name, re.I)
    if not match:
        return None, ""
    unit = match[2].lower().rstrip(".")
    unit = {"gr":"g","grs":"g","litro":"l","litros":"l","ud":"uds","unidades":"uds","huevos":"uds"}.get(unit,unit)
    return float(match[1].replace(",", ".")), unit


def reference_from_line(store, line):
    quantity, unit = inferred_content(line)
    return {"id":reference_key(store,line), "store":store, "name":line.get("name") or line.get("description", ""),
            "ean":line.get("ean", "") if gtin(line.get("ean")) else "", "reference_id":line.get("web_reference_id") or line.get("reference_id", ""),
            **({"ticket_reference_id":line["ticket_reference_id"]} if store=="lidl" and line.get("ticket_reference_id") else {}),
            "url":line.get("url", ""), "brand":brand_name(line.get("brand", "")), "content_quantity":quantity, "content_unit":unit, "content_confirmed":False,
            **({"image_url":image} if (image:=reference_image(line.get("image_url", ""))) else {})}


def matching_reference(product, store, line):
    refs = [ref for ref in product.get("commercial_references", []) if ref["store"] in (store, "")]
    key = reference_key(store,line)
    exact = next((ref for ref in refs if ref["id"]==key and ref["store"]==store), None)
    if exact:
        return exact
    if store=="lidl" and line.get("reference_id"):
        matched=next((ref for ref in refs if ref.get("ticket_reference_id")==line["reference_id"]),None)
        if matched:
            return matched
    ean = gtin(line.get("ean"))
    if ean:
        return next((ref for ref in refs if gtin(ref.get("ean"))==ean), None)
    return None


def normalized_references(values):
    if not isinstance(values,list) or len(values)>200:
        raise ValueError("Un producto puede tener hasta 200 referencias comerciales.")
    result=[]; seen=set()
    from .store_links import STORES, normalize_link
    for raw in values:
        if not isinstance(raw,dict) or set(raw)-{"id","store","name","ean","reference_id","url","brand","image_url","content_quantity","content_unit","content_confirmed","active","last_price","nutriscore","measure_price","ticket_reference_id"}:
            raise ValueError("La referencia comercial contiene campos no admitidos.")
        row={key:raw.get(key,"") for key in ("store","name","ean","reference_id","url","brand")}
        for key,limit in (("store",40),("name",500),("ean",14),("reference_id",512),("url",2048),("brand",160)):
            if not isinstance(row[key],str) or len(row[key])>limit or any(ord(c)<32 for c in row[key]):
                raise ValueError("La referencia comercial no es válida.")
            row[key]=row[key].strip()
        row["brand"] = brand_name(row["brand"])
        if raw.get("ticket_reference_id") is not None:
            value=raw["ticket_reference_id"]
            if row["store"]!="lidl" or not isinstance(value,str) or not re.fullmatch(r"[0-9]{1,16}",value):
                raise ValueError("La referencia del ticket de Lidl no es válida.")
            row["ticket_reference_id"]=value
        if raw.get("image_url"):
            if not (image:=reference_image(raw["image_url"])):
                raise ValueError("La imagen de la opción debe tener una URL HTTPS válida.")
            row["image_url"]=image
        if row["store"] and row["store"] not in STORES:
            raise ValueError("Selecciona una tienda válida para la referencia.")
        if row["ean"] and not gtin(row["ean"]):
            raise ValueError("El EAN de la referencia comercial no es válido.")
        if not (row["ean"] or row["reference_id"] or row["name"] or row["url"]):
            raise ValueError("La referencia necesita un EAN, una ID o un nombre comercial.")
        if row["url"]:
            link=normalize_link(row["store"],row["url"])
            if row["reference_id"] and row["reference_id"]!=link["id"]:
                raise ValueError("El enlace y la referencia comercial no corresponden al mismo producto.")
            row["reference_id"]=link["id"]
        quantity,unit=content(raw.get("content_quantity"),raw.get("content_unit",""))
        confirmed=raw.get("content_confirmed",False)
        if type(confirmed) is not bool or confirmed and quantity is None:
            raise ValueError("Confirma el contenido del envase antes de utilizarlo para comparar.")
        active=raw.get("active",True)
        if type(active) is not bool:
            raise ValueError("La referencia comercial no es válida.")
        row.update(id=reference_key(row["store"],row),content_quantity=quantity,content_unit=unit,content_confirmed=confirmed,active=active)
        price = raw.get("last_price")
        if price is not None:
            if (not isinstance(price,dict) or set(price)-{"price","currency","checked_at"}
                or type(price.get("price")) not in (int,float) or not math.isfinite(price["price"]) or not 0<=price["price"]<=1000000
                or price.get("currency")!="EUR" or type(price.get("checked_at")) not in (int,float)
                or not math.isfinite(price["checked_at"]) or price["checked_at"]<=0 or not row["store"]):
                raise ValueError("El precio recuperado de la opción no es válido.")
            row["last_price"] = deepcopy(price)
        nutrition = raw.get("nutriscore")
        if raw.get("measure_price") is not None:
            row["measure_price"] = measure_price(raw["measure_price"])
        if nutrition is not None:
            if (not isinstance(nutrition,dict) or nutrition.get("grade") not in tuple("abcde")
                or type(nutrition.get("checked_at")) not in (int,float) or not math.isfinite(nutrition["checked_at"]) or nutrition["checked_at"]<=0):
                raise ValueError("El Nutri-Score de la opción no es válido.")
            row["nutriscore"] = {"grade":nutrition["grade"],"checked_at":nutrition["checked_at"]}
        if row["id"] in seen:
            raise ValueError("Esta referencia comercial está repetida.")
        seen.add(row["id"]);result.append(row)
    return result


def merge_reference(references, store, line, *, confirmed=False):
    row=reference_from_line(store,line)
    existing=matching_reference({"commercial_references":references},store,line)
    if existing:
        if store=="lidl" and existing.get("ticket_reference_id") and not row.get("ticket_reference_id"):
            row.update(ticket_reference_id=existing["ticket_reference_id"],reference_id=existing["reference_id"],url=existing["url"])
        row["brand"]=row["brand"] or existing.get("brand", "")
        if not row.get("image_url") and existing.get("image_url"):
            row["image_url"]=existing["image_url"]
        for key in ("last_price","nutriscore","measure_price"):
            if key in existing:
                row[key]=deepcopy(existing[key])
    if existing and not existing["store"] and store:
        if existing.get("content_confirmed") and not confirmed:
            row.update({key:existing[key] for key in ("content_quantity","content_unit","content_confirmed")})
        references.remove(existing)
    if existing and existing["store"]==store:
        if existing.get("content_confirmed") and not confirmed:
            row.update({key:existing[key] for key in ("content_quantity","content_unit","content_confirmed")})
        elif row["content_quantity"] is None:
            row.update({key:existing[key] for key in ("content_quantity","content_unit","content_confirmed")})
        row["ean"]=row["ean"] or existing["ean"]
        row["url"]=row["url"] or (existing["url"] if row["reference_id"]==existing["reference_id"] else "")
        references.remove(existing)
    if confirmed:
        row["content_confirmed"]=row["content_quantity"] is not None
    references.append(row)


def format_observation(product, store, line):
    """Use an edited format consistently across past and current observations."""
    result=deepcopy(line)
    reference=matching_reference(product,store,line)
    if reference:
        result.update(commercial_reference_id=reference["id"],format_pending=not reference["content_confirmed"],reference_excluded=reference.get("active") is False)
        result["pack_quantity"]=reference["content_quantity"] if reference["content_confirmed"] else None
        result["pack_unit"]=reference["content_unit"] if reference["content_confirmed"] else ""
    return result


def package_cost(offer, quantity, unit):
    pack,target=SCALES.get(offer.get("pack_unit")),SCALES.get(unit)
    if not offer.get("format_pending") and pack and pack[0] in ("kg","l") and unit=="uds" and quantity>0:
        return round(math.ceil(quantity-1e-9)*offer["price"],2)
    if offer.get("format_pending") or not pack or not target or pack[0]!=target[0] or not offer.get("pack_quantity") or quantity<=0:
        return None
    packages=math.ceil(max(0,quantity*target[1]/(offer["pack_quantity"]*pack[1])-1e-9))
    return round(packages*offer["price"],2)
