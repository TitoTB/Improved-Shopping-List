import assert from "node:assert/strict";
import test from "node:test";
import { ListSettingsSession } from "../custom_components/improved_shopping_list/frontend/list-settings-client.js";

const deferred = () => {
  let resolve;
  const promise = new Promise(done => { resolve = done; });
  return { promise, resolve };
};

test("a pushed settings snapshot beats an older initial read", async () => {
  const read = deferred();
  let callback;
  let unsubscribed = 0;
  const hass = {
    callWS: () => read.promise,
    connection: { subscribeMessage: async listener => {
      callback = listener;
      listener({entities:["todo.b"], primary_entity:"todo.b"});
      return () => { unsubscribed++; };
    } },
  };
  const session = new ListSettingsSession(() => hass, () => {});
  const starting = session.start();
  read.resolve({entities:["todo.a"], primary_entity:"todo.a"});
  await starting;
  assert.equal(session.primary, "todo.b");
  session.stop();
  callback({entities:["todo.a"], primary_entity:"todo.a"});
  assert.equal(session.primary, "todo.b");
  assert.equal(unsubscribed, 1);
});

test("a later push beats a mutation response and errors allow retry", async () => {
  let callback;
  let fail = false;
  const mutation = deferred();
  const hass = {
    callWS: async message => {
      if (message.type.endsWith("/get")) return {entities:["todo.a"], primary_entity:"todo.a"};
      if (fail) throw new Error("Save failed");
      return mutation.promise;
    },
    connection: { subscribeMessage: async listener => { callback = listener; return () => {}; } },
  };
  const session = new ListSettingsSession(() => hass, () => {});
  await session.start();
  fail = true;
  await assert.rejects(session.update("remove", "todo.a"), /Save failed/);
  assert.equal(session.primary, "todo.a");
  fail = false;
  const updating = session.update("add", "todo.b");
  callback({entities:["todo.a","todo.b"], primary_entity:"todo.b"});
  mutation.resolve({entities:["todo.a","todo.b"], primary_entity:"todo.a"});
  await updating;
  assert.equal(session.primary, "todo.b");
  session.stop();
});
