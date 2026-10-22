"""Authorization boundaries, redaction, daily sync and recoverable uploads."""

import asyncio
from copy import deepcopy
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from aiohttp import ClientConnectionError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.improved_shopping_list.const import DOMAIN, CONF_TODO_ENTITY
from custom_components.improved_shopping_list.community_sync import CommunitySync, CommunityError, DATA_URL, API
from custom_components.improved_shopping_list.community_data import fingerprint, MARKER, CLIENT_ID
from custom_components.improved_shopping_list import community_sync as module


@pytest.fixture
async def shared(hass, monkeypatch):
    clock = [1792600000]
    monkeypatch.setattr(module, "time", SimpleNamespace(time=lambda:clock[0], monotonic=lambda:clock[0]))
    catalog = SimpleNamespace(products=[], async_apply_community=AsyncMock())
    icons = SimpleNamespace(_assets={})
    prices = SimpleNamespace(_data={"pending": []}, _preparing=0, _notify=Mock(), prices_for=Mock(return_value=[]), async_apply_revocations=AsyncMock())
    lookup = SimpleNamespace(cached=Mock(return_value=None))
    service = CommunitySync(hass, catalog, icons, prices, lookup)
    await service.async_load()
    service._active = True
    yield SimpleNamespace(service=service, clock=clock, catalog=catalog, icons=icons, prices=prices)
    await service.async_stop()


def credentials():
    return {"access_token": "ghu_PRIVATE_ACCESS", "refresh_token": "ghr_PRIVATE_REFRESH", "expires_in": 28800}


@pytest.mark.parametrize("retry_delay", [0,86400])
async def test_device_authorization_keeps_credentials_on_server_and_honors_poll_interval(shared, monkeypatch, retry_delay):
    service = shared.service
    retry_at=shared.clock[0]+retry_delay
    service._data["next_upload_attempt"]=retry_at
    device = {"device_code": "PRIVATE_DEVICE", "user_code": "ABCD-EFGH", "interval": 5, "expires_in": 900}
    service._request = AsyncMock(side_effect=[device, {"error":"authorization_pending"}, {"error":"slow_down"}, credentials(), {"login":"tester", "id":123}])
    service._queue = Mock()
    gate = asyncio.Event()
    async def pause(_interval):
        await gate.wait()
    sleep = AsyncMock(side_effect=pause)
    monkeypatch.setattr(module.asyncio, "sleep", sleep)
    status = await service.async_sharing(True)
    assert status["authorization"]["user_code"] == "ABCD-EFGH"
    assert "PRIVATE_DEVICE" not in json.dumps(status)
    gate.set()
    await service._auth
    assert [call.args[0] for call in sleep.await_args_list] == [5, 5, 10]
    assert service.snapshot["connected"] and service.snapshot["account"] == "tester"
    assert "PRIVATE" not in json.dumps(service.snapshot)
    assert service._data["credentials"]["access_token"] == "ghu_PRIVATE_ACCESS"
    assert service._request.await_args_list[0].kwargs["data"]["client_id"] == CLIENT_ID
    assert all("client_secret" not in call.kwargs.get("data", {}) for call in service._request.await_args_list)
    service._queue.assert_called_once_with(immediate_upload=True)
    assert service._data["next_upload_attempt"] == retry_at


async def test_enabling_sharing_uploads_now_despite_store_batch_and_keeps_daily_limit(shared):
    service=shared.service
    service._data.update(credentials={**credentials(),"expires_at":shared.clock[0]+1000},account="tester")
    shared.prices._data["pending"]=[{"reference":"pending"}]
    shared.prices._preparing=1
    posts=[]
    async def request(method,url,**kwargs):
        assert url != DATA_URL  # An immediate contribution does not consume another public read.
        if method == "GET":return []
        posts.append(url)
        return {"number":17}
    service._request=AsyncMock(side_effect=request)
    await service.async_sharing(True)
    await service._task
    assert service._data["last_upload"] == shared.clock[0]
    assert len(posts) == 2  # One batch: manifest issue and its data fragment.
    calls=service._request.await_count
    await service.async_sharing(False)
    service._data.update(credentials={**credentials(),"expires_at":shared.clock[0]+1000},account="tester")
    await service.async_sharing(True)
    await service._task
    assert service._request.await_count == calls
    shared.clock[0]+=module.DAY
    service._data["credentials"]["expires_at"]=shared.clock[0]+1000
    await service.async_sharing(True)
    await service._task
    assert len(posts) == 4


async def test_activation_during_existing_sync_is_not_lost_or_duplicated(shared):
    service=shared.service
    gate=asyncio.Event()
    started=asyncio.Event()
    calls=[]
    async def sync(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            started.set()
            await gate.wait()
    service.async_sync=AsyncMock(side_effect=sync)
    service._queue()
    await started.wait()
    service._queue(immediate_upload=True)
    service._queue(immediate_upload=True)
    gate.set()
    await service._task
    assert calls == [{"immediate_upload":False},{"immediate_upload":True}]


async def test_immediate_activation_preserves_retry_pause(shared):
    service=shared.service
    service._data.update(credentials=credentials(),account="tester",next_upload_attempt=shared.clock[0]+module.DAY)
    service._request=AsyncMock(side_effect=AssertionError("No request during retry pause"))
    await service.async_sharing(True)
    await service._task
    service._request.assert_not_awaited()


async def test_disable_cancels_authorization_and_forgets_local_credentials(shared):
    service = shared.service
    service._data.update(sharing=True, account="tester", credentials=credentials(), outbox={"private":"payload"})
    service._device = {"user_code":"ABCD-EFGH"}
    service._auth = asyncio.create_task(asyncio.Event().wait())
    result = await service.async_sharing(False)
    assert service._auth.cancelled()
    assert not result["sharing"] and not result["connected"] and result["authorization"] is None
    stored = await service._store.async_load()
    assert stored["credentials"] == {} and stored["outbox"] is None and stored["account"] == ""


async def test_refresh_rotates_and_persists_tokens_without_shared_secret(shared):
    service = shared.service
    service._data["credentials"] = {**credentials(), "expires_at": 0}
    service._request = AsyncMock(return_value={"access_token":"ghu_ROTATED", "refresh_token":"ghr_ROTATED", "expires_in":28800})
    assert await service._access_token() == "ghu_ROTATED"
    data = service._request.await_args.kwargs["data"]
    assert data == {"client_id":CLIENT_ID, "grant_type":"refresh_token", "refresh_token":"ghr_PRIVATE_REFRESH"}
    assert (await service._store.async_load())["credentials"]["refresh_token"] == "ghr_ROTATED"
    assert "ROTATED" not in json.dumps(service.snapshot)


async def test_payload_allowlist_excludes_personal_fields_unknown_images_and_borrowed_votes(shared):
    service = shared.service
    shared.catalog.products = [{"name":"Arroz", "name_en":"Rice", "barcode":"8410109115543", "barcodes":[],
        "notes":"PRIVATE", "nfc_tags":["PRIVATE"], "reader_actions":{"PRIVATE":"stock_add"},
        "category":"PRIVATE", "recurrence":{"days":10}, "image_url":"https://private.test/photo.png",
        "community_fields":{"name_en":fingerprint("Rice")}, "store_links":{}}]
    result = service.payload()
    assert "PRIVATE" not in json.dumps(result) and "private.test" not in json.dumps(result)
    assert result["products"][0]["icons"] == []
    assert result["products"][0]["borrowed_fields"] == ["name_en"]
    assert result["products"][0]["eans"] == ["08410109115543"]


async def test_daily_download_attempt_is_durable_and_reading_does_not_require_consent(shared, hass):
    service = shared.service
    data = {"schema":2, "reference_version":1, "generated_at":shared.clock[0], "products":[]}
    service._request = AsyncMock(return_value=data)
    await service.async_sync()
    await service.async_sync()
    service._request.assert_awaited_once_with("GET", DATA_URL, limit=16*1024*1024)
    assert not service.snapshot["sharing"]
    restored = CommunitySync(hass, shared.catalog, shared.icons, shared.prices, service.lookup)
    await restored.async_load(); restored._active = True
    restored._request = AsyncMock(side_effect=AssertionError("No second daily read"))
    await restored.async_sync()
    restored._request.assert_not_awaited()
    await restored.async_stop()


async def test_failed_download_retains_cache_and_limits_retries(shared):
    service = shared.service
    previous = deepcopy(service.dictionary)
    service._request = AsyncMock(side_effect=ClientConnectionError("PRIVATE RESPONSE"))
    await service.async_sync(); await service.async_sync()
    assert service.dictionary == previous and service._request.await_count == 1
    assert "PRIVATE" not in json.dumps(service.snapshot)


async def test_upload_recovers_accepted_comment_without_duplicate_after_lost_response(shared):
    service = shared.service
    service._data.update(sharing=True, account="tester", credentials={**credentials(), "expires_at":shared.clock[0]+1000})
    comments = []
    created_issues = []
    async def request(method, url, **kwargs):
        if method == "GET" and "/issues?" in url: return []
        if method == "POST" and url.endswith("/issues"):
            created_issues.append(kwargs["data"]); return {"number":17}
        if method == "GET": return deepcopy(comments)
        if method == "POST":
            comments.append(kwargs["data"])
            raise ClientConnectionError("response lost")
    service._request = AsyncMock(side_effect=request)
    with pytest.raises(ClientConnectionError): await service._upload()
    assert service._data["outbox"]["issue"] == 17
    await service._upload()
    assert len(created_issues) == 1 and len(comments) == 1
    assert service._data["outbox"] is None and service._data["last_upload"] == shared.clock[0]
    assert created_issues[0]["body"].startswith(MARKER)
    before = service._request.await_count
    await service._upload()
    assert service._request.await_count == before


async def test_community_admin_commands_do_not_expose_credentials_to_other_users(hass, hass_ws_client, hass_read_only_user, aioclient_mock):
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_TODO_ENTITY:"todo.bring"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    refresh = await hass.auth.async_create_refresh_token(hass_read_only_user, client_id="http://test.local")
    client = await hass_ws_client(hass, hass.auth.async_create_access_token(refresh))
    for i, command in enumerate(({"type":f"{DOMAIN}/community/status"},
                                 {"type":f"{DOMAIN}/community/sharing", "enabled":True}), 1):
        await client.send_json({"id":i, **command})
        assert (await client.receive_json())["error"]["code"] == "unauthorized"
    assert aioclient_mock.call_count == 0
