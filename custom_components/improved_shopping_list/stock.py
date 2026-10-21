"""Shared pantry quantities, independent of shopping-list providers."""

from asyncio import Lock
from copy import deepcopy
from decimal import Decimal, InvalidOperation
import re
import time
from uuid import uuid4

from homeassistant.core import callback
from homeassistant.helpers.storage import Store

from .catalog import CatalogError, normalized_name
from .const import DOMAIN

MAX_QUANTITY = 1000000
DAY = 86400
DEFAULT_CONFIG = {"unit":"uds", "mode":"manual", "days":7, "refill_quantity":1,
    "reorder_enabled":False, "reorder_at":0, "reorder_percent":0, "list_entity":"", "usage_entity":"",
    "usage_state":"", "usage_amount":1, "configured":False, "config_revision":0,
    "expires_at":0, "expired":False}


def quantity_value(value, *, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int,float)):
        raise CatalogError("Introduce una cantidad numérica válida.")
    try:
        number = Decimal(str(value))
        if (not number.is_finite() or not (0 < number if positive else 0 <= number)
            or number > MAX_QUANTITY or number != number.quantize(Decimal("0.001"))):
            raise InvalidOperation
        return int(number) if number == number.to_integral_value() else float(number)
    except InvalidOperation:
        raise CatalogError("La cantidad debe estar entre 0 y 1000000, con un máximo de tres decimales.") from None


def stock_config(data):
    fields = {"quantity","unit","mode","days","refill_quantity","reorder_enabled","reorder_at",
        "list_entity","usage_entity","usage_state","usage_amount"}
    if not isinstance(data, dict) or set(data) - {"reorder_percent"} != fields:
        raise CatalogError("La configuración de Stock no es válida.")
    result = deepcopy(data)
    result["reorder_percent"] = quantity_value(data.get("reorder_percent",0))
    if result["reorder_percent"] > 100:
        raise CatalogError("El porcentaje mínimo debe estar entre 0 y 100.")
    for field in ("quantity","refill_quantity","reorder_at","usage_amount"):
        result[field] = quantity_value(data[field],positive=field in ("refill_quantity","usage_amount"))
    if (not isinstance(data["unit"],str) or not data["unit"].strip() or len(data["unit"].strip()) > 32
        or any(ord(char)<32 for char in data["unit"])):
        raise CatalogError("Indica una unidad de hasta 32 caracteres.")
    result["unit"] = data["unit"].strip()
    if data["mode"] not in ("manual","perishable","usage") or type(data["reorder_enabled"]) is not bool:
        raise CatalogError("Selecciona un tipo de control de stock válido.")
    if type(data["days"]) is not int or not 1 <= data["days"] <= 3650:
        raise CatalogError("Indica entre 1 y 3650 días.")
    for field in ("list_entity","usage_entity"):
        if not isinstance(data[field],str) or data[field] and not re.fullmatch(r"[a-z_][a-z0-9_]*\.[a-z0-9_]+",data[field]):
            raise CatalogError("Selecciona una entidad válida.")
    if data["list_entity"] and not data["list_entity"].startswith("todo."):
        raise CatalogError("La lista de reposición debe ser una entidad todo.")
    if not isinstance(data["usage_state"],str) or len(data["usage_state"])>255 or any(ord(c)<32 for c in data["usage_state"]):
        raise CatalogError("El estado de consumo no es válido.")
    if data["mode"] == "usage" and (not data["usage_entity"] or not data["usage_state"].strip()
        or data["usage_state"] in ("unknown","unavailable")):
        raise CatalogError("Selecciona la entidad y el estado que representa cada uso.")
    return result


def remaining_percentage(item, now=None):
    """Remaining shelf life; an empty or expired product always has zero stock."""
    if item.get("quantity",0) <= 0 or item.get("expired"):
        return 0
    if not item.get("expires_at"):
        return 100
    remaining = item["expires_at"] - (time.time() if now is None else now)
    return max(0,min(100,remaining / (item["days"]*DAY) * 100))


class StockManager:
    def __init__(self, hass, catalog):
        self.hass, self.catalog = hass, catalog
        self._store = Store(hass, 1, f"{DOMAIN}.stock")
        self._items = {}
        self._lock = Lock()
        self._listeners = set()
        self.activity = None
        self._stop_catalog = None
        self.recurrence_coordinated = False
        catalog.recurrence_peer = lambda product: self.recurrence_stamp(self.item_for(product))

    def item_for(self, product):
        return next((item for item in self.snapshot["items"] if item["catalog_product_id"] == product.get("id")
            or normalized_name(item["name"]) == normalized_name(product["name"])), None)

    @staticmethod
    def recurrence_stamp(item):
        if not item:
            return 0
        if "recurrence_updated_at" in item:
            return item["recurrence_updated_at"]
        return max(1,item.get("expires_at",0)-item.get("days",7)*DAY) if item.get("mode") == "perishable" else 0

    def recurrence_ready(self, item):
        if not self.recurrence_coordinated or not (product := self._product(item)):
            return True
        recurrence = product.get("recurrence", {"enabled":False,"days":7})
        return (recurrence["enabled"] == (item.get("mode") == "perishable")
            and (not recurrence["enabled"] or recurrence["days"] == item["days"])
            and self.recurrence_stamp(item) == product.get("recurrence_updated_at",0))

    async def async_load(self):
        data = await self._store.async_load()
        if data is None:
            return
        items = data.get("items") if isinstance(data, dict) else None
        if not isinstance(items, dict) or any(not isinstance(item, dict) or item.get("id") != key
            or not isinstance(item.get("name"), str) or not item["name"] or len(item["name"]) > 255
            or not isinstance(item.get("catalog_product_id", ""), str)
            or type(item.get("quantity")) not in (int,float) or not 0 <= item["quantity"] <= MAX_QUANTITY
            or type(item.get("revision")) is not int or item["revision"] < 1 for key,item in items.items()):
            raise CatalogError("No se ha podido leer el stock guardado.", "storage_error")
        try:
            for item in items.values():
                merged = {**DEFAULT_CONFIG, **item}
                stock_config({field:merged[field] for field in ("quantity","unit","mode","days","refill_quantity",
                    "reorder_enabled","reorder_at","reorder_percent","list_entity","usage_entity","usage_state","usage_amount")})
        except CatalogError as err:
            raise CatalogError("No se ha podido leer el stock guardado.", "storage_error") from err
        self._items = {key:{**deepcopy(DEFAULT_CONFIG),**deepcopy(item)} for key,item in items.items()}

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
        quantity = quantity_value(round(max(0, before + delta),3))
        if quantity > MAX_QUANTITY:
            raise CatalogError("Se ha alcanzado el máximo de unidades del producto.")
        if delta < 0 and before == 0:
            return {**deepcopy(current or {}), "name":name, "quantity":0}
        item = {**deepcopy(current or DEFAULT_CONFIG), "id":current["id"] if current else str(uuid4()), "name":product["name"] if product else current["name"] if current else name,
            "catalog_product_id":product_id, "quantity":quantity, "revision":current["revision"]+1 if current else 1}
        await self._persist({**deepcopy(self._items), item["id"]:item})
        if self.activity:
            self.activity.record("stock.change", f'{item["name"]}: {quantity} {item["unit"]} en stock', source=source,
                product=item["name"], quantity=quantity, delta=quantity-before, **({"reader":reader} if reader else {}))
        return deepcopy(item)

    async def async_save(self, item_id, revision, data):
        config = stock_config(data)
        async with self._lock:
            current = self._items.get(item_id)
            if current is None or type(revision) is not int or current["revision"] != revision:
                raise CatalogError("El stock ha cambiado. Cierra y vuelve a abrir la ficha para actualizarla.", "conflict")
            item = {**deepcopy(current), **config, "configured":True,
                "config_revision":current.get("config_revision",0)+1, "revision":revision+1}
            if config["mode"] != "perishable":
                item.update(expires_at=0,expired=False)
            elif (current.get("mode") != "perishable" or current.get("days") != config["days"]
                or current["quantity"] != config["quantity"]):
                item.update(expires_at=time.time()+config["days"]*DAY,expired=False)
            if ((current.get("mode") == "perishable") != (config["mode"] == "perishable")
                or config["mode"] == "perishable" and current.get("days") != config["days"]):
                product = self._product(current) or {}
                item["recurrence_updated_at"] = max(time.time(), self.recurrence_stamp(current), product.get("recurrence_updated_at",0))+0.000001
            await self._persist({**deepcopy(self._items), item_id:item})
            if self.activity:
                self.activity.record("stock.configured",f'{item["name"]}: configuración de Stock guardada',source="manual",product=item["name"])
            return deepcopy(item)

    async def async_sync_recurrence(self, product, stamp, due):
        """Keep one perishable timer, retaining quantities, units and refill preferences."""
        async with self._lock:
            current = self.item_for(product)
            latest = next((entry for entry in self.catalog.products if entry["id"] == product["id"]),None)
            if latest is None or latest["revision"] != product["revision"] or self.recurrence_stamp(current) > stamp:
                return  # A newer edit will be reconciled on the next notification.
            recurrence = product.get("recurrence", {"enabled":False,"days":7})
            if not current and not recurrence["enabled"]:
                return
            if (current and current.get("recurrence_updated_at",0) == stamp
                and (current.get("mode") == "perishable") == recurrence["enabled"]
                and (not recurrence["enabled"] or current.get("days") == recurrence["days"])):
                return
            item = {**deepcopy(current or DEFAULT_CONFIG), "id":current["id"] if current else str(uuid4()),
                "name":product["name"], "catalog_product_id":product["id"], "quantity":current["quantity"] if current else 0,
                "revision":current["revision"]+1 if current else 1, "recurrence_updated_at":stamp,
                "config_revision":(current or {}).get("config_revision",0)+1, "days":recurrence["days"]}
            if recurrence["enabled"]:
                item.update(mode="perishable",configured=True,expires_at=due,expired=bool(current and current.get("expired") and not due))
            elif item["mode"] == "perishable":
                item.update(mode="manual",expires_at=0,expired=False)
            await self._persist({**deepcopy(self._items),item["id"]:item})

    async def async_automatic(self, item_id, config_revision, action):
        """Apply observed usage, a purchase, or expiry atomically against current settings."""
        async with self._lock:
            current = self._items.get(item_id)
            if not current or not current.get("configured") or current.get("config_revision") != config_revision or not self.recurrence_ready(current):
                return None
            item = deepcopy(current)
            before = item["quantity"]
            if action == "purchase":
                item["quantity"] = quantity_value(round(before+item["refill_quantity"],3))
                if item["mode"] == "perishable":
                    item.update(expires_at=time.time()+item["days"]*DAY,expired=False)
            elif action == "usage" and item["mode"] == "usage":
                item["quantity"] = quantity_value(round(max(0,before-item["usage_amount"]),3))
            elif action == "expire" and item["mode"] == "perishable" and item.get("expires_at",0) and time.time() >= item["expires_at"]:
                item.update(quantity=0,expires_at=0,expired=True)
            else:
                return None
            if item == current:
                return deepcopy(item)
            item["revision"] += 1
            await self._persist({**deepcopy(self._items), item_id:item})
            if self.activity:
                verb = {"purchase":"Reposición por compra", "usage":"Consumo registrado", "expire":"Caducidad alcanzada"}[action]
                self.activity.record(f"stock.{action}",f'{verb}: {item["name"]} · {item["quantity"]} {item["unit"]}',
                    source="automatic", product=item["name"],quantity=item["quantity"],delta=round(item["quantity"]-before,3))
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
            product = self._product(current)
            if self.recurrence_coordinated and product and product.get("recurrence",{}).get("enabled"):
                stamp = max(time.time(),self.recurrence_stamp(current),product.get("recurrence_updated_at",0))+0.000001
                await self.catalog.async_sync_recurrence(product["id"],product["revision"],
                    {"enabled":False,"days":product["recurrence"]["days"]},stamp,0)
            items = deepcopy(self._items); del items[item_id]
            await self._persist(items)
            if self.activity:
                self.activity.record("stock.remove", f'{current["name"]}: eliminado de Stock', source="manual", product=current["name"])
