"""Local shared product catalog, independent of any to-do list provider."""

from asyncio import Lock
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
    "format", "price", "currency", "image_url", "notes",
}


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
        self._lock = Lock()
        self._listeners: set = set()

    async def async_load(self) -> None:
        """Load existing products without overwriting an unreadable catalog."""
        data = await self._store.async_load()
        if data is not None:
            if not isinstance(data, dict) or not isinstance(data.get("products"), dict):
                raise CatalogError("No se ha podido leer el catálogo guardado.", "storage_error")
            self._products = data["products"]

    @property
    def products(self) -> list[dict[str, Any]]:
        """Return a snapshot so callers cannot mutate stored products."""
        return deepcopy(sorted(self._products.values(), key=lambda item: item["name"].casefold()))

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
            await self._store.async_save({"products": updated})
            self._products = updated
        for listener in tuple(self._listeners):
            listener()
        return deepcopy(product)
