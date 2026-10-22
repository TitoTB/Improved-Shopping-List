/** Catalog data lives in Home Assistant storage, shared by every panel session. */
const PREFIX = "improved_shopping_list/catalog/";

export class CatalogSession {
  constructor(getHass, onChange) {
    this.getHass = getHass;
    this.onChange = onChange;
    this.products = [];
    this.categories = [];
    this.dismissedSuggestions = [];
    this.loading = false;
    this.error = "";
    this._generation = 0;
    this._revision = 0;
  }

  async start() {
    this.stop();
    const generation = this._generation;
    this.loading = true;
    this.error = "";
    this.onChange();
    const initialRead = this.refresh();
    try {
      const unsubscribe = await this.getHass().connection.subscribeMessage((data) => {
        if (generation !== this._generation) return;
        this._revision += 1;
        this.products = data.products ?? [];
        this.categories = data.categories ?? [];
        this.dismissedSuggestions = data.dismissed_suggestions ?? [];
        this.loading = false;
        this.error = "";
        this.onChange();
      }, { type: `${PREFIX}subscribe` });
      if (generation !== this._generation) this._unsubscribeSafely(unsubscribe);
      else this._unsubscribe = unsubscribe;
    } catch (error) {
      if (generation === this._generation) {
        this.error = error.message ?? "No se ha podido conectar con el catálogo.";
        this.onChange();
      }
    }
    await initialRead;
  }

  async refresh() {
    const generation = this._generation;
    const revision = ++this._revision;
    try {
      const data = await this.getHass().callWS({ type: `${PREFIX}get` });
      if (generation !== this._generation || revision !== this._revision) return;
      this.products = data.products ?? [];
      this.categories = data.categories ?? [];
      this.dismissedSuggestions = data.dismissed_suggestions ?? [];
      this.error = "";
    } catch (error) {
      if (generation !== this._generation || revision !== this._revision) return;
      this.error = error.message ?? "No se ha podido cargar el catálogo.";
    } finally {
      if (generation === this._generation && revision === this._revision) {
        this.loading = false;
        this.onChange();
      }
    }
  }

  async save(product) {
    const generation = this._generation;
    const result = await this.getHass().callWS({ type: `${PREFIX}save`, product });
    if (generation === this._generation) await this.refresh();
    return result.product;
  }

  async setSeasonMonths(productId, months, enabled) {
    const generation = this._generation;
    await this.getHass().callWS({type: `${PREFIX}season_months`, product_id: productId, months, enabled});
    if (generation === this._generation) await this.refresh();
  }

  async saveCategory(category) {
    const generation = this._generation;
    const result = await this.getHass().callWS({ type: `${PREFIX}category/save`, category });
    if (generation === this._generation) await this.refresh();
    return result.category;
  }

  async deleteProduct(product) {
    const generation = this._generation;
    await this.getHass().callWS({ type: `${PREFIX}delete`, product_id: product.id, revision: product.revision });
    if (generation === this._generation) await this.refresh();
  }

  async deleteCategory(category) {
    const generation = this._generation;
    await this.getHass().callWS({ type: `${PREFIX}category/delete`, category_id: category.id, revision: category.revision });
    if (generation === this._generation) await this.refresh();
  }

  async actOnSuggestion(name, action) {
    const generation = this._generation;
    const result = await this.getHass().callWS({ type: `${PREFIX}suggestion`, name, action });
    if (generation === this._generation) await this.refresh();
    return result.product;
  }

  stop() {
    this._generation += 1;
    this._revision += 1;
    if (this._unsubscribe) this._unsubscribeSafely(this._unsubscribe);
    this._unsubscribe = undefined;
  }

  _unsubscribeSafely(unsubscribe) {
    try { Promise.resolve(unsubscribe()).catch(() => {}); } catch { /* Already disconnected. */ }
  }
}
