"""Anonymous Mercadona postal-code discovery; no customer account is used."""

import asyncio
import json
import re

import aiohttp

from homeassistant.helpers.aiohttp_client import async_create_clientsession

POSTAL_URL = "https://tienda.mercadona.es/api/postal-codes/actions/change-pc/"


class StoreError(ValueError):
    """A store configuration cannot be verified."""


async def async_resolve_mercadona(hass, postal_code: str) -> str:
    """Resolve an actual warehouse from response headers, never a fallback."""
    if not re.fullmatch(r"(?:0[1-9]|[1-4][0-9]|5[0-2])[0-9]{3}", postal_code):
        raise StoreError("Introduce un código postal español válido de cinco cifras.")
    # Isolate cookies and detach afterward without closing HA's shared connector.
    session = async_create_clientsession(hass, auto_cleanup=False, cookie_jar=aiohttp.DummyCookieJar())
    try:
        async with session.put(
            POSTAL_URL, json={"new_postal_code": postal_code},
            headers={"Accept": "application/json"},
            timeout=aiohttp.ClientTimeout(total=15), allow_redirects=False,
        ) as response:
            if response.status in (400, 404, 422):
                raise StoreError("Mercadona no ha confirmado el servicio para este código postal.")
            if response.status != 200:
                raise StoreError("Mercadona no está disponible. Vuelve a intentarlo más tarde.")
            body = bytearray()
            async for chunk in response.content.iter_chunked(8192):
                body.extend(chunk)
                if len(body) > 65536:
                    raise StoreError("La respuesta de Mercadona no es válida.")
            data = json.loads(body)
            warehouse = response.headers.get("x-customer-wh", "")
            returned_postal = response.headers.get("x-customer-pc", postal_code)
            if (not isinstance(data, dict) or type(data.get("warehouse_changed")) is not bool
                or not re.fullmatch(r"[a-zA-Z0-9_-]{1,32}", warehouse)
                or returned_postal != postal_code):
                raise StoreError("Mercadona no ha devuelto un almacén válido para este código postal.")
            return warehouse
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as err:
        if isinstance(err, StoreError):
            raise
        raise StoreError("No se ha podido consultar Mercadona. Revisa la conexión y vuelve a intentarlo.") from err
    finally:
        session.detach()
