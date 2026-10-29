/** Native Home Assistant APIs; the selected provider owns all list data. */
import { productNameKey, todoItemName, namedTodoItem } from "./product-names.js?v=0.48.0";
export const FEATURES = Object.freeze({ CREATE: 1, DELETE: 2, UPDATE: 4, DESCRIPTION: 64 });

export function todoEntities(hass) {
  return Object.values(hass?.states ?? {})
    .filter((state) => state.entity_id.startsWith("todo."))
    .sort((a, b) => (a.attributes.friendly_name ?? a.entity_id)
      .localeCompare(b.attributes.friendly_name ?? b.entity_id, "es"));
}

export function isAvailable(state) {
  return Boolean(state && !["unavailable", "unknown"].includes(state.state));
}

export function supports(state, feature) {
  return Boolean(Number(state?.attributes.supported_features ?? 0) & feature);
}

export function errorMessage(error) {
  const detail = error?.message ?? String(error ?? "Error desconocido");
  return `No se ha podido completar la operación. ${detail}`;
}

export class TodoSession {
  constructor(getHass, onChange, getDescriptionMode=()=>false) {
    this.getHass = getHass;
    this.onChange = onChange;
    this.getDescriptionMode = getDescriptionMode;
    this.entityId = "";
    this.items = [];
    this.loading = false;
    this.error = "";
    this._generation = 0;
    this._revision = 0;
    this._pendingAdds = new Map();
  }

  get items() { return this.getDescriptionMode(this.entityId)?this._items.map(item=>namedTodoItem(item,true)):this._items; }
  set items(value) { this._items=value; }

  async select(entityId) {
    this._stop();
    const generation = this._generation;
    this.entityId = entityId;
    this.items = [];
    this.error = "";
    this.loading = Boolean(entityId);
    this.onChange();
    if (!entityId) return;

    // Start a read even if subscribing fails (e.g. a provider is starting up).
    const initialRead = this.refresh();
    try {
      const unsubscribe = await this.getHass().connection.subscribeMessage(
        (result) => {
          if (generation !== this._generation) return;
          this._revision += 1;
          this.items = result.items ?? [];
          this.error = "";
          this.loading = false;
          this.onChange();
        },
        { type: "todo/item/subscribe", entity_id: entityId },
      );
      if (generation !== this._generation) {
        this._unsubscribeSafely(unsubscribe);
      } else {
        this._unsubscribe = unsubscribe;
      }
    } catch {
      // Some providers are temporarily unavailable during startup. Keep a
      // visible-panel fallback, without polling a cloud provider ourselves.
      if (generation === this._generation) {
        this._timer = setInterval(() => {
          if (globalThis.document?.visibilityState !== "hidden") void this.refresh();
        }, 30000);
      }
    }
    await initialRead;
  }

  async refresh() {
    if (!this.entityId) return;
    const generation = this._generation;
    const revision = ++this._revision;
    try {
      const result = await this.getHass().callWS({
        type: "todo/item/list", entity_id: this.entityId,
      });
      if (generation !== this._generation || revision !== this._revision) return;
      this.items = result.items ?? [];
      this.error = "";
    } catch (error) {
      if (generation !== this._generation || revision !== this._revision) return;
      this.error = errorMessage(error);
    } finally {
      if (generation === this._generation && revision === this._revision) {
        this.loading = false;
        this.onChange();
      }
    }
  }

  async add(summary) {
    const item = summary.trim();
    if (!item) return false;
    const entityId = this.entityId;
    const generation = this._generation;
    const key = JSON.stringify([entityId, productNameKey(item)]);
    if (this._pendingAdds.has(key)) return this._pendingAdds.get(key);
    const operation = (async () => {
      const validate = feature => {
        const state = this.getHass().states[entityId];
        if (!isAvailable(state)) throw new Error("La lista seleccionada no está disponible.");
        if (!supports(state, feature)) throw new Error("Esta lista no admite esa operación.");
      };
      validate(FEATURES.CREATE);
      const useDescription=Boolean(this.getDescriptionMode(entityId));
      // Read the provider before writing: the panel snapshot may be out of date.
      const {items} = await this.getHass().callWS({type:"todo/item/list",entity_id:entityId});
      if (!Array.isArray(items)) throw new Error("No se ha podido comprobar el contenido de la lista.");
      if(Boolean(this.getDescriptionMode(entityId))!==useDescription)throw new Error('Los ajustes de nombres han cambiado. Vuelve a intentarlo.');
      const matches = items.filter(value => productNameKey(todoItemName(value,useDescription)) === productNameKey(item));
      if (!matches.some(value => value.status !== "completed")) {
        const completed = matches.find(value => value.uid && value.status === "completed");
        if (matches.length && !completed) throw new Error("El producto de la lista no tiene un identificador válido.");
        validate(completed ? FEATURES.UPDATE : FEATURES.CREATE);
        await this.getHass().callService("todo", completed ? "update_item" : "add_item", completed
          ? {entity_id:entityId,item:completed.uid,status:"needs_action"}
          : {entity_id:entityId,item});
      }
      if (generation === this._generation) await this.refresh();
      return true;
    })();
    this._pendingAdds.set(key, operation);
    try { return await operation; }
    finally { if (this._pendingAdds.get(key) === operation) this._pendingAdds.delete(key); }
  }

  async setCompleted(item, completed) {
    // Use the provider UID: names need not be unique.
    if (!item.uid) throw new Error("Este producto no tiene un identificador válido.");
    return this._mutate("update_item", {
      item: item.uid, status: completed ? "completed" : "needs_action",
    }, FEATURES.UPDATE);
  }

  async clearCompleted() {
    return this._mutate("remove_completed_items", {}, FEATURES.DELETE);
  }

  async renameFromSuggestion(source, summary) {
    const name = summary.trim();
    const candidates = source.items.filter(item => String(item.summary ?? "").trim() !== name);
    if (!candidates.length) return 0;
    const entityId = source.entityId;
    const useDescription=Boolean(this.getDescriptionMode(entityId));
    const generation = this._generation;
    const state = this.getHass().states[entityId];
    if (!isAvailable(state)) throw new Error("La lista de origen no está disponible.");
    if (!supports(state, FEATURES.UPDATE)) throw new Error("La lista de origen no permite renombrar productos.");
    if (candidates.some(item => !item.uid)) throw new Error("El producto de la lista no tiene un identificador válido.");
    const {items} = await this.getHass().callWS({type:"todo/item/list",entity_id:entityId});
    if(Boolean(this.getDescriptionMode(entityId))!==useDescription)throw new Error('Los ajustes de nombres han cambiado. Vuelve a intentarlo.');
    const updates = [];
    for (const original of new Map(candidates.map(item => [item.uid,item])).values()) {
      const current = items.find(item => item.uid === original.uid);
      // A removed item stays removed. Successful earlier renames are safe to retry.
      if (!current || todoItemName(current,useDescription) === name) continue;
      if (productNameKey(todoItemName(current,useDescription)) !== productNameKey(todoItemName(original,useDescription))) {
        throw new Error("El producto de la lista ha cambiado en otra sesión. Revisa su nombre antes de continuar.");
      }
      const clearDescription=useDescription&&Boolean(current.description);
      if(clearDescription&&!supports(state,FEATURES.DESCRIPTION))throw new Error('La lista no permite actualizar la segunda línea del producto.');
      updates.push({uid:current.uid,clearDescription});
    }
    for (const {uid,clearDescription} of updates) await this.getHass().callService("todo","update_item",{entity_id:entityId,item:uid,rename:name,...(clearDescription?{description:''}:{})});
    if (generation === this._generation && this.entityId === entityId) await this.refresh();
    return updates.length;
  }

  async _mutate(service, data, feature) {
    const entityId = this.entityId;
    const generation = this._generation;
    const state = this.getHass().states[entityId];
    if (!isAvailable(state)) throw new Error("La lista seleccionada no está disponible.");
    if (!supports(state, feature)) throw new Error("Esta lista no admite esa operación.");
    await this.getHass().callService("todo", service, { ...data, entity_id: entityId });
    if (generation === this._generation) await this.refresh();
    return true;
  }

  dispose() {
    this._stop();
  }

  _stop() {
    this._generation += 1;
    this._revision += 1;
    clearInterval(this._timer);
    this._timer = undefined;
    if (this._unsubscribe) this._unsubscribeSafely(this._unsubscribe);
    this._unsubscribe = undefined;
  }

  _unsubscribeSafely(unsubscribe) {
    try {
      Promise.resolve(unsubscribe()).catch(() => {});
    } catch { /* A closed WebSocket has already discarded its subscriptions. */ }
  }
}
