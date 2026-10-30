"""Optional public shop catalogs: dictionary first, exact EANs, bounded discovery."""
import asyncio
from asyncio import sleep
from copy import deepcopy
import hashlib
import json
import re
import time
from urllib.parse import urlencode

import aiohttp
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.storage import Store

from .catalog_sources import CatalogSources
from .const import DOMAIN
from .ean_links import DAY, product_eans
from .option_lookup import metadata, web_measure_price
from .price_sources import PriceError, consum_offer
from .product_references import gtin
from .receipt_quantities import measure_price
from .store_links import STORES, normalize_link

PUBLIC_SHOPS = {
    "masymas": "https://tienda.masymas.com",
    "bm": "https://www.online.bmsupermercados.es",
    "consum": "https://tienda.consum.es",
}
HTTP_INTERVAL=20


class RequestGate:
    def __init__(self,hass):
        self.store=Store(hass,1,f"{DOMAIN}.public_catalog_http")
        self.next=None;self.lock=asyncio.Lock()

    async def before(self,store):
        async with self.lock:
            if self.next is None:
                saved=await self.store.async_load()
                self.next={k:v for k,v in (saved or {}).items() if k in PUBLIC_SHOPS and type(v) in (int,float) and time.time()<v<=time.time()+DAY} if isinstance(saved,dict) else {}
            await sleep(max(0,self.next.get(store,0)-time.time()))
            self.next[store]=time.time()+HTTP_INTERVAL
            await self.store.async_save(self.next)


def commercial_terms(products, code):
    """Never turn the user's generic catalog label into a commercial search."""
    names=[]
    for product in products:
        for ref in product.get("commercial_references",[]):
            if ref.get("active") is False or gtin(ref.get("ean"))!=code:continue
            name=" ".join(str(ref.get("name") or "").split())[:160]
            if not name or name.casefold()==product["name"].casefold():continue
            names.append(name)
            variant=re.sub(r"\b\d+(?:[.,]\d+)?\s*(?:kg|gr?|ml|cl|litros?|uds?)\b", " ",name,flags=re.I)
            variant=re.sub(r"\b(?:bolsa|paquete|envase|pack)\b", " ",variant,flags=re.I)
            brand=ref.get("brand")
            if brand:variant=re.sub(re.escape(brand)," ",variant,flags=re.I)
            variant=" ".join(variant.split())
            if len(variant)>=4:names.append(variant)
    return list(dict.fromkeys(names))[:2]  # At most two name queries per shop/EAN/day.


def shop_product(store, data, expected_ean=""):
    if not isinstance(data,dict) or not isinstance(data.get("productData"),dict):
        raise PriceError("La tienda no ha devuelto una ficha válida.",response_class="invalid_response")
    link=normalize_link(store,data["productData"].get("url",""))
    if str(data.get("code",""))!=link["id"] or not gtin(data.get("ean")) or expected_ean and gtin(data["ean"])!=gtin(expected_ean):
        raise PriceError("El EAN o la referencia no coincide con el producto.",response_class="ean_mismatch")
    offer=consum_offer(data,link)
    if not offer:
        # Unavailable products can still provide explicit package metadata.
        result=metadata({"name":data["productData"].get("description") or data["productData"].get("name"),"brand":data["productData"].get("brand")})
    else:
        result={**metadata(offer),**{key:offer[key] for key in ("price","currency","ean","reference_price","reference_unit") if key in offer}}
        result["price"]=float(result["price"])
        # Public shops use human-readable bases (KILO, 1 Kg, 100 ml).
        basis=re.fullmatch(r"\s*(?:(\d+(?:[.,]\d+)?)\s*)?(kg|kilo|kilogramos?|g|gr|gramos?|l|litros?|ml|cl|u\.?|uds?|unidades?)\s*",str(result.get("reference_unit", "")),re.I)
        if basis and result.get("reference_price"):
            raw_unit=basis[2].lower()
            unit="kg" if raw_unit.startswith(('kilo','kg')) else "g" if raw_unit.startswith(('gr','g')) else "l" if raw_unit.startswith(('litro','l')) else raw_unit if raw_unit in ('ml','cl') else "uds"
            try:result["measure_price"]=measure_price({"price":float(result["reference_price"]),"quantity":float((basis[1] or '1').replace(',','.')),"unit":unit,"currency":"EUR","source":"web","checked_at":int(time.time())})
            except (TypeError,ValueError):pass
        if "measure_price" not in result:
            if rate:=web_measure_price({k:v for k,v in result.items() if k not in ('reference_price','reference_unit')}):result["measure_price"]=rate
    result.update(store=store,ean=data["ean"],reference_id=link["id"],url=link["url"],checked_at=int(time.time()))
    return result


async def request(hass,store,path,before_request):
    if store not in PUBLIC_SHOPS or not path.startswith("/api/rest/V1.0/catalog/"):
        raise ValueError("Consulta de catálogo no admitida.")
    session=async_create_clientsession(hass,auto_cleanup=False,cookie_jar=aiohttp.DummyCookieJar())
    try:
        await before_request()
        runtime=hass.data.setdefault(DOMAIN,{})
        if "public_catalog_http_gate" not in runtime:runtime["public_catalog_http_gate"]=RequestGate(hass)
        gate=runtime["public_catalog_http_gate"]
        await gate.before(store)
        endpoint=PUBLIC_SHOPS[store]+path
        async with session.get(endpoint,headers={"Accept":"application/json","User-Agent":"Improved-Shopping-List"},allow_redirects=False,timeout=aiohttp.ClientTimeout(total=25)) as response:
            if response.status==404:return None
            if response.status!=200:
                retry=response.headers.get("Retry-After","")
                raise PriceError(f"{STORES[store]} ha rechazado la consulta (HTTP {response.status}).",http_status=response.status,
                    endpoint=endpoint.split("?",1)[0],response_class="access_denied" if response.status==403 else "http_error",
                    retry_seconds=min(DAY,max(900,int(retry) if retry.isdigit() else 900)) if response.status in (403,429,503) else 0)
            raw=bytearray()
            async for chunk in response.content.iter_chunked(65536):
                raw.extend(chunk)
                if len(raw)>4*1024*1024:raise PriceError("La respuesta del catálogo es demasiado grande.",response_class="response_too_large")
            try:return json.loads(raw)
            except (ValueError,UnicodeError) as err:raise PriceError("La tienda no ha devuelto JSON válido.",response_class="invalid_response") from err
    finally:session.detach()


async def retrieve(hass,store,url,before_request,expected_ean=""):
    link=normalize_link(store,url)
    data=await request(hass,store,f"/api/rest/V1.0/catalog/product/code/{link['id']}?showRecommendations=false",before_request)
    if not data:raise PriceError("No se ha encontrado esta ficha.",response_class="not_found")
    result=shop_product(store,data,expected_ean)
    if result["reference_id"]!=link["id"]:raise PriceError("La referencia devuelta no coincide.",response_class="invalid_product")
    return result


class CatalogDiscovery:
    """Shared ordering, persistent results and negative-cache; no implicit consent."""
    def __init__(self,hass,catalog,links,lookup):
        self.hass,self.catalog,self.links,self.lookup=hass,catalog,links,lookup
        self.managers={};self._entries={};self._lock=asyncio.Lock()
        self._store=Store(hass,1,f"{DOMAIN}.public_catalog_discovery")

    async def async_load(self):
        saved=await self._store.async_load()
        if isinstance(saved,dict):
            for key,entry in saved.items():
                if isinstance(key,str) and isinstance(entry,dict) and type(entry.get("expires")) in (int,float) and time.time()<entry["expires"]<=time.time()+30*DAY:
                    data=entry.get("data")
                    try:
                        if data and (key.split(":",1)[0]!=data["store"] or gtin(data["ean"])!=key.rsplit(":",1)[-1] or normalize_link(data["store"],data["url"])["id"]!=data["reference_id"]):continue
                    except (KeyError,TypeError,ValueError):continue
                    self._entries[key]=entry

    def enabled(self):
        return {store:source for store,source in self.managers.items() if source._active and source._data["enabled"]}

    def fingerprint(self):
        return "|".join(sorted(self.enabled()))

    async def _save(self):
        self._entries=dict(sorted(self._entries.items(),key=lambda item:item[1].get("expires",0))[-2000:])
        await self._store.async_save(deepcopy(self._entries))

    async def _dictionary(self,code):
        # Resolve all enabled stores before issuing any search query.
        result={}
        for store in self.enabled():
            link=await self.links.async_find_link(store,code)
            source=self.managers[store]
            if store=="mercadona" and not link:
                await source.index.async_refresh()
                if identifier:=source.index.products.get(code):link=normalize_link(store,f"https://tienda.mercadona.es/product/{identifier}")
            if link:result[store]=link
        return result

    async def _find(self,store,code,names,link=None):
        source=self.enabled().get(store)
        if not source:return None
        identity=store+":"+code
        signature=hashlib.sha256(json.dumps([link,names],sort_keys=True).encode()).hexdigest()
        cached=self._entries.get(identity,{})
        if cached.get("expires",0)>time.time() and (cached.get("data") or cached.get("signature")==signature):
            return deepcopy(cached.get("data"))
        if source._data["retry_at"]>time.time():return None
        try:
            if link:
                data=await self.lookup.retrieve(link["url"],store,code,before_request=source._before_request)
            elif store in PUBLIC_SHOPS:
                data=None
                for query in ([code[1:] if code.startswith("0") else code] if store=="masymas" else names):
                    response=await request(self.hass,store,"/api/rest/V1.0/catalog/searcher/products?"+urlencode({"q":query,"limit":5,"offset":0}),source._before_request)
                    catalog=response.get("catalog") if isinstance(response,dict) else None
                    if not isinstance(catalog,dict) or not isinstance(catalog.get("products"),list):
                        raise PriceError("La tienda ha devuelto una búsqueda no válida.",response_class="invalid_response")
                    matches=[p for p in catalog["products"] if isinstance(p,dict) and gtin(p.get("ean"))==code]
                    if len(matches)>1:raise PriceError("Hay varias referencias para este EAN; indica la URL manualmente.",response_class="ambiguous_product")
                    if matches:data=shop_product(store,matches[0],code);break
            else:return None
            if data and gtin(data.get("ean"))!=code:raise PriceError("El EAN no coincide.",response_class="ean_mismatch")
            self._entries[identity]={"signature":signature,"expires":time.time()+(30*DAY if data else DAY),"data":data}
            await self._save()
            return deepcopy(data)
        except (ValueError,OSError,TimeoutError,aiohttp.ClientError) as err:
            wait=getattr(err,"diagnostics",{}).get("retry_seconds",0)
            if wait:
                source._data["retry_at"]=time.time()+wait
                await source._save_state()
            raise

    async def async_find(self,store,code,names):
        async with self._lock:
            links=await self._dictionary(code)
            if store in links:return await self._find(store,code,names,links[store])
            # A name-search worker must first give exact-EAN providers a chance.
            if store!="masymas" and "masymas" in self.enabled():
                try:await self._find("masymas",code,[],links.get("masymas"))
                except (ValueError,OSError,TimeoutError,aiohttp.ClientError):pass
            return await self._find(store,code,names)

    async def async_hint(self,code):
        code=gtin(code)
        if not code or not self.enabled():return None
        async with self._lock:
            names=commercial_terms(self.catalog.products,code)
            links=await self._dictionary(code)
            # Cached data and dictionary URLs have priority over all searches.
            ordered=[*links,*[store for store in ("masymas","mercadona","alcampo","bm","consum") if store in self.enabled() and store not in links]]
            for store in ordered:
                try:data=await self._find(store,code,names,links.get(store))
                except (ValueError,OSError,TimeoutError,aiohttp.ClientError):continue
                if data and data.get("name"):
                    return {**data,"status":"found","product_name":data["name"],"source":STORES[store]}
        return None


class PublicCatalogSource(CatalogSources):
    def __init__(self,hass,catalog,links,lookup,activity,store,discovery):
        self.source_store,self.source_name=store,STORES[store]
        super().__init__(hass,catalog,links,lookup,activity)
        self.discovery=discovery

    def _gate(self):
        super()._gate()
        self.links.enabled_stores.discard(self.source_store)  # Never create an unverified option.

    async def _before_request(self):
        await super()._before_request()
        self._status["http_requests"]=self._status.get("http_requests",0)+1

    async def async_run(self):
        if not self._active or not self._data["enabled"]:return
        if self._data["retry_at"]>time.time():
            self._status.update(phase="paused");self._notify();return
        if self._timer:self._timer();self._timer=None
        products=self.catalog.products
        codes=sorted({code for p in products for code in product_eans(p)})
        self._status.update(running=True,phase="preparing",total=len(codes),processed=0,updated=0,errors=[],current="",http_requests=0)
        self._notify()
        try:
            for code in codes:
                if not self._active or not self._data["enabled"]:break
                product=next(p for p in products if code in product_eans(p))
                self._status.update(current=product["name"],phase="querying");self._notify()
                try:
                    data=await self.discovery.async_find(self.source_store,code,commercial_terms(products,code))
                    if not self._active or not self._data["enabled"]:break
                    if data:
                        identity=code+":"+data["reference_id"]
                        self._data["attempts"][identity]={"at":time.time(),"success":data.get("price") is not None,"matched":True,"data":deepcopy(data)}
                        await self._save_state()
                        self._status["updated"]+=await self.catalog.async_complete_store_option(self.source_store,code,data["url"],data,create=True,show_store=self._data["show_store"],catalog_source=True)
                except (ValueError,OSError,TimeoutError,aiohttp.ClientError) as err:
                    self._status["errors"].append({"product":product["name"],"ean":code,"message":str(err)[:500],"diagnostics":deepcopy(getattr(err,"diagnostics",{}))})
                self._status["processed"]+=1;self._notify()
                if self._data["retry_at"]>time.time():break
            self._status.update(phase="paused" if self._data["retry_at"]>time.time() else "finished")
        except asyncio.CancelledError:
            self._status["phase"]="cancelled"
            raise
        finally:
            self._status.update(running=False,current="");self._notify()
            if self.activity and (self._status["http_requests"] or self._status["updated"] or self._status["errors"]):
                phase={"paused":"pausada","cancelled":"cancelada"}.get(self._status["phase"],"finalizada")
                self.activity.record("stores.catalog",f"{self.source_name}: revisión del catálogo {phase}",source="automatic",diagnostics={**deepcopy(self._status),"retry_at":self._data["retry_at"]})
            if self._active and self._data["enabled"]:
                from homeassistant.helpers.event import async_call_later
                self._timer=async_call_later(self.hass,max(3600,self._data["retry_at"]-time.time()),self._launch)
