import { installDialogCloseButtons } from "./dialog-controls.js?v=0.17.0";
import { FEATURES, TodoSession, errorMessage, isAvailable, supports } from "./todo-client.js?v=0.17.0";
import { imageSource, normalizedName, productNameKey, cachedProductPrice } from "./catalog-panel.js?v=0.17.0";
import { ListSettingsSession, gradientTextColor } from "./list-settings-client.js?v=0.17.0";
import "./settings-panel.js?v=0.17.0";
import { ReadersSession } from "./readers-client.js?v=0.17.0";
import "./readers-panel.js?v=0.17.0";
import "./logs-panel.js?v=0.17.0";

const LOGO_URL = new URL("logo.png", import.meta.url).href;
const STORE_LOGOS = {
  mercadona:new URL("mercadona.png", import.meta.url).href,
  lidl:new URL("lidl.svg", import.meta.url).href,
  carrefour:"https://images.seeklogo.com/logo-png/31/2/carrefour-logo-png_seeklogo-318190.png",
  alcampo:"https://almeria.online/wp-content/uploads/2024/09/alcampo-logo.png",
};
const STORE_NAMES = {mercadona:"Mercadona",carrefour:"Carrefour",alcampo:"Alcampo",lidl:"Lidl"};
const searchText = value => normalizedName(value).normalize("NFD").replace(/\p{M}/gu, "");

class ImprovedShoppingListPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._session = new TodoSession(() => this._hass, () => this._renderData());
    this._settings = new ListSettingsSession(() => this._hass, () => this._applySettings());
    this._readers = new ReadersSession(() => this._hass, () => this._renderData());
    this._busy = false;
    this._rows = new Map();
    this._catalogProducts = new Map();
    this._catalogCategories = new Map();
    this._view = "shopping";
    this._listLayout = "grid";
    try { if (localStorage.getItem("isl-list-layout") === "rows") this._listLayout = "rows"; } catch { /* Storage may be disabled. */ }
    this._rowPrices = [];
    this._nutrition = new Map();
    this._onVisibility = () => {
      if (document.visibilityState === "visible") {
        void this._session.refresh();
        void this._settings.refresh();
        void this._readers.refresh();
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
    if (this._built) this.shadowRoot.querySelector("isl-logs").hass = value;
    this._ensureStarted();
    if (this._view === "readers") this.shadowRoot.querySelector("isl-readers").data = { hass:value, settings:this._settings, readers:this._readers };
    if (previousConnection && previousConnection !== value.connection) {
      void this._settings.start();
      void this._readers.start();
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
  }

  disconnectedCallback() {
    document.removeEventListener("visibilitychange", this._onVisibility);
    this._session.dispose();
    this._settings.stop();
    this._readers.stop();
    this._stopRowPrices();
    this._stopListNutrition();
    this._settingsApplied = false;
    this._started = false;
    this.shadowRoot.querySelector("#list-dialog")?.close();
  }

  _ensureStarted() {
    if (!this.isConnected || !this._built || !this._hass || !this._panel || this._started) return;
    this._started = true;
    void this._settings.start();
    void this._readers.start();
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
        #add-button { padding:0; align-self:auto; color:#fff; background:var(--isl-green); border:0; }
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
        h2 { margin:0; font-size:18px; font-weight:650; }
        .count { padding:5px 10px; border-radius:20px; background:var(--secondary-background-color,#edf4ee); font-size:13px; }
        ul { list-style:none; margin:0; padding:0; }
        #items-card { background:transparent; border:0; padding:0; }
        .product-grid { display:grid; grid-template-columns:repeat(var(--isl-columns,3),minmax(0,1fr)); gap:16px; }
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
        .empty { padding:28px 8px; text-align:center; color:var(--secondary-text-color,#63766b); line-height:1.6; }
        .empty strong { display:block; font-size:18px; color:var(--primary-text-color,#20352d); margin-bottom:5px; }
        details { margin-top:24px; }
        summary { cursor:pointer; color:var(--secondary-text-color,#63766b); font-size:14px; padding:10px 0; }
        #completed-summary { display:flex; align-items:center; gap:8px; }
        #completed-summary::before { content:"▸"; flex:none; }
        #completed-details[open] #completed-summary::before { content:"▾"; }
        #completed-label { flex:1; min-width:0; }
        #clear-completed { display:inline-flex; align-items:center; justify-content:center; gap:6px; flex:none; margin-left:auto; min-height:36px; font-size:12px; padding:8px 10px; white-space:nowrap; border:1px solid var(--divider-color,#dfe7e1); border-radius:10px; background:transparent; color:inherit; }
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
      </style>
      <header>
        <button class="menu" aria-label="Abrir menú de Home Assistant"><ha-icon icon="mdi:menu"></ha-icon></button>
        <div class="branding"><img class="brand-logo" src="${LOGO_URL}" alt="" width="44" height="44"><div class="brand-copy"><span class="brand">Improved Shopping List</span><span class="version">0.17.0</span></div></div>
        <nav class="section-nav" aria-label="Apartados">
          <button id="nav-shopping" aria-label="Lista" aria-pressed="true"><ha-icon icon="mdi:shopping" aria-hidden="true"></ha-icon><span class="nav-label">Lista</span></button>
          <button id="nav-catalog" aria-label="Catálogo" aria-pressed="false"><ha-icon icon="mdi:view-grid" aria-hidden="true"></ha-icon><span class="nav-label">Catálogo</span></button>
          <button id="nav-readers" aria-label="Lectores" aria-pressed="false"><ha-icon icon="mdi:barcode-scan" aria-hidden="true"></ha-icon><span class="nav-label">Lectores</span></button>
          <button id="nav-settings" aria-label="Ajustes" aria-pressed="false"><ha-icon icon="mdi:cog" aria-hidden="true"></ha-icon><span class="nav-label">Ajustes</span></button>
          <button id="nav-logs" aria-label="Logs" aria-pressed="false"><ha-icon icon="mdi:format-list-group" aria-hidden="true"></ha-icon><span class="nav-label">Logs</span></button>
        </nav>
      </header>
      <main>
        <div id="error" class="notice error" role="alert" hidden></div>
        <div id="status" class="notice" role="status" hidden></div>
        <section id="list-controls" aria-label="Seleccionar lista y añadir productos">
          <form id="add-form">
            <div class="input-wrap"><label class="sr-only" for="product-input">Añadir producto</label><input id="product-input" type="text" maxlength="255" placeholder="Busca o añade un producto" autocomplete="off" role="combobox" aria-autocomplete="list" aria-expanded="false" aria-controls="product-suggestions" aria-describedby="predictive-count" required><ul id="product-suggestions" class="predictive-results" role="listbox" aria-label="Productos del catálogo" hidden></ul><span id="predictive-count" class="sr-only" role="status" aria-live="polite"></span></div>
            <button id="add-button" class="icon-button" type="submit" aria-label="Añadir" title="Añadir producto"><ha-icon icon="mdi:plus-thick"></ha-icon></button>
            <button id="choose-list" class="icon-button" type="button" aria-label="Seleccionar lista" title="Seleccionar lista" aria-haspopup="dialog" aria-controls="list-dialog"><ha-icon icon="mdi:format-list-checks"></ha-icon></button>
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
          <div class="list-header"><h2 id="pending-title">Lista de la compra</h2><div class="list-totals"><span id="pending-count" class="count">0 productos</span><span id="pending-total" class="count" title="Importe aproximado · Últimos precios guardados" aria-live="polite">≈ 0,00 €</span></div></div>
          <ul id="pending" class="product-grid" aria-label="Lista de la compra"></ul>
          <div id="empty" class="empty" hidden></div>
          <details id="completed-details"><summary id="completed-summary"><span id="completed-label">Compras recientes</span><button id="clear-completed" type="button"><ha-icon icon="mdi:delete" aria-hidden="true"></ha-icon>Limpiar productos</button></summary><ul id="completed" class="product-grid" aria-label="Compras recientes"></ul></details>
        </section>
        <isl-catalog hidden></isl-catalog>
        <isl-settings hidden></isl-settings>
        <isl-readers hidden></isl-readers>
        <isl-logs hidden></isl-logs>
        <div id="announcement" class="sr-only" role="status" aria-live="polite"></div>
      </main>`;
    this._built = true;
    const root = this.shadowRoot;
    installDialogCloseButtons(root);
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
      this._listLayout = this._listLayout === "grid" ? "rows" : "grid";
      try { localStorage.setItem("isl-list-layout", this._listLayout); } catch { /* Storage may be disabled. */ }
      this._renderData();
    });
    root.querySelector("#nav-shopping").addEventListener("click", () => this._switchView("shopping"));
    root.querySelector("#clear-completed").addEventListener("click", event => {
      event.preventDefault();
      event.stopPropagation();
      void this._runAction(() => this._session.clearCompleted(), "Productos completados eliminados de la lista.");
    });
    root.querySelector("#nav-catalog").addEventListener("click", () => this._switchView("catalog"));
    root.querySelector("#nav-settings").addEventListener("click", () => this._switchView("settings"));
    root.querySelector("#nav-readers").addEventListener("click", () => this._switchView("readers"));
    root.querySelector("#nav-logs").addEventListener("click", () => this._switchView("logs"));
    root.querySelector("isl-readers").onSuggestions = () => { this._switchView("catalog"); root.querySelector("isl-catalog").showSuggestions(); };
    root.querySelector("isl-settings").onAction = (action, entity) => this._settings.update(action, entity);
    root.querySelector("isl-settings").onAppearance = appearance => this._settings.saveAppearance(appearance);
    root.querySelector("isl-catalog").onAdd = (product) => this._runAction(
      () => this._session.add(product.name), "",
    );
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
    root.querySelector("#list-dialog").addEventListener("close", () => root.querySelector("#choose-list").focus());
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
    this._view = view;
    this._actionError = "";
    const root = this.shadowRoot;
    root.querySelector("#list-controls").hidden = view !== "shopping";
    root.querySelector("#items-card").hidden = view !== "shopping";
    root.querySelector("#add-form").hidden = view !== "shopping";
    root.querySelector("isl-catalog").hidden = view !== "catalog";
    root.querySelector("isl-settings").hidden = view !== "settings";
    root.querySelector("isl-readers").hidden = view !== "readers";
    root.querySelector("isl-logs").hidden = view !== "logs";
    root.querySelector("isl-logs").active = view === "logs";
    root.querySelector("#nav-shopping").setAttribute("aria-pressed", String(view === "shopping"));
    root.querySelector("#nav-catalog").setAttribute("aria-pressed", String(view === "catalog"));
    root.querySelector("#nav-settings").setAttribute("aria-pressed", String(view === "settings"));
    root.querySelector("#nav-readers").setAttribute("aria-pressed", String(view === "readers"));
    root.querySelector("#nav-logs").setAttribute("aria-pressed", String(view === "logs"));
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
    const rows = this._listLayout === "rows";
    const layoutLabel = rows ? "Cambiar a vista de cuadrícula" : "Cambiar a vista de filas";
    const layoutButton = root.querySelector("#toggle-list-layout");
    layoutButton.setAttribute("aria-label", layoutLabel); layoutButton.title = layoutLabel;
    layoutButton.querySelector("ha-icon").setAttribute("icon", rows ? "mdi:view-comfy" : "mdi:view-sequential");
    for (const id of ["pending","completed"]) root.querySelector("#" + id).classList.toggle("rows", rows);
    this._ensureRowPrices();
    const appearance = this._settings.appearance;
    this.style.setProperty("--isl-gradient-start", appearance.gradient_start);
    this.style.setProperty("--isl-gradient-end", appearance.gradient_end);
    this.style.setProperty("--isl-gradient-text", gradientTextColor(appearance.gradient_start, appearance.gradient_end));
    this.style.setProperty("--isl-completed-gradient-start", appearance.completed_gradient_start);
    this.style.setProperty("--isl-completed-gradient-end", appearance.completed_gradient_end);
    this.style.setProperty("--isl-completed-gradient-text", gradientTextColor(appearance.completed_gradient_start, appearance.completed_gradient_end));
    this.style.setProperty("--isl-columns", appearance.columns);
    this.style.setProperty("--isl-mobile-columns", appearance.mobile_columns);
    root.querySelector("isl-settings").data = { hass: this._hass, settings: this._settings, products:[...this._catalogProducts.values()] };
    root.querySelector("isl-readers").data = { hass: this._hass, settings: this._settings, readers: this._readers };
    root.querySelector("isl-logs").hass = this._hass;
    const state = this._hass.states[session.entityId];
    const available = isAvailable(state);
    const canCreate = available && supports(state, FEATURES.CREATE);
    const canUpdate = available && supports(state, FEATURES.UPDATE);
    const catalog = root.querySelector("isl-catalog");
    catalog.priceData = {offers:this._rowPrices,favorite:this._settings.favoriteStore};
    catalog.hass = this._hass;
    catalog.readerData = this._readers;
    catalog.canAdd = canCreate && !this._busy && !session.loading;
    catalog.listName = state?.attributes.friendly_name ?? session.entityId;
    catalog.listEntity = session.entityId;
    catalog.listItems = available && !session.loading ? session.items : [];
    catalog.pendingItems = available && !session.loading
      ? session.items.filter(item => item.status !== "completed") : [];
    const locked = this._busy || session.loading || !available;
    root.querySelector("#product-input").disabled = locked || !canCreate;
    root.querySelector("#add-button").disabled = locked || !canCreate;
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
    const message = this._actionError || (this._view === "shopping" ? session.error || this._settings.error : "");
    error.hidden = !message;
    error.textContent = message;
    const pending = session.items.filter((item) => item.status !== "completed");
    const completed = session.items.filter((item) => item.status === "completed");
    if (this._rowsEntity !== session.entityId) {
      this._rows.clear();
      this._rowsEntity = session.entityId;
    }
    this._usedRows = new Set();
    root.querySelector("#pending-count").textContent = `${pending.length} ${pending.length === 1 ? "producto" : "productos"}`;
    const total = this._pendingTotal(pending);
    root.querySelector("#pending-total").textContent = `≈ ${total}`;
    root.querySelector("#pending-total").setAttribute("aria-label", `Importe aproximado de la lista: ${total}`);
    root.querySelector("#items-card").setAttribute("aria-busy", String(session.loading));
    this._renderItems(root.querySelector("#pending"), pending, locked || !canUpdate);
    this._renderItems(root.querySelector("#completed"), completed, locked || !canUpdate);
    if (rows && this._view === "shopping") void this._loadListNutrition();
    for (const key of this._rows.keys()) {
      if (!this._usedRows.has(key)) this._rows.delete(key);
    }
    const details = root.querySelector("#completed-details");
    details.hidden = !completed.length;
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
    this._renderPredictions();
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
    const pending = Promise.allSettled(["mercadona","carrefour","alcampo","lidl"].map(store =>
      this._hass.callWS({type:"improved_shopping_list/catalog/store_prices",store}))).then(results => {
        if (token !== this._rowPricesToken || !this.isConnected) return;
        const stores = ["mercadona","carrefour","alcampo","lidl"];
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

  _pendingTotal(items) {
    const totals = new Map();
    for (const item of items) {
      const offer = this._listPrice(this._catalogProducts.get(productNameKey(item.summary)));
      if (offer) totals.set(offer.currency,(totals.get(offer.currency) ?? 0) + Math.round(Number(offer.price)*100));
    }
    if (!totals.size) totals.set("EUR",0);
    return [...totals].map(([currency,cents]) => new Intl.NumberFormat("es-ES",{style:"currency",currency}).format(cents/100)).join(" + ");
  }

  _renderItems(container, items, disabled) {
    const focusedUid = this.shadowRoot.activeElement?.dataset.uid;
    const nodes = items.map((item, index) => {
      const key = item.uid ?? `missing:${item.status}:${index}`;
      this._usedRows.add(key);
      let row = this._rows.get(key);
      if (!row) {
        row = document.createElement("li");
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
        row.append(card);
        this._rows.set(key, row);
      }
      row._item = item;
      const card = row.querySelector("button");
      const completed = item.status === "completed";
      card.className = `item ${completed ? "completed" : "pending"}`;
      card.disabled = disabled || !item.uid;
      card.dataset.uid = item.uid ?? "";
      card.title = item.summary ?? "Producto sin nombre";
      card.setAttribute("aria-pressed", String(completed));
      card.setAttribute("aria-label", `${completed ? "Volver a poner por comprar" : "Marcar como comprado"}: ${item.summary ?? "Producto"}`);
      const summary = row.querySelector(".summary");
      summary.textContent = item.summary ?? "Producto sin nombre";
      const product = this._catalogProducts.get(productNameKey(item.summary));
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
      const offer = this._listLayout === "rows" ? this._listPrice(product) : null;
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
    container.replaceChildren(...nodes);
    if (focusedUid) {
      const card = [...container.querySelectorAll("button")].find(button => button.dataset.uid === focusedUid);
      card?.focus({ preventScroll: true });
    }
  }

  async _addItem() {
    const input = this.shadowRoot.querySelector("#product-input");
    const summary = input.value.trim();
    if (!summary || this._busy) return;
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
