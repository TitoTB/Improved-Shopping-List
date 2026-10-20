"""Credential-free public shopping data contract, shared with the feed exporter."""

from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
from urllib.parse import urlsplit

FIELDS = {"ean", "name", "price", "currency", "affiliate_url"}
MAX_PRODUCTS = 50000


def gtin(value):
    if (not isinstance(value, str) or len(value) not in (8, 12, 13, 14)
        or not value.isascii() or not value.isdigit()):
        raise ValueError("Código GTIN no válido.")
    check = (10 - sum(int(digit) * (3 if index % 2 == 0 else 1)
        for index, digit in enumerate(reversed(value[:-1])))) % 10
    if check != int(value[-1]):
        raise ValueError("Dígito de control GTIN no válido.")
    return value.zfill(14)


def record(data):
    if not isinstance(data, dict) or set(data) != FIELDS:
        raise ValueError("El producto no respeta los cinco campos públicos.")
    gtin(data["ean"])
    name, url = data["name"], data["affiliate_url"]
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 300 or any(ord(c) < 32 for c in name):
        raise ValueError("Nombre de producto no válido.")
    try:
        price = Decimal(data["price"]) if isinstance(data["price"], str) else Decimal("NaN")
        if not price.is_finite() or not 0 < price <= 1000000 or price.as_tuple().exponent < -2:
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        raise ValueError("Precio de producto no válido.") from None
    if data["currency"] != "EUR":
        raise ValueError("La moneda de este feed debe ser EUR.")
    if not isinstance(url, str) or len(url) > 4000 or any(ord(c) < 33 for c in url):
        raise ValueError("Enlace de afiliado no válido.")
    parts = urlsplit(url)
    if (parts.scheme != "https" or parts.hostname not in ("www.awin1.com", "awin1.com")
        or parts.username or parts.password or parts.port not in (None, 443)
        or parts.path not in ("/pclick.php", "/cread.php") or parts.fragment):
        raise ValueError("El enlace no corresponde a un enlace público de Awin.")
    # Preserve the original affiliate link without rewriting its tracking parameters.
    return {"ean": data["ean"], "name": name.strip(), "price": format(price, ".2f"),
            "currency": "EUR", "affiliate_url": url}


def encode(data):
    return (json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def index(products):
    if not isinstance(products, list) or not products or len(products) > MAX_PRODUCTS:
        raise ValueError("El catálogo está vacío o supera el tamaño permitido.")
    result = {}
    for item in products:
        item = record(item)
        key = gtin(item["ean"])
        if key in result:
            raise ValueError("El catálogo contiene códigos duplicados.")
        result[key] = item
    return result


def snapshot(products):
    entries = index(products)
    return encode({"schema": 1, "products": [entries[key] for key in sorted(entries)]})


def read_snapshot(raw):
    data = json.loads(raw)
    if not isinstance(data, dict) or set(data) != {"schema", "products"} or type(data["schema"]) is not int or data["schema"] != 1:
        raise ValueError("Versión de catálogo no compatible.")
    return index(data["products"])


def descriptor(path, raw):
    return {"path": path, "sha256": digest(raw), "bytes": len(raw)}


def check_descriptor(data):
    if (not isinstance(data, dict) or set(data) != {"path", "sha256", "bytes"}
        or not isinstance(data["path"], str) or not re.fullmatch(r"(?:snapshots|deltas)/[a-f0-9]{64}\.json", data["path"])
        or not isinstance(data["sha256"], str) or not re.fullmatch(r"[a-f0-9]{64}", data["sha256"])
        or type(data["bytes"]) is not int or not 1 <= data["bytes"] <= 16 * 1024 * 1024):
        raise ValueError("Referencia de catálogo no válida.")
    return data


def apply_delta(products, raw, base_version, version):
    data = json.loads(raw)
    if (not isinstance(data, dict) or set(data) != {"schema", "base_version", "version", "upsert", "deleted"}
        or type(data["schema"]) is not int or data["schema"] != 1 or data["base_version"] != base_version or data["version"] != version
        or not isinstance(data["upsert"], list) or not isinstance(data["deleted"], list)
        or len(data["upsert"]) > MAX_PRODUCTS or len(data["deleted"]) > MAX_PRODUCTS):
        raise ValueError("El delta no corresponde a la versión guardada.")
    result = dict(products)
    seen = set()
    for key in data["deleted"]:
        if not isinstance(key, str) or gtin(key) != key or key in seen:
            raise ValueError("Baja de producto no válida.")
        seen.add(key)
        result.pop(key, None)
    for item in data["upsert"]:
        item = record(item)
        key = gtin(item["ean"])
        if key in seen:
            raise ValueError("El delta contiene cambios duplicados.")
        seen.add(key)
        result[key] = item
    if digest(snapshot(list(result.values()))) != version:
        raise ValueError("La comprobación del catálogo actualizado ha fallado.")
    return result
