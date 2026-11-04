"""Anonymous fallback: bounded transfers, pacing and URL restrictions."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from custom_components.improved_shopping_list import public_http as module

URL='https://www.carrefour.es/supermercado/pavo/R-prod1/p'


@pytest.fixture
def native(monkeypatch):
    response=SimpleNamespace(status_code=200,headers={'Content-Type':'text/html'},aclose=AsyncMock())
    async def chunks():
        yield b'product'
    response.aiter_content=chunks
    session=SimpleNamespace(get=AsyncMock(return_value=response))
    class Context:
        async def __aenter__(self):return session
        async def __aexit__(self,*args):pass
    factory=lambda **kwargs:Context()
    hass=SimpleNamespace(async_add_executor_job=AsyncMock(return_value=SimpleNamespace(AsyncSession=factory)))
    monkeypatch.setattr(module,'sleep',AsyncMock())
    return hass,session,response


async def test_fallback_is_paced_anonymous_and_never_follows_redirects(native):
    hass,session,response=native;before=AsyncMock()
    result=await module.fetch(hass,'carrefour',URL,before)
    assert result.body==b'product' and result.headers['content-type']=='text/html'
    module.sleep.assert_awaited_once_with(20)
    before.assert_awaited_once()
    kwargs=session.get.call_args.kwargs
    assert kwargs['allow_redirects'] is False and kwargs['stream'] is True
    assert 'Cookie' not in kwargs['headers'] and 'Authorization' not in kwargs['headers']
    response.aclose.assert_awaited_once()


@pytest.mark.parametrize('url',['http://www.carrefour.es/x','https://127.0.0.1/x',
    'https://www.carrefour.es.evil.test/x','https://user:secret@www.carrefour.es/x','https://www.carrefour.es:8123/x'])
async def test_untrusted_urls_are_rejected_before_loading_native_library(native,url):
    hass,_,_=native
    with pytest.raises(module.PublicHTTPError):await module.fetch(hass,'carrefour',url,AsyncMock())
    hass.async_add_executor_job.assert_not_awaited()


async def test_oversized_response_is_closed(native,monkeypatch):
    hass,_,response=native;monkeypatch.setattr(module,'MAX_BYTES',3)
    with pytest.raises(module.PublicHTTPError,match='tamaño'):
        await module.fetch(hass,'carrefour',URL,AsyncMock())
    response.aclose.assert_awaited_once()
