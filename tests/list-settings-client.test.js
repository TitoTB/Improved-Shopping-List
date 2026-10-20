import assert from "node:assert/strict";
import test from "node:test";
import { DEFAULT_APPEARANCE, ListSettingsSession, gradientTextColor } from "../custom_components/improved_shopping_list/frontend/list-settings-client.js";

const deferred = () => {
  let resolve;
  const promise = new Promise(done => { resolve = done; });
  return { promise, resolve };
};

test("personalization defaults and readable text for custom gradients", () => {
  assert.equal(gradientTextColor("#ee524f", "#b52a27"), "#ffffff");
  assert.equal(gradientTextColor("#ffe082", "#ffb300"), "#000000");
  assert.equal(gradientTextColor("#111111", "#222222"), "#ffffff");
  const session = new ListSettingsSession(() => ({}), () => {});
  assert.deepEqual(session.appearance, DEFAULT_APPEARANCE);
  session._receive({entities:[], primary_entity:""});
  assert.deepEqual(session.appearance, DEFAULT_APPEARANCE);
  session._receive({appearance:{...DEFAULT_APPEARANCE,columns:6}});
  assert.equal(session.appearance.columns, 6);
  session._receive({appearance:{gradient_start:"#123456",gradient_end:"#abcdef",columns:2,mobile_columns:2}});
  assert.equal(session.appearance.completed_gradient_start, "#4faba2");
  assert.equal(session.appearance.completed_gradient_end, "#26857c");
  assert.equal(session.appearance.gradient_start, "#123456");
});

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
