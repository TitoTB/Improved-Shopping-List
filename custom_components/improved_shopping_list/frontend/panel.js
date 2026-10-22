import { StockSession } from "./stock-client.js?v=0.28.0";
import { QuantitySession, purchaseQuantity, quantityLabel } from "./quantity-client.js?v=0.28.0";
import { installDialogCloseButtons } from "./dialog-controls.js?v=0.28.0";
import { FEATURES, TodoSession, errorMessage, isAvailable, supports } from "./todo-client.js?v=0.28.0";
import { imageSource, normalizedName, productNameKey, cachedProductPrice } from "./catalog-panel.js?v=0.28.0";
import { ListSettingsSession, gradientTextColor } from "./list-settings-client.js?v=0.28.0";
import "./settings-panel.js?v=0.28.0";
import { ReadersSession } from "./readers-client.js?v=0.28.0";
import "./purchases-panel.js?v=0.28.0";

const LOGO_URL = new URL("logo.png", import.meta.url).href;
const STORE_LOGOS = {
  dia:new URL("dia.png", import.meta.url).href,
  eroski:new URL("eroski.svg", import.meta.url).href,
  consum:new URL("consum.jpg", import.meta.url).href,
  lasirena:new URL("lasirena.jpg", import.meta.url).href,
  mercadona:new URL("mercadona.png", import.meta.url).href,
  carrefour:"https://images.seeklogo.com/logo-png/31/2/carrefour-logo-png_seeklogo-318190.png",
  alcampo:"https://almeria.online/wp-content/uploads/2024/09/alcampo-logo.png",
};
const STORE_NAMES = {mercadona:"Mercadona",carrefour:"Carrefour",alcampo:"Alcampo",consum:"Consum",lasirena:"La Sirena",eroski:"Eroski",dia:"DIA"};
const searchText = value => normalizedName(value).normalize("NFD").replace(/\p{M}/gu, "");
const stockRemaining = (item, now=Date.now()/1000) => {
  if (item.quantity <= 0 || item.expired) return 0;
  if (item.expires_at && item.expires_at <= now) return 0;
  return Math.max(0,Math.min(100,item.quantity/(item.refill_quantity??1)*100));
};

class ImprovedShoppingListPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._session = new TodoSession(() => this._hass, () => this._renderData());
    this._settings = new ListSettingsSession(() => this._hass, () => this._applySettings());
    this._readers = new ReadersSession(() => this._hass, () => this._renderData());
    this._stock = new StockSession(() => this._hass, () => this._renderData());
    this._quantities = new QuantitySession(() => this._hass, () => this._renderData());
    this._stockLayout = "grid";
    this._stockView = "stock";
    this._stockSort = "lowest";
    this._stockGrouped = false;
    this._listGrouped = false;
    try {
      this._stockGrouped = localStorage.getItem("isl-stock-grouped") === "true";
      this._listGrouped = localStorage.getItem("isl-list-grouped") === "true";
    } catch { /* Storage disabled. */ }
    try { if (localStorage.getItem("isl-stock-layout") === "rows") this._stockLayout = "rows"; } catch { /* Storage disabled. */ }
    try { if (localStorage.getItem("isl-stock-sort") === "alphabetical") this._stockSort = "alphabetical"; } catch { /* Storage disabled. */ }
    if(this._stockGrouped)this._stockSort="alphabetical";
    this._busy = false;
    this._rows = new Map();
    this._catalogProducts = new Map();
    this._catalogCategories = new Map();
    this._view = "shopping";
    this._listLayout = "grid";
    this._ticket = false;
    this._ticketStore = "";
    try { if (localStorage.getItem("isl-list-layout") === "rows") this._listLayout = "rows"; } catch { /* Storage may be disabled. */ }
    this._rowPrices = [];
    this._nutrition = new Map();
    this._onVisibility = () => {
      if (document.visibilityState === "visible") {
        void this._session.refresh();
        void this._settings.refresh();
        void this._readers.refresh();
        void this._stock.refresh();
        void this._quantities.refresh();
        void this._refreshRowPrices();
      }
    };
  }

  set hass(value) {
    const previousHass = this._hass;
    const previousConnection = this._hass?.connection;
    const signature = JSON.stringify(Object.values(value.states ?? {}).filter(state => state.entity_id.startsWith("todo."))
      .map(state => [state.entity_id, state.attributes.friendly_name, isAvailable(state), state.attributes.supported_features])
      .sort((a, b) => a[0].localeCompare(b[0])));
    const changed = signature !== this._todoStatesSignature || previousHass?.user !== value.user ||
      previousHass?.states[this._session.entityId] !== value.states[this._session.entityId];
    this._todoStatesSignature = signature;
    this._hass = value;
    if (previousConnection !== value.connection) { this._stopRowPrices(); this._stopListNutrition(); }
    if (!this.isConnected) return;
    if (this._built) this.shadowRoot.querySelector("isl-catalog").hass = value;
    this._ensureStarted();
    if (this._view === "settings") this.shadowRoot.querySelector("isl-settings").hass = value;
    if (previousConnection && previousConnection !== value.connection) {
      void this._settings.start();
      void this._readers.start();
      void this._stock.start();
      void this._quantities.start();
      if (this._session.entityId) void this._session.select(this._session.entityId);
    }
    if (changed || previousConnection !== value.connection) this._renderData();
  }

  set panel(value) {
    this._panel = value;
    this._ensureStarted();
  }

  set narrow(value) {
    this.toggleAttribute("narrow", Boolean(value));
  }

  connectedCallback() {
    if (!this._built) this._build();
    document.addEventListener("visibilitychange", this._onVisibility);
    this._started = false;
    this._ensureStarted();
    clearInterval(this._stockClock);
    this._stockClock = setInterval(()=>{if(this._view === "stock" && document.visibilityState === "visible")this._renderData();},60000);
  }

  disconnectedCallback() {
    clearInterval(this._stockClock);
    document.removeEventListener("visibilitychange", this._onVisibility);
    this._session.dispose();
    this._settings.stop();
    this._readers.stop();
    this._stock.stop();
    this._quantities.stop();
    this._stopRowPrices();
    this._stopListNutrition();
    this._settingsApplied = false;
    this._started = false;
    this.shadowRoot.querySelector("#list-dialog")?.close();
    this.shadowRoot.querySelector("#stock-remove-dialog")?.close();
    this.shadowRoot.querySelector("#stock-editor-dialog")?.close();
    this.shadowRoot.querySelector("#stock-add-dialog")?.close();
  }

  _ensureStarted() {
    if (!this.isConnected || !this._built || !this._hass || !this._panel || this._started) return;
    this._started = true;
    void this._settings.start();
    void this._readers.start();
    void this._stock.start();
    void this._quantities.start();
  }

  _applySettings() {
    if (!this._built || !this._hass) return;
    const settings = this._settings;
    if (settings.loaded) {
      if (!this._settingsApplied || settings.primary !== this._previousPrimary ||
          (this._session.entityId && !settings.entities.includes(this._session.entityId))) {
        this._settingsApplied = true;
        this._previousPrimary = settings.primary;
        void this._session.select(settings.primary);
      }
    }
    this._renderData();
    void this._refreshRowPrices();
  }

  _build() {
    // All dynamic product names and provider messages are inserted as text.
    this.shadowRoot.innerHTML = `
      <style>
        :host { display:block; height:100%; overflow:auto; color:var(--primary-text-color,#20352d); background:var(--primary-background-color,#f5f7f5); font-family:var(--paper-font-body1_-_font-family,system-ui,sans-serif); --isl-green:#267052; }
        * { box-sizing:border-box; }
        button,input,select { font:inherit; }
        button { cursor:pointer; }
        button:disabled { cursor:default; opacity:.5; }
        button:focus-visible,input:focus-visible,select:focus-visible,summary:focus-visible { outline:3px solid var(--primary-color,#267052); outline-offset:3px; }
        header { display:flex; align-items:center; gap:12px; padding:16px 24px; border-bottom:1px solid var(--divider-color,#dfe7e1); background:transparent; }
        .menu { border:0; background:transparent; color:inherit; padding:8px; width:44px; height:44px; display:none; }
        :host([narrow]) .menu { display:inline-flex; align-items:center; justify-content:center; }
        .branding { display:flex; align-items:center; gap:10px; min-width:0; }
        .brand-copy { min-width:0; }
        .brand { font-size:16px; font-weight:650; }
        .brand-logo { width:44px; height:44px; object-fit:contain; flex-shrink:0; }
        .version { color:var(--secondary-text-color,#63766b); font-size:12px; margin-left:8px; white-space:nowrap; }
        .section-nav { display:flex; flex-wrap:wrap; gap:8px; margin-left:auto; }
        .section-nav button { display:inline-flex; align-items:center; gap:8px; padding:10px 12px; min-height:44px; border:0; border-radius:10px; color:var(--secondary-text-color,#63766b); background:transparent; }
        .section-nav button[aria-pressed=true] { background:var(--secondary-background-color,#edf4ee); color:var(--primary-text-color,#20352d); font-weight:650; }
        .section-nav ha-icon { --mdc-icon-size:20px; }
        main { max-width:900px; margin:auto; padding:36px 24px 64px; }
        .card { background:var(--card-background-color,#fff); border:1px solid var(--divider-color,#dfe7e1); border-radius:18px; padding:22px; margin-bottom:18px; }
        .label { display:block; font-size:13px; font-weight:650; margin:0 0 10px; }
        select,input { color:inherit; background:var(--secondary-background-color,#f6f8f6); border:1px solid var(--divider-color,#dfe7e1); border-radius:10px; min-height:48px; padding:10px 12px; min-width:0; }
        select { width:100%; }
        .refresh { flex-shrink:0; min-width:48px; border:1px solid var(--divider-color,#dfe7e1); border-radius:10px; background:transparent; color:inherit; }
        .helper { font-size:12px; color:var(--secondary-text-color,#63766b); line-height:1.6; margin:10px 0 0; }
        #list-controls { margin-bottom:24px; }
        #add-form { display:flex; align-items:center; gap:8px; margin:0; }
        .icon-button { display:inline-flex; align-items:center; justify-content:center; flex:0 0 48px; width:48px; height:48px; padding:0; border:1px solid var(--divider-color,#dfe7e1); border-radius:10px; color:inherit; background:var(--card-background-color,#fff); }
        #add-button, #add-stock, #upload-ticket { padding:0; align-self:auto; color:#fff; background:var(--isl-green); border:0; }
        .icon-button ha-icon { --mdc-icon-size:24px; }
        dialog { color:inherit; background:var(--card-background-color,#fff); border:1px solid var(--divider-color,#dfe7e1); border-radius:18px; padding:24px; width:min(460px,calc(100vw - 28px)); max-height:calc(100dvh - 28px); }
        dialog::backdrop { background:rgba(0,0,0,.4); }
        #list-options { display:grid; gap:8px; margin-top:20px; }
        .list-option { display:flex; align-items:center; gap:12px; width:100%; min-height:48px; padding:12px; border:1px solid var(--divider-color,#dfe7e1); border-radius:10px; color:inherit; background:transparent; text-align:left; overflow-wrap:anywhere; }
        .list-option span { flex:1; min-width:0; }
        .list-option[aria-pressed=true] { border-color:var(--isl-green); background:var(--secondary-background-color,#edf4ee); }
        .list-option ha-icon { flex-shrink:0; --mdc-icon-size:22px; }
        .dialog-actions { display:flex; justify-content:flex-end; gap:10px; margin-top:22px; }
        .dialog-actions button { padding:10px 14px; min-height:44px; border:1px solid var(--divider-color,#dfe7e1); border-radius:10px; color:inherit; background:transparent; }
        .input-wrap { flex:1; min-width:0; position:relative; }
        .predictive-results { position:absolute; top:calc(100% + 6px); left:0; right:0; z-index:10; max-height:320px; overflow:auto; padding:6px; background:var(--card-background-color,#fff); border:1px solid var(--divider-color,#dfe7e1); border-radius:12px; box-shadow:0 8px 24px rgba(0,0,0,.14); }
        .predictive-option { display:flex; align-items:center; gap:10px; padding:10px; min-height:54px; border-radius:8px; cursor:pointer; }
        .predictive-option:hover,.predictive-option[aria-selected=true] { background:var(--secondary-background-color,#edf4ee); }
        .predictive-image { width:36px; height:36px; object-fit:contain; flex-shrink:0; display:grid; place-items:center; }
        .predictive-image ha-icon { --mdc-icon-size:28px; }
        .predictive-text { min-width:0; overflow-wrap:anywhere; font-size:14px; }
        .predictive-text strong { display:block; }
        .predictive-text small { display:block; color:var(--secondary-text-color,#63766b); margin-top:3px; }
        input[type=text] { width:100%; }
        .primary { min-height:48px; padding:10px 20px; border:0; border-radius:10px; color:white; background:var(--isl-green); font-weight:650; align-self:end; }
        .list-header { display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:12px; margin-bottom:14px; }
        .list-totals { display:flex; align-items:center; gap:8px; margin-left:auto; }
        .list-totals .count { white-space:nowrap; }
        button.count { border:0; color:inherit; display:inline-flex; align-items:center; gap:7px; height:34px; }
        #pending-total[aria-expanded=false] { background:#fff; color:#000; font-weight:700; }
        #pending-count[aria-pressed=false] { background:#ee524f; color:#fff; font-weight:700; }
        .store-logo { width:24px; height:24px; object-fit:contain; background:white; padding:3px; border-radius:50%; flex:none; }
        #receipt { max-width:760px; margin:0 auto; }
        #receipt[hidden], #pending[hidden] { display:none; }
        .receipt-stores { display:flex; gap:6px; margin-bottom:16px; container-type:inline-size; }
        .receipt-stores button { display:flex; flex:1; min-width:0; justify-content:center; align-items:center; gap:clamp(2px,1cqi,8px); border:1px solid var(--divider-color,#dfe7e1); border-radius:12px; padding:10px clamp(2px,1cqi,10px); background:var(--card-background-color,#fff); color:inherit; font-size:clamp(10px,2.5cqi,14px); }
        .receipt-stores .store-logo { width:clamp(16px,4cqi,24px); height:clamp(16px,4cqi,24px); padding:2px; }
        .receipt-stores button[aria-pressed=true] { border-color:var(--primary-color,#267052); box-shadow:inset 0 0 0 1px var(--primary-color,#267052); }
        .receipt-store-copy { min-width:0; text-align:left; font-variant-numeric:tabular-nums; }
        .receipt-store-copy span { display:inline-block; white-space:nowrap; }
        .receipt-store-amount { font-weight:700; }
        .receipt-store-coverage { opacity:.6; }
        .receipt-paper { background:var(--card-background-color,#fff); border:1px solid var(--divider-color,#dfe7e1); border-radius:12px; padding:20px; }
        .receipt-row { display:flex; justify-content:space-between; gap:16px; padding:12px 0; border-bottom:1px dashed var(--divider-color,#dfe7e1); }
        .receipt-name { min-width:0; overflow-wrap:anywhere; }
        .receipt-price { flex:none; white-space:nowrap; font-variant-numeric:tabular-nums; }
        .receipt-unknown { margin:18px 0 0; padding-top:16px; border-top:2px dashed var(--divider-color,#dfe7e1); font-size:14px; }
        .receipt-unknown summary { cursor:pointer; font-weight:650; }
        .receipt-total { display:flex; justify-content:space-between; gap:16px; margin-top:20px; font-weight:700; }
        h2 { margin:0; font-size:18px; font-weight:650; }
        .count { padding:5px 10px; border-radius:20px; background:var(--secondary-background-color,#edf4ee); font-size:13px; }
        ul { list-style:none; margin:0; padding:0; }
        #items-card { background:transparent; border:0; padding:0; }
        .product-grid { display:grid; grid-template-columns:repeat(var(--isl-columns,3),minmax(0,1fr)); gap:16px; }
        .product-group { grid-column:1/-1; min-width:0; }
        .product-group-heading { display:flex; align-items:center; gap:8px; margin:8px 0 14px; font-size:17px; }
        .product-group-heading ha-icon { --mdc-icon-size:22px; width:22px; height:22px; flex:none; color:#fff; }
        .product-grid li { min-width:0; container-type:inline-size; }
        .item { position:relative; display:flex; flex-direction:column; align-items:center; justify-content:center; width:100%; aspect-ratio:1; min-width:0; min-height:0; overflow:hidden; gap:clamp(2px,2.5cqi,12px); padding:clamp(4px,5cqi,24px); border:1px solid var(--divider-color,#dfe7e1); border-radius:clamp(6px,6cqi,16px); background:var(--card-background-color,#fff); color:inherit; text-align:center; cursor:pointer; }
        .item.pending { background:linear-gradient(var(--isl-gradient-start,#ee524f),var(--isl-gradient-end,#b52a27)); border-color:var(--isl-gradient-end,#b52a27); color:var(--isl-gradient-text,#fff); }
        .item.completed { background:linear-gradient(var(--isl-completed-gradient-start,#4faba2),var(--isl-completed-gradient-end,#26857c)); border-color:var(--isl-completed-gradient-end,#26857c); color:var(--isl-completed-gradient-text,#fff); }
        .item .product-media { display:grid; place-items:center; width:clamp(14px,36cqi,192px); max-width:100%; min-height:0; flex-shrink:1; aspect-ratio:1; }
        .item .image { width:100%; max-width:100%; aspect-ratio:1; height:auto; max-height:100%; object-fit:contain; border-radius:10px; }
        .item .placeholder { display:grid; place-items:center; color:var(--secondary-text-color,#63766b); }
        .item .placeholder ha-icon { --mdc-icon-size:clamp(14px,30cqi,160px); }
        .item.pending .placeholder,.item.pending .subtitle,.item.pending .description,.item.completed .placeholder,.item.completed .subtitle,.item.completed .description { color:inherit; }
        .item.pending .tag,.item.completed .tag { background:rgba(255,255,255,.2); }
        .item .category-badge { --isl-list-badge-size:clamp(18px,17cqi,42px); position:absolute; top:clamp(3px,4cqi,12px); right:clamp(3px,4cqi,12px); display:flex; align-items:center; justify-content:center; flex:none; box-sizing:border-box; width:var(--isl-list-badge-size); min-width:var(--isl-list-badge-size); max-width:var(--isl-list-badge-size); height:var(--isl-list-badge-size); min-height:var(--isl-list-badge-size); max-height:var(--isl-list-badge-size); aspect-ratio:1 / 1; margin:0; padding:0; border:0; border-radius:50%; line-height:0; color:#fff; box-shadow:0 2px 6px rgba(0,0,0,.22); }
        .item .category-badge ha-icon { --mdc-icon-size:clamp(14px,11cqi,28px); display:flex; align-items:center; justify-content:center; flex:none; width:var(--mdc-icon-size); height:var(--mdc-icon-size); margin:0; padding:0; }
        .item-text { min-width:0; width:100%; overflow:hidden; flex-shrink:0; overflow-wrap:anywhere; line-height:1.2; }
        .item .summary { display:-webkit-box; -webkit-box-orient:vertical; -webkit-line-clamp:3; overflow:hidden; font-size:clamp(12px,10cqi,32px); font-weight:650; }
        .subtitle { display:block; color:var(--secondary-text-color,#63766b); font-size:clamp(7px,4cqi,12px); margin-top:4px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
        .tags { display:flex; flex-wrap:wrap; justify-content:center; gap:4px; max-width:100%; min-width:0; max-height:15cqi; overflow:hidden; flex-shrink:0; }
        .tag { padding:2px 5px; border-radius:20px; font-size:clamp(7px,4cqi,11px); background:var(--secondary-background-color,#edf4ee); max-width:100%; overflow-wrap:anywhere; }
        .description { display:-webkit-box; -webkit-box-orient:vertical; -webkit-line-clamp:2; overflow:hidden; color:var(--secondary-text-color,#63766b); font-size:clamp(7px,4cqi,12px); white-space:pre-wrap; }
        @container(max-width:140px) { .item .subtitle,.item .description,.item .tags { display:none; } .item .summary { -webkit-line-clamp:2; } }
        .completed .summary { text-decoration:line-through; color:inherit; }
        .row-meta { display:none; }
        .quantity-corner { position:absolute; top:0; left:0; width:clamp(32px,34cqi,100px); aspect-ratio:1; clip-path:polygon(0 0,100% 0,0 100%); background:var(--isl-quantity-color,#267052); color:#fff; text-align:left; }
        .quantity-corner span { position:absolute; top:7%; left:7%; max-width:72%; font-size:clamp(7px,5cqi,14px); font-weight:700; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; line-height:1.2; }
        .rows li { position:relative; }
        .rows .quantity-corner { display:none; }
        .row-quantity { display:inline-flex; align-items:center; padding:6px 9px; justify-content:center; background:rgba(255,255,255,.2); color:inherit; font-size:12px; font-weight:700; min-width:0; max-width:100%; white-space:nowrap; }
        .rows .list-product-row { display:grid; grid-template-columns:minmax(0,1fr); align-items:center; border-radius:12px; background:linear-gradient(var(--isl-gradient-start,#ee524f),var(--isl-gradient-end,#b52a27)); color:var(--isl-gradient-text,#fff); border:1px solid var(--isl-gradient-end,#b52a27); }
        .rows .list-product-row.list-completed { background:linear-gradient(var(--isl-completed-gradient-start,#4faba2),var(--isl-completed-gradient-end,#26857c)); color:var(--isl-completed-gradient-text,#fff); border-color:var(--isl-completed-gradient-end,#26857c); }
        .rows .list-product-row > .item { background:transparent; color:inherit; border:0; }
        .product-grid.rows { grid-template-columns:minmax(0,1fr); gap:10px; }
        .rows .item { display:grid; grid-template-columns:48px minmax(0,1fr) auto; gap:12px; aspect-ratio:auto; min-height:80px; padding:12px 16px; border-radius:12px; }
        .rows .item .product-media { grid-column:1; grid-row:1; width:48px; height:48px; }
        .rows .item .placeholder ha-icon { --mdc-icon-size:40px; }
        .rows .item-text { grid-column:2; grid-row:1; text-align:left; }
        .rows .item .summary { font-size:clamp(14px,2.5cqi,18px); -webkit-line-clamp:3; }
        .rows .item .category-badge,.rows .item .tags,.rows .item .description { display:none; }
        .rows .row-meta { grid-column:3; grid-row:1; display:flex; align-items:center; justify-content:flex-end; flex-wrap:wrap; gap:6px; max-width:min(40cqi,260px); }
        .row-category,.row-price { display:inline-flex; align-items:center; justify-content:center; gap:5px; padding:6px 9px; border-radius:16px; font-size:12px; line-height:1.2; min-width:0; max-width:100%; }
        .row-category { color:#fff; box-shadow:0 2px 6px rgba(0,0,0,.18); }
        .row-category span { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
        .row-price { background:rgba(255,255,255,.2); white-space:nowrap; }
        .row-price .store-logo { display:block; width:22px; height:22px; flex:none; padding:2px; object-fit:contain; background:#fff; border-radius:50%; }
        .row-nutriscore { display:inline-flex; align-items:center; justify-content:center; height:28px; min-width:28px; padding:4px 7px; border-radius:8px; font-size:14px; line-height:1; font-weight:750; color:#fff; }
        .row-nutriscore[data-grade=a] { background:#038141; }.row-nutriscore[data-grade=b] { background:#85bb2f; color:#182b22; }.row-nutriscore[data-grade=c] { background:#fecb02; color:#182b22; }.row-nutriscore[data-grade=d] { background:#ee8100; color:#182b22; }.row-nutriscore[data-grade=e] { background:#e63e11; }
        .row-meta ha-icon { display:flex; align-items:center; justify-content:center; width:18px; height:18px; --mdc-icon-size:18px; flex:none; }
        @media(max-width:540px) { .rows .item { grid-template-columns:36px minmax(0,1fr) auto; gap:8px; padding:10px; }.rows .item .product-media { width:36px; height:36px; }.rows .item .placeholder ha-icon { --mdc-icon-size:32px; }.row-category,.row-price { font-size:11px; padding:5px 7px; }.rows .row-category { width:28px; height:28px; padding:5px; }.rows .row-category span { display:none; }.row-price .store-logo { width:18px; height:18px; }.row-nutriscore { height:26px; min-width:26px; font-size:13px; } }
        .rows .row-category,.rows .row-price,.rows .row-nutriscore,.rows .row-quantity { box-sizing:border-box; height:34px; min-height:34px; border-radius:16px; }
        .rows .row-category,.rows .row-nutriscore { min-width:34px; }
        .rows .row-meta { max-width:min(35cqi,280px); }
        .empty { padding:28px 8px; text-align:center; color:var(--secondary-text-color,#63766b); line-height:1.6; }
        .empty strong { display:block; font-size:18px; color:var(--primary-text-color,#20352d); margin-bottom:5px; }
        details { margin-top:24px; }
        summary { cursor:pointer; color:var(--secondary-text-color,#63766b); font-size:14px; padding:10px 0; }
        #completed-summary { display:flex; align-items:center; gap:8px; }
        #completed-summary::before { content:"▸"; flex:none; }
        #completed-details[open] #completed-summary::before { content:"▾"; }
        #completed-label { flex:1; min-width:0; }
        #clear-completed { display:inline-flex; align-items:center; justify-content:center; gap:6px; flex:none; margin-left:auto; min-height:36px; font-size:12px; padding:8px 10px; white-space:nowrap; border:0; border-radius:10px; background:#d32f2f; color:#fff; opacity:.5; }
        #clear-completed ha-icon { display:flex; align-items:center; justify-content:center; flex:none; width:18px; height:18px; --mdc-icon-size:18px; }
        .notice { line-height:1.6; padding:12px 16px; border-radius:12px; background:var(--secondary-background-color,#edf4ee); margin:0 0 18px; font-size:14px; }
        .error { border:1px solid var(--error-color,#bd3636); color:var(--error-color,#bd3636); }
        [hidden] { display:none !important; }
        .sr-only { position:absolute; width:1px; height:1px; padding:0; overflow:hidden; clip:rect(0,0,0,0); white-space:nowrap; border:0; }
        @media(max-width:650px) { .product-grid { grid-template-columns:repeat(var(--isl-mobile-columns,1),minmax(0,1fr)); } }
        @media(max-width:650px) { header { flex-wrap:nowrap; gap:6px; padding:10px 12px; } .branding { flex:0 0 auto; } .brand-copy { display:none; } .brand-logo { width:36px; height:36px; } .section-nav { flex-wrap:nowrap; gap:0; } .section-nav button { flex:0 0 auto; gap:4px; padding:10px 8px; min-width:44px; justify-content:center; font-size:13px; white-space:nowrap; } .section-nav button[aria-pressed=false] .nav-label { display:none; } }
        @media(max-width:360px) { header { gap:4px; padding:10px 8px; } .brand-logo { width:28px; height:28px; } .menu { width:32px; padding:4px; flex:none; } .section-nav button { min-width:32px; padding:10px 6px; font-size:12px; } }
        .section-nav ha-icon { --mdc-icon-size:20px; width:20px; height:20px; flex:none; }
        @media(max-width:540px) { main { padding:26px 14px 40px; } .card { padding:18px 16px; border-radius:14px; } .primary { padding:10px 14px; } }
        .stock-item { min-height:132px; background:linear-gradient(var(--isl-stock-gradient-start,#f59a23),var(--isl-stock-gradient-end,#c65b0c)); color:#fff; border:0; padding:clamp(4px,4cqi,20px); }
        .stock-item.stock-progress { isolation:isolate; background:linear-gradient(#0005,#0005),linear-gradient(var(--isl-stock-gradient-start,#f59a23),var(--isl-stock-gradient-end,#c65b0c)); }
        .stock-item.stock-progress::before { content:""; position:absolute; inset:0; width:var(--stock-remaining); background:linear-gradient(color-mix(in srgb,var(--isl-stock-gradient-start,#f59a23) var(--stock-remaining),#d32f2f),color-mix(in srgb,var(--isl-stock-gradient-end,#c65b0c) var(--stock-remaining),#b52a27)); pointer-events:none; z-index:-1; }
        .stock-life { display:inline; font-weight:400; opacity:.5; white-space:nowrap; }
        .stock-amount { font-weight:750; }
        .stock-item .placeholder { color:inherit; }.stock-item .product-media { width:clamp(18px,26cqi,144px); }
        .stock-item .summary { -webkit-line-clamp:2; }
        .stock-open { display:flex; flex-direction:column; align-items:center; justify-content:center; flex:1; gap:8px; min-width:0; width:100%; padding:0; border:0; background:transparent; color:inherit; cursor:pointer; }
        .stock-controls { display:flex; align-items:center; justify-content:center; gap:6px; flex:none; }
        .stock-controls button { display:grid; place-items:center; width:28px; height:28px; padding:0; border:0; border-radius:8px; background:rgba(255,255,255,.24); color:inherit; }
        .stock-controls ha-icon { width:20px; height:20px; --mdc-icon-size:20px; }
        .stock-quantity { font-weight:400; font-size:clamp(12px,10cqi,24px); font-variant-numeric:tabular-nums; }
        .rows .stock-item { display:flex; flex-direction:row; min-height:80px; gap:12px; }
        .rows .stock-open { display:grid; grid-template-columns:48px minmax(0,1fr) auto; gap:12px; text-align:left; }
        .rows .stock-item .product-media { width:48px; height:48px; }.rows .stock-quantity { font-size:16px; white-space:nowrap; }
        @media(max-width:540px) { .rows .stock-open { grid-template-columns:32px minmax(0,1fr) auto; gap:8px; }.rows .stock-item .product-media { width:32px; height:32px; }.rows .stock-controls { flex-direction:column; gap:4px; } }
        .stock-form-fields { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:18px; margin-top:20px; }
        .stock-form-fields label { display:block; min-width:0; font-size:14px; font-weight:600; }
        .stock-form-fields input:not([type=checkbox]),.stock-form-fields select { display:block; width:100%; min-width:0; height:44px; margin-top:8px; padding:8px 10px; border:1px solid var(--divider-color,#dfe7e1); border-radius:10px; color:inherit; background:var(--card-background-color,#fff); }
        .stock-form-fields .wide { grid-column:1/-1; }.stock-form-fields .check { display:flex; align-items:center; gap:10px; }
        .stock-form-fields .check input { width:20px; height:20px; }
        .stock-expiry-refill { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); align-items:end; gap:14px; }
        .stock-expiry-refill:has(#stock-days-label[hidden]) { grid-template-columns:minmax(0,1fr); }
        .stock-reorder-row { display:grid; grid-template-columns:minmax(0,1fr) 88px; align-items:center; gap:10px; }
        .stock-reorder-row .check { margin:0; }.stock-reorder-row .check input { flex:none; margin:0; }
        .stock-reorder-row:has(#stock-threshold-label[hidden]) { grid-template-columns:minmax(0,1fr); }
        .stock-quantity-editor { display:grid; grid-template-columns:40px minmax(0,1fr) 40px; gap:8px; align-items:end; }
        .stock-quantity-editor button { width:40px; height:44px; padding:0; display:grid; place-items:center; border:0; border-radius:10px; }
        .stock-quantity-editor input,.stock-form-fields select[name=unit] { text-align:center; text-align-last:center; padding-left:24px; padding-right:24px; }
        .stock-quantity-editor input { appearance:textfield; }
        .stock-quantity-editor input::-webkit-inner-spin-button,.stock-quantity-editor input::-webkit-outer-spin-button { -webkit-appearance:none; margin:0; }
        #stock-editor-form > .dialog-actions { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); }
        #stock-editor-form > .dialog-actions button { min-width:0; width:100%; }
        .stock-form-fields [hidden] { display:none; } #delete-stock-from-editor { background:#d32f2f; color:white; border:0; }
        #save-stock-config { background:var(--isl-green); color:white; border:0; }
        @media(max-width:420px) { .stock-form-fields { grid-template-columns:minmax(0,1fr); } }
        #confirm-stock-remove { background:#d32f2f; color:#fff; border:0; }
        #stock-heading { display:flex; align-items:center; justify-content:space-between; gap:12px; margin-bottom:16px; }
        .stock-tabs,.stock-tabs nav,#stock-actions { display:flex; align-items:center; gap:8px; flex:none; }
        #stock-actions { margin-left:auto; }
        .stock-tabs [role=tab] { display:flex; align-items:center; gap:6px; min-height:42px; padding:8px 10px; border:0; border-radius:10px; background:transparent; color:inherit; }
        .stock-tabs [aria-selected=true] { background:var(--secondary-background-color,#edf4ee); font-weight:700; }
        .stock-tabs ha-icon { --mdc-icon-size:22px; width:22px; height:22px; }
        #stock-add-form label { display:flex; flex-direction:column; gap:8px; }
        #stock-add-form input { min-height:44px; padding:10px; border:1px solid var(--divider-color,#dfe7e1); border-radius:10px; color:inherit; background:var(--card-background-color,#fff); }
        #stock-add-submit { background:var(--isl-green); color:white; border:0; }
        @media(max-width:500px) { #stock-heading { gap:6px; }.stock-tabs,.stock-tabs nav,#stock-actions { gap:4px; }.stock-tabs [role=tab] { padding:8px 4px; font-size:12px; gap:4px; }.stock-tabs [aria-selected=false] span { display:none; }#stock-actions .icon-button { width:38px; height:42px; flex-basis:38px; } }
        @media(max-width:360px) { #stock-actions { gap:3px; } #stock-actions .icon-button { width:32px; flex-basis:32px; } #stock-actions .icon-button ha-icon { --mdc-icon-size:20px; } }
        @media(max-width:380px) { header { gap:4px; padding:10px 8px; }.brand-logo { width:32px; height:32px; }.menu { width:36px; padding:6px; }.section-nav button { min-width:28px; padding:10px 4px; gap:3px; font-size:12px; }.section-nav ha-icon { --mdc-icon-size:18px; } }
      </style>
      <header>
        <button class="menu" aria-label="Abrir menú de Home Assistant"><ha-icon icon="mdi:menu"></ha-icon></button>
        <div class="branding"><img class="brand-logo" src="${LOGO_URL}" alt="" width="44" height="44"><div class="brand-copy"><span class="brand">Improved Shopping List</span><span class="version">0.28.0</span></div></div>
        <nav class="section-nav" aria-label="Apartados">
          <button id="nav-shopping" aria-label="Lista" aria-pressed="true"><ha-icon icon="mdi:shopping" aria-hidden="true"></ha-icon><span class="nav-label">Lista</span></button>
          <button id="nav-catalog" aria-label="Catálogo" aria-pressed="false"><ha-icon icon="mdi:view-grid" aria-hidden="true"></ha-icon><span class="nav-label">Catálogo</span></button>
          <button id="nav-stock" aria-label="Stock" aria-pressed="false"><ha-icon icon="mdi:package-variant" aria-hidden="true"></ha-icon><span class="nav-label">Stock</span></button>
          <button id="nav-settings" aria-label="Ajustes" aria-pressed="false"><ha-icon icon="mdi:cog" aria-hidden="true"></ha-icon><span class="nav-label">Ajustes</span></button>
        </nav>
      </header>
      <main>
        <div id="error" class="notice error" role="alert" hidden></div>
        <div id="status" class="notice" role="status" hidden></div>
        <div id="stock-heading" hidden><nav class="stock-tabs" role="tablist" aria-label="Vistas de Stock"><button id="stock-tab" type="button" role="tab" aria-label="Stock" aria-selected="true" aria-controls="stock-card"><ha-icon icon="mdi:package-variant" aria-hidden="true"></ha-icon><span>Stock</span></button><button id="purchases-tab" type="button" role="tab" aria-label="Compras" aria-selected="false" aria-controls="purchase-history"><ha-icon icon="mdi:receipt-text" aria-hidden="true"></ha-icon><span>Compras</span></button></nav><div id="stock-actions"><button id="add-stock" class="icon-button" type="button" aria-label="Añadir producto al stock" title="Añadir producto al stock"><ha-icon icon="mdi:plus-thick" aria-hidden="true"></ha-icon></button><button id="upload-ticket" class="icon-button" type="button" aria-label="Subir ticket" title="Subir ticket PDF"><ha-icon icon="mdi:file-upload" aria-hidden="true"></ha-icon></button></div></div>
        <section id="list-controls" aria-label="Seleccionar lista y añadir productos">
          <form id="add-form">
            <div class="input-wrap"><label class="sr-only" for="product-input">Añadir producto</label><input id="product-input" type="text" maxlength="255" placeholder="Busca o añade un producto" autocomplete="off" role="combobox" aria-autocomplete="list" aria-expanded="false" aria-controls="product-suggestions" aria-describedby="predictive-count" required><ul id="product-suggestions" class="predictive-results" role="listbox" aria-label="Productos del catálogo" hidden></ul><span id="predictive-count" class="sr-only" role="status" aria-live="polite"></span></div>
            <button id="add-button" class="icon-button" type="submit" aria-label="Añadir" title="Añadir producto"><ha-icon icon="mdi:plus-thick"></ha-icon></button>
            <button id="toggle-stock-sort" class="icon-button" type="button" aria-label="Ordenar por menor stock" title="Ordenar por menor stock" hidden><ha-icon icon="mdi:sort-numeric-ascending" aria-hidden="true"></ha-icon></button>
            <button id="choose-list" class="icon-button" type="button" aria-label="Seleccionar lista" title="Seleccionar lista" aria-haspopup="dialog" aria-controls="list-dialog"><ha-icon icon="mdi:format-list-checks"></ha-icon></button>
            <button id="toggle-product-grouping" class="icon-button" type="button" aria-label="Agrupar por categorías" title="Agrupar por categorías" aria-pressed="false"><ha-icon icon="mdi:label" aria-hidden="true"></ha-icon></button>
            <button id="toggle-list-layout" class="icon-button" type="button" aria-label="Cambiar a vista de filas" title="Cambiar a vista de filas"><ha-icon icon="mdi:view-sequential" aria-hidden="true"></ha-icon></button>
          </form>
          <p id="capability-help" class="helper" hidden></p>
        </section>
        <dialog id="list-dialog" aria-labelledby="list-dialog-title">
          <h2 id="list-dialog-title">Seleccionar lista</h2>
          <div id="list-options" role="group" aria-label="Listas de la compra"></div>
          <p id="no-lists" class="helper" hidden>No hay listas añadidas. Puedes añadir entidades todo desde Ajustes.</p>
          <div class="dialog-actions"><button id="refresh" type="button">Actualizar lista</button><button id="close-list-dialog" type="button">Cerrar</button></div>
        </dialog>
        <section class="card" aria-labelledby="pending-title" id="items-card">
          <div class="list-header"><h2 id="pending-title">Lista de la compra</h2><div class="list-totals"><button type="button" id="pending-count" class="count" title="Volver a la vista habitual" aria-controls="pending">0 productos</button><button type="button" id="pending-total" class="count" title="Ver ticket · Últimos precios guardados" aria-controls="receipt" aria-expanded="false" aria-live="polite">≈ 0,00 €</button></div></div>
          <ul id="pending" class="product-grid" aria-label="Lista de la compra"></ul>
          <div id="receipt" aria-label="Ticket de la compra" hidden></div>
          <div id="empty" class="empty" hidden></div>
          <details id="completed-details"><summary id="completed-summary"><span id="completed-label">Compras recientes</span><button id="clear-completed" type="button"><ha-icon icon="mdi:delete" aria-hidden="true"></ha-icon>Limpiar productos</button></summary><ul id="completed" class="product-grid" aria-label="Compras recientes"></ul></details>
        </section>
        <section id="stock-card" aria-label="Stock" hidden><ul id="stock-items" class="product-grid" aria-label="Productos en stock"></ul><p id="stock-empty" class="empty" hidden>Añade productos para empezar a controlar tu despensa.</p></section>
        <isl-purchases id="purchase-history" hidden></isl-purchases>
        <dialog id="stock-add-dialog" aria-labelledby="stock-add-title"><form id="stock-add-form"><h2 id="stock-add-title">Añadir producto al stock</h2><label>Nombre del producto<input name="name" type="text" maxlength="255" list="stock-add-products" autocomplete="off" required></label><datalist id="stock-add-products"></datalist><p id="stock-add-error" class="notice error" role="alert" hidden></p><div class="dialog-actions"><button id="stock-add-submit" type="submit">Añadir</button></div></form></dialog>
        <dialog id="stock-editor-dialog" aria-labelledby="stock-editor-title">
          <form id="stock-editor-form"><h2 id="stock-editor-title">Configurar Stock</h2><p id="stock-editor-error" class="notice error" role="alert" hidden></p>
          <div class="stock-form-fields">
            <label>Stock actual<div class="stock-quantity-editor"><button id="stock-draft-minus" type="button" aria-label="Disminuir stock"><ha-icon icon="mdi:minus" aria-hidden="true"></ha-icon></button><input name="quantity" aria-label="Stock actual" type="number" min="0" max="1000000" step="0.001" required><button id="stock-draft-plus" type="button" aria-label="Incrementar stock"><ha-icon icon="mdi:plus" aria-hidden="true"></ha-icon></button></div></label>
            <label>Unidades<select name="unit" aria-label="Unidades"><option value="uds">uds</option><option value="kg">kg</option><option value="g">g</option><option value="l">l</option><option value="ml">ml</option><option value="custom">Personalizadas</option></select></label>
            <label class="wide" id="stock-custom-unit-label" hidden>Unidad personalizada<input name="custom_unit" maxlength="32" placeholder="Por ejemplo, Latas"></label>
            <label class="wide">Control del stock<select name="mode" aria-label="Control del stock"><option value="manual">Manual / lectores</option><option value="perishable">Perecedero</option><option value="usage">Consumo registrado</option></select></label>
            <div id="stock-usage-fields" class="wide" hidden><div class="stock-form-fields">
              <label class="wide">Entidad de consumo<input name="usage_entity" list="stock-usage-entities" placeholder="Por ejemplo, binary_sensor.lavadora"></label><datalist id="stock-usage-entities"></datalist>
              <label>Estado que representa un uso<input name="usage_state" maxlength="255" placeholder="Por ejemplo, on"></label>
              <label>Cantidad consumida por uso<input name="usage_amount" type="number" min="0.001" max="1000000" step="0.001" required></label>
            </div></div>
            <div class="stock-expiry-refill wide">
              <label id="stock-days-label" hidden>Caduca cada cuántos días desde la compra<input name="days" type="number" min="1" max="3650" step="1" required></label>
              <label>Cantidad que se suma al marcarlo como comprado<input name="refill_quantity" type="number" min="0.001" max="1000000" step="0.001" required></label>
            </div>
            <div class="stock-reorder-row wide">
              <label class="check"><input name="reorder_enabled" type="checkbox">Añadir a la lista cuando el stock llegue al mínimo</label>
              <label id="stock-threshold-label" hidden><span id="stock-threshold-title">Stock mínimo</span><input name="reorder_at" type="number" min="0" max="1000000" step="0.001" required></label>
            </div>
            <label id="stock-target-label" class="wide">Lista para reponer<select name="list_entity" aria-label="Lista para reponer"></select></label>
          </div><div class="dialog-actions"><button id="delete-stock-from-editor" type="button">Eliminar producto del stock</button><button id="save-stock-config" type="submit">Guardar</button></div></form>
        </dialog>
        <dialog id="stock-remove-dialog" aria-labelledby="stock-remove-title"><h2 id="stock-remove-title">Eliminar de Stock</h2><p id="stock-remove-description"></p><p id="stock-remove-error" class="notice error" role="alert" hidden></p><div class="dialog-actions"><button id="cancel-stock-remove" type="button">Cancelar</button><button id="confirm-stock-remove" type="button">Eliminar producto</button></div></dialog>
        <isl-catalog hidden></isl-catalog>
        <isl-settings hidden></isl-settings>
        <div id="announcement" class="sr-only" role="status" aria-live="polite"></div>
      </main>`;
    this._built = true;
    const root = this.shadowRoot;
    installDialogCloseButtons(root);
    root.querySelector('#add-stock').addEventListener('click',()=>this._openStockAdd());
    root.querySelector('#stock-add-form').addEventListener('submit',event=>{event.preventDefault();void this._addStockProduct();});
    root.querySelector('#stock-add-dialog').addEventListener('cancel',event=>{if(this._busy)event.preventDefault();});
    for(const [id,view] of [['stock-tab','stock'],['purchases-tab','purchases']])root.querySelector('#'+id).addEventListener('click',()=>{this._stockView=view;this._renderData();});
    root.querySelector('#upload-ticket').addEventListener('click',()=>root.querySelector('isl-purchases').chooseFile());
    root.querySelector('isl-purchases').addEventListener('receipt-busy',event=>{this._receiptBusy=event.detail;this._renderData();});
    root.querySelector('isl-purchases').addEventListener('receipt-imported',()=>{this._stockView='purchases';void this._stock.refresh();void this._refreshRowPrices();this._renderData();});
    root.querySelector('isl-purchases').createProduct=name=>root.querySelector('isl-catalog').createProduct(name);
    root.querySelector("#pending-total").addEventListener("click", () => {
      this._ticket = true;
      this._renderData();
    });
    root.querySelector("#pending-count").addEventListener("click", () => {
      this._ticket = false;
      this._renderData();
    });
    root.querySelector("isl-catalog").addEventListener("product-nutriscore", event => {
      const {code,nutriscore} = event.detail;
      if (typeof code !== "string" || !/^[a-e]$/.test(nutriscore?.grade ?? "")) return;
      this._nutrition.set(code.padStart(14,"0"),{code,grade:nutriscore.grade});
      this._renderData();
    });
    root.querySelector("isl-catalog").addEventListener("catalog-change", event => {
      this._catalogProducts = new Map(event.detail.products.map(product => [productNameKey(product.name), product]));
      this._catalogCategories = new Map(event.detail.categories.map(category => [normalizedName(category.name), category]));
      this._renderData();
      void this._refreshRowPrices();
    });
    root.querySelector("isl-catalog").addEventListener("catalog-layout-change", () => {
      this._renderData();
    });
    root.querySelector("#toggle-list-layout").addEventListener("click", () => {
      if (this._view === "stock") {
        this._stockLayout=this._stockLayout === "grid" ? "rows" : "grid";
        try { localStorage.setItem("isl-stock-layout",this._stockLayout); } catch { /* Storage disabled. */ }
      } else {
        this._ticket = false;
        this._listLayout = this._listLayout === "grid" ? "rows" : "grid";
        try { localStorage.setItem("isl-list-layout", this._listLayout); } catch { /* Storage disabled. */ }
      }
      this._renderData();
    });
    root.querySelector("#toggle-product-grouping").addEventListener("click",()=>{
      this._listGrouped=!this._listGrouped;
      this._ticket=false;
      try { localStorage.setItem('isl-list-grouped',String(this._listGrouped)); } catch { /* Storage disabled. */ }
      this._renderData();
    });
    root.querySelector("#nav-stock").addEventListener("click",()=>this._switchView("stock"));
    root.querySelector("#toggle-stock-sort").addEventListener("click",()=>{
      if(this._stockGrouped){this._stockGrouped=false;this._stockSort='lowest';}
      else if(this._stockSort==='lowest')this._stockSort='alphabetical';
      else this._stockGrouped=true;
      try { localStorage.setItem("isl-stock-sort",this._stockSort);localStorage.setItem('isl-stock-grouped',String(this._stockGrouped)); } catch { /* Storage disabled. */ }
      this._renderData();
    });
    root.querySelector("#stock-editor-form").addEventListener("submit",event=>{event.preventDefault();void this._saveStockConfig();});
    root.querySelector("#stock-editor-form").addEventListener("change",event=>{
      if(event.target.name === "mode") {
        const form=event.currentTarget,perishable=form.elements.mode.value === "perishable";
        if(this._stockDraftMode === "perishable")this._stockDraftPercent=Number(form.elements.reorder_at.value);
        else this._stockDraftMinimum=Number(form.elements.reorder_at.value);
        form.elements.reorder_at.value=perishable ? this._stockDraftPercent : this._stockDraftMinimum;
        this._stockDraftMode=form.elements.mode.value;
      }
      this._updateStockForm();
    });
    root.querySelector("#stock-editor-dialog").addEventListener("cancel",event=>{if(this._busy)event.preventDefault();});
    for(const [id,delta] of [["stock-draft-minus",-1],["stock-draft-plus",1]])root.querySelector('#'+id).addEventListener("click",()=>{
      const input=root.querySelector('#stock-editor-form').elements.quantity;
      input.value=String(Math.min(1000000,Math.max(0,Math.round((Number(input.value)+delta)*1000)/1000)));
    });
    root.querySelector('#delete-stock-from-editor').addEventListener('click',()=>{
      if(!this._stockEditing||this._busy)return;
      this._stockDeleteTarget=this._stock.items.find(item=>item.id===this._stockEditing.id)??this._stockEditing;
      root.querySelector('#stock-remove-description').textContent='¿Eliminar «'+this._stockEditing.name+'» de Stock?';
      root.querySelector('#stock-remove-error').hidden=true;root.querySelector('#stock-remove-dialog').showModal();
    });
    root.querySelector("#cancel-stock-remove").addEventListener("click",()=>root.querySelector("#stock-remove-dialog").close());
    root.querySelector("#confirm-stock-remove").addEventListener("click",()=>void this._removeStockItem());
    root.querySelector("#stock-remove-dialog").addEventListener("cancel",event=>{if(this._busy)event.preventDefault();});
    root.querySelector("#nav-shopping").addEventListener("click", () => this._switchView("shopping"));
    root.querySelector("#clear-completed").addEventListener("click", event => {
      event.preventDefault();
      event.stopPropagation();
      void this._runAction(() => this._session.clearCompleted(), "Productos completados eliminados de la lista.");
    });
    root.querySelector("#nav-catalog").addEventListener("click", () => this._switchView("catalog"));
    root.querySelector("#nav-settings").addEventListener("click", () => this._switchView("settings"));
    root.querySelector("isl-settings").onAction = (action, entity) => this._settings.update(action, entity);
    root.querySelector("isl-settings").onNotifications = config => this._settings.saveNotifications(config);
    root.querySelector("isl-settings").onAppearance = appearance => this._settings.saveAppearance(appearance);
    root.querySelector("isl-catalog").onAdd = (product) => this._runAction(
      () => this._session.add(product.name), "",
    );
    root.querySelector("isl-catalog").onAdjustQuantity = (entity,uid,direction) => this._quantities.adjust(entity,uid,direction);
    root.querySelector("isl-catalog").onRenameSuggestion = (source, name) => this._session.renameFromSuggestion(source,name);
    root.querySelector(".menu").addEventListener("click", () => {
      this.dispatchEvent(new CustomEvent("hass-toggle-menu", { bubbles: true, composed: true }));
    });
    root.querySelector("#choose-list").addEventListener("click", () => {
      this._predictionClosed = true;
      this._renderPredictions();
      this._renderOptions();
      root.querySelector("#list-dialog").showModal();
      root.querySelector('.list-option[aria-pressed="true"]')?.focus();
    });
    root.querySelector("#close-list-dialog").addEventListener("click", () => root.querySelector("#list-dialog").close());
    root.querySelector("#list-dialog").addEventListener("close", () => {
      const selector=root.querySelector("#choose-list");
      (selector.hidden ? root.querySelector(this._view === "stock" ? "#add-stock" : "#product-input") : selector).focus();
    });
    root.querySelector("#refresh").addEventListener("click", () => {
      this._actionError = "";
      void this._session.refresh();
      void this._settings.refresh();
    });
    root.querySelector("#add-form").addEventListener("submit", (event) => {
      event.preventDefault();
      void this._addItem();
    });
    const input = root.querySelector("#product-input");
    input.addEventListener("input", () => { this._predictionIndex = -1; this._predictionClosed = false; this._renderPredictions(); });
    input.addEventListener("focus", () => { this._predictionClosed = false; this._renderPredictions(); });
    input.addEventListener("blur", () => { this._predictionClosed = true; this._renderPredictions(); });
    input.addEventListener("keydown", event => this._predictionKeydown(event));
  }

  _switchView(view) {
    if (this._view !== view && (view === "stock" || this._view === "stock")) {
      this.shadowRoot.querySelector("#product-input").value="";
      this._predictionClosed=true;this._predictionIndex=-1;
    }
    this._view = view;
    this._actionError = "";
    const root = this.shadowRoot;
    root.querySelector("#list-controls").hidden = !["shopping","stock"].includes(view);
    root.querySelector("#items-card").hidden = view !== "shopping";
    root.querySelector("#add-form").hidden = !["shopping","stock"].includes(view);
    root.querySelector("#stock-card").hidden=view!=="stock";
    root.querySelector("#nav-stock").setAttribute("aria-pressed",String(view==="stock"));
    root.querySelector("isl-catalog").hidden = view !== "catalog";
    root.querySelector("isl-settings").hidden = view !== "settings";
    root.querySelector("#nav-shopping").setAttribute("aria-pressed", String(view === "shopping"));
    root.querySelector("#nav-catalog").setAttribute("aria-pressed", String(view === "catalog"));
    root.querySelector("#nav-settings").setAttribute("aria-pressed", String(view === "settings"));
    this._renderData();
  }

  _renderOptions() {
    if (!this._built || !this._hass) return;
    const root = this.shadowRoot;
    const entities = this._settings.entities.map(entity => this._hass.states[entity] ?? {
      entity_id: entity, state: "unavailable", attributes: {},
    });
    const signature = JSON.stringify(entities.map((state) => [state.entity_id, state.attributes.friendly_name, state.state === "unavailable"]));
    const selected = this._session.entityId;
    if (signature !== this._optionsSignature || selected !== this._optionsSelected) {
      this._optionsSignature = signature;
      this._optionsSelected = selected;
      root.querySelector("#no-lists").hidden = entities.length > 0;
      const options = entities.map(state => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "list-option";
        button.dataset.entityId = state.entity_id;
        button.setAttribute("aria-pressed", String(state.entity_id === selected));
        const icon = document.createElement("ha-icon");
        icon.setAttribute("icon", state.entity_id === selected ? "mdi:check" : "mdi:format-list-checks");
        const name = document.createElement("span");
        name.textContent = (state.attributes.friendly_name ?? state.entity_id) + (isAvailable(state) ? "" : " · No disponible");
        button.append(icon, name);
        button.addEventListener("click", () => {
          root.querySelector("#list-dialog").close();
          this._actionError = "";
          void this._session.select(state.entity_id);
        });
        return button;
      });
      root.querySelector("#list-options").replaceChildren(...options);
    }
    const listName = this._hass.states[selected]?.attributes.friendly_name ?? selected;
    root.querySelector("#choose-list").title = listName ? `Lista actual: ${listName}` : "Seleccionar lista";
  }

  _renderData() {
    if (!this._built || !this._hass) return;
    this._renderOptions();
    const root = this.shadowRoot;
    const session = this._session;
    const stockView=this._view === "stock";
    const stockItemsView=stockView&&this._stockView==='stock';
    root.querySelector('#stock-heading').hidden=!stockView;
    root.querySelector('#stock-card').hidden=!stockItemsView;
    root.querySelector('#list-controls').hidden=this._view!=='shopping';
    const actions=root.querySelector(stockView?'#stock-actions':'#add-form');
    for(const id of ['toggle-stock-sort','choose-list','toggle-product-grouping','toggle-list-layout']){
      const button=root.querySelector('#'+id);
      if(button.parentElement!==actions)actions.append(button);
      button.hidden=(stockView&&!stockItemsView)||(id==='toggle-product-grouping'&&stockView)||(id==='choose-list'&&this._settings.entities.length===1);
    }
    if(this._settings.entities.length===1)root.querySelector('#list-dialog').close();
    const grouped=stockView ? this._stockGrouped : this._listGrouped;
    const groupingButton=root.querySelector('#toggle-product-grouping');
    const groupingLabel=grouped ? 'Mostrar todos los productos' : 'Agrupar por categorías';
    groupingButton.title=groupingLabel;groupingButton.setAttribute('aria-label',groupingLabel);
    groupingButton.setAttribute('aria-pressed',String(grouped));
    groupingButton.querySelector('ha-icon').setAttribute('icon',grouped ? 'mdi:sort-alphabetical-ascending' : 'mdi:label');
    root.querySelector('#add-stock').hidden=!stockItemsView;
    root.querySelector('#upload-ticket').hidden=!stockView||stockItemsView;
    root.querySelector('#stock-tab').setAttribute('aria-selected',String(this._stockView==='stock'));
    root.querySelector('#purchases-tab').setAttribute('aria-selected',String(this._stockView==='purchases'));
    root.querySelector('#upload-ticket').disabled=Boolean(this._receiptBusy)||this._hass.user?.is_admin!==true;
    root.querySelector('isl-purchases').hidden=!stockView;
    root.querySelector('isl-purchases').data={hass:this._hass,active:stockView,history:this._stockView==='purchases',pricesEnabled:this._settings.priceUpdatesEnabled!==false};
    const sortButton=root.querySelector("#toggle-stock-sort");
    sortButton.hidden=!stockItemsView;
    const sortLabel=this._stockGrouped ? "Ordenar por menor stock" : this._stockSort === "lowest" ? "Ordenar alfabéticamente" : "Agrupar por categorías";
    sortButton.title=sortLabel;sortButton.setAttribute("aria-label",sortLabel);
    sortButton.querySelector("ha-icon").setAttribute("icon",this._stockGrouped ? "mdi:sort-numeric-ascending" : this._stockSort === "lowest" ? "mdi:sort-alphabetical-ascending" : "mdi:label");
    sortButton.dataset.mode=this._stockGrouped ? "categories" : this._stockSort;
    const rows = (stockView ? this._stockLayout : this._listLayout) === "rows";
    const layoutLabel = rows ? "Cambiar a vista de cuadrícula" : "Cambiar a vista de filas";
    const layoutButton = root.querySelector("#toggle-list-layout");
    layoutButton.setAttribute("aria-label", layoutLabel); layoutButton.title = layoutLabel;
    layoutButton.querySelector("ha-icon").setAttribute("icon", rows ? "mdi:view-comfy" : "mdi:view-sequential");
    for (const id of ["pending","completed"]) root.querySelector("#" + id).classList.toggle("rows", rows);
    this._ensureRowPrices();
    const appearance = this._settings.appearance;
    this.style.setProperty("--isl-gradient-start", appearance.gradient_start);
    this.style.setProperty("--isl-stock-gradient-start",appearance.stock_gradient_start);
    this.style.setProperty("--isl-stock-gradient-end",appearance.stock_gradient_end);
    this.style.setProperty("--isl-recipe-gradient-start",appearance.recipe_gradient_start);
    this.style.setProperty("--isl-recipe-gradient-end",appearance.recipe_gradient_end);
    this.style.setProperty("--isl-quantity-color",appearance.quantity_color??'#267052');
    this.style.setProperty("--isl-gradient-end", appearance.gradient_end);
    this.style.setProperty("--isl-gradient-text", gradientTextColor(appearance.gradient_start, appearance.gradient_end));
    this.style.setProperty("--isl-completed-gradient-start", appearance.completed_gradient_start);
    this.style.setProperty("--isl-completed-gradient-end", appearance.completed_gradient_end);
    this.style.setProperty("--isl-completed-gradient-text", gradientTextColor(appearance.completed_gradient_start, appearance.completed_gradient_end));
    this.style.setProperty("--isl-columns", appearance.columns);
    this.style.setProperty("--isl-mobile-columns", appearance.mobile_columns);
    root.querySelector("isl-settings").data = { hass: this._hass, settings: this._settings, readers:this._readers, products:[...this._catalogProducts.values()] };
    root.querySelector("isl-settings").active = this._view === "settings";
    const state = this._hass.states[session.entityId];
    const available = isAvailable(state);
    const canCreate = available && supports(state, FEATURES.CREATE);
    const canUpdate = available && supports(state, FEATURES.UPDATE);
    const catalog = root.querySelector("isl-catalog");
    catalog.priceData = {offers:this._settings.priceUpdatesEnabled === false ? [] : this._rowPrices,favorite:this._settings.favoriteStore,enabled:this._settings.priceUpdatesEnabled !== false};
    catalog.hass = this._hass;
    catalog.readerData = this._readers;
    catalog.canAdd = canCreate && !this._busy && !session.loading;
    catalog.listName = state?.attributes.friendly_name ?? session.entityId;
    catalog.listEntity = session.entityId;
    catalog.active = this._view === "catalog";
    catalog.listItems = available && !session.loading ? session.items : [];
    catalog.pendingItems = available && !session.loading
      ? session.items.filter(item => item.status !== "completed") : [];
    catalog.quantityData = {entries:this._quantities.entries[session.entityId]??{},loaded:this._quantities.loaded,loading:this._quantities.loading,locked:this._busy||session.loading||!available};
    const locked = this._busy || session.loading || !available;
    const stockLocked=this._busy || !this._stock.loaded || this._stock.loading || this._hass.user?.is_admin !== true;
    root.querySelector('#add-stock').disabled=stockLocked;
    root.querySelector('#stock-add-submit').disabled=stockLocked;
    root.querySelector('#stock-add-form').elements.name.disabled=stockLocked;
    root.querySelector("#product-input").closest('.input-wrap').hidden = stockView;
    root.querySelector("#add-button").hidden = stockView;
    root.querySelector("#product-input").disabled = stockView || locked || !canCreate;
    root.querySelector("#add-button").disabled = stockView || locked || !canCreate;
    root.querySelector("#add-button").setAttribute("aria-busy", String(this._busy));
    root.querySelector("#refresh").disabled = session.loading || !session.entityId;
    const capabilityHelp = root.querySelector("#capability-help");
    capabilityHelp.hidden = this._view !== "shopping" || !available || (canCreate && canUpdate);
    capabilityHelp.textContent = !canCreate
      ? "Esta lista no permite añadir productos desde Home Assistant."
      : "Esta lista permite añadir productos, pero no marcarlos como comprados.";
    const status = root.querySelector("#status");
    status.hidden = this._view !== "shopping" || (available && !session.loading);
    status.textContent = !this._settings.loaded && this._settings.loading ? "Cargando ajustes…" : session.loading ? "Cargando tu lista…"
      : session.entityId ? "La lista seleccionada no está disponible. Comprueba su integración o selecciona otra lista."
        : "Añade una lista de la compra desde Ajustes para empezar.";
    const error = root.querySelector("#error");
    if(stockView){status.hidden=!this._stock.loading;status.textContent="Cargando Stock…";}
    const message = this._actionError || (stockView ? this._stock.error : this._view === "shopping" ? session.error || this._quantities.error || this._settings.error : "");
    error.hidden = !message;
    error.textContent = message;
    const pending = session.items.filter((item) => item.status !== "completed");
    const completed = session.items.filter((item) => item.status === "completed");
    if (this._rowsEntity !== session.entityId) {
      this._rows.clear();
      this._rowsEntity = session.entityId;
      this._ticketStore = "";
    }
    this._usedRows = new Set();
    root.querySelector("#pending-count").textContent = `${pending.length} ${pending.length === 1 ? "producto" : "productos"}`;
    const receipts = this._storeReceipts(pending);
    if (!receipts.some(receipt => receipt.store === this._ticketStore)) this._ticketStore = receipts[0]?.store ?? "";
    const selectedReceipt = receipts.find(receipt => receipt.store === this._ticketStore);
    const total = selectedReceipt ? this._receiptTotal(selectedReceipt) : this._pendingTotal(pending);
    root.querySelector("#pending-total").textContent = `≈ ${total}`;
    if (selectedReceipt) root.querySelector("#pending-total").append(this._storeLogo(selectedReceipt.store));
    root.querySelector("#pending-total").setAttribute("aria-label", `Ver ticket · Importe aproximado de la lista: ${total}${selectedReceipt ? ` · ${STORE_NAMES[selectedReceipt.store]}` : ""}`);
    root.querySelector("#pending-total").setAttribute("aria-expanded", String(this._ticket));
    root.querySelector("#pending-total").hidden=this._settings.priceUpdatesEnabled === false;
    if(this._settings.priceUpdatesEnabled === false)this._ticket=false;
    root.querySelector("#pending-count").setAttribute("aria-pressed", String(!this._ticket));
    root.querySelector("#pending").hidden = this._ticket;
    this._renderReceipt(pending, receipts, selectedReceipt);
    root.querySelector("#items-card").setAttribute("aria-busy", String(session.loading));
    this._renderItems(root.querySelector("#pending"), pending, locked || !canUpdate);
    this._renderItems(root.querySelector("#completed"), completed, locked || !canUpdate);
    if (rows && this._view === "shopping") void this._loadListNutrition();
    for (const key of this._rows.keys()) {
      if (!this._usedRows.has(key)) this._rows.delete(key);
    }
    const details = root.querySelector("#completed-details");
    details.hidden = this._ticket || !completed.length;
    root.querySelector("#completed-label").textContent = `Compras recientes (${completed.length})`;
    const clearCompleted = root.querySelector("#clear-completed");
    const canDelete = supports(state, FEATURES.DELETE);
    clearCompleted.disabled = locked || !canDelete || !completed.length;
    clearCompleted.title = canDelete ? "Eliminar todos los productos completados de esta lista" : "Esta lista no permite eliminar productos desde Home Assistant";
    clearCompleted.setAttribute("aria-busy", String(this._busy));
    const empty = root.querySelector("#empty");
    empty.hidden = pending.length > 0 || session.loading || !available || Boolean(session.error);
    if (!empty.hidden) {
      const title = document.createElement("strong");
      title.textContent = "Todo listo por aquí";
      empty.replaceChildren(title, document.createTextNode("Añade lo que necesites para tu próxima compra."));
    }
    this._renderStock(stockLocked);
    this._renderPredictions();
  }

  _openStockAdd() {
    if(this._busy||!this._stock.loaded||this._hass.user?.is_admin!==true)return;
    const root=this.shadowRoot,form=root.querySelector('#stock-add-form');
    form.reset();root.querySelector('#stock-add-error').hidden=true;
    root.querySelector('#stock-add-products').replaceChildren(...[...this._catalogProducts.values()].map(product=>new Option(product.name,product.name)));
    root.querySelector('#stock-add-dialog').showModal();form.elements.name.focus();
  }

  async _addStockProduct() {
    const root=this.shadowRoot,form=root.querySelector('#stock-add-form'),name=form.elements.name.value.trim();
    if(!name||this._busy||this._hass.user?.is_admin!==true)return;
    const success=await this._runAction(()=>this._stock.add(name),'Una unidad añadida a Stock.');
    if(success)root.querySelector('#stock-add-dialog').close();
    else {const error=root.querySelector('#stock-add-error');error.textContent=this._actionError;error.hidden=false;}
  }

  _renderStock(locked) {
    const root=this.shadowRoot, now=Date.now()/1000, items=[...this._stock.items], grid=root.querySelector("#stock-items");
    const remaining=item=>stockRemaining(item,now);
    items.sort((a,b)=>(this._stockSort === 'lowest' ? remaining(a)-remaining(b) : 0)||a.name.localeCompare(b.name,'es',{sensitivity:'base'}));
    grid.classList.toggle("rows",this._stockLayout === "rows");
    root.querySelector("#stock-empty").hidden=items.length>0||this._stock.loading||!this._stock.loaded||Boolean(this._stock.error);
    root.querySelector("#stock-card").setAttribute("aria-busy",String(this._stock.loading||this._busy));
    const focus=root.activeElement, focusedId=focus?.closest?.("[data-stock-id]")?.dataset.stockId, focusedAction=focus?.dataset.stockAction;
    const products=new Map([...this._catalogProducts.values()].map(product=>[product.id,product]));
    const node=(tag,className,text)=>{const element=document.createElement(tag);if(className)element.className=className;if(text!==undefined)element.textContent=text;return element;};
    const nodes=items.map(item=>{
      const product=products.get(item.catalog_product_id)??this._catalogProducts.get(productNameKey(item.name));
      const category=this._catalogCategories.get(normalizedName(product?.category));
      const li=node("li");li.dataset.stockId=item.id;
      const card=node("div","item stock-item"), open=node("button","stock-open");
      const percent=stockRemaining(item,now);
      const progress=item.mode === 'perishable' || item.mode === 'usage';
      if(progress) {
        card.classList.add('stock-progress');
        card.style.setProperty('--stock-remaining',percent+'%');
      }
      open.type="button";open.setAttribute("aria-label",`Configurar stock de ${item.name}`);open.addEventListener("click",()=>this._openStockEditor(item));
      const media=node("span","product-media"), placeholder=node("span","image placeholder"), icon=node("ha-icon");
      icon.setAttribute("icon",product?.icon||category?.icon||"mdi:package-variant");placeholder.append(icon);
      const source=imageSource(product?.image_url);
      if(source){const image=node("img","image");image.src=source;image.alt="";image.loading="lazy";image.referrerPolicy="no-referrer";image.addEventListener("error",()=>image.replaceWith(placeholder),{once:true});media.append(image);}else media.append(placeholder);
      const text=node("span","item-text");text.append(node("span","summary",item.name));
      const button=(action,mdi,label,disabled,callback)=>{
        const result=node("button");result.type="button";result.dataset.stockAction=action;result.setAttribute("aria-label",label);result.title=label;result.disabled=disabled;
        const glyph=node("ha-icon");glyph.setAttribute("icon",mdi);glyph.setAttribute("aria-hidden","true");result.append(glyph);result.addEventListener("click",callback);return result;
      };
      const quantity=node("span","stock-quantity");
      quantity.append(node("strong","stock-amount",new Intl.NumberFormat('es-ES',{maximumFractionDigits:3}).format(item.quantity)+' '+(item.unit??'uds')),document.createTextNode(' '));
      quantity.setAttribute('aria-label',`Stock de ${item.name}: ${item.quantity} ${item.unit??'uds'}`);
      const life=node('span','stock-life',`(${Math.round(percent)}%)`);
      if(progress){
        life.setAttribute('role','progressbar');life.setAttribute('aria-label','Stock restante');
        life.setAttribute('aria-valuemin','0');life.setAttribute('aria-valuemax','100');life.setAttribute('aria-valuenow',String(Math.round(percent)));
      }
      quantity.append(life);
      open.append(media,text,quantity);card.append(open);
      if(this._stockLayout==='rows'){
        const controls=node('div','stock-controls');
        controls.append(button('decrease','mdi:minus',`Quitar una unidad de ${item.name}`,locked||item.quantity===0,()=>void this._runAction(()=>this._stock.adjust(item,-1),'Stock actualizado.')),
          button('increase','mdi:plus',`Añadir una unidad de ${item.name}`,locked||item.quantity>=1000000,()=>void this._runAction(()=>this._stock.adjust(item,1),'Stock actualizado.')));
        card.append(controls);
      }
      li.append(card);return li;
    });
    this._renderProductGroups(grid,nodes,items,item=>products.get(item.catalog_product_id)??this._catalogProducts.get(productNameKey(item.name)),this._stockGrouped,this._stockLayout);
    if(focusedId){const li=[...grid.querySelectorAll('[data-stock-id]')].find(item=>item.dataset.stockId===focusedId);const button=(focusedAction ? li?.querySelector(`[data-stock-action="${focusedAction}"]:not([disabled])`) : null)??li?.querySelector("button:not([disabled])");button?.focus({preventScroll:true});}
    root.querySelector("#confirm-stock-remove").disabled=this._busy;
    root.querySelector("#cancel-stock-remove").disabled=this._busy;
    if(root.querySelector("#stock-editor-dialog").open)this._updateStockForm();
  }

  _openStockEditor(item) {
    const root=this.shadowRoot, form=root.querySelector('#stock-editor-form');
    this._stockEditing={...item};
    const defaults={unit:'uds',mode:'manual',days:7,refill_quantity:1,reorder_enabled:false,reorder_at:0,usage_entity:'',usage_state:'',usage_amount:1};
    const config={...defaults,...item};
    this._stockDraftMinimum=config.reorder_at;this._stockDraftPercent=config.reorder_percent??0;this._stockDraftMode=config.mode;
    for(const key of ['quantity','mode','days','refill_quantity','reorder_at','usage_entity','usage_state','usage_amount'])form.elements[key].value=config[key];
    if(config.mode === 'perishable')form.elements.reorder_at.value=this._stockDraftPercent;
    const standard=['uds','kg','g','l','ml'].includes(config.unit);
    form.elements.unit.value=standard?config.unit:'custom';form.elements.custom_unit.value=standard?'':config.unit;
    form.elements.reorder_enabled.checked=config.reorder_enabled;
    const options=this._settings.entities??[], target=item.list_entity||this._session.entityId||this._settings.primary||'';
    form.elements.list_entity.replaceChildren(...options.map(id=>new Option(this._hass.states[id]?.attributes?.friendly_name??id,id)));
    if(target&&!options.includes(target))form.elements.list_entity.add(new Option(target+' · No disponible',target));
    if(!form.elements.list_entity.options.length)form.elements.list_entity.add(new Option('No hay listas configuradas',''));
    if(target)form.elements.list_entity.value=target;
    root.querySelector('#stock-usage-entities').replaceChildren(...Object.entries(this._hass.states).filter(([id])=>!id.startsWith('todo.')).map(([id,state])=>new Option(state.attributes?.friendly_name??id,id)));
    root.querySelector('#stock-editor-title').textContent=item.name+' · Stock';root.querySelector('#stock-editor-error').hidden=true;
    this._updateStockForm();root.querySelector('#stock-editor-dialog').showModal();
  }

  _updateStockForm() {
    const root=this.shadowRoot,form=root.querySelector('#stock-editor-form'),locked=this._busy||this._hass.user?.is_admin!==true;
    const custom=form.elements.unit.value==='custom',usage=form.elements.mode.value==='usage',perishable=form.elements.mode.value==='perishable';
    root.querySelector('#stock-custom-unit-label').hidden=!custom;
    root.querySelector('#stock-days-label').hidden=!perishable;root.querySelector('#stock-usage-fields').hidden=!usage;
    root.querySelector('#stock-threshold-title').textContent=perishable ? 'Mínimo (%)' : 'Stock mínimo';
    form.elements.reorder_at.setAttribute('aria-label',perishable ? 'Porcentaje mínimo restante (%)' : 'Stock mínimo');
    form.elements.reorder_at.max=perishable ? '100' : '1000000';
    root.querySelector('#stock-threshold-label').hidden=!form.elements.reorder_enabled.checked;
    for(const input of form.querySelectorAll('input,select,button'))input.disabled=locked;
    form.elements.custom_unit.required=custom;form.elements.days.disabled=locked||!perishable;
    for(const key of ['usage_entity','usage_state','usage_amount']){form.elements[key].disabled=locked||!usage;form.elements[key].required=usage;}
    form.elements.reorder_at.disabled=locked||!form.elements.reorder_enabled.checked;
    form.elements.list_entity.required=perishable||form.elements.reorder_enabled.checked;
  }

  async _saveStockConfig() {
    if(this._busy||!this._stockEditing||this._hass.user?.is_admin!==true)return;
    const root=this.shadowRoot,form=root.querySelector('#stock-editor-form');
    if(!form.reportValidity())return;
    const value=key=>form.elements[key].value;
    const config={quantity:Number(value('quantity')),unit:value('unit')==='custom'?value('custom_unit').trim():value('unit'),
      mode:value('mode'),days:Number(value('days')),refill_quantity:Number(value('refill_quantity')),
      reorder_enabled:form.elements.reorder_enabled.checked,
      reorder_at:value('mode') === 'perishable' ? this._stockDraftMinimum : Number(value('reorder_at')),
      reorder_percent:value('mode') === 'perishable' ? Number(value('reorder_at')) : this._stockDraftPercent,
      list_entity:value('list_entity'),usage_entity:value('usage_entity').trim(),usage_state:value('usage_state'),usage_amount:Number(value('usage_amount'))};
    const success=await this._runAction(()=>this._stock.save(this._stockEditing,config),'Stock guardado.');
    if(success){root.querySelector('#stock-editor-dialog').close();this._stockEditing=null;}
    else {const error=root.querySelector('#stock-editor-error');error.textContent=this._actionError;error.hidden=!error.textContent;}
  }

  async _removeStockItem() {
    if(!this._stockDeleteTarget||this._busy)return;
    const item=this._stockDeleteTarget;
    const result=await this._runAction(()=>this._stock.remove(item),"Producto eliminado de Stock.");
    if(result){this.shadowRoot.querySelector("#stock-remove-dialog").close();this.shadowRoot.querySelector("#stock-editor-dialog").close();this._stockDeleteTarget=null;}
    else {const error=this.shadowRoot.querySelector("#stock-remove-error");error.textContent=this._actionError;error.hidden=!error.textContent;}
  }

  _renderPredictions() {
    if (!this._built) return;
    const root = this.shadowRoot;
    const input = root.querySelector("#product-input");
    const list = root.querySelector("#product-suggestions");
    const query = searchText(input.value);
    const searching = Boolean(query) && this._view === "shopping" && !input.disabled &&
      !this._predictionClosed && root.activeElement === input;
    this._predictions = searching ? [...this._catalogProducts.values()]
      .filter(product => [product.name, product.barcode, ...(product.barcodes ?? []), ...(product.nfc_tags ?? []), ...(product.tags ?? [])].some(value => searchText(value).includes(query)))
      .sort((a, b) => Number(searchText(b.name).startsWith(query)) - Number(searchText(a.name).startsWith(query)) || a.name.localeCompare(b.name, "es"))
      .slice(0, 8) : [];
    if (!Number.isInteger(this._predictionIndex) || this._predictionIndex >= this._predictions.length) this._predictionIndex = -1;
    const options = this._predictions.map((product, index) => {
      const option = document.createElement("li");
      option.id = `product-prediction-${index}`;
      option.className = "predictive-option";
      option.setAttribute("role", "option");
      option.setAttribute("aria-selected", String(index === this._predictionIndex));
      const placeholder = document.createElement("span");
      placeholder.className = "predictive-image";
      const icon = document.createElement("ha-icon");
      icon.setAttribute("icon", product.icon || this._catalogCategories.get(normalizedName(product.category))?.icon || "mdi:shopping");
      placeholder.append(icon);
      const source = imageSource(product.image_url);
      if (source) {
        const image = document.createElement("img");
        image.className = "predictive-image";
        image.src = source;
        image.alt = "";
        image.referrerPolicy = "no-referrer";
        image.addEventListener("error", () => image.replaceWith(placeholder), { once: true });
        option.append(image);
      } else option.append(placeholder);
      const text = document.createElement("span");
      text.className = "predictive-text";
      const name = document.createElement("strong");
      name.textContent = product.name;
      text.append(name);
      option.append(text);
      option.addEventListener("pointerdown", event => event.preventDefault());
      option.addEventListener("click", () => this._selectPrediction(product));
      return option;
    });
    list.replaceChildren(...options);
    list.hidden = !options.length;
    input.setAttribute("aria-expanded", String(options.length > 0));
    if (options.length && this._predictionIndex >= 0) {
      input.setAttribute("aria-activedescendant", options[this._predictionIndex].id);
      options[this._predictionIndex].scrollIntoView({ block: "nearest" });
    } else input.removeAttribute("aria-activedescendant");
    root.querySelector("#predictive-count").textContent = searching
      ? options.length ? `${options.length} coincidencias del catálogo. Usa las flechas para elegir y Enter para añadir.` : "Sin coincidencias en el catálogo. Puedes añadir el nombre escrito."
      : "";
  }

  _predictionKeydown(event) {
    if (event.isComposing) return;
    if (event.key === "Escape") {
      this._predictionClosed = true;
      this._predictionIndex = -1;
      this._renderPredictions();
    } else if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      this._predictionClosed = false;
      this._renderPredictions();
      const count = this._predictions.length;
      if (!count) return;
      this._predictionIndex = this._predictionIndex < 0 ? (event.key === "ArrowDown" ? 0 : count - 1)
        : (this._predictionIndex + (event.key === "ArrowDown" ? 1 : -1) + count) % count;
      this._renderPredictions();
    } else if (event.key === "Enter" && this._predictionIndex >= 0 && this._predictions[this._predictionIndex]) {
      event.preventDefault();
      this._selectPrediction(this._predictions[this._predictionIndex]);
    }
  }

  _selectPrediction(product) {
    const input = this.shadowRoot.querySelector("#product-input");
    if (this._busy || input.disabled) return;
    input.value = product.name;
    this._predictionClosed = true;
    this._predictionIndex = -1;
    this._renderPredictions();
    void this._addItem();
  }

  _stopRowPrices() {
    this._rowPricesToken = null;
    this._rowPricesConnection = null;
    this._rowPricesLoading = null;
    this._rowPricesAgain = false;
    this._stopRowPricesSubscription?.(); this._stopRowPricesSubscription = null;
    this._rowPrices = [];
  }

  _ensureRowPrices() {
    const connection = this._hass?.connection;
    if (!this.isConnected || !connection || this._rowPricesConnection === connection) return;
    this._stopRowPrices();
    this._rowPricesConnection = connection;
    const token = this._rowPricesToken = {};
    void connection.subscribeMessage(() => {
      if (this._rowPricesToken === token) void this._refreshRowPrices();
    }, {type:"improved_shopping_list/settings/store_progress"}).then(stop => {
      if (this._rowPricesToken !== token) stop();
      else this._stopRowPricesSubscription = stop;
    }).catch(() => { /* Optional cached prices must not block list operations. */ });
    void this._refreshRowPrices();
  }

  async _refreshRowPrices() {
    if (!this.isConnected || !this._hass) return;
    if (this._rowPricesLoading) { this._rowPricesAgain = true; return this._rowPricesLoading; }
    const token = this._rowPricesToken;
    const pending = Promise.allSettled(["mercadona","carrefour","alcampo","consum","lasirena","eroski","dia"].map(store =>
      this._hass.callWS({type:"improved_shopping_list/catalog/store_prices",store}))).then(results => {
        if (token !== this._rowPricesToken || !this.isConnected) return;
        const stores = ["mercadona","carrefour","alcampo","consum","lasirena","eroski","dia"];
        this._rowPrices = results.flatMap((result,index) => result.status === "fulfilled" ?
          result.value.products ?? [] : this._rowPrices.filter(offer => offer.store === stores[index]));
        this._renderData();
      }).finally(() => {
        if (this._rowPricesLoading !== pending) return;
        this._rowPricesLoading = null;
        if (this._rowPricesAgain) { this._rowPricesAgain = false; void this._refreshRowPrices(); }
      });
    this._rowPricesLoading = pending;
    return pending;
  }

  _listPrice(product) {
    if(this._settings.priceUpdatesEnabled === false)return null;
    return cachedProductPrice(product,this._rowPrices,this._settings.favoriteStore);
  }

  _nutritionCodes(product) {
    const seen = new Set();
    return [this._listPrice(product)?.ean,product?.barcode,...(product?.barcodes ?? [])].filter(code => {
      if (typeof code !== "string" || !/^(?:\d{8}|\d{12,14})$/.test(code)) return false;
      const total = [...code.slice(0,-1)].reverse().reduce((sum,digit,index) => sum + Number(digit)*(index%2 ? 1 : 3),0);
      const key=code.padStart(14,"0");
      if ((10-total%10)%10 !== Number(code.at(-1)) || seen.has(key)) return false;
      seen.add(key); return true;
    });
  }

  _stopListNutrition() {
    this._nutritionToken = null; this._nutritionLoading = false; this._nutrition.clear();
  }

  async _loadListNutrition() {
    if (this._nutritionLoading || !this.isConnected || !this._hass) return;
    const codes = new Map();
    for (const item of this._session.items) {
      for (const code of this._nutritionCodes(this._catalogProducts.get(productNameKey(item.summary)))) {
        if (!this._nutrition.has(code.padStart(14,"0"))) codes.set(code.padStart(14,"0"),code);
      }
    }
    if (!codes.size) return;
    const token = this._nutritionToken = {};
    this._nutritionLoading = true;
    try {
      for (const [key,code] of codes) {
        if (token !== this._nutritionToken || !this.isConnected || this._listLayout !== "rows" || this._view !== "shopping") break;
        this._nutrition.set(key,null);
        try {
          const result = await this._hass.callWS({type:"improved_shopping_list/catalog/nutriscore",code});
          if (token !== this._nutritionToken || !this.isConnected) return;
          if (/^[a-e]$/.test(result.nutriscore?.grade ?? "")) this._nutrition.set(key,{code,grade:result.nutriscore.grade});
        } catch { /* Missing optional nutrition never blocks the shopping list. */ }
        if (token === this._nutritionToken) this._renderData();
      }
    } finally {
      if (token === this._nutritionToken) { this._nutritionLoading = false; if (this.isConnected) this._renderData(); }
    }
  }

  _storeLogo(store) {
    const image = document.createElement("img");
    image.className = "store-logo";
    image.src = STORE_LOGOS[store];
    image.alt = STORE_NAMES[store] ?? store;
    image.addEventListener("error", () => image.remove(), {once:true});
    return image;
  }

  _storeReceipts(items) {
    if(this._settings.priceUpdatesEnabled === false)return [];
    const sorted = [...items].sort((a,b) => a.summary.localeCompare(b.summary,"es",{sensitivity:"base"}));
    return Object.keys(STORE_NAMES).filter(store => this._settings.stores[store]?.enabled).map(store => {
      const prices = this._rowPrices.filter(offer => offer.store === store);
      const lines = sorted.map(item => {
        const product = this._catalogProducts.get(productNameKey(item.summary));
        // Store tickets never substitute manual prices or prices from another shop.
        const offer = this._quantityOffer(item,cachedProductPrice(product ? {...product,price:null} : null,prices,store));
        return {name:item.summary,offer,quantity:this._purchaseQuantity(item,product)};
      });
      return {store,lines,coverage:lines.filter(line => line.offer).length,cents:lines.reduce((sum,line) => sum + (line.offer ? Math.round(Number(line.offer.price)*100) : 0),0)};
    }).filter(receipt => receipt.coverage).sort((a,b) => b.coverage-a.coverage || a.cents-b.cents || STORE_NAMES[a.store].localeCompare(STORE_NAMES[b.store],"es")).slice(0,4);
  }

  _receiptTotal(receipt) {
    const totals = new Map();
    for (const {offer} of receipt.lines) if (offer) totals.set(offer.currency,(totals.get(offer.currency) ?? 0)+Math.round(Number(offer.price)*100));
    if (!totals.size) totals.set("EUR",0);
    return [...totals].map(([currency,cents]) => new Intl.NumberFormat("es-ES",{style:"currency",currency}).format(cents/100)).join(" + ");
  }

  _renderReceipt(items, receipts, selected) {
    const root = this.shadowRoot.querySelector("#receipt");
    root.hidden = !this._ticket;
    if (!this._ticket) return;
    const previousUnknown = root.querySelector(".receipt-unknown");
    const unknownOpen = previousUnknown?.dataset.store === (selected?.store ?? "") && previousUnknown.open;
    const focusStore = this.shadowRoot.activeElement?.dataset.receiptStore;
    const make = (tag, className, text) => {
      const node = document.createElement(tag);
      node.className = className;
      if (text !== undefined) node.textContent = text;
      return node;
    };
    const stores = make("div","receipt-stores");
    stores.setAttribute("role","group"); stores.setAttribute("aria-label","Tiendas con precios guardados");
    for (const receipt of receipts) {
      const button = make("button",""); button.type="button"; button.dataset.receiptStore=receipt.store;
      button.setAttribute("aria-pressed",String(receipt.store === selected?.store));
      button.setAttribute("aria-label",`${STORE_NAMES[receipt.store]} · ${this._receiptTotal(receipt)} (${receipt.coverage}/${items.length})`);
      const copy = make("span","receipt-store-copy");
      copy.append(make("span","receipt-store-amount",this._receiptTotal(receipt)),document.createTextNode(" "),
        make("span","receipt-store-coverage",`(${receipt.coverage}/${items.length})`));
      button.append(this._storeLogo(receipt.store),copy);
      button.addEventListener("click",()=>{this._ticketStore=receipt.store;this._renderData();});
      stores.append(button);
    }
    // Retain legacy manual estimates when no enabled shop has a saved price.
    const receipt = selected ?? {lines:[...items].sort((a,b)=>a.summary.localeCompare(b.summary,"es",{sensitivity:"base"})).map(item=>({
      name:item.summary,offer:this._quantityOffer(item,this._listPrice(this._catalogProducts.get(productNameKey(item.summary)))),quantity:this._purchaseQuantity(item)
    }))};
    const paper = make("div","receipt-paper");
    paper.append(make("h3","",selected ? STORE_NAMES[selected.store] : "Últimos precios guardados"));
    const known = make("ul","receipt-known"), unknown=make("ul","receipt-missing");
    known.setAttribute("aria-label","Productos con precio"); unknown.setAttribute("aria-label","Productos sin precio");
    for (const line of receipt.lines) {
      const row=make("li","receipt-row");
      row.append(make("span","receipt-name",line.name),make("span","receipt-price",line.offer ? new Intl.NumberFormat("es-ES",{style:"currency",currency:line.offer.currency}).format(Number(line.offer.price)) : "Sin precio"));
      (line.offer ? known : unknown).append(row);
    }
    paper.append(known);
    if (unknown.childElementCount) {
      const group = make("details","receipt-unknown");
      group.dataset.store = selected?.store ?? "";
      group.open = Boolean(unknownOpen);
      group.append(make("summary","",`Productos sin precio (${unknown.childElementCount})`),unknown);
      paper.append(group);
    }
    const total=make("div","receipt-total");
    total.append(make("span","","Total estimado"),make("span","receipt-price",`≈ ${this._receiptTotal(receipt)}`));
    paper.append(total);
    root.replaceChildren(stores,paper);
    if (focusStore) [...stores.children].find(button=>button.dataset.receiptStore===focusStore)?.focus({preventScroll:true});
  }

  _pendingTotal(items) {
    const totals = new Map();
    for (const item of items) {
      const offer = this._quantityOffer(item,this._listPrice(this._catalogProducts.get(productNameKey(item.summary))));
      if (offer) totals.set(offer.currency,(totals.get(offer.currency) ?? 0) + Math.round(Number(offer.price)*100));
    }
    if (!totals.size) totals.set("EUR",0);
    return [...totals].map(([currency,cents]) => new Intl.NumberFormat("es-ES",{style:"currency",currency}).format(cents/100)).join(" + ");
  }

  _renderProductGroups(container,nodes,items,productFor,grouped,layout) {
    if(!grouped){container.replaceChildren(...nodes);return;}
    const groups=new Map();
    items.forEach((item,index)=>{
      const product=productFor(item), key=normalizedName(product?.category);
      const category=this._catalogCategories.get(key);
      if(!groups.has(key))groups.set(key,{key,name:category?.name||product?.category||'Sin categoría',category,nodes:[]});
      groups.get(key).nodes.push(nodes[index]);
    });
    container.replaceChildren(...[...groups.values()].sort((a,b)=>Number(!a.key)-Number(!b.key)||a.name.localeCompare(b.name,'es',{sensitivity:'base'})).map(group=>{
      const section=document.createElement('li');section.className='product-group';section.setAttribute('aria-label',group.name);
      const heading=document.createElement('h3');heading.className='product-group-heading';
      const icon=document.createElement('ha-icon');icon.setAttribute('icon',group.category?.icon||'mdi:label-outline');icon.setAttribute('aria-hidden','true');
      heading.append(icon,document.createTextNode(group.name));
      const grid=document.createElement('ul');grid.className='product-grid'+(layout==='rows'?' rows':'');grid.setAttribute('aria-label',group.name);grid.append(...group.nodes);
      section.append(heading,grid);return section;
    }));
  }

  _renderItems(container, items, disabled) {
    items=[...items].sort((a,b)=>(a.summary??'').localeCompare(b.summary??'','es',{sensitivity:'base'}));
    const focusedUid = this.shadowRoot.activeElement?.dataset.uid;
    const focusedDirection=this.shadowRoot.activeElement?.dataset.quantityDirection;
    const nodes = items.map((item, index) => {
      const key = item.uid ?? `missing:${item.status}:${index}`;
      this._usedRows.add(key);
      let row = this._rows.get(key);
      if (!row) {
        row = document.createElement("li");
        row.className = "list-product-row";
        const card = document.createElement("button");
        card.type = "button";
        const media = document.createElement("span");
        media.className = "product-media";
        const badge = document.createElement("span");
        badge.className = "category-badge";
        card.addEventListener("click", () => {
          const completed = row._item.status !== "completed";
          void this._runAction(() => this._session.setCompleted(row._item, completed), "Lista actualizada.");
        });
        const text = document.createElement("span");
        text.className = "item-text";
        const summary = document.createElement("span");
        summary.className = "summary";
        const description = document.createElement("span");
        description.className = "description";
        const tags = document.createElement("span");
        tags.className = "tags";
        text.append(summary, description);
        const metadata = document.createElement("span");
        metadata.className = "row-meta";
        card.append(badge, media, text, tags, metadata);
        const quantity=document.createElement('span');quantity.className='quantity-corner';quantity.append(document.createElement('span'));card.append(quantity);
        row.append(card);
        this._rows.set(key, row);
      }
      row._item = item;
      const card = row.querySelector("button");
      const completed = item.status === "completed";
      row.classList.toggle('list-completed',completed);
      card.className = `item ${completed ? "completed" : "pending"}`;
      card.disabled = disabled || !item.uid;
      card.dataset.uid = item.uid ?? "";
      card.title = item.summary ?? "Producto sin nombre";
      card.setAttribute("aria-pressed", String(completed));
      card.setAttribute("aria-label", `${completed ? "Volver a poner por comprar" : "Marcar como comprado"}: ${item.summary ?? "Producto"}`);
      const summary = row.querySelector(".summary");
      summary.textContent = item.summary ?? "Producto sin nombre";
      const product = this._catalogProducts.get(productNameKey(item.summary));
      const purchase=this._purchaseQuantity(item,product);
      const corner=row.querySelector('.quantity-corner');corner.hidden=purchase.quantity===1;
      const quantityText=quantityLabel(purchase);corner.firstChild.textContent=quantityText;corner.title=quantityText;
      const category = this._catalogCategories.get(normalizedName(product?.category));
      const metadata = row.querySelector(".row-meta");
      metadata.replaceChildren();
      if (category && this._listLayout === "rows") {
        const categoryTag = document.createElement("span");
        categoryTag.className = "row-category"; categoryTag.style.backgroundColor = category.color;
        categoryTag.title = category.name;
        categoryTag.setAttribute("aria-label",`Categoría: ${category.name}`);
        const icon = document.createElement("ha-icon"); icon.setAttribute("icon",category.icon); icon.setAttribute("aria-hidden","true");
        const label = document.createElement("span"); label.textContent = category.name;
        categoryTag.append(icon,label); metadata.append(categoryTag);
      }
      const offer = this._listLayout === "rows" ? this._quantityOffer(item,this._listPrice(product)) : null;
      const nutrition = this._listLayout === "rows" ? this._nutritionCodes(product).map(code=>this._nutrition.get(code.padStart(14,"0"))).find(value=>value?.grade) : null;
      if (nutrition) {
        const badge=document.createElement("span");badge.className="row-nutriscore";badge.dataset.grade=nutrition.grade;
        badge.textContent=nutrition.grade.toUpperCase();badge.title=`Nutri-Score ${badge.textContent} · ${nutrition.code}`;
        badge.setAttribute("aria-label",`Nutri-Score ${badge.textContent}`);metadata.append(badge);
      }
      if (offer) {
        const price = document.createElement("span"); price.className = "row-price";
        if (STORE_LOGOS[offer.store]) {
          const logo=document.createElement("img");logo.className="store-logo";logo.src=STORE_LOGOS[offer.store];
          logo.alt=STORE_NAMES[offer.store];logo.referrerPolicy="no-referrer";
          logo.addEventListener("error",()=>logo.remove(),{once:true});price.append(logo);
        }
        const label = document.createElement("span");
        label.textContent = new Intl.NumberFormat("es-ES",{style:"currency",currency:offer.currency}).format(Number(offer.price));
        price.title = offer.store ? `Último precio guardado · ${STORE_NAMES[offer.store] ?? offer.store}` : "Precio manual";
        price.append(label); metadata.append(price);
      }
      if(this._listLayout === 'rows' && purchase.quantity !== 1){
        const quantity=document.createElement('span');quantity.className='row-quantity';quantity.textContent=quantityText;quantity.title=quantityText;metadata.append(quantity);
      }
      const badge = row.querySelector(".category-badge");
      badge.hidden = !category;
      if (category) {
        badge.style.backgroundColor = category.color;
        badge.title = category.name;
        badge.setAttribute("aria-label", `Categoría: ${category.name}`);
        const icon = document.createElement("ha-icon");
        icon.setAttribute("icon", category.icon);
        badge.replaceChildren(icon);
      }
      const source = imageSource(product?.image_url);
      const iconName = product?.icon || category?.icon || "mdi:shopping";
      const mediaKey = JSON.stringify([source, iconName]);
      if (row._mediaKey !== mediaKey) {
        row._mediaKey = mediaKey;
        const placeholder = document.createElement("span");
        placeholder.className = "image placeholder";
        const icon = document.createElement("ha-icon");
        icon.setAttribute("icon", iconName);
        placeholder.append(icon);
        let media = placeholder;
        if (source) {
          media = document.createElement("img");
          media.className = "image";
          media.src = source;
          media.alt = "";
          media.loading = "lazy";
          media.referrerPolicy = "no-referrer";
          media.addEventListener("error", () => media.replaceWith(placeholder), { once: true });
        }
        row.querySelector(".product-media").replaceChildren(media);
      }
      const tags = row.querySelector(".tags");
      tags.replaceChildren(...(product?.tags ?? []).map(tag => {
        const node = document.createElement("span");
        node.className = "tag";
        node.textContent = tag;
        return node;
      }));
      tags.hidden = !tags.childElementCount;
      const description = row.querySelector(".description");
      description.textContent = item.description ?? "";
      description.hidden = !item.description;
      return row;
    });
    this._renderProductGroups(container,nodes,items,item=>this._catalogProducts.get(productNameKey(item.summary)),this._listGrouped,this._listLayout);
    if (focusedUid) {
      const card = [...container.querySelectorAll("button")].find(button => button.dataset.uid === focusedUid && button.dataset.quantityDirection===focusedDirection);
      card?.focus({ preventScroll: true });
    }
  }

  _purchaseQuantity(item,product=this._catalogProducts.get(productNameKey(item.summary))) {
    return purchaseQuantity(product,this._quantities.entries[this._session.entityId]?.[item.uid]);
  }

  _quantityOffer(item,offer) {
    if(!offer)return null;
    const value=this._purchaseQuantity(item);
    return {...offer,price:Number(offer.price)*value.quantity/value.unit_quantity};
  }

  async _addItem() {
    const input = this.shadowRoot.querySelector("#product-input");
    const summary = input.value.trim();
    if (!summary || this._busy || this._view !== "shopping") return;
    const entityId = this._session.entityId;
    const succeeded = await this._runAction(() => this._session.add(summary), "Producto añadido.");
    if (succeeded && entityId === this._session.entityId && input.value.trim() === summary) input.value = "";
    if (this.isConnected && !input.disabled) input.focus();
  }

  async _runAction(action, announcement) {
    if (this._busy) return false;
    this._busy = true;
    this._actionError = "";
    const entityId = this._session.entityId;
    this._renderData();
    try {
      await action();
      if (entityId === this._session.entityId) this.shadowRoot.querySelector("#announcement").textContent = announcement;
      return true;
    } catch (error) {
      if (entityId === this._session.entityId) this._actionError = errorMessage(error);
      return false;
    } finally {
      this._busy = false;
      if (this.isConnected) this._renderData();
    }
  }
}

if (!customElements.get("improved-shopping-list-panel")) {
  customElements.define("improved-shopping-list-panel", ImprovedShoppingListPanel);
}
