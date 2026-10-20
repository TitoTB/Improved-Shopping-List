/** Shared list settings; entity contents remain owned by native todo providers. */
const PREFIX = "improved_shopping_list/settings/";

export class ListSettingsSession {
  constructor(getHass, onChange) {
    this.getHass = getHass;
    this.onChange = onChange;
    this.entities = [];
    this.primary = "";
    this.loaded = false;
    this.loading = false;
    this.error = "";
    this._generation = 0;
    this._revision = 0;
  }

  _receive(data) {
    this.entities = data.entities ?? [];
    this.primary = data.primary_entity ?? "";
    this.loaded = true;
    this.loading = false;
    this.error = "";
    this.onChange();
  }

  async start() {
    this.stop();
    const generation = this._generation;
    this.loading = true;
    this.error = "";
    this.onChange();
    const initial = this.refresh();
    try {
      const unsubscribe = await this.getHass().connection.subscribeMessage(data => {
        if (generation !== this._generation) return;
        this._revision += 1;
        this._receive(data);
      }, { type: `${PREFIX}subscribe` });
      if (generation !== this._generation) this._unsubscribeSafely(unsubscribe);
      else this._unsubscribe = unsubscribe;
    } catch (error) {
      if (generation === this._generation) {
        this.error = error.message ?? "No se han podido sincronizar los ajustes.";
        this.onChange();
      }
    }
    await initial;
  }

  async refresh() {
    const generation = this._generation;
    const revision = ++this._revision;
    try {
      const data = await this.getHass().callWS({ type: `${PREFIX}get` });
      if (generation === this._generation && revision === this._revision) this._receive(data);
    } catch (error) {
      if (generation === this._generation && revision === this._revision) {
        this.error = error.message ?? "No se han podido cargar los ajustes.";
        this.loading = false;
        this.onChange();
      }
    }
  }

  async update(action, entityId) {
    const generation = this._generation;
    const revision = ++this._revision;
    const data = await this.getHass().callWS({ type: `${PREFIX}update`, action, entity_id: entityId });
    if (generation === this._generation && revision === this._revision) this._receive(data);
    // A newer pushed snapshot takes precedence over this response.
  }

  stop() {
    this._generation += 1;
    this._revision += 1;
    if (this._unsubscribe) this._unsubscribeSafely(this._unsubscribe);
    this._unsubscribe = undefined;
  }

  _unsubscribeSafely(unsubscribe) {
    try { Promise.resolve(unsubscribe()).catch(() => {}); } catch { /* Disconnected. */ }
  }
}
