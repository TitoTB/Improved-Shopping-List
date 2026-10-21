"""Public postal coverage for Consum and La Sirena, isolated from customer sessions."""

import asyncio
import json
import re
from urllib.parse import urlencode

import aiohttp
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .stores import StoreError
from .eroski import EroskiClient, EroskiError, AREA_PATTERN, pickup_areas
from .dia import resolve_postal as resolve_dia_postal, DiaError

REGIONAL_STORES = {"consum": "Consum", "lasirena": "La Sirena", "eroski":"Eroski", "dia":"DIA"}
POSTAL_PATTERN = r"(?:0[1-9]|[1-4][0-9]|5[0-2])[0-9]{3}"


def valid_area(store, area):
    pattern = POSTAL_PATTERN if store == "dia" else AREA_PATTERN if store == "eroski" else r"[0-9]{1,8}D" if store == "consum" else r"lasirena[0-9]{1,8}"
    return isinstance(area, str) and re.fullmatch(pattern, area) is not None


def coverage_areas(store, data):
    """Return only enabled, well-formed centers offered by the merchant."""
    if not isinstance(data, list):
        raise StoreError("La tienda no ha devuelto una cobertura válida.")
    areas = {}
    for group in data:
        if not isinstance(group, dict):
            raise StoreError("La tienda no ha devuelto una cobertura válida.")
        entries = group.get("shippingAreas", []) if store == "consum" else group.get("sellers", [])
        if not isinstance(entries, list):
            raise StoreError("La tienda no ha devuelto una cobertura válida.")
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            if store == "consum":
                zone = entry.get("zone") or {}
                identifier = entry.get("shippingZoneId")
                if (entry.get("enabled") is not True or entry.get("deliveryTypeId") != "D"
                    or not isinstance(zone, dict) or not valid_area(store, identifier)
                    or str(zone.get("id", "")) + "D" != identifier):
                    continue
                address = zone.get("address") or {}
                city = str(address.get("city", ""))[:80] if isinstance(address, dict) else ""
                name = str(zone.get("name") or f"Centro {zone['id']}")[:120]
                areas[identifier] = {"id": identifier, "name": f"{name} · {city}" if city else name, "zone": str(zone["id"])}
            else:
                identifier = entry.get("id")
                if valid_area(store, identifier):
                    areas[identifier] = {"id": identifier, "name": f"Centro {identifier.removeprefix('lasirena')}"}
    return sorted(areas.values(), key=lambda area: area["id"])


async def async_resolve_areas(hass, store, postal_code):
    if store not in REGIONAL_STORES or not isinstance(postal_code, str) or not re.fullmatch(POSTAL_PATTERN, postal_code):
        raise StoreError("Introduce un código postal español válido de cinco cifras.")
    if store == "dia":
        try:
            return await hass.async_add_executor_job(resolve_dia_postal,postal_code)
        except DiaError as err:
            raise StoreError(str(err)) from err
    if store == "eroski":
        client = EroskiClient(hass)
        try:
            areas = pickup_areas(await client.selection(postal_code))
            if not areas:
                raise StoreError("Eroski no ha devuelto centros de recogida disponibles.")
            return {"postal_code":postal_code, "areas":areas}
        except (EroskiError, aiohttp.ClientError, asyncio.TimeoutError, ValueError) as err:
            raise StoreError(str(err) if isinstance(err,(EroskiError,StoreError)) else "No se ha podido consultar Eroski.") from err
        finally:
            client.close()
    url = ("https://tienda.consum.es/api/rest/V1.0/shipping/area?" + urlencode({"shippingMethod":"D", "zipCode":postal_code})
        if store == "consum" else "https://www.lasirena.es/es/api/checkout/pub/regions?" + urlencode({"country":"ESP", "postalCode":postal_code, "sc":"1"}))
    session = async_create_clientsession(hass, auto_cleanup=False, cookie_jar=aiohttp.DummyCookieJar())
    try:
        async with session.get(url, headers={"Accept":"application/json", "User-Agent":"Improved-Shopping-List",
            **({"x-tol-app":"shop-front", "x-tol-channel":"1", "x-tol-locale":"es"} if store == "consum" else {})},
            timeout=aiohttp.ClientTimeout(total=25), allow_redirects=False) as response:
            if response.status != 200:
                raise StoreError(f"{REGIONAL_STORES[store]} no ha podido verificar la cobertura (HTTP {response.status}).")
            raw = bytearray()
            async for chunk in response.content.iter_chunked(8192):
                raw.extend(chunk)
                if len(raw) > 262144:
                    raise StoreError("La respuesta de cobertura es demasiado grande.")
        areas = coverage_areas(store, json.loads(raw))
        if not areas:
            raise StoreError(f"{REGIONAL_STORES[store]} no ofrece entrega para este código postal.")
        return {"postal_code":postal_code, "areas":areas}
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as err:
        if isinstance(err, StoreError):
            raise
        raise StoreError(f"No se ha podido comprobar la cobertura de {REGIONAL_STORES[store]}.") from err
    finally:
        session.detach()
