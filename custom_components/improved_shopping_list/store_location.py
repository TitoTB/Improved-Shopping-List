"""Anonymous location discovery shared by store configuration."""

import asyncio
import json
import math
import re
from urllib.parse import quote

import aiohttp
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .regional_stores import POSTAL_PATTERN, async_resolve_areas
from .stores import StoreError, async_resolve_mercadona

UUID_PATTERN = r"[a-fA-F0-9]{8}(?:-[a-fA-F0-9]{4}){3}-[a-fA-F0-9]{12}"
# Reference locations when the user explicitly leaves the shared postal code blank.
DEFAULT_POSTALS = {"mercadona":"28001", "consum":"46409", "lasirena":"28024", "eroski":"48001", "dia":"28024"}


async def _json(session, method, url, **kwargs):
    async with session.request(method, url, timeout=aiohttp.ClientTimeout(total=20), allow_redirects=False, **kwargs) as response:
        if response.status != 200:
            raise StoreError(f"No se pudo comprobar la ubicación (HTTP {response.status}).")
        raw = bytearray()
        async for chunk in response.content.iter_chunked(8192):
            raw.extend(chunk)
            if len(raw) > 524288:
                raise StoreError("La respuesta de ubicación es demasiado grande.")
        return json.loads(raw)


async def _public_location(hass, store, postal):
    headers = {"Accept":"application/json", "User-Agent":"Mozilla/5.0 (compatible; Improved-Shopping-List)"}
    session = async_create_clientsession(hass, auto_cleanup=False,
        cookie_jar=aiohttp.CookieJar() if store == "alcampo" else aiohttp.DummyCookieJar())
    try:
        if store == "carrefour":
            data = await _json(session, "GET", "https://www.carrefour.es/cloud-api/salepoints/v1/salepoint",
                params={"id":postal, "type":"postal_code"}, headers={**headers,"Referer":"https://www.carrefour.es/","delivery_type":"A_DOMICILIO"})
            point = data.get("salepoint") if isinstance(data, dict) else None
            if not isinstance(point, str) or not re.fullmatch(r"[0-9]{6}", point):
                raise StoreError("Carrefour no ha devuelto un centro válido para el código postal.")
            return {"sale_point":point}
        base = "https://www.compraonline.alcampo.es"
        headers.update({"Referer":base+"/", "Origin":base, "ecom-request-source":"web"})
        # Alcampo requires its own fresh anonymous session and CSRF token for PUT/POST.
        # No browser cookie, user account or persisted credential is involved.
        async with session.get(base+"/", headers=headers, timeout=aiohttp.ClientTimeout(total=20), allow_redirects=False) as response:
            if response.status != 200:
                raise StoreError(f"Alcampo no pudo iniciar la consulta de ubicación (HTTP {response.status}).")
            raw = bytearray()
            async for chunk in response.content.iter_chunked(8192):
                raw.extend(chunk)
                if len(raw) > 2097152:
                    raise StoreError("La respuesta inicial de Alcampo es demasiado grande.")
            visitor = response.cookies.get("VISITORID")
        csrf = re.search(r'"session"\s*:\s*\{\s*"csrf"\s*:\s*\{\s*"token"\s*:\s*"([A-Za-z0-9._~+/=-]{1,1024})"', raw.decode("utf-8", errors="replace"))
        if not csrf or not visitor or not re.fullmatch(r"[A-Za-z0-9._~+/=-]{1,256}", visitor.value):
            raise StoreError("Alcampo no ha devuelto una sesión anónima válida.")
        headers.update({"x-csrf-token":csrf[1], "visitor-id":visitor.value, "visitorid":visitor.value})
        areas = await _json(session, "PUT", base+"/api/address/v1/addresses/areas", data={"query":postal}, headers=headers)
        if not isinstance(areas, list) or not areas or not isinstance(areas[0], dict):
            raise StoreError("Alcampo no ha encontrado el código postal.")
        identifier = areas[0].get("id")
        if not isinstance(identifier, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,256}", identifier):
            raise StoreError("Alcampo ha devuelto una ubicación no válida.")
        area = await _json(session, "GET", base+"/api/address/v1/addresses/areas/"+quote(identifier, safe=""), headers=headers)
        if not isinstance(area, dict) or area.get("postalCode") != postal or area.get("countryCode") != "ES":
            raise StoreError("Alcampo no ha confirmado el código postal solicitado.")
        lat, lon = area.get("latitude"), area.get("longitude")
        if (type(lat) not in (int,float) or type(lon) not in (int,float) or not math.isfinite(lat) or not math.isfinite(lon)
            or not -90 <= lat <= 90 or not -180 <= lon <= 180 or not isinstance(area.get("formattedAddress"), str)):
            raise StoreError("Alcampo no ha devuelto coordenadas válidas.")
        # Only the public postal area's centroid is sent, never a user's street/address.
        destination = await _json(session, "POST", base+"/api/ecomdeliverydestinations/v2/temporary-delivery-destinations",
            json={"visitorId":visitor.value, "latitude":lat, "longitude":lon, "postalCode":postal,
                  "formattedAddress":area["formattedAddress"][:500]}, headers=headers)
        if not isinstance(destination, str) or not re.fullmatch(UUID_PATTERN, destination):
            raise StoreError("Alcampo no ha devuelto un destino válido.")
        result = await _json(session, "GET", base+"/api/ecomdeliverydestinations/v4/delivery-addresses/"+destination, headers=headers)
        region = result.get("resolvedRegionId") if isinstance(result, dict) else None
        if (not isinstance(result, dict) or result.get("postalCode") != postal or result.get("deliverability") != "DELIVERABLE"
            or not isinstance(region, str) or not re.fullmatch(UUID_PATTERN, region)):
            raise StoreError("Alcampo no ha confirmado una región de entrega para el código postal.")
        return {"region_id":region.lower()}
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as err:
        if isinstance(err, StoreError):
            raise
        raise StoreError("No se ha podido consultar la ubicación de la tienda.") from err
    finally:
        session.cookie_jar.clear()
        session.detach()


async def resolve_location(hass, store, postal, current):
    """Resolve the user's postcode; never silently fall back when it was supplied."""
    if postal and not re.fullmatch(POSTAL_PATTERN, postal):
        raise StoreError("Introduce un código postal español válido de cinco cifras.")
    effective = postal or DEFAULT_POSTALS.get(store, "")
    if store == "mercadona":
        return {"postal_code":effective, "warehouse":await async_resolve_mercadona(hass, effective)}
    if store in ("carrefour", "alcampo"):
        return {"postal_code":postal, **(await _public_location(hass, store, postal) if postal else
            {"sale_point":"005290"} if store == "carrefour" else {"region_id":""})}
    coverage = await async_resolve_areas(hass, store, effective)
    areas = coverage["areas"]
    # Retain an existing valid choice; otherwise use the first public center offered.
    selected = next((area for area in areas if current.get("postal_code") == effective and area["id"] == current.get("area_id")), areas[0])
    return {"postal_code":effective, "area_id":selected["id"], "area_name":selected["name"], "zone":selected.get("zone", "")}
