"""Local, push-based summaries shared by Home Assistant entities."""

from datetime import timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from homeassistant.components.todo import DATA_COMPONENT, serialize_todo_item
from homeassistant.core import callback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .catalog import normalized_name
from .stock import stock_needs_reorder
from .store_links import STORES
from .todo_names import named_item


class EntityData:
    """Observe existing managers and the primary todo provider without HTTP reads."""

    def __init__(self, hass, managers):
        self.hass, self.managers = hass, managers
        self._listeners, self._stops = set(), []
        self._list = None
        self._active = False
        self.pending = None
        self.estimate = None
        self.last_purchase = None
        self.low_stock = []

    @property
    def settings(self):
        return self.managers["settings"].snapshot

    @property
    def active(self):
        return self._active

    @callback
    def subscribe(self, listener):
        self._listeners.add(listener)
        return lambda: self._listeners.discard(listener)

    @callback
    def start(self):
        if self._active:
            return
        self._active = True
        self._stops = [self.managers[key].subscribe(self._changed) for key in
            ("settings", "catalog", "stock", "readers", "price_manager", "community_sync", "quantities")]
        self._stops += [self.hass.bus.async_listen("state_changed", self._state_changed),
            async_track_time_interval(self.hass, self._changed, timedelta(minutes=1))]
        self._changed()

    @callback
    def stop(self):
        self._active = False
        for stop in self._stops:
            stop()
        self._stops = []
        if self._list:
            self._list[2]()
            self._list = None
        self.pending = self.estimate = self.last_purchase = None

    @callback
    def _state_changed(self, event):
        if event.data.get("entity_id") == self.settings["primary_entity"]:
            self._changed()

    @callback
    def _changed(self, *_args):
        if not self._active:
            return
        target = self.settings["primary_entity"]
        component = self.hass.data.get(DATA_COMPONENT)
        entity = component.get_entity(target) if component and target else None
        if self._list and (self._list[0] != target or self._list[1] is not entity):
            self._list[2]()
            self._list = None
        if entity is not None and self._list is None:
            self._list = (target, entity, entity.async_subscribe_updates(self._items_changed))
        self._refresh(entity.todo_items if entity is not None else None)

    @callback
    def _items_changed(self, items):
        if self._active:
            self._refresh(items)

    def _refresh(self, items):
        target = self.settings["primary_entity"]
        state = self.hass.states.get(target) if target else None
        serialized = [named_item(self.settings, target, serialize_todo_item(item)) for item in items] if items is not None else None
        self.pending = ([] if not target else None) if serialized is None else [item
            for item in serialized if item.get("status") == "needs_action"]
        if target and (state is None or state.state in ("unknown", "unavailable")):
            self.pending = None
        self.estimate = self._estimate()
        self.last_purchase = self._last_purchase()
        self.low_stock = [item for item in self.managers["stock"].snapshot["items"] if stock_needs_reorder(item)]
        for listener in tuple(self._listeners):
            listener()

    def _estimate(self):
        if self.pending is None or not self.settings["price_updates_enabled"]:
            return None
        products = {normalized_name(product["name"]): product for product in self.managers["catalog"].products}
        offers = {}
        for item in self.pending:
            product = products.get(normalized_name(item.get("summary") or ""))
            if product and product["id"] not in offers:
                offers[product["id"]] = self.managers["price_manager"].prices_for(product)
        stores = []
        for store, config in self.settings["stores"].items():
            if not config.get("enabled") or store not in STORES:
                continue
            cents = coverage = 0
            for item in self.pending:
                product = products.get(normalized_name(item.get("summary") or ""))
                candidates=[offer for offer in offers.get(product["id"],[]) if offer.get("store")==store and offer.get("currency","EUR")=="EUR"] if product else []
                quantity=self.managers["quantities"].value(self.settings["primary_entity"],item,product) if product else None
                from .product_references import package_cost
                def cost(offer):
                    try:
                        price=Decimal(str(offer["price"]))
                        if not price.is_finite() or price<0:return None
                        converted=package_cost({**offer,"price":float(price)},quantity["quantity"],quantity.get("unit",product.get("purchase_unit","uds")))
                        if converted is not None:return Decimal(str(converted))
                        if offer.get("format_pending") or offer.get("pack_quantity"):return None
                        return price*Decimal(str(quantity["quantity"]))/Decimal(str(quantity["unit_quantity"]))
                    except (KeyError,InvalidOperation,ValueError,TypeError):
                        return None
                candidates=[(offer,cost(offer)) for offer in candidates]
                candidates=[(offer,value) for offer,value in candidates if value is not None]
                offer,value=min(candidates,key=lambda pair:pair[1]) if candidates else (None,None)
                if not offer or offer.get("currency", "EUR") != "EUR":
                    continue
                try:
                    price = Decimal(str(offer["price"]))
                    if not price.is_finite() or price < 0:
                        continue
                    cents += int((Decimal(str(value))*100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
                except (KeyError, InvalidOperation, ValueError):
                    continue
                coverage += 1
            if coverage:
                stores.append({"store": store, "store_name": STORES[store], "priced_products": coverage,
                    "total_products": len(self.pending), "unpriced_products": len(self.pending)-coverage,
                    "cents": cents, "list_entity": self.settings["primary_entity"]})
        return min(stores, key=lambda item: (-item["priced_products"], item["cents"], item["store_name"])) if stores else {
            "store": None, "store_name": None, "priced_products": 0, "total_products": len(self.pending),
            "unpriced_products": len(self.pending), "cents": 0, "list_entity": self.settings["primary_entity"]}

    def _last_purchase(self):
        # Only summarize receipt metadata; never copy or expose whole ticket lines.
        receipts = self.managers["stock"].receipts["history"].values()
        dated = []
        for receipt in receipts:
            date = dt_util.parse_datetime(receipt["purchased_at"])
            if date is not None:
                if date.tzinfo is None:
                    date = date.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
                dated.append({key: receipt.get(key) for key in ("id", "total", "store", "store_name", "currency")}
                    | {"date": dt_util.as_utc(date)})
        return max(dated, key=lambda receipt: receipt["date"]) if dated else None

