"""DIA public prices using Python's standard urllib client in HA's executor."""

import http.cookiejar
import json
import re
import urllib.error
import urllib.request
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode, urlsplit

ROOT = "https://www.dia.es"
POSTAL_PATH = "/api/v1/common-aggregator/save-shipping-address"
SEARCH_PATH = "/api/v1/search-back/search/reduced"
MAX_RESPONSE = 4*1024*1024


class DiaError(ValueError):
    def __init__(self, message, **diagnostics):
        super().__init__(message)
        self.diagnostics = diagnostics


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def anonymous_opener():
    # Keep urllib's truthful default User-Agent; do not impersonate a browser.
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()), NoRedirect())


def request_json(opener, path, *, postal=False):
    """Synchronous bounded I/O: callers must run this in HA's executor."""
    request = urllib.request.Request(ROOT+path, data=b"null" if postal else None,
        headers={"Content-Type":"application/json"} if postal else {}, method="PUT" if postal else "GET")
    try:
        with opener.open(request, timeout=25) as response:
            if response.status != (204 if postal else 200):
                raise DiaError("DIA ha devuelto una respuesta inesperada.", response_class="invalid_response", http_status=response.status)
            raw = response.read(MAX_RESPONSE+1)
            if len(raw) > MAX_RESPONSE:
                raise DiaError("La respuesta de DIA es demasiado grande.", response_class="response_too_large")
            return None if postal else json.loads(raw)
    except urllib.error.HTTPError as err:
        try:
            wait = err.headers.get("Retry-After", "")
            raise DiaError(f"DIA: consulta rechazada (HTTP {err.code}). Se conserva el último precio.",
                http_status=err.code, response_class="access_denied" if err.code == 403 else "rate_limited" if err.code == 429 else "http_error",
                retry_seconds=min(86400,int(wait)) if wait.isdigit() else 0,
                endpoint=path.split("?",1)[0], server=str(err.headers.get("Server", ""))[:80]) from None
        finally:
            err.close()
    except (urllib.error.URLError, OSError) as err:
        raise DiaError("No se ha podido conectar con DIA. Se conserva el último precio.", response_class="network_error") from err
    except (ValueError, UnicodeError) as err:
        if isinstance(err, DiaError):
            raise
        raise DiaError("DIA no ha devuelto JSON válido.", response_class="invalid_response") from err


def postal_path(postal):
    return POSTAL_PATH+"?"+urlencode({"new_postal_code":postal, "skip_dry_run":"true"})


def search_path(query):
    return SEARCH_PATH+"?"+urlencode({"q":query, "page":1})


def confirm_postal(data, postal):
    if (not isinstance(data,dict) or not isinstance(data.get("cart"),dict)
        or data["cart"].get("postal_code") != postal or not isinstance(data.get("search_items"),list)):
        raise DiaError("DIA no ha confirmado el código postal solicitado.", response_class="invalid_region")


def resolve_postal(postal):
    opener = anonymous_opener()
    request_json(opener,postal_path(postal),postal=True)
    # A nonempty query is required; the postal code need not match a product.
    confirm_postal(request_json(opener,search_path(postal)),postal)
    return {"postal_code":postal, "areas":[{"id":postal, "zone":postal, "name":f"Código postal {postal}"}]}


def money(value):
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or not 0 < amount <= 1000000:
            raise InvalidOperation
        return format(amount.quantize(Decimal("0.01")),".2f")
    except (InvalidOperation, ValueError, TypeError):
        raise DiaError("DIA no ha devuelto un precio válido.", response_class="invalid_price") from None


def product_offer(data, link, postal):
    from .store_links import normalize_link
    confirm_postal(data,postal)
    matches = [p for p in data["search_items"] if isinstance(p,dict) and str(p.get("sku_id", "")) == link["id"]]
    if not matches:
        return None
    if len(matches) != 1:
        raise DiaError("DIA no ha confirmado una referencia única.", response_class="invalid_product")
    product = matches[0]
    prices = product.get("prices")
    if not isinstance(prices,dict) or prices.get("currency") != "EUR":
        raise DiaError("DIA no ha devuelto un precio en EUR.", response_class="invalid_price")
    # Conditional club prices and unavailable products must not become a general price.
    if prices.get("is_club_price") is True or product.get("units_in_stock") == 0:
        return None
    if product.get("object_id") is not None and str(product["object_id"]) != link["id"]:
        raise DiaError("DIA ha devuelto identificadores incompatibles.", response_class="invalid_product")
    url = link["url"]
    if isinstance(product.get("url"),str):
        candidate = normalize_link("dia",ROOT+product["url"] if product["url"].startswith("/") else product["url"])
        if candidate["id"] != link["id"]:
            raise DiaError("DIA ha devuelto un enlace de otro producto.", response_class="invalid_product")
        url = candidate["url"]
    return {"store":"dia", "reference_id":link["id"], "url":url,
        "store_name":str(product.get("display_name") or "")[:300], "price":money(prices.get("price")),
        "currency":"EUR", "ean":"", "available":product.get("units_in_stock",0)>0 if type(product.get("units_in_stock")) is int else None,
        "reference_price":money(prices["price_per_unit"]) if prices.get("price_per_unit") is not None else None,
        "reference_unit":str(prices.get("measure_unit") or "")[:40]}


class DiaClient:
    def __init__(self,hass):
        self.hass = hass
        self.opener = None
        self.postal = None

    def close(self):
        # Drop references without touching a cookie jar an executor worker might still use.
        self.opener = self.postal = None

    async def fetch(self,link,config,gate):
        postal = config.get("postal_code", "")
        if (not isinstance(postal,str) or not re.fullmatch(r"(?:0[1-9]|[1-4][0-9]|5[0-2])[0-9]{3}",postal)
            or config.get("area_id") != postal or config.get("zone") != postal):
            raise DiaError("Configura el código postal de DIA.", response_class="missing_region")
        try:
            if self.opener is None or self.postal != postal:
                opener = await self.hass.async_add_executor_job(anonymous_opener)
                self.opener = opener
                await gate()
                await self.hass.async_add_executor_job(lambda:request_json(opener,postal_path(postal),postal=True))
                if self.opener is not opener:
                    raise DiaError("La sesión de DIA se ha detenido.", response_class="configuration_changed")
                self.postal = postal
            opener = self.opener
            await gate()
            data = await self.hass.async_add_executor_job(request_json,opener,search_path(link["id"]))
            if self.opener is not opener:
                raise DiaError("La sesión de DIA se ha detenido.", response_class="configuration_changed")
            return product_offer(data,link,postal)
        except BaseException:
            self.close()
            raise
