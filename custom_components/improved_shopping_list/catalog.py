"""Local shared product catalog, independent of any to-do list provider."""

from asyncio import Lock
from collections import Counter
from copy import deepcopy
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
import re
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.storage import Store

from .const import DOMAIN

STORAGE_KEY = f"{DOMAIN}.catalog"
FIELDS = {
    "id", "revision", "name", "category", "tags", "brand", "barcode",
    "format", "price", "currency", "image_url", "icon", "notes",
}
CATEGORY_FIELDS = {"id", "revision", "name", "icon", "color"}
DEFAULT_CATEGORY_ICON = "mdi:tag"
DEFAULT_CATEGORY_COLOR = "#64748b"


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
    if not isinstance(data, dict) or set(data) - FIELDS:
        raise CatalogError("El producto contiene campos no admitidos.")
    product = {
        key: _text(data, key, limit)
        for key, limit in (
            ("name", 160), ("category", 80), ("brand", 100),
            ("barcode", 64), ("format", 100), ("image_url", 2048), ("notes", 1000),
        )
    }
    if not product["name"]:
        raise CatalogError("El nombre del producto es obligatorio.")
    product["icon"] = _mdi_icon(data.get("icon", ""), optional=True)
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
        self._store = Store(hass, 1, STORAGE_KEY)
        self._products: dict[str, dict[str, Any]] = {}
        self._categories: dict[str, dict[str, Any]] = {}
        self._lock = Lock()
        self._listeners: set = set()

    async def async_load(self) -> None:
        """Load existing products without overwriting an unreadable catalog."""
        data = await self._store.async_load()
        if data is not None:
            if not isinstance(data, dict) or not isinstance(data.get("products"), dict):
                raise CatalogError("No se ha podido leer el catálogo guardado.", "storage_error")
            self._products = data["products"]
            categories = data.get("categories", {})
            if not isinstance(categories, dict):
                raise CatalogError("No se han podido leer las categorías guardadas.", "storage_error")
            categories = deepcopy(categories)
            known = {category["name"].casefold() for category in categories.values()}
            migrated = "categories" not in data
            # Earlier installations stored category names directly on products.
            # Promote those names without dropping products or their metadata.
            for product in self._products.values():
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
                await self._store.async_save({"products": self._products, "categories": categories})
            self._categories = categories

    @property
    def products(self) -> list[dict[str, Any]]:
        """Return a snapshot so callers cannot mutate stored products."""
        return deepcopy(sorted(self._products.values(), key=lambda item: item["name"].casefold()))

    @property
    def categories(self) -> list[dict[str, Any]]:
        """Include usage counts without persisting derived information."""
        counts = Counter(product["category"].casefold() for product in self._products.values())
        return [
            {**deepcopy(category), "product_count": counts[category["name"].casefold()]}
            for category in sorted(self._categories.values(), key=lambda item: item["name"].casefold())
        ]

    @property
    def snapshot(self) -> dict[str, Any]:
        return {"products": self.products, "categories": self.categories}

    async def _persist(self, products, categories) -> None:
        """Commit related category and product changes together under the lock."""
        await self._store.async_save({"products": products, "categories": categories})
        self._products = products
        self._categories = categories

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

    async def async_save_product(self, data: dict[str, Any]) -> dict[str, Any]:
        """Persist before publishing, preserving the previous state on write failure."""
        product = normalize_product(data)
        async with self._lock:
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
            if product["category"]:
                category = next((item for item in self._categories.values()
                                 if item["name"].casefold() == product["category"].casefold()), None)
                if category is None:
                    raise CatalogError("La categoría ya no existe. Selecciona otra o créala en Categorías.")
                product["category"] = category["name"]
            if product["barcode"] and any(
                item["barcode"] == product["barcode"] and item["id"] != product_id
                for item in self._products.values()
            ):
                raise CatalogError("Ya existe un producto con ese código de barras.", "duplicate_barcode")
            now = datetime.now(UTC).isoformat()
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
