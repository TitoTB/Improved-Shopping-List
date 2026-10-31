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
from .store_links import STORES

MAX_QUANTITY = 1000000
DAY = 86400
DEFAULT_CONFIG = {"unit":"uds", "mode":"manual", "days":7, "refill_quantity":1,
    "reorder_enabled":False, "reorder_at":0, "reorder_percent":0, "list_entity":"", "usage_entity":"",
    "usage_state":"", "usage_amount":1, "configured":False, "config_revision":0,
    "expires_at":0, "expired":False,"meal_rules":[]}


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
    if not isinstance(data, dict) or set(data) - {"reorder_percent","quantity_changed","meal_rules"} != fields:
        raise CatalogError("La configuración de Stock no es válida.")
    if "quantity_changed" in data and type(data["quantity_changed"]) is not bool:
        raise CatalogError("La edición de la cantidad no es válida.")
    result = deepcopy(data)
    result.pop("quantity_changed",None)
    result["reorder_percent"] = quantity_value(data.get("reorder_percent",0))
    if result["reorder_percent"] > 100:
        raise CatalogError("El porcentaje mínimo debe estar entre 0 y 100.")
    for field in ("quantity","refill_quantity","reorder_at","usage_amount"):
        result[field] = quantity_value(data[field],positive=field in ("refill_quantity","usage_amount"))
    if (not isinstance(data["unit"],str) or not data["unit"].strip() or len(data["unit"].strip()) > 32
        or any(ord(char)<32 for char in data["unit"])):
        raise CatalogError("Indica una unidad de hasta 32 caracteres.")
    result["unit"] = data["unit"].strip()
    if data["mode"] not in ("manual","perishable","usage","meals") or type(data["reorder_enabled"]) is not bool:
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
    if 'meal_rules' in data or data['mode']=='meals':
        from .meal_routines import normalize_rules
        result['meal_rules']=normalize_rules(data.get('meal_rules',[]))
        if data['mode']=='meals' and not result['meal_rules']:raise CatalogError("Selecciona al menos una comida para este producto.")
    return result


def remaining_quantity(item, now=None):
    """Estimate a perishable linearly from its last quantity observation to expiry."""
    quantity=item.get("quantity",0)
    if item.get("mode")!="perishable":
        return quantity
    if quantity<=0 or item.get("expired"):
        return 0
    now=time.time() if now is None else now
    end=item.get("expires_at",0)
    if not end:
        return quantity
    start=item.get("quantity_at") or end-item.get("days",7)*DAY
    if end<=now or end<=start:
        return 0
    return round(quantity*max(0,min(1,(end-now)/(end-start))),3)


def materialized_stock(item, now=None):
    now=time.time() if now is None else now
    result=deepcopy(item)
    if item.get("mode")=="perishable":
        result.update(quantity=remaining_quantity(item,now),quantity_at=now)
    return result


def remaining_percentage(item, now=None):
    """Use exactly the same remaining quantity as the UI and mutations."""
    return max(0,min(100,remaining_quantity(item,now)/item.get("refill_quantity",1)*100))


def stock_needs_reorder(item, now=None):
    """Shared low-stock threshold used by automation and dashboard sensors."""
    return item.get("configured") and (item.get("expired") or
        item.get("reorder_enabled") and (
            remaining_percentage(item, now) <= item.get("reorder_percent", 0)
            if item.get("mode") == "perishable" else item["quantity"] <= item["reorder_at"]))


class StockManager:
    def __init__(self, hass, catalog):
        self.hass, self.catalog = hass, catalog
        self._store = Store(hass, 1, f"{DOMAIN}.stock")
        self._items = {}
        self.receipts = {"history":{}, "aliases":{}, "purchases":{}, "coverage":{}}
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
                if type(merged.get("quantity_at",0)) not in (int,float) or not 0 <= merged.get("quantity_at",0) <= 100000000000:
                    raise CatalogError("La fecha de stock no es válida.")
                stock_config({field:merged[field] for field in ("quantity","unit","mode","days","refill_quantity",
                    "reorder_enabled","reorder_at","reorder_percent","list_entity","usage_entity","usage_state","usage_amount","meal_rules")})
        except CatalogError as err:
            raise CatalogError("No se ha podido leer el stock guardado.", "storage_error") from err
        self._items = {key:{**deepcopy(DEFAULT_CONFIG),**deepcopy(item)} for key,item in items.items()}
        receipts = data.get("receipts", {})
        if not isinstance(receipts, dict) or any(not isinstance(receipts.get(key, {}), dict) for key in self.receipts):
            raise CatalogError("No se ha podido leer el historial de compras.", "storage_error")
        self.receipts.update(deepcopy(receipts))

    def _product(self, item):
        products = self.catalog.products
        return next((product for product in products if product["id"] == item.get("catalog_product_id")), None) or next(
            (product for product in products if normalized_name(product["name"]) == normalized_name(item["name"])), None)

    @property
    def receipt_stores(self):
        """Expose confirmed receipt associations without prices or private receipt data."""
        associations = {}
        products = {product["id"] for product in self.catalog.products}

        def associate(store, product_id):
            if store in STORES and product_id in products:
                associations.setdefault(product_id, set()).add(store)

        for key, alias in self.receipts["aliases"].items():
            associate(key.split(":", 1)[0], alias.get("product_id", ""))
        for receipt in self.receipts["history"].values():
            if receipt.get("summary_only") or receipt.get("pending_review"):
                continue
            for line in receipt.get("lines", []):
                associate(receipt.get("store", ""), line.get("product_id", ""))
        return {product_id: sorted(stores) for product_id, stores in associations.items()}

    @property
    def snapshot(self):
        items = []
        now=time.time()
        for item in self._items.values():
            product = self._product(item)
            items.append({**materialized_stock(item,now), "name":product["name"] if product else item["name"],
                "catalog_product_id":product["id"] if product else ""})
        return {"items":sorted(items, key=lambda item: normalized_name(item["name"])), "receipt_stores":self.receipt_stores}

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

    async def _persist(self, items, *, receipts=None):
        receipt_data = self.receipts if receipts is None else receipts
        await self._store.async_save({"items":items, "receipts":receipt_data})
        self._items = items
        self.receipts = receipt_data
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
        current=materialized_stock(current) if current else None
        before = current["quantity"] if current else 0
        quantity = quantity_value(round(max(0, before + delta),3))
        if quantity > MAX_QUANTITY:
            raise CatalogError("Se ha alcanzado el máximo de unidades del producto.")
        if delta < 0 and before == 0:
            return {**deepcopy(current or {}), "name":name, "quantity":0}
        item = {**deepcopy(current or DEFAULT_CONFIG), "id":current["id"] if current else str(uuid4()), "name":product["name"] if product else current["name"] if current else name,
            "catalog_product_id":product_id, "quantity":quantity, "revision":current["revision"]+1 if current else 1}
        receipts=deepcopy(self.receipts)
        if delta>0:receipts["coverage"].pop("awaiting:"+item["id"],None)
        await self._persist({**deepcopy(self._items), item["id"]:item},receipts=receipts)
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
            quantity_changed=data.get("quantity_changed",current["quantity"]!=config["quantity"])
            item = {**materialized_stock(current), **config, "configured":True,
                "config_revision":current.get("config_revision",0)+1, "revision":revision+1}
            if config['mode']=='meals' and (current['mode']!='meals' or item.get('meal_rules')!=current.get('meal_rules')):item['meal_config_at']=time.time()
            if not quantity_changed:
                item["quantity"]=remaining_quantity(current)
            item["quantity_at"]=time.time()
            if config["mode"] != "perishable":
                item.update(expires_at=0,expired=False)
            elif (current.get("mode") != "perishable" or current.get("days") != config["days"]
                or quantity_changed):
                item.update(expires_at=time.time()+config["days"]*DAY,expired=False)
            if ((current.get("mode") == "perishable") != (config["mode"] == "perishable")
                or config["mode"] == "perishable" and current.get("days") != config["days"]):
                product = self._product(current) or {}
                item["recurrence_updated_at"] = max(time.time(), self.recurrence_stamp(current), product.get("recurrence_updated_at",0))+0.000001
            receipts=deepcopy(self.receipts)
            if quantity_changed and item["quantity"]>remaining_quantity(current):receipts["coverage"].pop("awaiting:"+item_id,None)
            await self._persist({**deepcopy(self._items), item_id:item},receipts=receipts)
            if self.activity:
                self.activity.record("stock.configured",f'{item["name"]}: configuración de Stock guardada',source="manual",product=item["name"])
            return deepcopy(item)

    def replenishment_config(self, product, payload):
        """Validate catalog edits without accepting or changing stock quantities."""
        if not isinstance(product,dict) or not isinstance(product.get("name"),str):
            raise CatalogError("Indica el nombre del producto.")
        fields={"unit","mode","days","refill_quantity","reorder_enabled","reorder_at","reorder_percent",
                "list_entity","usage_entity","usage_state","usage_amount"}
        if not isinstance(payload,dict) or set(payload)!={"config_revision","config"} or not isinstance(payload["config"],dict) or set(payload["config"])-{'meal_rules'}!=fields:
            raise CatalogError("La configuración de reposición no es válida.")
        current=self.item_for(product)
        if type(payload["config_revision"]) is not int or payload["config_revision"]!=(current or {}).get("config_revision",0):
            raise CatalogError("La reposición ha cambiado en Stock. Cierra y vuelve a abrir la ficha.","conflict")
        return stock_config({**payload["config"],"quantity":(current or {}).get("quantity",0),"quantity_changed":False})

    async def async_save_replenishment(self, product, payload):
        async with self._lock:
            config=self.replenishment_config(product,payload)
            current=self.item_for(product)
            if not current and config["mode"]=="manual":return
            now=time.time()
            item={**deepcopy(current or DEFAULT_CONFIG),**config,"id":current["id"] if current else str(uuid4()),
                  "name":product["name"],"catalog_product_id":product["id"],"configured":True,
                  "revision":(current or {}).get("revision",0)+1,"config_revision":(current or {}).get("config_revision",0)+1,
                  "quantity_at":now,"recurrence_updated_at":max(now,self.recurrence_stamp(current),product.get("recurrence_updated_at",0))+0.000001}
            if config['mode']=='meals' and (not current or current['mode']!='meals' or item.get('meal_rules')!=current.get('meal_rules')):item['meal_config_at']=now
            if config["mode"]!="perishable":item.update(expires_at=0,expired=False)
            elif not current or current["mode"]!="perishable" or current["days"]!=config["days"]:
                item.update(expires_at=now+config["days"]*DAY,expired=False)
            await self._persist({**deepcopy(self._items),item["id"]:item})
            if self.activity:self.activity.record("stock.configured",f'{product["name"]}: reposición guardada desde el catálogo',source="manual",product=product["name"])

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

    async def async_automatic(self, item_id, config_revision, action, event=None):
        """Completion only waits for a receipt; usage/expiry can change quantities."""
        if action not in ("completion","usage","expire"):return None
        async with self._lock:
            current = self._items.get(item_id)
            if not current or current.get("config_revision") != config_revision:return None
            if action=="completion":
                # Persist only a reorder guard: quantities and expiry remain untouched.
                at=(event or {}).get("at",time.time())
                if not current.get("configured") or not stock_needs_reorder(current,at):return deepcopy(current)
                if any(p.get("item_id")==item_id and p.get("receipt_id") and self.receipts["history"].get(p["receipt_id"],{}).get("imported_at",0)>=at
                       for p in self.receipts["purchases"].values()):return deepcopy(current)
                key="awaiting:"+item_id
                if key not in self.receipts["coverage"]:
                    receipts=deepcopy(self.receipts);receipts["coverage"][key]={"item_id":item_id,"at":at}
                    await self._persist(deepcopy(self._items),receipts=receipts)
                return deepcopy(current)
            if not current.get("configured") or not self.recurrence_ready(current):
                return None
            item = materialized_stock(current)
            receipts = deepcopy(self.receipts)
            before = item["quantity"]
            if action == "usage" and item["mode"] == "usage":
                item["quantity"] = quantity_value(round(max(0,before-item["usage_amount"]),3))
            elif action == "expire" and item["mode"] == "perishable" and item.get("expires_at",0) and time.time() >= item["expires_at"]:
                item.update(quantity=0,expires_at=0,expired=True)
            else:
                return None
            if item == current and receipts == self.receipts:
                return deepcopy(item)
            item["revision"] += 1
            await self._persist({**deepcopy(self._items), item_id:item}, receipts=receipts)
            if self.activity:
                verb = {"usage":"Consumo registrado", "expire":"Caducidad alcanzada"}[action]
                self.activity.record(f"stock.{action}",f'{verb}: {item["name"]} · {item["quantity"]} {item["unit"]}',
                    source="automatic", product=item["name"],quantity=item["quantity"],delta=round(item["quantity"]-before,3))
            return deepcopy(item)

    async def async_meals(self,item_id,config_revision,events):
        """Persist stock and event ledger together: restarts cannot repeat a meal."""
        async with self._lock:
            current=self._items.get(item_id)
            if not current or current['mode']!='meals' or current.get('config_revision')!=config_revision or not self.recurrence_ready(current):return
            receipts=deepcopy(self.receipts);ledger=receipts.setdefault('meal_events',{});now=time.time()
            fresh=[e for e in events if e['key'] not in ledger]
            if not fresh:return
            item=deepcopy(current);before=item['quantity']
            item['quantity']=quantity_value(round(max(0,before-sum(e['amount'] for e in fresh)),3));item['revision']+=1
            for event in fresh:ledger[event['key']]={'at':event['at'],'item_id':item_id,'amount':event['amount']}
            receipts['meal_events']={key:value for key,value in ledger.items() if value.get('at',0)>now-32*DAY}
            await self._persist({**deepcopy(self._items),item_id:item},receipts=receipts)
            if self.activity:
                self.activity.record('stock.meal',f'Consumo por comidas: {item["name"]} · {before-item["quantity"]:g} {item["unit"]}',source='automatic',
                    product=item['name'],quantity=item['quantity'],delta=round(item['quantity']-before,3),diagnostics={'comidas':fresh})
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
            receipts=deepcopy(self.receipts);receipts["coverage"].pop("awaiting:"+item_id,None)
            await self._persist(items,receipts=receipts)
            if self.activity:
                self.activity.record("stock.remove", f'{current["name"]}: eliminado de Stock', source="manual", product=current["name"])
