"""Shared pantry quantities, independent of shopping-list providers."""

from asyncio import Lock
from copy import deepcopy
from uuid import uuid4

from homeassistant.core import callback
from homeassistant.helpers.storage import Store

from .catalog import CatalogError, normalized_name
from .const import DOMAIN

MAX_QUANTITY = 1000000


class StockManager:
    def __init__(self, hass, catalog):
        self.hass, self.catalog = hass, catalog
        self._store = Store(hass, 1, f"{DOMAIN}.stock")
        self._items = {}
        self._lock = Lock()
        self._listeners = set()
        self.activity = None
        self._stop_catalog = None

    async def async_load(self):
        data = await self._store.async_load()
        if data is None:
            return
        items = data.get("items") if isinstance(data, dict) else None
        if not isinstance(items, dict) or any(not isinstance(item, dict) or item.get("id") != key
            or not isinstance(item.get("name"), str) or not item["name"] or len(item["name"]) > 255
            or not isinstance(item.get("catalog_product_id", ""), str)
            or type(item.get("quantity")) is not int or not 0 <= item["quantity"] <= MAX_QUANTITY
            or type(item.get("revision")) is not int or item["revision"] < 1 for key,item in items.items()):
            raise CatalogError("No se ha podido leer el stock guardado.", "storage_error")
        self._items = deepcopy(items)

    def _product(self, item):
        products = self.catalog.products
        return next((product for product in products if product["id"] == item.get("catalog_product_id")), None) or next(
            (product for product in products if normalized_name(product["name"]) == normalized_name(item["name"])), None)

    @property
    def snapshot(self):
        items = []
        for item in self._items.values():
            product = self._product(item)
            items.append({**deepcopy(item), "name":product["name"] if product else item["name"],
                "catalog_product_id":product["id"] if product else ""})
        return {"items":sorted(items, key=lambda item: normalized_name(item["name"]))}

    @callback
    def start(self):
        if not self._stop_catalog:
            self._stop_catalog = self.catalog.subscribe(self._notify)

    @callback
    def stop(self):
        if self._stop_catalog:
            self._stop_catalog(); self._stop_catalog = None

    @callback
    def subscribe(self, listener):
        self._listeners.add(listener)
        return lambda: self._listeners.discard(listener)

    @callback
    def _notify(self):
        for listener in tuple(self._listeners):
            listener()

    async def _persist(self, items):
        await self._store.async_save({"items":items})
        self._items = items
        self._notify()

    async def async_add(self, name, *, source="manual"):
        if not isinstance(name, str) or not name.strip() or len(name.strip()) > 255 or any(ord(char) < 32 for char in name):
            raise CatalogError("Introduce un nombre de producto válido de hasta 255 caracteres.")
        name = name.strip()
        async with self._lock:
            product = next((product for product in self.catalog.products if normalized_name(product["name"]) == normalized_name(name)), None)
            return await self._change(name, product, 1, source=source)

    async def async_change_product(self, product, delta, *, reader="", guard=None):
        if type(delta) is not int or delta not in (-1,1):
            raise CatalogError("El cambio de stock debe ser una unidad.")
        async with self._lock:
            if guard is not None and not guard():
                raise CatalogError("La configuración del lector o producto ha cambiado.")
            return await self._change(product["name"], product, delta, source="reader", reader=reader)

    async def _change(self, name, product, delta, *, source, reader="", item_id=None):
        product_id = product["id"] if product else ""
        current = self._items.get(item_id) if item_id else next((item for item in self._items.values()
            if product_id and item.get("catalog_product_id") == product_id
            or normalized_name((self._product(item) or item)["name"]) == normalized_name(name)), None)
        before = current["quantity"] if current else 0
        quantity = max(0, before + delta)
        if quantity > MAX_QUANTITY:
            raise CatalogError("Se ha alcanzado el máximo de unidades del producto.")
        if delta < 0 and before == 0:
            return {**deepcopy(current or {}), "name":name, "quantity":0}
        item = {"id":current["id"] if current else str(uuid4()), "name":product["name"] if product else current["name"] if current else name,
            "catalog_product_id":product_id, "quantity":quantity, "revision":current["revision"]+1 if current else 1}
        await self._persist({**deepcopy(self._items), item["id"]:item})
        if self.activity:
            self.activity.record("stock.change", f'{item["name"]}: {quantity} unidades en stock', source=source,
                product=item["name"], quantity=quantity, delta=quantity-before, **({"reader":reader} if reader else {}))
        return deepcopy(item)

    async def async_adjust(self, item_id, delta):
        if type(delta) is not int or delta not in (-1,1):
            raise CatalogError("El cambio de stock debe ser una unidad.")
        async with self._lock:
            current = self._items.get(item_id)
            if current is None:
                raise CatalogError("El producto ya no está en Stock.", "not_found")
            return await self._change(current["name"], self._product(current), delta, source="manual", item_id=item_id)

    async def async_remove(self, item_id, revision):
        if type(revision) is not int or revision < 1:
            raise CatalogError("La revisión del producto no es válida.")
        async with self._lock:
            current = self._items.get(item_id)
            if current is None or current["revision"] != revision:
                raise CatalogError("El stock del producto ha cambiado. Revisa la cantidad antes de eliminarlo.", "conflict")
            items = deepcopy(self._items); del items[item_id]
            await self._persist(items)
            if self.activity:
                self.activity.record("stock.remove", f'{current["name"]}: eliminado de Stock', source="manual", product=current["name"])
