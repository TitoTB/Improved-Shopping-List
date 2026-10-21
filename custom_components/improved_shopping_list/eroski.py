"""Eroski public pickup-center sessions and bounded HTML price extraction."""

import json
import re
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from urllib.parse import urlencode, urlsplit
from yarl import URL

import aiohttp
from homeassistant.helpers.aiohttp_client import async_create_clientsession

ROOT = "https://supermercado.eroski.es"
SLOT_PATH = "/es/login/delivery/index.selectdelivery.addressselector.pickupaddressselector.slotform"
AREA_PATTERN = r"[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}"


class EroskiError(ValueError):
    def __init__(self, message, **diagnostics):
        super().__init__(message)
        self.diagnostics = diagnostics


class EroskiPage(HTMLParser):
    """Parse data only; scripts and inline handlers are never executed."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.forms = {}
        self.centers = {}
        self.canonical = ""
        self.currency = ""
        self.prices = []
        self.name = []
        self._form = None
        self._center = None
        self._capture = None
        self._depth = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if self._capture is not None and tag not in ("input", "meta", "link", "img", "br", "hr"):
            self._depth += 1
        if tag == "form":
            self._form = {"action":a.get("action", ""), "fields":{}}
            self.forms[a.get("id", "")] = self._form
        if tag == "input" and self._form is not None and a.get("name") in ("t:formdata", "zipCode"):
            self._form["fields"][a["name"]] = a.get("value", "")
        if tag == "li" and a.get("data-address-ref"):
            identifier, shop = a["data-address-ref"], a.get("data-shopref", "")
            if (re.fullmatch(AREA_PATTERN, identifier) and re.fullmatch(r"[A-Za-z0-9_-]{1,32}", shop)
                and a.get("data-currency") == "EUR"
                and a.get("data-deliverymode") in ("DRIVE_DELIVERY", "SHOP_DELIVERY", "LOCKER_DELIVERY")):
                self._center = {"id":identifier, "zone":shop, "name":""}
                self.centers[identifier] = self._center
        if tag == "span" and "center_name" in a.get("class", "").split() and self._center:
            self._capture, self._depth = self._center, 1
        if tag == "h1" and a.get("itemprop") == "description":
            self._capture, self._depth = self.name, 1
        if a.get("itemprop") == "price" and "offer-now" in a.get("class", "").split():
            value = []
            self.prices.append(value)
            self._capture, self._depth = value, 1
        if tag == "meta" and a.get("itemprop") == "priceCurrency":
            self.currency = a.get("content", "")
        if tag == "link" and a.get("rel") == "canonical":
            self.canonical = a.get("href", "")

    def handle_data(self, text):
        if isinstance(self._capture, dict):
            self._capture["name"] += text
        elif isinstance(self._capture, list):
            self._capture.append(text)

    def handle_endtag(self, tag):
        if tag in ("input", "meta", "link", "img", "br", "hr"):
            return
        if tag == "form":
            self._form = None
        if tag == "li":
            self._center = None
        if self._capture is not None:
            self._depth -= 1
            if self._depth <= 0:
                self._capture = None


def parse_page(raw):
    page = EroskiPage()
    page.feed(raw)
    return page


def pickup_areas(page):
    return sorted(({**area, "name":" ".join(area["name"].split())[:200]} for area in page.centers.values()
        if area["name"].strip()), key=lambda area:area["name"].casefold())


def product_offer(raw, link):
    from .store_links import normalize_link
    page = parse_page(raw)
    try:
        canonical = normalize_link("eroski", page.canonical)
    except ValueError:
        raise EroskiError("Eroski no ha confirmado la ficha del producto.", response_class="invalid_product") from None
    if canonical["id"] != link["id"] or page.currency != "EUR" or len(page.prices) != 1:
        raise EroskiError("Eroski no ha confirmado un precio único para esta referencia.", response_class="invalid_product")
    text = "".join(page.prices[0]).strip()
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]{3})*,[0-9]{2}", text):
        raise EroskiError("Eroski no ha devuelto un precio válido.", response_class="invalid_price")
    try:
        price = Decimal(text.replace(".", "").replace(",", "."))
        if not 0 < price <= 1000000:
            raise InvalidOperation
    except InvalidOperation:
        raise EroskiError("Eroski no ha devuelto un precio válido.", response_class="invalid_price") from None
    return {"store":"eroski", "reference_id":link["id"], "url":canonical["url"],
        "store_name":" ".join("".join(page.name).split())[:300], "price":format(price,".2f"),
        "currency":"EUR", "ean":"", "available":None}


class EroskiClient:
    """Own anonymous cookies in memory; never import or persist browser sessions."""

    def __init__(self, hass):
        self.hass = hass
        self.session = None
        self.context = None

    def close(self):
        if self.session is not None:
            self.session.cookie_jar.clear()
            self.session.detach()  # HA owns the shared connector.
        self.session = self.context = None

    def _start(self):
        self.close()
        self.session = async_create_clientsession(self.hass, auto_cleanup=False, cookie_jar=aiohttp.CookieJar(),
            headers={"User-Agent":"Mozilla/5.0 (compatible; Improved-Shopping-List)", "Accept-Language":"es-ES,es;q=0.9"})

    async def request(self, path, gate, *, data=None):
        if gate is not None:
            await gate()
        async with self.session.request("POST" if data is not None else "GET", ROOT+path,
            data=data, headers={"X-Requested-With":"XMLHttpRequest"} if data is not None else {},
            timeout=aiohttp.ClientTimeout(total=25), allow_redirects=False) as response:
            if response.status != 200:
                wait = response.headers.get("Retry-After", "")
                raise EroskiError(f"Eroski: consulta rechazada (HTTP {response.status}). Se conserva el último precio.",
                    http_status=response.status, response_class="access_denied" if response.status == 403 else "rate_limited" if response.status == 429 else "http_error",
                    retry_seconds=min(86400,int(wait)) if wait.isdigit() else 0, endpoint=path.split("?",1)[0],
                    redirect_path=urlsplit(response.headers.get("Location", "")).path[:200])
            raw = bytearray()
            async for chunk in response.content.iter_chunked(65536):
                raw.extend(chunk)
                if len(raw) > 4*1024*1024:
                    raise EroskiError("La respuesta de Eroski es demasiado grande.", response_class="response_too_large")
            return raw.decode(response.charset or "utf-8", errors="replace")

    async def selection(self, postal, gate=None):
        self._start()
        await self.request("/es/",gate)
        return parse_page(await self.request("/es/login/delivery/?"+urlencode({"zipCode":postal}),gate))

    def _shop(self):
        cookies = self.session.cookie_jar.filter_cookies(URL(ROOT))
        return cookies["supermarket.ali.shop"].value if "supermarket.ali.shop" in cookies else ""

    async def fetch(self, link, config, gate):
        key = (config.get("postal_code"), config.get("area_id"), config.get("zone"))
        try:
            if (self.context != key or self.session is None or self._shop() != key[2]):
                page = await self.selection(key[0],gate)
                area = page.centers.get(key[1])
                form = page.forms.get("slotForm", {})
                action = urlsplit(form.get("action", ""))
                if (not area or area["zone"] != key[2] or action.scheme != "https" or action.hostname != "supermercado.eroski.es"
                    or action.port not in (None,443) or action.username or action.password or action.path != SLOT_PATH
                    or action.query or action.fragment or not form.get("fields", {}).get("t:formdata")
                    or form["fields"].get("zipCode") != key[0]):
                    raise EroskiError("Eroski no ha confirmado el centro seleccionado.", response_class="invalid_region")
                fields = {**form["fields"], "radiogroup":"offQuick", "selectedAddressRef":key[1], "t:zoneid":"^"}
                result = json.loads(await self.request(SLOT_PATH,gate,data=fields))
                target = urlsplit(result.get("_tapestry",{}).get("redirectURL", "")) if isinstance(result,dict) else urlsplit("")
                if target.hostname != "supermercado.eroski.es" or target.scheme != "https" or target.path not in ("", "/", "/es/") or self._shop() != key[2]:
                    raise EroskiError("Eroski no ha aplicado el centro seleccionado.", response_class="invalid_region")
                self.context = key
            raw = await self.request(urlsplit(link["url"]).path,gate)
            if self._shop() != key[2]:
                raise EroskiError("La sesión de Eroski ha cambiado de centro.", response_class="invalid_region")
            return product_offer(raw,link)
        except BaseException:
            self.close()
            raise
