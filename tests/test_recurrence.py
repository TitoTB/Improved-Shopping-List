"""Durable recurrence timing and native provider mutations without an open panel."""

import asyncio
from copy import deepcopy
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from homeassistant.core import SupportsResponse
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.improved_shopping_list import catalog as catalog_module, recurrence as module
from custom_components.improved_shopping_list.catalog import Catalog, CatalogError, FIELDS, normalize_product
from custom_components.improved_shopping_list.const import CONF_TODO_ENTITY, DOMAIN
from custom_components.improved_shopping_list.list_settings import ListSettings
from custom_components.improved_shopping_list.recurrence import DAY, RecurrenceManager


@pytest.fixture
async def env(hass, monkeypatch):
    clock = [1800000000.0]

    class ClockDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.fromtimestamp(clock[0], tz)

    monkeypatch.setattr(catalog_module, "datetime", ClockDateTime)
    monkeypatch.setattr(module, "time", SimpleNamespace(time=lambda: clock[0]))
    hass.states.async_set("todo.main", "0", {"supported_features": 5})
    hass.states.async_set("todo.other", "0", {"supported_features": 5})
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_TODO_ENTITY: "todo.main"})
    entry.add_to_hass(hass)
    settings = ListSettings(hass)
    settings.attach(entry)
    catalog = Catalog(hass)
    await catalog.async_load()
    activity = SimpleNamespace(record=Mock())
    manager = RecurrenceManager(hass, catalog, settings, activity, asyncio.Lock())
    await manager.async_load()
    manager._active = True
    state = SimpleNamespace(manager=manager, catalog=catalog, settings=settings, clock=clock, activity=activity,
                            items={"todo.main": [], "todo.other": []}, calls=[], fail=False, delay=False,
                            entered=asyncio.Event(), resume=asyncio.Event())

    async def get_items(call):
        if state.delay:
            state.entered.set()
            await state.resume.wait()
        return {call.data["entity_id"]: {"items": deepcopy(state.items[call.data["entity_id"]])}}

    async def add_item(call):
        if state.fail:
            raise RuntimeError("Provider offline")
        state.calls.append(("add", dict(call.data)))
        state.items[call.data["entity_id"]].append({"uid": "p1", "summary": call.data["item"], "status": "needs_action"})

    async def update_item(call):
        state.calls.append(("update", dict(call.data)))
        next(item for item in state.items[call.data["entity_id"]] if item["uid"] == call.data["item"])["status"] = "needs_action"

    hass.services.async_register("todo", "get_items", get_items, supports_response=SupportsResponse.ONLY)
    hass.services.async_register("todo", "add_item", add_item)
    hass.services.async_register("todo", "update_item", update_item)
    yield state
    await manager.async_stop()


async def recurring(env, **changes):
    return await env.catalog.async_save_product({"name": "Seitán", "recurrence": {"enabled": True, "days": 3}, **changes})


def edit(product, **changes):
    return {**{key: value for key, value in product.items() if key in FIELDS}, **changes}


@pytest.mark.parametrize("recurrence", [None, {}, {"enabled": 1, "days": 3}, {"enabled": True, "days": True},
    {"enabled": True, "days": 0}, {"enabled": True, "days": 3651}, {"enabled": True, "days": 1.5},
    {"enabled": True, "days": "3"}, {"enabled": True, "days": 3, "next_due": 0}])
def test_invalid_recurrence(recurrence):
    with pytest.raises(CatalogError):
        normalize_product({"name": "Cacao", "recurrence": recurrence})


async def test_first_due_resets_and_survives_reload(env, hass):
    product = await recurring(env)
    await env.manager.async_check()
    assert env.calls == []
    assert env.manager._schedules[product["id"]]["next_due"] == env.clock[0] + 3 * DAY
    env.clock[0] += 3 * DAY + 1
    await asyncio.gather(env.manager.async_check(), env.manager.async_check())
    assert len(env.calls) == 1 and env.calls[0][1]["entity_id"] == "todo.main"
    due = env.manager._schedules[product["id"]]["next_due"]
    assert due == env.clock[0] + 3 * DAY
    restored = RecurrenceManager(hass, env.catalog, env.settings, env.activity, asyncio.Lock())
    await restored.async_load()
    assert restored._schedules[product["id"]]["next_due"] == due
    env.items["todo.main"].clear()
    env.clock[0] += 60
    await env.manager.async_check()
    assert len(env.calls) == 1


async def test_pending_deduplicates_accents_and_restarts_period(env):
    product = await recurring(env)
    env.items["todo.main"] = [{"uid": "existing", "summary": " SEITAN ", "status": "needs_action"}]
    env.clock[0] += 3 * DAY
    await env.manager.async_check()
    assert env.calls == []
    assert env.manager._schedules[product["id"]]["next_due"] == env.clock[0] + 3 * DAY
    assert env.activity.record.call_args.args[0] == "recurrence.pending"


async def test_completed_is_restored_by_uid(env):
    await recurring(env)
    env.items["todo.main"] = [{"uid": "existing", "summary": "Seitán", "status": "completed"}]
    env.clock[0] += 3 * DAY
    await env.manager.async_check()
    assert env.calls == [("update", {"entity_id": "todo.main", "item": "existing", "status": "needs_action"})]
    assert len(env.items["todo.main"]) == 1


async def test_provider_failure_keeps_due_and_retries(env):
    product = await recurring(env)
    env.clock[0] += 3 * DAY
    env.fail = True
    await env.manager.async_check()
    assert env.manager._schedules[product["id"]]["next_due"] == env.clock[0]
    assert env.calls == []
    env.fail = False
    env.clock[0] += 60
    await env.manager.async_check()
    assert env.calls == []
    env.clock[0] += 241
    await env.manager.async_check()
    assert len(env.calls) == 1
    assert env.manager._schedules[product["id"]]["next_due"] == env.clock[0] + 3 * DAY


async def test_old_client_and_other_edits_do_not_reset_but_changed_days_do(env):
    product = await recurring(env)
    anchor = product["recurrence_started_at"]
    env.clock[0] += DAY
    payload = edit(product, notes="Changed")
    del payload["recurrence"]
    product = await env.catalog.async_save_product(payload)
    assert product["recurrence_started_at"] == anchor
    assert product["recurrence"] == {"enabled": True, "days": 3}
    product = await env.catalog.async_save_product(edit(product, recurrence={"enabled": True, "days": 5}))
    assert product["recurrence_started_at"] != anchor
    await env.manager.async_check()
    assert env.manager._schedules[product["id"]]["next_due"] == env.clock[0] + 5 * DAY
    await env.catalog.async_save_product(edit(product, recurrence={"enabled": False, "days": 5}))
    await env.manager.async_check()
    assert env.manager._schedules == {}


async def test_primary_change_during_read_does_not_write_old_list(env):
    await recurring(env)
    env.clock[0] += 3 * DAY
    env.delay = True
    task = asyncio.create_task(env.manager.async_check())
    await env.entered.wait()
    env.settings.update("primary", "todo.other")
    env.resume.set()
    await task
    assert env.calls == []


async def test_readonly_list_and_missing_update_support_do_not_duplicate(env, hass):
    await recurring(env)
    hass.states.async_set("todo.main", "0", {"supported_features": 1})
    env.items["todo.main"] = [{"uid": "existing", "summary": "Seitán", "status": "completed"}]
    env.clock[0] += 3 * DAY
    await env.manager.async_check()
    assert env.calls == []
    assert env.activity.record.call_args.args[0] == "recurrence.error"


async def test_start_processes_overdue_without_panel_and_stop_cleans_up(env, hass):
    await recurring(env)
    env.manager._active = False
    env.clock[0] += 30 * DAY
    env.manager.start()
    await hass.async_block_till_done()
    assert len(env.calls) == 1  # Missed periods never create a backlog of purchases.
    await env.manager.async_stop()
    env.items["todo.main"].clear()
    env.clock[0] += 30 * DAY
    env.manager._queue()
    await hass.async_block_till_done()
    assert len(env.calls) == 1
