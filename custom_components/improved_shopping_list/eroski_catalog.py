"""Anonymous Eroski catalog: exact EAN search, unique result and canonical page."""
from asyncio import Lock
from html.parser import HTMLParser
import re
import time
from urllib.parse import urlencode, urljoin, urlsplit

from .eroski import EroskiClient, EroskiError, ROOT, product_offer
from .product_references import brand_name, gtin, inferred_content
from .receipt_quantities import measure_price
from .store_links import normalize_link

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}


class SearchPage(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.cards = []
        self.heading_depth = None
        self.headings = []
        self.links = {}
        self.no_results = False
        self.invalid_link = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag not in VOID:
            self.depth += 1
        classes = a.get("class", "").split()
        if a.get("id") == "productListZone":
            self.cards.append(self.depth)
        if a.get("idautomation") == "no_results_found" or "no_results_found" in classes:
            self.no_results = True
        if tag == "h1":
            self.heading_depth = self.depth
            self.headings.append([])
        if tag == "a" and self.cards and "/es/productdetail/" in a.get("href", ""):
            try:
                link = normalize_link("eroski", urljoin(ROOT, a["href"]))
                self.links[link["id"]] = link
            except ValueError:
                self.invalid_link = True

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        if self.heading_depth == self.depth:
            self.heading_depth = None
        self.cards = [depth for depth in self.cards if depth < self.depth]
        self.depth = max(0, self.depth - 1)

    def handle_data(self, value):
        if self.heading_depth is not None:
            self.headings[-1].append(value)


def search_result(raw, code):
    page = SearchPage()
    page.feed(raw)
    if page.invalid_link:
        raise EroskiError("Eroski ha devuelto un enlace de producto no válido.", response_class="invalid_product")
    if page.no_results and not page.links:
        return None
    headings = [" ".join("".join(parts).split()) for parts in page.headings]
    query = re.search(r"Mostrando resultados para\s+(\d{8,14})\s*\((\d+)\)\s*$", headings[0]) if len(headings) == 1 else None
    if not query or gtin(query[1]) != gtin(code):
        raise EroskiError("Eroski no ha confirmado la búsqueda del EAN solicitado.", response_class="invalid_response")
    if query[2] == "0" and not page.links:
        return None
    if query[2] != "1" or len(page.links) != 1 or page.no_results:
        raise EroskiError("Eroski no permite confirmar una única referencia para este EAN.", response_class="ambiguous_product")
    return next(iter(page.links.values()))


class PackageFields(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.brand = ""

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if a.get("itemprop") == "brand" and a.get("content"):
            self.brand = brand_name(a["content"])


def product_data(raw, link, ean=""):
    offer = product_offer(raw, link)
    fields = PackageFields()
    fields.feed(raw)
    result = {"store": "eroski", "reference_id": link["id"], "url": offer["url"],
        "name": offer["store_name"], "brand": fields.brand, "price": float(offer["price"]),
        "currency": "EUR", "checked_at": int(time.time())}
    quantity, unit = inferred_content({"name": result["name"]})
    if quantity and unit:
        result.update(content_quantity=quantity, content_unit=unit)
        result["measure_price"] = measure_price({"price": result["price"], "quantity": quantity, "unit": unit,
            "currency": "EUR", "source": "web", "checked_at": result["checked_at"]})
    if ean:
        result["ean"] = ean
    return result


class EroskiCatalogClient(EroskiClient):
    def __init__(self, hass):
        super().__init__(hass)
        self.lock = Lock()

    async def _request(self, path, gate, stage):
        try:
            return await self.request(path, gate)
        except EroskiError as err:
            diagnostics = {**err.diagnostics, "stage": stage}
            if diagnostics.get("http_status") in (403, 429, 503):
                diagnostics["retry_seconds"] = max(900, diagnostics.get("retry_seconds", 0))
            raise EroskiError(str(err), **diagnostics) from err

    async def _ready(self, gate):
        if self.session is None:
            self._start()
            await self._request("/es/", gate, "session")

    async def _find(self, code, gate):
        code = gtin(code)
        if not code:
            raise EroskiError("Indica un EAN válido.", response_class="invalid_product")
        native = code[1:] if code.startswith("0") else code
        raw = await self._request("/es/search/results/?" + urlencode({"q": native}), gate, "ean_search")
        return search_result(raw, code), native

    async def search(self, code, gate):
        async with self.lock:
            try:
                await self._ready(gate)
                link, native = await self._find(code, gate)
                if link is None:
                    return None
                raw = await self._request(urlsplit(link["url"]).path, gate, "product_page")
                return product_data(raw, link, native)
            except BaseException:
                self.close()
                raise

    async def retrieve(self, url, gate, expected_ean=""):
        link = normalize_link("eroski", url)
        async with self.lock:
            try:
                await self._ready(gate)
                native = ""
                if expected_ean:
                    found, native = await self._find(expected_ean, gate)
                    if found is None or found["id"] != link["id"]:
                        raise EroskiError("El EAN de Eroski no corresponde al enlace del producto.", response_class="ean_mismatch")
                raw = await self._request(urlsplit(link["url"]).path, gate, "product_page")
                return product_data(raw, link, native)
            except BaseException:
                self.close()
                raise
