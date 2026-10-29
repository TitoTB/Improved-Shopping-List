"""Receipt prices plus opt-in Alcampo and DIA observations; no community prices."""

from copy import deepcopy
import time

from homeassistant.helpers.storage import Store

from .const import DOMAIN

# Kept for older imports; there is no request queue or network scheduler.
INTERVAL = 300


class PriceManager:
    def __init__(self,hass,catalog,settings,activity):
        self.hass,self.catalog,self.settings,self.activity=hass,catalog,settings,activity
        self._store=Store(hass,1,f"{DOMAIN}.prices")
        self._data={"offers":{},"legacy_ean":{},"attempts":{},"pending":[],"errors":{},"total":0,"processed":0}
        self._active=False
        self._preparing=0
        self._listeners=set()
        self._settings_stop=None

    async def async_load(self):
        # Cancel durable public-provider jobs left by earlier integration versions.
        saved=await self._store.async_load()
        if saved and (saved.get("pending") or saved.get("offers") or saved.get("legacy_ean")):
            await self._store.async_save(deepcopy(self._data))

    def start(self):
        if self._active:
            return
        self._active=True
        if hasattr(self.settings,"subscribe"):
            self._settings_stop=self.settings.subscribe(self._notify)

    async def async_stop(self):
        self._active=False
        if self._settings_stop:
            self._settings_stop();self._settings_stop=None

    @property
    def prices_enabled(self):
        return self.settings.snapshot.get("price_updates_enabled",True)

    def scope(self,store):
        config=self.settings.snapshot["stores"].get(store,{})
        if store in ("consum","lasirena","eroski","dia"):
            return f"{config['postal_code']}:{config['area_id']}" if config.get("postal_code") and config.get("area_id") else ""
        return config.get("warehouse","") if store=="mercadona" else config.get("region_id","") if store=="alcampo" else config.get("sale_point","005290")

    def prices_for(self,product):
        if not self.prices_enabled:
            return []
        receipts=getattr(self,"receipts",None)
        offers = [deepcopy(price) for price in receipts.offers_for(product) if price.get("source")=="receipt"] if receipts else []
        from .product_references import format_observation
        for ref in product.get("commercial_references", []):
            if ref.get("active") is not False and ref.get("last_price"):
                offers.append(format_observation(product,ref["store"],{**ref["last_price"],"store":ref["store"],
                    **({"ticket_reference_id":ref["ticket_reference_id"]} if ref.get("ticket_reference_id") else {}),
                    "reference_id":ref["reference_id"],"ean":ref["ean"],"name":ref["name"],"store_name":ref["name"],
                    "url":ref["url"],"source":"web"}))
        for store, attribute in (("alcampo", "alcampo"), ("dia", "dia_prices")):
            manager = getattr(self, attribute, None)
            offer = manager.offer_for(product) if manager else None
            if offer:
                from .product_references import format_observation
                offers.append(format_observation(product,store,offer))
        latest={}
        for price in offers:
            key=(price["store"],price.get("commercial_reference_id") or price.get("reference_id") or price.get("ean") or "legacy")
            if key not in latest or price.get("checked_at",0)>latest[key].get("checked_at",0):
                latest[key]=price
        return [{**price,"catalog_product_id":product["id"]} for price in latest.values()]

    def snapshot(self,store=None):
        return {"products":[price for product in self.catalog.products for price in self.prices_for(product) if store is None or price["store"]==store],
            "nightly":False,"update_time":self.settings.snapshot.get("price_update_time","01:00"),
            "sale_point":self.scope(store) if store=="carrefour" else None,"enabled":True,"warehouse":self.scope(store) if store else "",
            "error":"","remaining":0,"processed":0,"total":0,"next_request":None,"retry_at":0,
            "automatic_refresh_blocked":False,"running":False,"not_found":0}

    @property
    def progress(self):
        receipts=getattr(self,"receipts",None)
        latest=max((offer.get("checked_at",0) for product in self.catalog.products for offer in receipts.offers_for(product)),default=0) if receipts else 0
        return {"running":False,"total":0,"processed":0,"errors":{},"batch_id":None,"finished_at":None,
            "log_pending":False,"last_updated":latest,"started_at":time.time(),"phase":"processed","estimated_seconds":0}

    def subscribe(self,listener):
        self._listeners.add(listener)
        return lambda:self._listeners.discard(listener)

    def _notify(self,*_args):
        for listener in tuple(self._listeners):
            listener()

    async def async_refresh_all(self):
        self._notify()
        return {"queued":0,"errors":[],"running":False,"total":0,"processed":0}

    async def async_refresh_store(self,store):
        return await self.async_refresh_all()

    async def async_tick(self):
        # Compatibility for pending callbacks on reload: never contact a provider.
        return

    async def async_apply_revocations(self,_revoked):
        return


class StorePriceView:
    def __init__(self,manager,store):
        self.manager,self.store=manager,store

    def snapshot(self):
        return self.manager.snapshot(self.store)

    @property
    def progress(self):
        return {**self.manager.progress,"warehouse":self.manager.scope(self.store)}

    def subscribe(self,callback):
        return self.manager.subscribe(callback)

    async def async_refresh(self,force=False):
        return self.snapshot()
