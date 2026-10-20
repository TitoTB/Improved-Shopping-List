import assert from "node:assert/strict";
import { test } from "node:test";
import { FEATURES, TodoSession, isAvailable, supports, todoEntities } from "../custom_components/improved_shopping_list/frontend/todo-client.js";

const deferred = () => {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
};

function fixture() {
  const calls = [];
  const listeners = [];
  const hass = {
    states: {
      "todo.bring": { entity_id: "todo.bring", state: "0", attributes: { friendly_name: "Compra Bring", supported_features: 5 } },
      "todo.local": { entity_id: "todo.local", state: "0", attributes: { friendly_name: "Casa", supported_features: 5 } },
    },
    callWS: async () => ({ items: [] }),
    callService: async (...args) => { calls.push(args); },
    connection: {
      subscribeMessage: async (callback, message) => {
        const subscription = { callback, message, stopped: false };
        listeners.push(subscription);
        return () => { subscription.stopped = true; };
      },
    },
  };
  const session = new TodoSession(() => hass, () => {});
  return { hass, session, calls, listeners };
}

test("discovers every todo provider and respects capability flags", () => {
  const { hass } = fixture();
  hass.states["sensor.other"] = { entity_id: "sensor.other", attributes: {} };
  assert.deepEqual(todoEntities(hass).map((state) => state.entity_id), ["todo.local", "todo.bring"]);
  assert.equal(supports(hass.states["todo.bring"], FEATURES.CREATE), true);
  assert.equal(isAvailable({ state: "unavailable" }), false);
  assert.equal(isAvailable(undefined), false);
});

test("writes to the native provider, trims input and uses UID for equal names", async () => {
  const { session, calls } = fixture();
  await session.select("todo.bring");
  await session.add("  Cacao  ");
  await session.setCompleted({ uid: "second-cacao", summary: "Cacao" }, true);
  await session.setCompleted({ uid: "second-cacao", summary: "Cacao" }, false);
  assert.deepEqual(calls, [
    ["todo", "add_item", { item: "Cacao", entity_id: "todo.bring" }],
    ["todo", "update_item", { item: "second-cacao", status: "completed", entity_id: "todo.bring" }],
    ["todo", "update_item", { item: "second-cacao", status: "needs_action", entity_id: "todo.bring" }],
  ]);
  assert.equal(await session.add("   "), false);
  session.dispose();
});

test("blocks unsupported and unavailable mutations without sending requests", async () => {
  const { hass, session, calls } = fixture();
  await session.select("todo.bring");
  hass.states["todo.bring"].attributes.supported_features = 0;
  await assert.rejects(session.add("Cacao"), /no admite/);
  hass.states["todo.bring"].state = "unavailable";
  await assert.rejects(session.setCompleted({ uid: "1" }, true), /no está disponible/);
  assert.equal(calls.length, 0);
  session.dispose();
});

test("a slow old-list response cannot overwrite the newly selected list", async () => {
  const { hass, session, listeners } = fixture();
  const oldRead = deferred();
  hass.callWS = ({ entity_id }) => entity_id === "todo.bring"
    ? oldRead.promise : Promise.resolve({ items: [{ uid: "new", summary: "Nueva lista" }] });
  const first = session.select("todo.bring");
  await session.select("todo.local");
  oldRead.resolve({ items: [{ uid: "old", summary: "Lista anterior" }] });
  await first;
  listeners[0].callback({ items: [{ uid: "late-event" }] });
  assert.equal(session.entityId, "todo.local");
  assert.equal(session.items[0].uid, "new");
  assert.equal(listeners[0].stopped, true);
  session.dispose();
});

test("push updates win over an older read even when pending count is unchanged", async () => {
  const { hass, session, listeners } = fixture();
  const read = deferred();
  hass.callWS = () => read.promise;
  const selecting = session.select("todo.bring");
  await Promise.resolve();
  listeners[0].callback({ items: [{ uid: "1", summary: "Nombre actualizado" }] });
  read.resolve({ items: [{ uid: "1", summary: "Nombre anterior" }] });
  await selecting;
  assert.equal(session.items[0].summary, "Nombre actualizado");
  session.dispose();
});

test("pending subscription is cleaned up if the panel closes before it resolves", async () => {
  const { hass, session } = fixture();
  const subscription = deferred();
  let stopped = false;
  hass.connection.subscribeMessage = () => subscription.promise;
  const selecting = session.select("todo.bring");
  session.dispose();
  subscription.resolve(() => { stopped = true; });
  await selecting;
  assert.equal(stopped, true);
});

test("failed subscriptions retain a manual read and a disposable fallback", async () => {
  const { hass, session } = fixture();
  hass.connection.subscribeMessage = async () => { throw new Error("Provider starting"); };
  hass.callWS = async () => ({ items: [{ uid: "1", summary: "Cacao" }] });
  await session.select("todo.bring");
  assert.equal(session.items[0].summary, "Cacao");
  assert.ok(session._timer);
  session.dispose();
  assert.equal(session._timer, undefined);
});

test("provider errors propagate and do not report successful mutations", async () => {
  const { hass, session } = fixture();
  await session.select("todo.bring");
  hass.callService = async () => { throw new Error("Bring no responde"); };
  await assert.rejects(session.add("Cacao"), /Bring no responde/);
  session.dispose();
});
