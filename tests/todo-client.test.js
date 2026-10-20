import assert from "node:assert/strict";
import { test } from "node:test";
import { FEATURES, TodoSession, isAvailable, supports, todoEntities } from "../custom_components/improved_shopping_list/frontend/todo-client.js";
import { productNameKey } from "../custom_components/improved_shopping_list/frontend/product-names.js";

const deferred = () => {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
};

test("product names compare without accents, case, compatibility or spacing differences", () => {
  assert.equal(productNameKey("  SEITA\u0301N  "), productNameKey("Seitán"));
  assert.equal(productNameKey("ＣＡＦÉ   molido"), productNameKey("cafe molido"));
  assert.notEqual(productNameKey("Leche entera"), productNameKey("Leche sin lactosa"));
});

test("renames suggestion UIDs on their original list without sending status or other fields", async () => {
  const {hass,session,calls} = fixture();
  const items = [{uid:"first",summary:"Seitan",status:"completed",description:"Keep me"}, {uid:"second",summary:"SEITÁN",status:"needs_action"}];
  hass.callWS = async ({entity_id}) => ({items:entity_id === "todo.bring" ? structuredClone(items) : []});
  await session.select("todo.local");
  assert.equal(await session.renameFromSuggestion({entityId:"todo.bring",items},"Seitán"),2);
  assert.deepEqual(calls,[
    ["todo","update_item",{entity_id:"todo.bring",item:"first",rename:"Seitán"}],
    ["todo","update_item",{entity_id:"todo.bring",item:"second",rename:"Seitán"}],
  ]);
  assert.equal(session.entityId,"todo.local");
  assert.deepEqual(session.items,[]);
  session.dispose();
});

test("rename retry skips removed or already renamed items and rejects concurrent unrelated changes", async () => {
  const {hass,session,calls} = fixture();
  const source={entityId:"todo.bring",items:[{uid:"gone",summary:"Seitan"},{uid:"done",summary:"Seitan"},{uid:"pending",summary:"Seitan"}]};
  let items=[{uid:"done",summary:"Seitán"},{uid:"pending",summary:"Arroz"}];
  hass.callWS=async()=>({items});
  await assert.rejects(session.renameFromSuggestion(source,"Seitán"),/otra sesión/);
  assert.equal(calls.length,0);
  items[1].summary="SEITAN";
  assert.equal(await session.renameFromSuggestion(source,"Seitán"),1);
  assert.equal(calls[0][2].item,"pending");
});

test("rename validates capabilities and propagates provider errors for retry", async () => {
  const {hass,session,calls}=fixture();
  const source={entityId:"todo.bring",items:[{uid:"a",summary:"Seitan"}]};
  hass.states['todo.bring'].attributes.supported_features=0;
  await assert.rejects(session.renameFromSuggestion(source,"Seitán"),/no permite renombrar/);
  hass.states['todo.bring'].attributes.supported_features=5;
  hass.callWS=async()=>({items:source.items});
  hass.callService=async()=>{throw new Error("Provider failed");};
  await assert.rejects(session.renameFromSuggestion(source,"Seitán"),/Provider failed/);
  assert.equal(calls.length,0);
});

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

test("adding checks fresh names without accents or case and reuses completed UIDs", async () => {
  const {hass,session,calls}=fixture();
  await session.select("todo.bring");
  let items=[{uid:"existing",summary:"  SEITÁN  ",status:"needs_action"}];
  hass.callWS=async()=>({items:structuredClone(items)});
  await session.add("Seitan");
  assert.equal(calls.length,0);
  items[0].status="completed";
  await session.add("Seitan");
  assert.deepEqual(calls,[["todo","update_item",{entity_id:"todo.bring",item:"existing",status:"needs_action"}]]);
  session.dispose();
});

test("simultaneous equivalent additions share one write and a failure permits retry", async () => {
  const {hass,session,calls}=fixture();
  await session.select("todo.bring");
  const read=deferred();
  hass.callWS=()=>read.promise;
  const first=session.add("Seitán");
  const second=session.add("SEITAN");
  read.resolve({items:[]});
  await Promise.all([first,second]);
  assert.equal(calls.length,1);
  hass.callWS=async()=>{throw new Error("Lectura fallida");};
  await assert.rejects(session.add("Arroz"),/Lectura fallida/);
  hass.callWS=async()=>({items:[]});
  await session.add("Arroz");
  assert.equal(calls.length,2);
  session.dispose();
});

test("a delayed add keeps its original list and refuses to duplicate completed items without update support", async () => {
  const {hass,session,calls}=fixture();
  await session.select("todo.bring");
  const read=deferred();
  hass.callWS=({entity_id})=>entity_id==="todo.bring"?read.promise:Promise.resolve({items:[]});
  const adding=session.add("Cacao");
  await session.select("todo.local");
  read.resolve({items:[]});
  await adding;
  assert.equal(calls[0][2].entity_id,"todo.bring");
  hass.states['todo.local'].attributes.supported_features=1;
  hass.callWS=async()=>({items:[{uid:"done",summary:"Pan",status:"completed"}]});
  await assert.rejects(session.add("Pan"),/no admite/);
  assert.equal(calls.length,1);
  session.dispose();
});

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

test("clearing completed delegates to the native action on the selected list only", async () => {
  const {hass,session,calls}=fixture();
  hass.states['todo.bring'].attributes.supported_features=7;
  await session.select('todo.bring');
  assert.equal(await session.clearCompleted(),true);
  assert.deepEqual(calls,[["todo","remove_completed_items",{entity_id:"todo.bring"}]]);
  session.dispose();
});

test("clearing completed respects availability, delete capability and provider errors", async () => {
  const {hass,session,calls}=fixture();
  await session.select('todo.bring');
  await assert.rejects(session.clearCompleted(),/no admite/);
  assert.equal(calls.length,0);
  hass.states['todo.bring'].attributes.supported_features=7;
  hass.states['todo.bring'].state='unavailable';
  await assert.rejects(session.clearCompleted(),/no está disponible/);
  hass.states['todo.bring'].state='1';
  hass.callService=async()=>{throw new Error('Provider failed');};
  await assert.rejects(session.clearCompleted(),/Provider failed/);
  session.dispose();
});

test("a pending clear cannot refresh or change a newly selected list", async () => {
  const {hass,session,calls}=fixture();
  const mutation=deferred();
  hass.states['todo.bring'].attributes.supported_features=7;
  hass.callService=(...args)=>{calls.push(args);return mutation.promise;};
  await session.select('todo.bring');
  const clearing=session.clearCompleted();
  await session.select('todo.local');
  mutation.resolve();
  await clearing;
  assert.equal(session.entityId,'todo.local');
  assert.equal(calls[0][2].entity_id,'todo.bring');
  session.dispose();
});
