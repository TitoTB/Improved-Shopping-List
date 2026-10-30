"""Strict store-specific references. User links are never arbitrary fetch URLs."""

import re
from urllib.parse import urlsplit

STORES = {"masymas":"Masymas", "bm":"BM", "elcorteingles":"El Corte Inglés", "lidl":"Lidl", "mercadona": "Mercadona", "carrefour": "Carrefour", "alcampo": "Alcampo", "consum": "Consum", "lasirena": "La Sirena", "eroski":"Eroski", "dia":"DIA"}
HOSTS = {"masymas":{"tienda.masymas.com"}, "bm":{"www.online.bmsupermercados.es"}, "elcorteingles":{"www.elcorteingles.es"}, "lidl":{"www.lidl.es"}, "mercadona": {"tienda.mercadona.es"}, "carrefour": {"www.carrefour.es", "carrefour.es"},
         "alcampo": {"www.compraonline.alcampo.es", "compraonline.alcampo.es"},
         "consum": {"tienda.consum.es"}, "lasirena": {"www.lasirena.es"}, "eroski":{"supermercado.eroski.es"}, "dia":{"www.dia.es","dia.es"}}


def normalize_link(store, value):
    if store not in STORES or not isinstance(value, (str, dict)):
        raise ValueError("La vinculación de tienda no es válida.")
    if isinstance(value, dict):
        if set(value) - {"id", "url"}:
            raise ValueError("La vinculación contiene campos no admitidos.")
        identifier, url = value.get("id", ""), value.get("url", "")
        if not isinstance(identifier, str) or not isinstance(url, str):
            raise ValueError("El enlace o ID debe ser un texto.")
        parsed = normalize_link(store, url or identifier)
        if identifier and identifier != parsed["id"]:
            raise ValueError("El enlace y la ID no corresponden al mismo producto.")
        return parsed
    value = value.strip()
    if not value or len(value) > 2048 or any(ord(c) < 33 for c in value):
        raise ValueError("Introduce un enlace o ID de producto válido.")
    url = ""
    if "://" in value:
        parts = urlsplit(value)
        if (parts.scheme != "https" or parts.hostname not in HOSTS[store] or parts.username or parts.password
            or parts.port not in (None, 443) or "%" in parts.netloc or "\\" in parts.path
            or any(segment in (".", "..") for segment in parts.path.split("/"))
            or re.search(r"%(?:2f|5c|2e)", parts.path, re.I)):
            raise ValueError(f"Utiliza un enlace HTTPS de {STORES[store]}.")
        patterns = {"masymas":r"/(?:es/)?p/[^/]+/([0-9]{1,12})/?", "bm":r"/(?:es/)?p/[^/]+/([0-9]{1,12})/?", "elcorteingles":r"/supermercado/(B[0-9]{1,20})-[^/]+/?", "lidl":r"/(?:[^/]+/)*p([0-9]{1,12})/?", "mercadona": r"/product/([0-9]{1,12})(?:/[^/]*)?/?",
            "alcampo": r"/products/[^/]+/([0-9]{1,12})/?",
            "carrefour": r"/supermercado/(?:[^/]+/)?(R-[A-Za-z0-9-]{1,80})/p/?",
            "consum": r"/(?:es/)?p/[^/]+/([0-9]{1,12})/?",
            "lasirena": r"/(?:es/)?[^/]+-([0-9]{1,12})/p/?",
            "eroski": r"/es/productdetail/([0-9]{1,12})-[^/]+/?",
            "dia": r"/(?:[^/]+/)*p/([0-9]{1,12})/?"}
        match = re.fullmatch(patterns[store], parts.path)
        if not match:
            raise ValueError(f"El enlace no es una ficha de producto de {STORES[store]}.")
        identifier = match[1]
        # Remove tracking, fragments and user-controlled query parameters.
        url = f"https://{sorted(HOSTS[store], key=len, reverse=True)[0]}{parts.path.rstrip('/')}"
        if store in ("eroski","elcorteingles"):
            url += "/"  # The public product route redirects without this slash.
    else:
        if store in ("eroski","elcorteingles"):
            raise ValueError(f"{STORES[store]} necesita el enlace completo de la ficha del producto; la ID sola no es suficiente.")
        identifier = value
    pattern = r"B[0-9]{1,20}" if store == "elcorteingles" else r"R-[A-Za-z0-9-]{1,80}" if store == "carrefour" else r"[0-9]{1,12}"
    if not re.fullmatch(pattern, identifier):
        raise ValueError(f"La ID de {STORES[store]} no es válida.")
    defaults = {"masymas":f"https://tienda.masymas.com/es/p/producto/{identifier}", "bm":f"https://www.online.bmsupermercados.es/es/p/producto/{identifier}", "elcorteingles":url, "lidl":"", "mercadona": f"https://tienda.mercadona.es/product/{identifier}",
        "alcampo": f"https://www.compraonline.alcampo.es/products/producto/{identifier}",
        "carrefour": f"https://www.carrefour.es/supermercado/{identifier}/p",
        "consum": f"https://tienda.consum.es/es/p/producto/{identifier}",
        "lasirena": f"https://www.lasirena.es/es/producto-{identifier}/p",
        "eroski":url, "dia":f"https://www.dia.es/p/{identifier}"}
    return {"id": identifier, "url": url or defaults[store]}


def normalize_links(values):
    if not isinstance(values, dict) or set(values) - set(STORES):
        raise ValueError("Las tiendas de las vinculaciones no son válidas.")
    return {store: normalize_link(store, value) for store, value in values.items() if value != ""}
