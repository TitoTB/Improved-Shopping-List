/** Shared list settings; entity contents remain owned by native todo providers. */
const PREFIX = "improved_shopping_list/settings/";

export const DEFAULT_APPEARANCE = Object.freeze({ gradient_start: "#ee524f", gradient_end: "#b52a27", completed_gradient_start: "#4faba2", completed_gradient_end: "#26857c", columns: 3, mobile_columns: 1 });

export function gradientTextColor(start, end) {
  // Keep the requested white foreground on the default completed gradient.
  if (start.toLowerCase() === DEFAULT_APPEARANCE.completed_gradient_start &&
      end.toLowerCase() === DEFAULT_APPEARANCE.completed_gradient_end) return "#ffffff";
  const luminance = color => {
    const channels = color.match(/[a-f\d]{2}/gi).map(channel => parseInt(channel, 16) / 255)
      .map(value => value <= .04045 ? value / 12.92 : ((value + .055) / 1.055) ** 2.4);
    return channels[0] * .2126 + channels[1] * .7152 + channels[2] * .0722;
  };
  const values = [luminance(start), luminance(end)];
  return 1.05 / (Math.max(...values) + .05) >= (Math.min(...values) + .05) / .05 ? "#ffffff" : "#000000";
}

export class ListSettingsSession {
  constructor(getHass, onChange, prefix = PREFIX) {
    this.prefix = prefix;
    this.getHass = getHass;
    this.onChange = onChange;
    this.entities = [];
    this.primary = "";
    this.stores = {};
    this.favoriteStore = "";
    this.appearance = { ...DEFAULT_APPEARANCE };
    this.loaded = false;
    this.loading = false;
    this.error = "";
    this._generation = 0;
    this._revision = 0;
  }

  _receive(data) {
    this.entities = data.entities ?? [];
    this.primary = data.primary_entity ?? "";
    this.stores = data.stores ?? {};
    this.favoriteStore = data.favorite_store ?? "";
    this.priceUpdateTime = data.price_update_time ?? "01:00";
    this.appearance = { ...DEFAULT_APPEARANCE, ...data.appearance };
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
      }, { type: `${this.prefix}subscribe` });
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
      const data = await this.getHass().callWS({ type: `${this.prefix}get` });
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

  async saveAppearance(appearance) {
    const generation = this._generation;
    const revision = ++this._revision;
    const data = await this.getHass().callWS({ type: `${PREFIX}personalization`, appearance });
    if (generation === this._generation && revision === this._revision) this._receive(data);
  }

  async saveStore(enabled, postalCode, verify = false) {
    const generation = this._generation;
    const revision = ++this._revision;
    const data = await this.getHass().callWS({ type: `${PREFIX}store`, store: "mercadona", enabled, postal_code: postalCode, verify });
    if (generation === this._generation && revision === this._revision) this._receive(data);
  }

  async saveCarrefour(enabled, salePoint) {
    const generation = this._generation, revision = ++this._revision;
    const data = await this.getHass().callWS({type:`${PREFIX}store`,store:"carrefour",enabled,...(salePoint === undefined ? {} : {sale_point:salePoint})});
    if (generation === this._generation && revision === this._revision) this._receive(data);
  }

  async saveFavoriteStore(store) {
    const generation = this._generation, revision = ++this._revision;
    const data = await this.getHass().callWS({type:`${PREFIX}favorite_store`,store});
    if (generation === this._generation && revision === this._revision) this._receive(data);
  }

  async saveAlcampo(enabled, regionId) {
    const generation = this._generation, revision = ++this._revision;
    const data = await this.getHass().callWS({type:`${PREFIX}store`,store:"alcampo",enabled,region_id:regionId});
    if (generation === this._generation && revision === this._revision) this._receive(data);
  }

  async savePriceSchedule(time) {
    const generation = this._generation, revision = ++this._revision;
    const data = await this.getHass().callWS({type:`${PREFIX}price_schedule`,time});
    if (generation === this._generation && revision === this._revision) this._receive(data);
  }

  async saveLidl(enabled, regionId) {
    const generation = this._generation, revision = ++this._revision;
    const data = await this.getHass().callWS({type:`${PREFIX}store`,store:"lidl",enabled,region_id:regionId});
    if (generation === this._generation && revision === this._revision) this._receive(data);
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
