"""Bounded anonymous HTTP alternative for explicitly supported public stores."""
from asyncio import sleep
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from importlib import import_module
import time
from urllib.parse import urlsplit

from .store_links import HOSTS

MAX_BYTES = 2 * 1024 * 1024
SUPPORTED = frozenset({'carrefour', 'alcampo', 'elcorteingles'})


def retry_seconds(value):
    """Respect both Retry-After formats, within the existing daily bound."""
    try:
        delay = int(value)
    except (TypeError, ValueError):
        try:
            delay = int(parsedate_to_datetime(value).timestamp() - time.time())
        except (TypeError, ValueError, OverflowError):
            delay = 900
    return min(86400, max(900, delay))


class PublicHTTPError(ValueError):
    """A public transport error; never carries cookies or response bodies."""


@dataclass(frozen=True)
class Response:
    status: int
    headers: dict
    body: bytes


async def fetch(hass, store, url, before_request, *, headers=None):
    """Make one paced request, without redirects, account state or retries."""
    parsed = urlsplit(url)
    if (store not in SUPPORTED or parsed.scheme != 'https'
            or parsed.hostname not in HOSTS[store] or parsed.port not in (None, 443)
            or parsed.username is not None or parsed.password is not None):
        raise PublicHTTPError('El enlace público no es válido.')
    # Import native libraries outside Core's event loop. No browser is needed.
    requests = await hass.async_add_executor_job(import_module, 'curl_cffi.requests')
    await sleep(20)
    await before_request()
    try:
        async with requests.AsyncSession(impersonate='chrome') as session:
            response = await session.get(url, headers={
                'Accept-Language': 'es-ES,es;q=0.9', **(headers or {})},
                timeout=20, allow_redirects=False, stream=True)
            try:
                body = bytearray()
                async for chunk in response.aiter_content():
                    body.extend(chunk)
                    if len(body) > MAX_BYTES:
                        raise PublicHTTPError('La ficha supera el tamaño máximo permitido.')
                return Response(response.status_code,
                    {key.lower(): value for key, value in response.headers.items()}, bytes(body))
            finally:
                await response.aclose()
    except PublicHTTPError:
        raise
    except Exception as err:
        # Native transport exceptions can include URLs; do not expose their text.
        raise PublicHTTPError('No se ha podido conectar con la ficha pública.') from err
