"""Search Iconify and keep selected, validated SVGs in Home Assistant storage."""

from asyncio import Lock
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import re
from time import monotonic
from urllib.parse import urlsplit
from xml.etree import ElementTree as ET

from aiohttp import ClientError, ClientTimeout

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store

from .const import DOMAIN, VERSION

BASE_URL = "https://api.iconify.design"
ICONS_URL = "/improved_shopping_list_icons"
PREFIXES = ("mdi", "tabler", "openmoji", "noto", "fluent-emoji-flat")
COLOR_PREFIXES = ("noto", "fluent-emoji-flat", "openmoji")
MAX_BYTES = 262144
BATCH_SIZE = 32  # Iconify's minimum search batch; the picker displays three color icons.
MAX_START = 320
_NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_TAGS = {"svg", "g", "path", "circle", "ellipse", "rect", "line", "polyline", "polygon",
         "defs", "linearGradient", "radialGradient", "stop", "clipPath", "mask", "title", "desc"}
_ATTRS = {"id", "d", "x", "y", "x1", "y1", "x2", "y2", "cx", "cy", "r", "rx", "ry",
          "width", "height", "viewBox", "points", "transform", "fill", "fill-rule", "fill-opacity",
          "stroke", "stroke-width", "stroke-linecap", "stroke-linejoin", "stroke-miterlimit",
          "stroke-dasharray", "stroke-dashoffset", "stroke-opacity", "opacity", "clip-rule",
          "clip-path", "clipPathUnits", "mask", "maskUnits", "maskContentUnits", "offset",
          "stop-color", "stop-opacity", "gradientUnits", "gradientTransform", "spreadMethod",
          "fx", "fy", "fr", "color", "vector-effect", "preserveAspectRatio"}


class IconError(ValueError):
    """An error that can be displayed in the icon picker."""


def split_icon(value: str) -> tuple[str, str]:
    """Only request known, open icon sets and plain resource names."""
    if not isinstance(value, str) or len(value) > 160 or value.count(":") != 1:
        raise IconError("El identificador del icono no es válido.")
    prefix, name = value.split(":")
    if prefix not in PREFIXES or not _NAME.fullmatch(name):
        raise IconError("El identificador del icono no es válido.")
    return prefix, name


def _text(value, limit=200) -> str:
    return value.strip()[:limit] if isinstance(value, str) else ""


def _url(value) -> str:
    value = _text(value, 2048)
    try:
        parsed = urlsplit(value)
        if parsed.scheme == "https" and parsed.hostname and not parsed.username and "\\" not in value:
            return value
    except ValueError:
        pass
    return ""


def collection_info(data) -> dict:
    """Keep only the attribution needed to use an icon."""
    if not isinstance(data, dict):
        raise IconError("No se ha podido obtener la licencia del icono.")
    author, license_info = data.get("author"), data.get("license")
    if not isinstance(author, dict) or not isinstance(license_info, dict):
        raise IconError("No se ha podido obtener la licencia del icono.")
    result = {"collection": _text(data.get("name")), "author": _text(author.get("name")),
              "author_url": _url(author.get("url")), "license": _text(license_info.get("title")),
              "license_url": _url(license_info.get("url"))}
    if not result["author"] or not result["license"] or not result["license_url"]:
        raise IconError("No se ha podido obtener la licencia del icono.")
    return result


def validated_svg(raw: bytes) -> bytes:
    """Accept static vector shapes only, with no scripts, CSS or external references."""
    if len(raw) > MAX_BYTES or b"<!" in raw or b"<?" in raw:
        raise IconError("El formato del icono no es compatible.")
    try:
        root = ET.fromstring(raw.decode("utf-8"))
        if root.tag != "{http://www.w3.org/2000/svg}svg":
            raise ValueError
        bounds = [float(value) for value in root.attrib["viewBox"].replace(",", " ").split()]
        if len(bounds) != 4 or not all(math.isfinite(value) and abs(value) <= 100000 for value in bounds) or min(bounds[2:]) <= 0:
            raise ValueError
        for node in root.iter():
            if not node.tag.startswith("{http://www.w3.org/2000/svg}") or node.tag.split("}")[1] not in _TAGS:
                raise ValueError
            for key, value in node.attrib.items():
                if key not in _ATTRS or any(ord(char) < 32 for char in value):
                    raise ValueError
                # Paint servers/clip paths may refer only to a fragment in this SVG.
                if re.search(r"url\s*\(", value, re.I) and not re.fullmatch(r"url\(#[a-zA-Z0-9_-]+\)", value):
                    raise ValueError
        root.set("width", "128")
        root.set("height", "128")
        root.set("color", "#20352d")
        return ET.tostring(root, encoding="utf-8")
    except (ET.ParseError, KeyError, ValueError, TypeError, UnicodeError) as err:
        raise IconError("El formato del icono no es compatible.") from err


class IconLibrary:
    """All network requests use Iconify; only explicitly selected icons go on disk."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self.directory = Path(hass.config.path(".storage", f"{DOMAIN}_icons"))
        self._store = Store(hass, 1, f"{DOMAIN}.icon_assets")
        self._assets: dict[str, dict] = {}
        self._collections: dict[str, dict] = {}
        self._searches: dict[tuple, tuple] = {}
        self._lock = Lock()
        self._retry_after = 0.0

    async def async_load(self) -> None:
        data = await self._store.async_load()
        self._assets = (data or {}).get("assets", {})
        await self.hass.async_add_executor_job(self.directory.mkdir, 0o700, True, True)

    def info(self, image_url: str) -> dict | None:
        """Metadata is kept separately so existing product fields remain compatible."""
        return deepcopy(self._assets.get(image_url))

    async def _request(self, path: str, params: dict | None = None, *, svg=False):
        if monotonic() < self._retry_after:
            raise IconError("Iconify ha limitado las consultas. Espera un minuto e inténtalo de nuevo.")
        try:
            session = async_get_clientsession(self.hass)
            async with session.get(f"{BASE_URL}{path}", params=params, allow_redirects=False,
                                   timeout=ClientTimeout(total=12), headers={"User-Agent": f"ImprovedShoppingList/{VERSION}"}) as response:
                if response.status == 429:
                    self._retry_after = monotonic() + 60
                if response.status != 200:
                    raise IconError("No se ha podido consultar Iconify. Inténtalo de nuevo más tarde.")
                body = bytearray()
                async for chunk in response.content.iter_chunked(16384):
                    body.extend(chunk)
                    if len(body) > MAX_BYTES:
                        raise IconError("La respuesta de Iconify es demasiado grande.")
                return bytes(body) if svg else json.loads(body)
        except (ClientError, TimeoutError, ValueError, UnicodeError) as err:
            if isinstance(err, IconError):
                raise
            raise IconError("No se ha podido conectar con Iconify. Comprueba la conexión e inténtalo de nuevo.") from err

    async def async_search(self, query: str, start: int = 0) -> dict:
        query = query.strip()
        if not 2 <= len(query) <= 100 or any(ord(char) < 32 for char in query) or type(start) is not int or not 0 <= start <= MAX_START:
            raise IconError("Escribe una búsqueda de entre 2 y 100 caracteres.")
        key = (query.casefold(), start)
        async with self._lock:
            cached = self._searches.get(key)
            if cached and cached[0] > monotonic():
                return deepcopy(cached[1])
            data = await self._request("/search", {"query": query, "limit": BATCH_SIZE, "start": start, "prefixes": ",".join(COLOR_PREFIXES)})
            if not isinstance(data, dict) or not isinstance(data.get("icons"), list) or not isinstance(data.get("collections"), dict):
                raise IconError("Iconify ha devuelto una respuesta no válida.")
            icons = []
            for identifier in dict.fromkeys(value for value in data["icons"][:BATCH_SIZE] if isinstance(value, str)):
                try:
                    prefix, name = split_icon(identifier)
                    metadata = data["collections"].get(prefix)
                    if prefix not in COLOR_PREFIXES or not isinstance(metadata, dict) or metadata.get("palette") is not True:
                        continue
                    info = collection_info(data["collections"].get(prefix))
                except IconError:
                    continue
                self._collections[prefix] = info
                icons.append({"id": identifier, "label": name.replace("-", " "), **info,
                              "preview_url": f"{BASE_URL}/{prefix}/{name}.svg?height=96"})
            result = {"icons": icons, "next_start": start + BATCH_SIZE,
                      "has_more": len(data["icons"]) == BATCH_SIZE and start < MAX_START}
            self._searches[key] = (monotonic() + 21600, result)
            if len(self._searches) > 100:
                del self._searches[next(iter(self._searches))]
            return deepcopy(result)

    async def async_import(self, identifier: str) -> dict:
        prefix, name = split_icon(identifier)
        async with self._lock:
            existing = next((deepcopy(asset) for asset in self._assets.values() if asset.get("id") == identifier), None)
            if existing and await self.hass.async_add_executor_job((self.directory / existing["url"].rsplit("/", 1)[-1]).is_file):
                return existing
            if len(self._assets) >= 2000:
                raise IconError("Se ha alcanzado el límite de iconos guardados.")
            info = self._collections.get(prefix)
            if not info:
                data = await self._request("/collections", {"prefixes": prefix})
                info = collection_info(data.get(prefix) if isinstance(data, dict) else None)
                self._collections[prefix] = info
            svg = validated_svg(await self._request(f"/{prefix}/{name}.svg", {"height": "128"}, svg=True))
            filename = hashlib.sha256(identifier.encode() + svg).hexdigest() + ".svg"
            url = f"{ICONS_URL}/{filename}"
            asset = {"id": identifier, "url": url, **info,
                     "source_url": f"https://icon-sets.iconify.design/{prefix}/{name}/"}
            # Write off the event loop. Publish metadata only after both writes succeed.
            try:
                await self.hass.async_add_executor_job((self.directory / filename).write_bytes, svg)
                assets = {**self._assets, url: asset}
                await self._store.async_save({"assets": assets})
            except (OSError, HomeAssistantError) as err:
                raise IconError("No se ha podido guardar el icono en Home Assistant.") from err
            self._assets = assets
            return deepcopy(asset)
