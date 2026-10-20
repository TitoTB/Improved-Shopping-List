"""Best-effort Spanish to English names for later icon searches."""

from html import unescape
import json

from aiohttp import ClientError, ClientTimeout
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import VERSION

URL = "https://api.mymemory.translated.net/get"
MAX_BYTES = 32768


async def async_translate_name(hass: HomeAssistant, name: str) -> str:
    """Return a validated translation, never a provider error as a product name."""
    if not name.strip() or len(name.encode("utf-8")) > 500:
        return ""
    try:
        async with async_get_clientsession(hass).get(
            URL, params={"q": name, "langpair": "es|en"},
            allow_redirects=False, timeout=ClientTimeout(total=5),
            headers={"User-Agent": f"ImprovedShoppingList/{VERSION}"},
        ) as response:
            if response.status != 200:
                return ""
            body = bytearray()
            async for chunk in response.content.iter_chunked(4096):
                body.extend(chunk)
                if len(body) > MAX_BYTES:
                    return ""
            data = json.loads(body)
        if not isinstance(data, dict) or str(data.get("responseStatus")) != "200" or data.get("quotaFinished"):
            return ""
        result = data.get("responseData")
        text = result.get("translatedText") if isinstance(result, dict) else None
        if not isinstance(text, str):
            return ""
        text = unescape(text).strip()
        if not text or len(text) > 300 or any(ord(char) < 32 for char in text):
            return ""
        return text
    except (ClientError, TimeoutError, ValueError, UnicodeError):
        return ""
