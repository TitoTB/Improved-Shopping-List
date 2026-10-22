"""Local shared product catalog, independent of any to-do list provider."""

from asyncio import Lock
from collections import Counter
from copy import deepcopy
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
import re
from typing import Any
from unicodedata import category as unicode_category, normalize
from urllib.parse import urlsplit
from uuid import uuid4

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.storage import Store

from .const import DOMAIN
from .product_translation import async_translate_name
from .store_links import normalize_links
from .community_data import fingerprint
from .quantity_values import DEFAULT_PURCHASE, normalize_purchase

STORAGE_KEY = f"{DOMAIN}.catalog"
FIELDS = {
    "id", "revision", "name", "category", "tags", "barcode",
    "price", "currency", "image_url", "icon", "notes",
    "barcodes", "nfc_tags", "reader_actions", "recurrence", "store_links",
    "purchase_unit", "unit_quantity", "quantity_step",
}
READER_ACTIONS = {"none", "add_list", "stock_remove", "stock_add"}
LEGACY_PRODUCT_FIELDS = {"brand", "format"}


def code_key(kind: str, code: str) -> str:
    code = code.strip()
    if kind == "nfc":
        if re.fullmatch(r"[0-9a-fA-F:-]+", code):
            return code.replace(":", "").replace("-", "").lower()
        return code.casefold()
    return code


def product_codes(product: dict, kind: str) -> list[str]:
    return ([product.get("barcode", "")] + product.get("barcodes", [])) if kind == "barcode" else product.get("nfc_tags", [])


def _codes(data: dict, field: str, kind: str) -> list[str]:
    values = data.get(field, [])
    if not isinstance(values, list) or len(values) > 50:
        raise CatalogError("Puedes asignar hasta 50 códigos de cada tipo.")
    result = {}
    for value in values:
        if not isinstance(value, str) or not value.strip() or len(value) > 1024 or any(ord(char) < 32 for char in value):
            raise CatalogError("Cada código debe ser un texto de entre 1 y 1024 caracteres, sin saltos de línea.")
        result.setdefault(code_key(kind, value), value.strip())
    return list(result.values())
CATEGORY_FIELDS = {"id", "revision", "name", "icon", "color"}
DEFAULT_CATEGORY_ICON = "mdi:tag"
DEFAULT_CATEGORY_COLOR = "#64748b"


def normalized_name(value: str) -> str:
    """Compare product names without accents, case or spacing differences."""
    value = "".join(char for char in normalize("NFKD", value) if not unicode_category(char).startswith("M"))
    return " ".join(value.split()).lower()


def _mdi_icon(value: Any, *, optional: bool = False) -> str:
    if optional and value == "":
        return ""
    if not isinstance(value, str) or len(value) > 100 or not re.fullmatch(r"mdi:[a-z0-9]+(?:-[a-z0-9]+)*", value):
        raise CatalogError("Utiliza un icono MDI como mdi:shopping.")
    return value


def normalize_category(data: dict[str, Any]) -> dict[str, Any]:
    """Validate category properties before using colors in the frontend."""
    if not isinstance(data, dict) or set(data) - CATEGORY_FIELDS:
        raise CatalogError("La categoría contiene campos no admitidos.")
    name = _text(data, "name", 80)
    if not name:
        raise CatalogError("El nombre de la categoría es obligatorio.")
    icon = _mdi_icon(data.get("icon", DEFAULT_CATEGORY_ICON))
    color = data.get("color", DEFAULT_CATEGORY_COLOR)
    if not isinstance(color, str) or not re.fullmatch(r"#[a-fA-F0-9]{6}", color):
        raise CatalogError("Selecciona un color hexadecimal válido, como #267052.")
    return {"name": name, "icon": icon, "color": color.lower()}


class CatalogError(ValueError):
    """An actionable catalog validation or concurrency error."""

    def __init__(self, message: str, code: str = "invalid_product") -> None:
        super().__init__(message)
        self.code = code


def _text(data: dict[str, Any], key: str, limit: int) -> str:
    value = data.get(key, "")
    if not isinstance(value, str) or len(value.strip()) > limit:
        raise CatalogError(f"El campo {key} debe ser un texto de hasta {limit} caracteres.")
    return value.strip()


def normalize_product(data: dict[str, Any]) -> dict[str, Any]:
    """Validate editable fields and keep identifiers as text, including leading zeros."""
    if not isinstance(data, dict) or set(data) - FIELDS - LEGACY_PRODUCT_FIELDS:
        raise CatalogError("El producto contiene campos no admitidos.")
    product = {
        key: _text(data, key, limit)
        for key, limit in (
            ("name", 160), ("category", 80),
            ("barcode", 1024), ("image_url", 2048), ("notes", 1000),
        )
    }
    if not product["name"]:
        raise CatalogError("El nombre del producto es obligatorio.")
    try:
        product.update(normalize_purchase(data))
    except ValueError as err:
        raise CatalogError(str(err)) from err
    product["icon"] = _mdi_icon(data.get("icon", ""), optional=True)
    product["barcodes"] = _codes(data, "barcodes", "barcode")
    if product["barcode"]:
        _codes({"barcode": [product["barcode"]]}, "barcode", "barcode")
    product["nfc_tags"] = _codes(data, "nfc_tags", "nfc")
    actions = data.get("reader_actions", {})
    if not isinstance(actions, dict) or len(actions) > 100 or any(
        not isinstance(key, str) or not 1 <= len(key) <= 100 or not isinstance(value, str) or value not in READER_ACTIONS
        for key, value in actions.items()
    ):
        raise CatalogError("Las acciones de los lectores no son válidas.")
    product["reader_actions"] = dict(actions)
    recurrence = data.get("recurrence", {"enabled": False, "days": 7})
    if (not isinstance(recurrence, dict) or set(recurrence) != {"enabled", "days"}
        or type(recurrence["enabled"]) is not bool or type(recurrence["days"]) is not int
        or not 1 <= recurrence["days"] <= 3650):
        raise CatalogError("La recurrencia debe indicar si está activa y un número entero de días entre 1 y 3650.")
    product["recurrence"] = dict(recurrence)
    try:
        product["store_links"] = normalize_links(data.get("store_links", {}))
    except ValueError as err:
        raise CatalogError(str(err)) from err
    tags = data.get("tags", [])
    if not isinstance(tags, list) or len(tags) > 20:
        raise CatalogError("Puedes asignar hasta 20 etiquetas.")
    unique: dict[str, str] = {}
    for tag in tags:
        if not isinstance(tag, str) or len(tag.strip()) > 40:
            raise CatalogError("Cada etiqueta debe ser un texto de hasta 40 caracteres.")
        if tag.strip():
            unique.setdefault(tag.strip().casefold(), tag.strip())
    product["tags"] = list(unique.values())
    currency = data.get("currency", "EUR")
    if not isinstance(currency, str) or not re.fullmatch(r"[A-Z]{3}", currency):
        raise CatalogError("La moneda debe ser un código como EUR, USD o GBP.")
    product["currency"] = currency
    price = data.get("price")
    product["price"] = None
    if price is not None and price != "":
        if isinstance(price, bool) or not isinstance(price, (str, int, float)):
            raise CatalogError("El precio debe ser un número positivo o cero.")
        try:
            amount = Decimal(str(price).replace(",", "."))
            if not amount.is_finite() or not 0 <= amount <= 1000000:
                raise InvalidOperation
            rounded = amount.quantize(Decimal("0.01"))
            if rounded != amount:
                raise CatalogError("El precio admite como máximo dos decimales.")
            product["price"] = format(rounded, ".2f")
        except InvalidOperation as err:
            raise CatalogError("El precio debe estar entre 0 y 1000000.") from err
    image = product["image_url"]
    if image:
        try:
            parsed = urlsplit(image)
            local = image.startswith("/") and not image.startswith("//")
            remote = parsed.scheme in ("http", "https") and bool(parsed.hostname)
            if "\\" in image or any(ord(char) < 32 for char in image) or not (local or remote):
                raise ValueError
        except ValueError as err:
            raise CatalogError("Utiliza una URL http/https o una ruta local como /local/producto.png.") from err
    return product


class Catalog:
    """Own durable catalog data and serialize writes from different clients."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._store = Store(hass, 1, STORAGE_KEY)
        self._products: dict[str, dict[str, Any]] = {}
        self._categories: dict[str, dict[str, Any]] = {}
        self._recommendation_categories: dict[str, dict[str, Any]] = {}
        self._dismissed_suggestions: set[str] = set()
        self._lock = Lock()
        self._listeners: set = set()
        self.recurrence_peer = lambda _product: 0

    async def async_load(self) -> None:
        """Load existing products without overwriting an unreadable catalog."""
        data = await self._store.async_load()
        if data is not None:
            if not isinstance(data, dict) or not isinstance(data.get("products"), dict):
                raise CatalogError("No se ha podido leer el catálogo guardado.", "storage_error")
            self._products = data["products"]
            groups = data.get("recommendation_categories", {})
            if not isinstance(groups, dict) or any(not isinstance(group, dict) or not isinstance(group.get("product_ids", []), list) for group in groups.values()):
                raise CatalogError("No se han podido leer las categorías de sugerencias.", "storage_error")
            self._recommendation_categories = deepcopy(groups)
            dismissed = data.get("dismissed_suggestions", [])
            if not isinstance(dismissed, list) or any(not isinstance(name, str) for name in dismissed):
                raise CatalogError("No se han podido leer las sugerencias descartadas.", "storage_error")
            self._dismissed_suggestions = {normalized_name(name) for name in dismissed}
            categories = data.get("categories", {})
            if not isinstance(categories, dict):
                raise CatalogError("No se han podido leer las categorías guardadas.", "storage_error")
            categories = deepcopy(categories)
            known = {category["name"].casefold() for category in categories.values()}
            migrated = "categories" not in data
            # Earlier installations stored category names directly on products.
            # Promote those names without dropping products or their metadata.
            for product in self._products.values():
                for key, default in DEFAULT_PURCHASE.items():
                    if key not in product:
                        product[key] = default
                        migrated = True
                links = product.get("store_links")
                if isinstance(links, dict) and "lidl" in links:
                    del links["lidl"]
                    migrated = True
                for field in LEGACY_PRODUCT_FIELDS:
                    if field in product:
                        del product[field]
                        migrated = True
                name = product.get("category", "")
                if name and name.casefold() not in known:
                    now = datetime.now(UTC).isoformat()
                    category_id = str(uuid4())
                    categories[category_id] = {
                        "id": category_id, "revision": 1, "name": name,
                        "icon": DEFAULT_CATEGORY_ICON, "color": DEFAULT_CATEGORY_COLOR,
                        "created_at": now, "updated_at": now,
                    }
                    known.add(name.casefold())
                    migrated = True
            if migrated:
                await self._store.async_save({"products": self._products, "categories": categories,
                                              "dismissed_suggestions": sorted(self._dismissed_suggestions),
                                              "recommendation_categories": self._recommendation_categories})
            self._categories = categories

    @property
    def products(self) -> list[dict[str, Any]]:
        """Return a snapshot so callers cannot mutate stored products."""
        return deepcopy(sorted(self._products.values(), key=lambda item: item["name"].casefold()))

    def find_by_code(self, kind: str, code: str) -> dict | None:
        key = code_key(kind, code)
        for product in self._products.values():
            if key and any(value and code_key(kind, value) == key for value in product_codes(product, kind)):
                return deepcopy(product)
        return None

    @property
    def categories(self) -> list[dict[str, Any]]:
        """Include usage counts without persisting derived information."""
        counts = Counter(product["category"].casefold() for product in self._products.values())
        return [
            {**deepcopy(category), "product_count": counts[category["name"].casefold()]}
            for category in sorted(self._categories.values(), key=lambda item: item["name"].casefold())
        ]

    @property
    def recommendation_categories(self) -> list[dict]:
        return [{**deepcopy(group), "product_ids": [uid for uid in group["product_ids"] if uid in self._products]}
                for group in sorted(self._recommendation_categories.values(), key=lambda item: item["name"].casefold())]

    @property
    def snapshot(self) -> dict[str, Any]:
        return {"products": self.products, "categories": self.categories,
                "recommendation_categories": self.recommendation_categories,
                "dismissed_suggestions": sorted(self._dismissed_suggestions)}

    async def _persist(self, products, categories, dismissed=None, recommendation_categories=None) -> None:
        """Commit related category and product changes together under the lock."""
        if dismissed is None:
            dismissed = self._dismissed_suggestions
        groups = deepcopy(self._recommendation_categories if recommendation_categories is None else recommendation_categories)
        for group in groups.values():
            members = [uid for uid in group["product_ids"] if uid in products]
            if members != group["product_ids"]:
                group.update(product_ids=members, revision=group["revision"] + 1,
                             updated_at=datetime.now(UTC).isoformat())
        await self._store.async_save({"products": products, "categories": categories,
                                      "dismissed_suggestions": sorted(dismissed), "recommendation_categories": groups})
        self._recommendation_categories = groups
        self._products = products
        self._categories = categories
        self._dismissed_suggestions = dismissed

    @callback
    def _notify(self) -> None:
        for listener in tuple(self._listeners):
            listener()

    @callback
    def subscribe(self, listener):
        """Subscribe without coupling catalog storage to WebSockets."""
        self._listeners.add(listener)

        @callback
        def unsubscribe():
            self._listeners.discard(listener)

        return unsubscribe

    async def async_apply_community(self, community):
        """Fill missing confirmed data, preserving local choices and edit revisions."""
        async with self._lock:
            products = deepcopy(self._products)
            changed = False
            for product in products.values():
                strong_match = community.find(product)
                item = strong_match or community.find(query=product["name"])
                if item is None:
                    continue
                borrowed = product.setdefault("community_fields", {})
                filled = False
                if not product.get("name_en") and "name_en" in item["confirmed_fields"]:
                    product["name_en"] = item["name_en"]
                    borrowed["name_en"] = fingerprint(item["name_en"])
                    filled = True
                links = product.setdefault("store_links", {})
                for store, link in item["store_links"].items():
                    if strong_match and store not in links and "store_links."+store in item["confirmed_fields"]:
                        links[store] = normalize_links({store: link})[store]
                        borrowed["store_links."+store] = fingerprint(links[store])
                        filled = True
                if filled:
                    product["revision"] += 1
                    changed = True
            if changed:
                await self._persist(products, self._categories)
        if changed:
            self._notify()

    async def async_save_product(self, data: dict[str, Any], *, from_suggestion: bool = False) -> dict[str, Any]:
        """Persist before publishing, preserving the previous state on write failure."""
        product = normalize_product(data)
        async with self._lock:
            if from_suggestion:
                for existing in self._products.values():
                    if normalized_name(existing["name"]) == normalized_name(product["name"]):
                        return deepcopy(existing)
            product_id = data.get("id")
            if product_id is not None and not isinstance(product_id, str):
                raise CatalogError("Identificador de producto no válido.")
            current = self._products.get(product_id) if product_id else None
            if product_id and current is None:
                raise CatalogError("El producto ya no existe.", "not_found")
            if current and data.get("revision") != current["revision"]:
                raise CatalogError(
                    "Otra sesión ha modificado este producto. Cierra y vuelve a abrir su ficha.",
                    "conflict",
                )
            # Older panel sessions must not erase newly introduced reader fields.
            if current:
                for key, default in DEFAULT_PURCHASE.items():
                    if key not in data:
                        product[key] = current.get(key, default)
                for field in ("barcodes", "nfc_tags", "reader_actions"):
                    if field not in data:
                        product[field] = deepcopy(current.get(field, {} if field == "reader_actions" else []))
                if "recurrence" not in data:
                    product["recurrence"] = deepcopy(current.get("recurrence", {"enabled": False, "days": 7}))
                if "store_links" not in data:
                    product["store_links"] = deepcopy(current.get("store_links", {}))
            if product["category"]:
                category = next((item for item in self._categories.values()
                                 if item["name"].casefold() == product["category"].casefold()), None)
                if category is None:
                    raise CatalogError("La categoría ya no existe. Selecciona otra o créala en Categorías.")
                product["category"] = category["name"]
            for kind in ("barcode", "nfc"):
                keys = {code_key(kind, value) for value in product_codes(product, kind) if value}
                if any(item["id"] != product_id and keys.intersection(code_key(kind, value) for value in product_codes(item, kind) if value)
                       for item in self._products.values()):
                    raise CatalogError("Ya existe un producto con uno de esos códigos.", "duplicate_barcode" if kind == "barcode" else "duplicate_nfc")
            product["season_months"] = list((current or {}).get("season_months", []))
            # Translation is server-owned metadata; old clients cannot erase it.
            product["community_fields"] = deepcopy((current or {}).get("community_fields", {}))
            community = getattr(self, "community", None)
            shared = (community.find(product) or community.find(query=product["name"])) if community else None
            shared_translation = shared.get("name_en", "") if shared and "name_en" in shared["confirmed_fields"] else ""
            product["name_en"] = (
                current["name_en"]
                if current and current.get("name_en") and normalized_name(current["name"]) == normalized_name(product["name"])
                else shared_translation or await async_translate_name(self.hass, product["name"])
            )
            if shared_translation and product["name_en"] == shared_translation:
                product["community_fields"]["name_en"] = fingerprint(shared_translation)
            if not current and shared and normalized_name(product["name"]) == normalized_name(shared.get("name", "")):
                product["community_fields"]["name"] = fingerprint(product["name"])
            now = datetime.now(UTC).isoformat()
            recurrence_changed = (current or {}).get("recurrence", {"enabled": False, "days": 7}) != product["recurrence"]
            product["recurrence_updated_at"] = (
                max(datetime.now(UTC).timestamp(), (current or {}).get("recurrence_updated_at", 0), self.recurrence_peer(current or product)) + 0.000001
                if recurrence_changed else (current or {}).get("recurrence_updated_at", 0)
            )
            product["recurrence_started_at"] = (
                current.get("recurrence_started_at")
                if current and current.get("recurrence_started_at") and current.get("recurrence") == product["recurrence"]
                else now if product["recurrence"]["enabled"] else None
            )
            product.update({
                "id": current["id"] if current else str(uuid4()),
                "revision": current["revision"] + 1 if current else 1,
                "created_at": current["created_at"] if current else now,
                "updated_at": now,
                "price_updated_at": (
                    current["price_updated_at"]
                    if current and current["price"] == product["price"]
                    and current["currency"] == product["currency"]
                    else now if product["price"] is not None else None
                ),
            })
            updated = {**self._products, product["id"]: product}
            await self._persist(updated, self._categories)
        self._notify()
        return deepcopy(product)

    async def async_sync_recurrence(self, product_id, revision, recurrence, stamp, anchor):
        """Reconcile a durable pantry edit without translating or changing other fields."""
        async with self._lock:
            current = self._products.get(product_id)
            if not current or current["revision"] != revision:
                raise CatalogError("El producto ha cambiado durante la sincronización de Stock.", "conflict")
            if current.get("recurrence") == recurrence and current.get("recurrence_updated_at") == stamp:
                return deepcopy(current)
            product = {**deepcopy(current), "recurrence":deepcopy(recurrence), "recurrence_updated_at":stamp,
                "recurrence_started_at":datetime.fromtimestamp(anchor,UTC).isoformat() if recurrence["enabled"] else None,
                "revision":revision+1, "updated_at":datetime.now(UTC).isoformat()}
            await self._persist({**self._products, product_id:product}, self._categories)
        self._notify()
        return deepcopy(product)

    async def async_set_season_months(self, product_id: str, months: list[int], enabled: bool) -> dict:
        """Atomically associate a product with months without overwriting other edits."""
        if (not isinstance(months, list) or not 1 <= len(months) <= 12
            or any(type(month) is not int or not 1 <= month <= 12 for month in months)
            or type(enabled) is not bool):
            raise CatalogError("Selecciona uno o varios meses válidos.")
        async with self._lock:
            current = self._products.get(product_id)
            if current is None:
                raise CatalogError("El producto ya no existe.", "not_found")
            previous = set(current.get("season_months", []))
            updated = sorted(previous.union(months) if enabled else previous.difference(months))
            if updated == sorted(previous):
                return deepcopy(current)
            product = {**deepcopy(current), "season_months": updated,
                       "revision": current["revision"] + 1, "updated_at": datetime.now(UTC).isoformat()}
            await self._persist({**self._products, product_id: product}, self._categories)
        self._notify()
        return deepcopy(product)

    async def async_delete_product(self, product_id: str, revision: int) -> None:
        """Remove a catalog entry and its codes, leaving provider list items alone."""
        async with self._lock:
            current = self._products.get(product_id)
            if current is None:
                raise CatalogError("El producto ya no existe.", "not_found")
            if current["revision"] != revision:
                raise CatalogError("Otra sesión ha modificado este producto. Vuelve a abrir la confirmación.", "conflict")
            await self._persist({key: value for key, value in self._products.items() if key != product_id}, self._categories)
        self._notify()

    async def async_icon_query(self, product_id: str, name: str) -> str:
        """Backfill missing translations without invalidating the open edit form."""
        current = self._products.get(product_id)
        if not current or normalized_name(current["name"]) != normalized_name(name):
            return name
        if current.get("name_en"):
            return current["name_en"]
        translated = await async_translate_name(self.hass, current["name"])
        if not translated:
            return name
        async with self._lock:
            current = self._products.get(product_id)
            if current and normalized_name(current["name"]) == normalized_name(name):
                if current.get("name_en"):
                    return current["name_en"]
                # Server-owned metadata is disjoint from editable fields. Keep revision.
                await self._persist({**self._products, product_id: {**current, "name_en": translated}}, self._categories)
        self._notify()
        return translated

    async def async_dismiss_suggestion(self, name: str) -> None:
        """Persist shared dismissals without modifying the native shopping list."""
        name = _text({"name": name}, "name", 160)
        key = normalized_name(name)
        if not key:
            raise CatalogError("El nombre de la sugerencia es obligatorio.")
        async with self._lock:
            if key in self._dismissed_suggestions:
                return
            await self._persist(self._products, self._categories, self._dismissed_suggestions | {key})
        self._notify()

    async def async_save_recommendation_category(self, data: dict) -> dict:
        """Save an independent suggestion group; products can belong to several groups."""
        if not isinstance(data, dict) or set(data) - CATEGORY_FIELDS - {"product_ids"}:
            raise CatalogError("La categoría de sugerencias contiene campos no admitidos.")
        group = normalize_category({key: value for key, value in data.items() if key != "product_ids"})
        members = data.get("product_ids", [])
        if not isinstance(members, list) or len(members) > 10000 or any(not isinstance(uid, str) for uid in members):
            raise CatalogError("Selecciona productos válidos del catálogo.")
        async with self._lock:
            uid = data.get("id")
            if uid is not None and not isinstance(uid, str):
                raise CatalogError("Identificador de categoría no válido.")
            current = self._recommendation_categories.get(uid) if uid else None
            if uid and current is None:
                raise CatalogError("La categoría de sugerencias ya no existe.", "not_found")
            if current and data.get("revision") != current["revision"]:
                raise CatalogError("Otra sesión ha modificado esta categoría. Vuelve a abrirla.", "conflict")
            if normalized_name(group["name"]) == "productos de temporada" or any(
                item["id"] != uid and normalized_name(item["name"]) == normalized_name(group["name"])
                for item in self._recommendation_categories.values()):
                raise CatalogError("Ya existe una categoría de sugerencias con ese nombre.", "duplicate_category")
            if any(product_id not in self._products for product_id in members):
                raise CatalogError("Alguno de los productos ya no existe. Vuelve a abrir la categoría.", "not_found")
            now = datetime.now(UTC).isoformat()
            group.update(id=uid or str(uuid4()), revision=current["revision"] + 1 if current else 1,
                         created_at=current["created_at"] if current else now, updated_at=now,
                         product_ids=sorted(set(members)))
            await self._persist(self._products, self._categories,
                                recommendation_categories={**self._recommendation_categories, group["id"]: group})
        self._notify()
        return deepcopy(group)

    async def async_delete_recommendation_category(self, category_id: str, revision: int) -> None:
        async with self._lock:
            current = self._recommendation_categories.get(category_id)
            if current is None:
                raise CatalogError("La categoría de sugerencias ya no existe.", "not_found")
            if current["revision"] != revision:
                raise CatalogError("Otra sesión ha modificado esta categoría. Vuelve a abrirla.", "conflict")
            await self._persist(self._products, self._categories, recommendation_categories={
                key: value for key, value in self._recommendation_categories.items() if key != category_id})
        self._notify()

    async def async_save_category(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create or rename a category and keep product references consistent."""
        category = normalize_category(data)
        async with self._lock:
            category_id = data.get("id")
            if category_id is not None and not isinstance(category_id, str):
                raise CatalogError("Identificador de categoría no válido.")
            current = self._categories.get(category_id) if category_id else None
            if category_id and current is None:
                raise CatalogError("La categoría ya no existe.", "not_found")
            if current and data.get("revision") != current["revision"]:
                raise CatalogError("Otra sesión ha modificado esta categoría. Vuelve a abrirla.", "conflict")
            if any(item["name"].casefold() == category["name"].casefold() and item["id"] != category_id
                   for item in self._categories.values()):
                raise CatalogError("Ya existe una categoría con ese nombre.", "duplicate_category")
            now = datetime.now(UTC).isoformat()
            category.update({
                "id": current["id"] if current else str(uuid4()),
                "revision": current["revision"] + 1 if current else 1,
                "created_at": current["created_at"] if current else now,
                "updated_at": now,
            })
            products = self._products
            if current and current["name"] != category["name"]:
                products = self._reassign_category(current["name"], category["name"], now)
            await self._persist(products, {**self._categories, category["id"]: category})
        self._notify()
        return deepcopy(category)

    async def async_delete_category(self, category_id: str, revision: int) -> None:
        """Remove only the category, retaining its products without a category."""
        async with self._lock:
            current = self._categories.get(category_id)
            if current is None:
                raise CatalogError("La categoría ya no existe.", "not_found")
            if revision != current["revision"]:
                raise CatalogError("Otra sesión ha modificado esta categoría. Vuelve a abrirla.", "conflict")
            now = datetime.now(UTC).isoformat()
            products = self._reassign_category(current["name"], "", now)
            categories = {key: value for key, value in self._categories.items() if key != category_id}
            await self._persist(products, categories)
        self._notify()

    def _reassign_category(self, previous: str, replacement: str, now: str) -> dict:
        return {
            key: {**product, "category": replacement, "revision": product["revision"] + 1,
                  "updated_at": now}
            if product["category"].casefold() == previous.casefold() else product
            for key, product in self._products.items()
        }
