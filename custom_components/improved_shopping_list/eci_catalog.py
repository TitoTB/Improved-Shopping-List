"""Opt-in public EAN search; verified products, no browser session or credentials."""
import asyncio
from copy import deepcopy
import json
import math
import re
import time
from urllib.parse import urlencode, urljoin

import aiohttp
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.storage import Store

from .catalog_sources import CatalogSources, INTERVAL
from .const import DOMAIN
from .ean_links import product_eans, DAY
from .price_sources import PriceError
from .product_references import gtin, brand_name, content
from .receipt_quantities import measure_price
from .store_links import normalize_link

STORE = "elcorteingles"
BASE = "https://www.elcorteingles.es"


def number(value):
    if isinstance(value, bool) or value in (None, ""):
        return None
    try:
        result = float(str(value).replace(",", "."))
        return result if math.isfinite(result) and 0 <= result <= 1000000 else None
    except (TypeError, ValueError):
        return None


def product_data(payload, link, expected_ean=""):
    pdp = payload.get("pdp") if isinstance(payload, dict) else None
    product = pdp.get("product", {}) if isinstance(pdp, dict) else {}
    if not isinstance(product, dict) or product.get("id") != link["id"]:
        raise PriceError("La ficha de El Corte Inglés no corresponde al producto.", response_class="invalid_product")
    info = product.get("information_alimentary")
    general = info.get("general", {}) if isinstance(info,dict) else {}
    if not isinstance(general,dict):general={}
    ean = general.get("ean") or product.get("ean")
    if not gtin(ean) or expected_ean and gtin(ean) != gtin(expected_ean):
        raise PriceError("El EAN de El Corte Inglés no coincide con el producto.", response_class="ean_mismatch")
    at = time.time()
    brand = product.get("brand", {})
    result = {"store":STORE, "reference_id":link["id"], "url":link["url"], "ean":ean,
              "name":str(product.get("description", ""))[:500],
              "brand":brand_name(brand.get("name", "") if isinstance(brand, dict) else ""), "checked_at":at}
    net = general.get("netAmount") or {}
    if not isinstance(net,dict):net={}
    unit_text=net.get("unit_text")
    unit = str(net.get("unitName") or (unit_text.get("name", "") if isinstance(unit_text,dict) else "")).lower().strip()
    unit = {"gr":"g", "grs":"g", "litro":"l", "litros":"l", "ud":"uds", "unidades":"uds"}.get(unit, unit)
    quantity = number(net.get("value"))
    try:
        quantity, unit = content(quantity, unit)
    except ValueError:
        quantity, unit = None, ""
    if quantity is not None:
        result.update(content_quantity=quantity, content_unit=unit)
    prices = product.get("priceSpecification") or {}
    if not isinstance(prices,dict):prices={}
    # salePrice is the single-item price; promotional_actions contain conditional multi-buy prices.
    price = number(prices.get("salePrice"))
    if price is None:price=number(prices.get("price"))
    if price is not None:
        result.update(price=price, currency="EUR")
    rate, basis = number(prices.get("measurementUnitPrice")), str(prices.get("pum_description", "")).lower().strip().rstrip(".")
    units = {"kilo":("kg",1), "kg":("kg",1), "litro":("l",1), "unidad":("uds",1),
             "docena":("uds",12), "100 gramos":("g",100), "100 g":("g",100), "100 ml":("ml",100)}
    if rate and basis in units:
        unit, quantity = units[basis]
        result["measure_price"] = measure_price({"price":rate,"quantity":quantity,"unit":unit,"currency":"EUR","checked_at":at,"source":"web"})
    return result


class ECIClient:
    def __init__(self, hass):
        self.hass = hass

    async def _json(self, url, before_request):
        await before_request()
        session = async_create_clientsession(self.hass, auto_cleanup=False, cookie_jar=aiohttp.DummyCookieJar())
        try:
            async with session.get(url, allow_redirects=False, timeout=aiohttp.ClientTimeout(total=25),
                headers={"Accept":"application/json, text/plain, */*", "response_type":"json", "Accept-Language":"es-ES,es;q=0.9",
                         "User-Agent":"Mozilla/5.0", "Referer":BASE+"/supermercado/"}) as response:
                if response.status != 200:
                    retry = response.headers.get("Retry-After", "")
                    raise PriceError(f"El Corte Inglés ha rechazado la consulta (HTTP {response.status}).", http_status=response.status,
                        endpoint=url.split("?",1)[0], response_class="access_denied" if response.status == 403 else "http_error",
                        retry_seconds=min(DAY,max(900,int(retry) if retry.isdigit() else 900)) if response.status in (403,429,503) else 0)
                body = bytearray()
                async for chunk in response.content.iter_chunked(65536):
                    body.extend(chunk)
                    if len(body) > 2*1024*1024:
                        raise PriceError("La respuesta de El Corte Inglés supera el tamaño permitido.")
                result = json.loads(body)
                if not isinstance(result, dict):
                    raise PriceError("El Corte Inglés no ha devuelto datos reconocidos.")
                return result
        finally:
            session.detach()

    async def retrieve(self, url, before_request, expected_ean=""):
        link = normalize_link(STORE,url)
        return product_data(await self._json(link["url"],before_request),link,expected_ean)

    async def search(self, code, before_request):
        if not gtin(code):
            raise PriceError("El EAN no es válido.")
        # The provider expects the printed EAN, not its zero-padded GTIN-14 representation.
        query = code[1:] if len(code)==14 and code.startswith("0") else code
        payload = await self._json(BASE+"/supermercado/buscar/?"+urlencode({"question":query,"catalog":"supermercado","stype":"text_box"}),before_request)
        candidates = {}
        rows=payload.get("products",[])
        if not isinstance(rows,list):raise PriceError("El buscador no ha devuelto productos reconocidos.")
        for item in rows[:100]:
            if not isinstance(item,dict) or not re.fullmatch(r"B[0-9]{1,20}",str(item.get("id",""))):
                continue  # Search results also contain advertisements and executable artwork templates.
            try:
                link = normalize_link(STORE,urljoin(BASE,item.get("url","")))
            except ValueError:
                continue
            if link["id"] == item["id"]:
                candidates[link["id"]] = link
        if len(candidates) != 1:
            return None
        return await self.retrieve(next(iter(candidates.values()))["url"],before_request,code)


class ECICatalog(CatalogSources):
    def __init__(self,hass,catalog,lookup,activity):
        super().__init__(hass,catalog,None,lookup,activity)
        self._store = Store(hass,1,f"{DOMAIN}.eci_catalog")
        self.client = ECIClient(hass)

    def _gate(self):
        pass  # Consent is independent of the static EAN dictionary and other catalogs.

    async def async_run(self):
        if not self._active or not self._data["enabled"]:
            return
        if self._timer:
            self._timer(); self._timer = None
        if self._data["retry_at"]>time.time():
            self._status.update(phase="paused"); self._notify(); return
        codes = {code:p["name"] for p in self.catalog.products for code in product_eans(p)}
        printed = {key:value for p in self.catalog.products for key,value in product_eans(p).items()}
        self._status.update(running=True,phase="preparing",total=len(codes),processed=0,updated=0,errors=[],current="")
        self._notify()
        try:
            for code,name in codes.items():
                if not self._active or not self._data["enabled"]:
                    break
                self._status.update(current=name); self._notify()
                saved = self._data["attempts"].get(code,{})
                data = saved.get("data") if saved.get("success") else None
                try:
                    if not data and saved.get("at",0)+DAY <= time.time():
                        data = await self.client.search(printed[code],self._before_request)
                        self._data["attempts"][code] = {"at":time.time(),"success":bool(data),**({"data":deepcopy(data)} if data else {})}
                    if data and self._active and self._data["enabled"]:
                        self._status["updated"] += await self.catalog.async_complete_store_option(STORE,code,data["url"],data,create=True)
                except (ValueError,OSError,TimeoutError,aiohttp.ClientError) as err:
                    diagnostics = deepcopy(getattr(err,"diagnostics",{}))
                    self._status["errors"].append({"product":name,"ean":code,"message":str(err)[:500],"diagnostics":diagnostics})
                    self._data["attempts"][code] = {"at":time.time(),"success":False}
                    if retry:=diagnostics.get("retry_seconds",0):
                        self._data["retry_at"] = time.time()+retry
                self._status["processed"] += 1
                await self._store.async_save(deepcopy(self._data)); self._notify()
                if self._data["retry_at"] > time.time():
                    break
            self._status.update(phase="paused" if self._data["retry_at"]>time.time() else "finished",current="")
        finally:
            self._status["running"] = False; self._notify()
            if codes and self.activity:
                self.activity.record("stores.catalog","El Corte Inglés: revisión del catálogo finalizada",source="automatic",
                    diagnostics={**deepcopy(self._status),"interval_seconds":INTERVAL,"retry_at":self._data["retry_at"]})
            if self._active and self._data["enabled"]:
                self._timer = async_call_later(self.hass,max(3600,self._data["retry_at"]-time.time()),self._launch)
