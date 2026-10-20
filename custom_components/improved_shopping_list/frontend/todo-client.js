/** Native Home Assistant APIs; the selected provider owns all list data. */
export const FEATURES = Object.freeze({ CREATE: 1, UPDATE: 4 });

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
  constructor(getHass, onChange) {
    this.getHass = getHass;
    this.onChange = onChange;
    this.entityId = "";
    this.items = [];
    this.loading = false;
    this.error = "";
    this._generation = 0;
    this._revision = 0;
  }

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
    return this._mutate("add_item", { item }, FEATURES.CREATE);
  }

  async setCompleted(item, completed) {
    // Use the provider UID: names need not be unique.
    if (!item.uid) throw new Error("Este producto no tiene un identificador válido.");
    return this._mutate("update_item", {
      item: item.uid, status: completed ? "completed" : "needs_action",
    }, FEATURES.UPDATE);
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
