"""Validated physical stores, independent of retailer accounts and product IDs."""
import re
from urllib.parse import urlsplit


def normalize_places(places):
    if not isinstance(places, list) or len(places) > 100:
        raise ValueError("Puedes configurar hasta 100 tiendas.")
    result, identifiers = [], set()
    for place in places:
        if not isinstance(place, dict) or set(place)-{"id","name","image_url","color","account","zones"}:
            raise ValueError("La tienda contiene campos no válidos.")
        identifier, name = place.get("id"), place.get("name")
        if (not isinstance(identifier,str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}",identifier)
                or identifier in identifiers or not isinstance(name,str) or not 1 <= len(name.strip()) <= 100):
            raise ValueError("Indica un nombre y un identificador únicos para la tienda.")
        image, color, account, zones = place.get("image_url",""), place.get("color","#267052"), place.get("account",""), place.get("zones",[])
        if not isinstance(image,str) or len(image)>2048:
            raise ValueError("La imagen de la tienda no es válida.")
        parsed = urlsplit(image)
        if image and not (image.startswith('/local/') and not image.startswith('//')) and (
                parsed.scheme not in ('https','http') or not parsed.hostname or parsed.username or parsed.password):
            raise ValueError("Indica una URL HTTP/HTTPS o una imagen de /local/.")
        if not isinstance(color,str) or not re.fullmatch(r"#[a-fA-F0-9]{6}",color) or account not in ('','carrefour'):
            raise ValueError("Selecciona un color y una cuenta compatible.")
        if not isinstance(zones,list) or len(zones)>50 or any(not isinstance(z,str) or not re.fullmatch(r"zone\.[a-z0-9_]+",z) for z in zones):
            raise ValueError("Selecciona zonas válidas de Home Assistant.")
        identifiers.add(identifier)
        result.append({"id":identifier,"name":name.strip(),"image_url":image,"color":color.lower(),"account":account,"zones":list(dict.fromkeys(zones))})
    return result
