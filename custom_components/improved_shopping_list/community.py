"""Voluntary offline exports and a reviewed, read-only GitHub image dictionary."""

import base64
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import re
from time import monotonic
from urllib.parse import unquote, urlsplit
import zipfile

from aiohttp import ClientError, ClientTimeout
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store

from .catalog import normalized_name
from .const import DOMAIN, VERSION
from .icons import ICONS_URL, MAX_BYTES, IconError, validated_svg

REPOSITORY = "https://github.com/TitoTB/Improved-Shopping-List"
BASE_URL = "https://raw.githubusercontent.com/TitoTB/Improved-Shopping-List/main/community/"
MAX_INDEX = 2 * 1024 * 1024
MAX_EXPORT = 8 * 1024 * 1024
ID = re.compile(r"[a-z0-9][a-z0-9-]{0,79}")
FILE = re.compile(r"images/[a-f0-9]{64}\.(svg|png|jpg|webp)")


def image_bytes(raw: bytes, extension: str) -> bytes:
    """Only static SVG or recognized raster formats, never HTML or arbitrary files."""
    if len(raw) > MAX_BYTES:
        raise IconError("La imagen supera el tamaño permitido.")
    if extension == "svg":
        return validated_svg(raw)
    valid = ((extension == "png" and raw.startswith(b"\x89PNG\r\n\x1a\n"))
             or (extension == "jpg" and raw.startswith(b"\xff\xd8\xff"))
             or (extension == "webp" and raw[:4] == b"RIFF" and raw[8:12] == b"WEBP"))
    if not valid:
        raise IconError("El formato de la imagen no es compatible.")
    return raw


def public_url(value: str) -> str:
    """Do not export credentials, query tokens or local Home Assistant paths."""
    try:
        url = urlsplit(value)
        if url.scheme == "https" and url.hostname and not url.username and not url.password and not url.query:
            return url._replace(fragment="").geturl()
    except ValueError:
        pass
    return ""


def build_export(products: list[dict], assets: dict, config: Path, directory: Path) -> dict:
    """Export an explicit allowlist; no list contents, identifiers, codes or notes."""
    entries = {}
    files = {}
    skipped = 0
    for product in products:
        url = product.get("image_url", "")
        icon = product.get("icon", "")
        if not url and not icon:
            continue
        info = assets.get(url, {})
        content = None
        extension = ""
        try:
            root = None
            relative = ""
            if url.startswith(ICONS_URL + "/"):
                root, relative = directory, url[len(ICONS_URL) + 1:]
            elif url.startswith("/local/"):
                root, relative = config / "www", unquote(urlsplit(url).path[len("/local/"):])
            if root:
                root = root.resolve()
                path = (root / relative).resolve()
                if not path.is_relative_to(root) or not path.is_file() or path.stat().st_size > MAX_BYTES:
                    raise ValueError
                extension = path.suffix.lower().lstrip(".").replace("jpeg", "jpg")
                with path.open("rb") as source:
                    content = image_bytes(source.read(MAX_BYTES + 1), extension)
        except (OSError, ValueError, IconError):
            skipped += 1
        digest = hashlib.sha256(content).hexdigest() if content is not None else ""
        file = f"images/{digest}.{extension}" if digest else ""
        if file:
            files[file] = content
            if sum(map(len, files.values())) > MAX_EXPORT:
                raise IconError("Las imágenes superan 8 MB. Exporta un catálogo con imágenes más pequeñas.")
        source_url = public_url(info.get("source_url", "")) or public_url(url)
        if not file and not source_url and (url or not re.fullmatch(r"mdi:[a-z0-9-]+", icon)):
            if not root:
                skipped += 1
            continue
        name = product.get("name", "").strip()
        name_en = product.get("name_en", "").strip()
        identity = (normalized_name(name_en or name), digest or source_url or icon)
        if identity in entries:
            entries[identity]["catalog_uses"] += 1
            if name not in entries[identity]["terms"]:
                entries[identity]["terms"].append(name)
            continue
        entries[identity] = {
            "name": name, "name_en": name_en, "terms": list(dict.fromkeys([name, name_en])) if name_en else [name],
            "file": file, "sha256": digest, "icon": icon if not url else "",
            "source_url": source_url, "author": info.get("author", ""),
            "license": info.get("license", "unknown"), "license_url": public_url(info.get("license_url", "")),
            "catalog_uses": 1, "requires_review": True,
        }
    if sum(map(len, files.values())) > MAX_EXPORT:
        raise IconError("Las imágenes superan 8 MB. Exporta un catálogo con imágenes más pequeñas.")
    manifest = {"schema_version": 1, "kind": "improved-shopping-list-icon-export", "entries": list(entries.values())}
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("dictionary.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        archive.writestr("README.txt", "Aportación voluntaria. Revisar traducciones y licencias antes de publicar.\n"
                          "catalog_uses cuenta fichas locales, no usuarios globales.\n"
                          "Las URL externas no se han descargado. Las licencias desconocidas requieren revisión.\n")
        for filename, raw in files.items():
            archive.writestr(filename, raw)
    if buffer.tell() > MAX_EXPORT + MAX_INDEX:
        raise IconError("El diccionario supera el tamaño máximo de exportación.")
    return {"filename": "improved-shopping-list-icons.zip", "data": base64.b64encode(buffer.getvalue()).decode(),
            "entries": len(entries), "images": len(files), "skipped": skipped}


def build_catalog_export(products: list[dict], categories: list[dict]) -> dict:
    """Download commercial catalog data without account or household automation data."""
    category_names = {item["id"]: item["name"] for item in categories}
    rows = []
    for product in products:
        row = {key: deepcopy(product[key]) for key in ("name", "name_en", "icon", "barcode", "barcodes") if key in product}
        row["category"] = category_names.get(product.get("category"), product.get("category", ""))
        row["image_url"] = public_url(product.get("image_url", ""))
        row["commercial_references"] = []
        for reference in product.get("commercial_references", []):
            option = {key: deepcopy(reference[key]) for key in (
                "store", "name", "ean", "reference_id", "brand", "content_quantity", "content_unit",
                "content_confirmed", "active", "last_price", "nutriscore", "measure_price") if key in reference}
            option["url"] = public_url(reference.get("url", ""))
            row["commercial_references"].append(option)
        rows.append(row)
    data = json.dumps({"schema_version": 1, "kind": "improved-shopping-list-catalog-export", "products": rows},
                      ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8")
    if len(data) > MAX_EXPORT:
        raise IconError("El catálogo supera el tamaño máximo de exportación (8 MB).")
    return {"filename": "improved-shopping-list-catalog.json", "data": base64.b64encode(data).decode(), "products": len(rows)}


def validate_index(data: dict) -> list[dict]:
    if not isinstance(data, dict) or data.get("schema_version") != 1 or not isinstance(data.get("icons"), list) or len(data["icons"]) > 5000:
        raise IconError("El índice comunitario no es válido.")
    result = []
    identifiers = set()
    for item in data["icons"]:
        if not isinstance(item, dict) or not ID.fullmatch(item.get("id", "")) or item["id"] in identifiers:
            raise IconError("Identificador comunitario no válido.")
        if not FILE.fullmatch(item.get("file", "")) or item.get("sha256") != item["file"].split("/")[1].split(".")[0]:
            raise IconError("Archivo comunitario no válido.")
        terms = item.get("terms", [])
        if not isinstance(terms, list) or not 1 <= len(terms) <= 30 or any(not isinstance(term, str) or not 1 <= len(term) <= 100 for term in terms):
            raise IconError("Términos comunitarios no válidos.")
        for key in ("name_en", "author", "license"):
            if not isinstance(item.get(key), str) or not 1 <= len(item[key]) <= 300:
                raise IconError("Faltan datos de atribución comunitarios.")
        if not public_url(item.get("license_url", "")):
            raise IconError("Falta la licencia comunitaria.")
        uses = item.get("contributions", 0)
        if type(uses) is not int or not 0 <= uses <= 1000000:
            raise IconError("Recuento comunitario no válido.")
        identifiers.add(item["id"])
        result.append({key: deepcopy(item[key]) for key in ("id", "file", "sha256", "terms", "name_en", "author", "license", "license_url")} | {"contributions": uses})
    return result


class CommunityLibrary:
    """Read reviewed assets only from this repository; cache for offline fallback."""

    def __init__(self, hass, icons):
        self.hass, self.icons = hass, icons
        self._store = Store(hass, 1, f"{DOMAIN}.community")
        self._items = []
        self._next_refresh = 0.0

    async def async_load(self):
        try:
            self._items = validate_index(await self._store.async_load() or {"schema_version": 1, "icons": []})
        except (IconError, TypeError, ValueError):
            self._items = []

    async def _fetch(self, path: str, limit: int) -> bytes:
        session = async_get_clientsession(self.hass)
        async with session.get(BASE_URL + path, allow_redirects=False, timeout=ClientTimeout(total=5),
                               headers={"User-Agent": f"ImprovedShoppingList/{VERSION}"}) as response:
            if response.status != 200:
                raise IconError("No se ha podido consultar el catálogo comunitario.")
            body = bytearray()
            async for chunk in response.content.iter_chunked(16384):
                body.extend(chunk)
                if len(body) > limit:
                    raise IconError("La respuesta comunitaria supera el tamaño permitido.")
            return bytes(body)

    async def async_search(self, query: str) -> list[dict]:
        if monotonic() >= self._next_refresh:
            self._next_refresh = monotonic() + 300
            try:
                items = validate_index(json.loads(await self._fetch("index.json", MAX_INDEX)))
                await self._store.async_save({"schema_version": 1, "icons": items})
                self._items = items
                self._next_refresh = monotonic() + 86400
            except (ClientError, TimeoutError, OSError, HomeAssistantError, IconError, ValueError, TypeError):
                pass  # Keep cached suggestions and let Iconify continue independently.
        key = normalized_name(query)
        matches = [item for item in self._items if any(normalized_name(term) == key for term in [item["name_en"], *item["terms"]])]
        return [{"id": "community:" + item["id"], "label": item["name_en"], "collection": "Comunidad",
                 "author": item["author"], "author_url": REPOSITORY, "license": item["license"], "license_url": item["license_url"],
                 "preview_url": BASE_URL + item["file"], "contributions": item["contributions"]}
                for item in sorted(matches, key=lambda item: (-item["contributions"], item["id"]))[:100]]

    async def async_import(self, identifier: str) -> dict:
        item = next((item for item in self._items if "community:" + item["id"] == identifier), None)
        if item is None:
            raise IconError("La imagen comunitaria ya no está disponible. Repite la búsqueda.")
        async with self.icons._lock:
            existing = next((asset for asset in self.icons._assets.values() if asset.get("id") == identifier and asset.get("sha256") == item["sha256"]), None)
            if existing and await self.hass.async_add_executor_job((self.icons.directory / existing["url"].rsplit("/", 1)[1]).is_file):
                return deepcopy(existing)
            if len(self.icons._assets) >= 2000:
                raise IconError("Se ha alcanzado el límite de iconos guardados.")
            try:
                raw = await self._fetch(item["file"], MAX_BYTES)
                if hashlib.sha256(raw).hexdigest() != item["sha256"]:
                    raise IconError("La imagen comunitaria no coincide con el archivo revisado.")
                extension = item["file"].rsplit(".", 1)[1]
                raw = image_bytes(raw, extension)
                filename = hashlib.sha256(raw).hexdigest() + "." + extension
                url = ICONS_URL + "/" + filename
                asset = {"id": identifier, "sha256": item["sha256"], "url": url, "collection": "Comunidad", "author": item["author"],
                         "author_url": REPOSITORY, "license": item["license"], "license_url": item["license_url"],
                         "source_url": REPOSITORY + "/blob/main/community/" + item["file"]}
                await self.hass.async_add_executor_job((self.icons.directory / filename).write_bytes, raw)
                assets = {**self.icons._assets, url: asset}
                await self.icons._store.async_save({"assets": assets})
                self.icons._assets = assets
                return deepcopy(asset)
            except (ClientError, TimeoutError, OSError, HomeAssistantError) as err:
                raise IconError("No se ha podido guardar la imagen comunitaria.") from err
