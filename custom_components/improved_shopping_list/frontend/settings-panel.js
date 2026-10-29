import "./shopping-places.js?v=0.53.0";
import "./dia-prices-settings.js?v=0.53.0";
import "./alcampo-settings.js?v=0.53.0";
import "./catalog-sources.js?v=0.53.0";
import "./carrefour-account.js?v=0.53.0";
import "./lidl-account.js?v=0.53.0";
import "./logs-panel.js?v=0.53.0";
import "./notification-settings.js?v=0.53.0";
import "./readers-panel.js?v=0.53.0";
import { installDialogCloseButtons } from "./dialog-controls.js?v=0.53.0";
import { installToggleStyles } from "./toggle-styles.js?v=0.53.0";
import { todoEntities, isAvailable } from "./todo-client.js?v=0.53.0";
import { DEFAULT_APPEARANCE, gradientTextColor } from "./list-settings-client.js?v=0.53.0";

const MERCADONA_LOGO_URL = new URL("mercadona.png", import.meta.url).href;

function storeError(name, message) {
  let detail=String(message??"").trim();
  const prefix=new RegExp(`^(?:${name}(?::\\s*|\\s+))+`,"i");
  detail=detail.replace(prefix,"");
  return `${name}: ${detail}`;
}

class ImprovedShoppingSettings extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._view = "lists";
  }

  set data(value) { this._data = value; if(this.isConnected&&!this._built)this._build(); this._render(); }
  set hass(value) {
    if(!this._data)return;
    this._data={...this._data,hass:value};this._syncReaders();this._syncCatalogSources();
    const places=this.shadowRoot.querySelector('isl-shopping-places');if(places)places.data=this._data;
    if(this._built){
      const settings=this._data.settings;
      const locked=value?.user?.is_admin!==true||!settings.loaded||settings.loading||this._busy;
      this._renderPurchasePersons(locked,settings.purchaseDetection??{});
    }
  }

  set active(value) { this._active = Boolean(value); if(!this._active){this.shadowRoot.querySelector("#lidl-dialog")?.close();this.shadowRoot.querySelector("isl-lidl-account")?.deactivate();this.shadowRoot.querySelector('#carrefour-dialog')?.close();this.shadowRoot.querySelector('isl-carrefour-account')?.deactivate();this.shadowRoot.querySelector('#dia-dialog')?.close();this.shadowRoot.querySelector('isl-dia-prices-settings')?.deactivate();} this._syncLogs(); this._syncReaders(); this._syncCatalogSources(); }

  _syncCatalogSources(){const source=this.shadowRoot.querySelector('isl-catalog-sources');if(source){source.data=this._data;source.active=this._active&&this._view==='stores';}}

  _syncReaders() {
    const readers=this.shadowRoot.querySelector('isl-readers');
    if(!readers)return;
    const active=Boolean(this._active&&this._view==='readers'&&this.isConnected);
    readers.active=active;
    if(active&&this._data?.readers)readers.data={hass:this._data.hass,settings:this._data.settings,readers:this._data.readers};
  }

  _syncLogs() {
    const logs = this.shadowRoot.querySelector("isl-logs");
    if (!logs) return;
    if (this._data?.hass) logs.hass = this._data.hass;
    logs.active = Boolean(this._active && this._view === "logs" && this.isConnected);
  }


  connectedCallback() {
    if (this._data&&!this._built) this._build();
    this._render();
  }

  disconnectedCallback() {
    this.active = false;
    this.shadowRoot.querySelector("isl-carrefour-account")?.deactivate();
    this.shadowRoot.querySelector("#lidl-dialog")?.close();this.shadowRoot.querySelector("isl-lidl-account")?.deactivate();
    for (const store of ["consum", "lasirena", "eroski", "dia"]) this.shadowRoot.querySelector(`#${store}-dialog`)?.close();
    clearInterval(this._pricesProgressTimer);
    this.shadowRoot.querySelector("#prices-progress-dialog")?.close();
    this.shadowRoot.querySelector("#price-schedule-dialog")?.close();
    this._priceStatusToken = null; this._priceStatusConnection = null; this._stopPriceStatus?.(); this._stopPriceStatus = null;
    this._productsLoading = false; this._productsGeneration = (this._productsGeneration || 0) + 1;
    this._carrefourGeneration = (this._carrefourGeneration || 0) + 1; this._carrefourLoading = false; this._alcampoGeneration = (this._alcampoGeneration || 0) + 1;
    this.shadowRoot.querySelector("#alcampo-dialog")?.close(); this.shadowRoot.querySelector("#carrefour-dialog")?.close(); this.shadowRoot.querySelector("#store-dialog")?.close();
  }

  _build() {
    this.shadowRoot.innerHTML = `
      <style>
        :host { display:block; color:var(--primary-text-color,#20352d); }
        :host([hidden]),[hidden] { display:none !important; }
        * { box-sizing:border-box; }
        h1 { font-size:32px; letter-spacing:-.03em; margin:0; }
        h2 { font-size:20px; margin:0 0 16px; }
        p { color:var(--secondary-text-color,#63766b); line-height:1.6; font-size:13px; }
        .card { padding:22px; border:1px solid var(--divider-color,#dfe7e1); border-radius:16px; background:var(--card-background-color,#fff); margin-top:20px; }
        button,select,input { font:inherit; min-height:46px; border:1px solid var(--divider-color,#dfe7e1); border-radius:10px; color:inherit; background:transparent; padding:10px 14px; }
        button { cursor:pointer; }
        button:disabled,select:disabled,input:disabled { opacity:.5; cursor:default; }
        button:focus-visible,select:focus-visible,input:focus-visible { outline:3px solid var(--primary-color,#267052); outline-offset:3px; }
        .settings-heading { display:flex; align-items:center; justify-content:space-between; gap:16px; margin:0 0 16px; }
        .settings-heading h1 { flex:none; margin:0; }
        .settings-tabs { display:flex; flex-wrap:nowrap; min-width:0; gap:6px; margin-left:auto; overflow-x:auto; scrollbar-width:thin; }
        .settings-tabs button { display:inline-flex; flex:none; align-items:center; justify-content:center; gap:6px; padding:10px; font-size:13px; white-space:nowrap; }
        .settings-tabs button[aria-pressed=false] .tab-label { display:none; }
        @media(max-width:650px) { .settings-heading { gap:8px; }.settings-heading h1 { font-size:26px; }.settings-tabs { gap:4px; }.settings-tabs button { min-width:32px; padding:10px 5px; } }
        @media(max-width:390px) { .settings-heading { gap:6px; }.settings-heading h1 { font-size:22px; }.settings-tabs button { min-width:28px; padding-inline:3px; font-size:12px; }.settings-tabs ha-icon { --mdc-icon-size:18px; width:18px; height:18px; } }
        @media(max-width:360px) { .settings-heading { gap:4px; } .settings-heading h1 { font-size:18px; } .settings-tabs { gap:2px; } .settings-tabs button { min-width:24px; padding-inline:2px; } .settings-tabs ha-icon { --mdc-icon-size:16px; width:16px; height:16px; } }
        .settings-tabs ha-icon { --mdc-icon-size:20px; display:flex; align-items:center; justify-content:center; width:20px; height:20px; flex:none; line-height:0; }
        .settings-tabs [aria-pressed=true] { background:var(--secondary-background-color,#edf4ee); font-weight:650; }

        .appearance-fields { display:grid; grid-template-columns:1fr 1fr; gap:18px; }
        .appearance-fields.appearance-colors { grid-template-columns:repeat(4,minmax(0,1fr)); align-items:stretch; }
        .appearance-colors > div { min-width:0; display:flex; flex-direction:column; justify-content:flex-end; gap:6px; }
        .appearance-colors label { overflow-wrap:anywhere; line-height:1.4; }
        .appearance-colors input { min-width:0; flex-shrink:0; }
        input[type=checkbox] { min-height:20px; width:20px; vertical-align:middle; accent-color:#267052; }
        input[type=color] { display:block; width:100%; padding:5px; cursor:pointer; }
        .appearance-actions { display:flex; justify-content:flex-end; flex-wrap:wrap; gap:10px; margin-top:24px; }
        .appearance-previews { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:18px; margin-top:24px; }
        .appearance-previews + .appearance-fields { margin-top:24px; }
        .preview { display:grid; place-items:center; min-width:0; min-height:120px; border-radius:16px; padding:20px; font-weight:650; text-align:center; overflow-wrap:anywhere; }
        @media(max-width:540px) { .appearance-fields { grid-template-columns:1fr; } }
        .store-row { display:grid; grid-template-columns:56px minmax(0,1fr) auto; gap:8px 12px; align-items:center; }
        .store-row[data-enabled=false] { opacity:.55; }
        .store-row[data-enabled=true] { background:rgba(38,112,82,.10); }
        #price-schedule-form .price-config-row { display:grid; grid-template-columns:minmax(0,1fr) minmax(90px,140px); gap:18px; align-items:center; margin:18px 0; }
        .price-config-row label { margin:0; }.price-config-row input:not([type=checkbox]) { min-width:0; width:100%; }.price-config-row .store-toggle { justify-self:end; }
        #price-update-time { display:block; width:100%; }
        #settings-stores { container-type:inline-size; }
        .stores-grid { display:grid; grid-template-columns:minmax(0,1fr); gap:12px; }
        @container(min-width:800px) { .stores-grid { grid-template-columns:repeat(2,minmax(0,1fr)); } }
        .store-logo { width:56px; height:56px; padding:8px; flex:none; object-fit:contain; border-radius:10px; background:#fff; }
        .store-row .store-logo { grid-column:1; grid-row:1; }
        .store-linked-count { font-size:12px;opacity:.65;margin-top:4px; }
        .store-name { grid-column:2; grid-row:1; min-width:0; display:flex; flex-direction:column; justify-content:center; overflow-wrap:anywhere; }
        .store-favorite[aria-pressed=true] { color:#e53935; }
        .stores-heading { display:flex; align-items:center; justify-content:space-between; gap:12px; flex-wrap:wrap; margin-bottom:16px; }
        .stores-heading h2 { margin:0; }
        .stores-heading-actions { display:flex; align-items:center; justify-content:flex-end; gap:10px; margin-left:auto; }
        .stores-footer { margin-top:14px; text-align:right; font-size:11px; color:var(--secondary-text-color,#63766b); }
        #stores-last-updated { white-space:nowrap; }
        .store-refresh { display:inline-flex; align-items:center; justify-content:center; flex:none; width:44px; height:44px; min-height:44px; padding:0; }
        .store-refresh ha-icon { width:20px; height:20px; flex:none; --mdc-icon-size:20px; }
        .store-controls { grid-column:3; grid-row:1; display:flex; align-items:center; gap:12px; margin-left:auto; flex:none; }
        .store-toggle[type=checkbox] { appearance:none; position:relative; width:40px; height:24px; min-height:24px; margin:0; padding:0; border:0; border-radius:20px; background:#b3261e; cursor:pointer; }
        .store-toggle::before { content:""; position:absolute; top:4px; left:4px; width:16px; height:16px; border-radius:50%; background:white; }
        .store-toggle:checked { background:#267052; }.store-toggle:checked::before { transform:translateX(16px); }
        .store-cog { display:flex; align-items:center; justify-content:center; padding:0; width:44px; height:44px; min-height:44px; border:0; background:transparent; box-shadow:none; }
        .store-products-badge { display:inline-flex; align-items:center; justify-content:center; gap:6px; min-height:32px; padding:5px 10px; border:0; border-radius:999px; background:var(--secondary-background-color,#edf4ee); color:var(--primary-text-color); font-weight:650; white-space:nowrap; }
        .store-products-badge ha-icon { --mdc-icon-size:20px; width:20px; height:20px; display:flex; align-items:center; justify-content:center; flex:none; }
        .store-cog ha-icon { display:flex; align-items:center; justify-content:center; width:24px; height:24px; --mdc-icon-size:24px; }
        dialog { color:inherit; background:var(--card-background-color,#fff); width:min(680px,calc(100vw - 28px)); max-height:calc(100dvh - 28px); border:1px solid var(--divider-color,#dfe7e1); border-radius:18px; padding:24px; }
        dialog::backdrop { background:rgba(0,0,0,.4); }
        .store-products { display:grid; gap:12px; margin-top:16px; }.store-product { display:flex; justify-content:space-between; align-items:center; gap:12px; border:1px solid var(--divider-color,#dfe7e1); border-radius:10px; padding:14px; }
        .store-cache-footer { text-align:left; margin:16px 0 0; font-size:12px; }
        #stores-refresh-error { white-space:pre-line; }
        .store-progress { text-align:center; }
        .store-progress-track { position:relative; }
        .store-progress-percentage { position:absolute; inset:0; display:grid; place-items:center; pointer-events:none; color:#fff; font-size:13px; font-weight:700; line-height:26px; text-shadow:0 0 2px #000,0 1px 2px #000; }
        #store-progress-count { position:absolute; width:1px; height:1px; padding:0; margin:-1px; overflow:hidden; clip-path:inset(50%); white-space:nowrap; }
        .store-progress progress { display:block; width:100%; height:26px; appearance:none; border:0; border-radius:13px; overflow:hidden; background:var(--divider-color,#dfe7e1); accent-color:var(--primary-color,#267052); }
        .store-progress progress::-webkit-progress-bar { background:var(--divider-color,#dfe7e1); border-radius:13px; }
        .store-progress progress::-webkit-progress-value { background:var(--primary-color,#267052); border-radius:13px; }
        .store-progress progress::-moz-progress-bar { background:var(--primary-color,#267052); border-radius:13px; }.store-progress p { margin:6px 0; }
        .store-product-info { min-width:0; overflow-wrap:anywhere; }.store-product-info p { margin:4px 0 0; }.store-price { flex:none; max-width:50%; text-align:right; }.store-price p { margin:4px 0; font-size:12px; }
        @media(max-width:540px) { dialog { padding:18px; }.store-row { grid-template-columns:40px minmax(0,1fr) auto; padding:12px; gap:8px; }.store-logo { width:40px; height:40px; padding:6px; }.store-controls { gap:8px; }.store-cog { width:32px; height:32px; min-height:32px; } }
        .primary { color:#fff; background:#267052; border:0; }
        .add-row { display:flex; align-items:end; gap:10px; }
        .select-wrap { flex:1; min-width:0; }
        .gateway-add { display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1fr) auto; gap:14px; align-items:end; }
        .gateway-add .gateway-cleanup { grid-column:1/-1; }
        .gateway-cleanup { display:flex; align-items:center; gap:10px; margin:0; font-weight:400; }
        .gateway-cleanup input { flex:none; }
        .gateway-options { flex:1; min-width:180px; display:grid; gap:14px; }
        @media(max-width:650px) { .gateway-add { grid-template-columns:minmax(0,1fr); }.gateway-add button { justify-self:end; } }
        .community-export { display:flex; align-items:center; gap:24px; }
        .community-export p { flex:1; min-width:0; }
        .community-action { display:inline-flex; align-items:center; justify-content:flex-start; gap:8px; flex:0 0 240px; width:240px; max-width:100%; min-height:46px; padding:10px 14px; border:0; border-radius:10px; text-decoration:none; text-align:left; font:inherit; }
        .community-action svg { width:16px; height:16px; flex:none; fill:currentColor; }
        #settings-community a { color:var(--primary-color,#267052); }
        #settings-community .community-join { background:#0088cc; color:#fff; }
        #settings-community .community-patreon { background:#000; color:#fff; }
        .community-action:focus-visible { outline:3px solid var(--primary-color,#267052); outline-offset:3px; }
        @media(max-width:540px) { .community-export { flex-wrap:wrap; gap:8px; }.community-export p { flex-basis:100%; }.community-action { flex-basis:auto; margin-left:auto; } }
        label { display:block; font-size:13px; font-weight:600; margin-bottom:8px; }
        select { width:100%; background:var(--card-background-color,#fff); }
        .lists { display:grid; gap:12px; margin-top:24px; }
        article { display:flex; flex-wrap:wrap; gap:14px; align-items:center; padding:18px; border:1px solid var(--divider-color,#dfe7e1); border-radius:12px; }
        .list-info { flex:1; min-width:150px; overflow-wrap:anywhere; }
        .list-name-mode{display:flex;align-items:center;gap:8px;margin-top:8px;font-size:12px;line-height:1.4;cursor:pointer}.list-name-mode input[type=checkbox]{width:18px;height:18px;min-height:18px;flex:none;margin:0;padding:0}
        .list-action { display:grid; place-items:center; width:44px; height:44px; min-height:44px; padding:0; border:0; flex:none; }
        .list-action ha-icon { display:block; width:22px; height:22px; --mdc-icon-size:22px; }
        .list-remove { background:#d32f2f; color:#fff; }
        .list-primary[aria-pressed=true] { background:#ffca28; color:#352800; }
        h3 { margin:0; font-size:16px; }
        .entity { margin:5px 0 0; font-size:12px; }
        .badge { display:inline-flex; gap:5px; align-items:center; color:var(--primary-color,#267052); font-size:12px; margin-top:8px; }
        .badge ha-icon { --mdc-icon-size:18px; }
        .actions { display:flex; gap:8px; flex-wrap:wrap; }
        .notice { padding:12px 14px; border-radius:10px; background:var(--secondary-background-color,#edf4ee); font-size:13px; line-height:1.6; margin:14px 0; }
        .error { color:var(--error-color,#bd3636); border:1px solid var(--error-color,#bd3636); }
        @media(max-width:540px) { .card { padding:18px 14px; } .add-row { flex-wrap:wrap; } .select-wrap { flex-basis:100%; } .actions { width:100%; } }
        #carrefour-products-view,#alcampo-products-view,#store-products-view,[id$="-products-view"]{display:none!important}#carrefour-dialog>h2{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%)}
      .zone-settings{margin-top:20px;padding-top:16px;border-top:1px solid var(--divider-color,#dfe7e1)}.zone-settings select{width:100%;max-width:320px;min-height:120px}.zone-settings label{display:block;margin-bottom:10px}.zone-settings button{margin-top:12px}.zone-settings p{margin:8px 0}.purchase-detection-settings{margin-top:24px;padding-top:18px;border-top:1px solid var(--divider-color,#dfe7e1)}.detection-row{display:flex;align-items:center;justify-content:space-between;gap:16px;margin-top:16px}.detection-row input[type=number]{width:90px;text-align:center;flex:none}
      .purchase-users-field{display:grid;grid-template-columns:minmax(0,1fr) minmax(180px,360px);gap:12px;align-items:start;margin-top:16px}.purchase-users-field>span{padding-top:12px}.person-picker{min-width:0;border:1px solid var(--divider-color,#dfe7e1);border-radius:10px}.person-picker summary{display:flex;align-items:center;justify-content:space-between;gap:12px;min-height:46px;padding:10px 12px;list-style:none;cursor:pointer}.person-picker summary::-webkit-details-marker{display:none}.person-picker summary span{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.person-picker summary ha-icon{width:20px;height:20px;--mdc-icon-size:20px;flex:none}.person-picker[open] summary ha-icon{transform:rotate(180deg)}.person-picker summary:focus-visible{outline:3px solid var(--primary-color,#267052);outline-offset:3px}.person-options{max-height:240px;overflow-y:auto;padding:0 8px 8px}.person-option{display:flex;align-items:center;gap:10px;margin:0;padding:10px 4px;cursor:pointer;overflow-wrap:anywhere}.person-option input[type=checkbox]{width:20px;height:20px;min-height:20px;flex:none;padding:0;margin:0}.person-option:has(input:disabled){cursor:default;opacity:.65}.person-options .helper{margin:4px}.purchase-users>h3{font-size:20px;margin:0}
      .detection-pair{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:24px;margin-top:16px}.detection-pair>.detection-row{margin:0;min-width:0}
      @media(max-width:540px){.purchase-users-field{grid-template-columns:1fr;gap:8px}.purchase-users-field>span{padding-top:0}.detection-pair{gap:16px}.detection-pair>.detection-row{flex-direction:column;align-items:stretch;gap:10px}.detection-pair input{align-self:flex-end}.detection-pair input[type=number]{width:72px}}
    </style>
      <div class="settings-heading"><h1>Ajustes</h1>
      <nav class="settings-tabs" aria-label="Vistas de ajustes"><button id="settings-view-lists" aria-label="Listas" aria-pressed="true"><ha-icon icon="mdi:format-list-checks" aria-hidden="true"></ha-icon><span class="tab-label">Listas</span></button><button id="settings-view-appearance" aria-label="Personalización" aria-pressed="false"><ha-icon icon="mdi:palette" aria-hidden="true"></ha-icon><span class="tab-label">Personalización</span></button><button id="settings-view-stores" aria-label="Tiendas" aria-pressed="false"><ha-icon icon="mdi:store" aria-hidden="true"></ha-icon><span class="tab-label">Tiendas</span></button><button id="settings-view-notifications" aria-label="Notificaciones" aria-pressed="false"><ha-icon icon="mdi:bell-outline" aria-hidden="true"></ha-icon><span class="tab-label">Notificaciones</span></button><button id="settings-view-community" aria-label="Comunidad" aria-pressed="false"><ha-icon icon="mdi:account-group" aria-hidden="true"></ha-icon><span class="tab-label">Comunidad</span></button><button id="settings-view-logs" aria-label="Logs" aria-pressed="false"><ha-icon icon="mdi:format-list-group" aria-hidden="true"></ha-icon><span class="tab-label">Logs</span></button></nav></div>
      <div id="settings-error" class="notice error" role="alert" hidden></div>
      <div id="settings-status" class="notice" role="status" hidden></div>
      <p id="admin-help" hidden>Necesitas una cuenta administradora de Home Assistant para modificar estos ajustes.</p>
      <section id="settings-lists" class="card" aria-labelledby="settings-lists-title">
        <h2 id="settings-lists-title">Listas de la compra</h2>
        <div class="add-row"><div class="select-wrap"><label for="todo-entity">Entidad todo</label><select id="todo-entity"></select></div><button id="add-list" class="primary">Añadir lista</button></div>
        <div id="configured-lists" class="lists"></div>
        <p id="settings-empty" hidden>No hay listas añadidas. Añade una entidad todo para empezar.</p>
        <div class="purchase-detection-settings"><h3>Detección automática de compra</h3><form id="purchase-detection-form"><div id="purchase-persons-label" class="purchase-users-field"><span id="purchase-users-label">Usuarios que realizan las compras</span><details id="purchase-zone-persons" class="person-picker"><summary aria-labelledby="purchase-users-label purchase-users-summary"><span id="purchase-users-summary">Seleccionar usuarios</span><ha-icon icon="mdi:chevron-down" aria-hidden="true"></ha-icon></summary><div class="person-options" role="group" aria-labelledby="purchase-users-label"></div></details></div><div class="detection-pair"><label class="detection-row" for="purchase-detection-enabled">Activar detección automática<input id="purchase-detection-enabled" class="store-toggle" type="checkbox" role="switch"></label><label class="detection-row" for="purchase-detection-threshold">Más de X productos completados en un día<input id="purchase-detection-threshold" type="number" min="1" max="1000" step="1" value="5" required></label></div><div class="detection-pair"><label class="detection-row" for="purchase-zone-assignment">Asignación de tienda basada en zona<input id="purchase-zone-assignment" class="store-toggle" type="checkbox" role="switch"></label><label class="detection-row" for="purchase-minimum-minutes">Permanencia mínima en la zona (minutos)<input id="purchase-minimum-minutes" type="number" min="1" max="1440" step="1" value="5" required></label></div><p id="purchase-zone-help" class="helper">Solo se tendrán en cuenta visitas que alcancen la permanencia mínima configurada.</p><div class="appearance-actions"><button class="primary" id="save-purchase-detection" type="submit">Guardar</button></div></form></div>
      </section>

      <section id="settings-notifications" hidden><isl-notification-settings></isl-notification-settings></section>
      <section id="settings-appearance" class="card" aria-labelledby="settings-appearance-title" hidden>
        <h2 id="settings-appearance-title">Personalización</h2>
        <p>Personaliza las tarjetas del apartado Lista. Pulsa una tarjeta para marcar o desmarcar su compra.</p>
        <form id="appearance-form">
          <div class="appearance-fields appearance-colors">
            <div><label for="gradient-start">Color inicial del degradado</label><input id="gradient-start" name="gradient_start" type="color" value="#ee524f"></div>
            <div><label for="gradient-end">Color final del degradado</label><input id="gradient-end" name="gradient_end" type="color" value="#b52a27"></div>
            <div><label for="completed-gradient-start">Color inicial de Comprados</label><input id="completed-gradient-start" name="completed_gradient_start" type="color" value="#4faba2"></div>
            <div><label for="completed-gradient-end">Color final de Comprados</label><input id="completed-gradient-end" name="completed_gradient_end" type="color" value="#26857c"></div>
          </div>
          <div class="appearance-previews">
            <div id="appearance-preview" class="preview">Vista previa de producto pendiente</div>
            <div id="completed-appearance-preview" class="preview">Vista previa de producto comprado</div>
          </div>
          <div style="margin-top:18px"><label for="quantity-color">Color del indicador de cantidad</label><input id="quantity-color" name="quantity_color" type="color" value="#267052"></div>
          <div class="appearance-fields appearance-colors" style="margin-top:24px">
            <div><label for="stock-gradient-start">Color inicial de Stock</label><input id="stock-gradient-start" name="stock_gradient_start" type="color" value="#f59a23"></div>
            <div><label for="stock-gradient-end">Color final de Stock</label><input id="stock-gradient-end" name="stock_gradient_end" type="color" value="#c65b0c"></div>
            <div><label for="recipe-gradient-start">Color inicial de Recetas</label><input id="recipe-gradient-start" name="recipe_gradient_start" type="color" value="#66bb6a"></div>
            <div><label for="recipe-gradient-end">Color final de Recetas</label><input id="recipe-gradient-end" name="recipe_gradient_end" type="color" value="#2e7d32"></div>
          </div>
          <div class="appearance-previews">
            <div id="stock-appearance-preview" class="preview">Vista previa de producto en stock</div>
            <div id="recipe-appearance-preview" class="preview">Vista previa de receta</div>
          </div>
          <div class="appearance-fields">
            <div><label for="desktop-columns">Productos por fila (ordenador)</label><select id="desktop-columns" name="columns">${[1,2,3,4,5,6].map(value => `<option value="${value}">${value}</option>`).join("")}</select></div>
            <div><label for="mobile-columns">Productos por fila (móvil)</label><select id="mobile-columns" name="mobile_columns">${[1,2,3,4].map(value => `<option value="${value}">${value}</option>`).join("")}</select></div>
          </div>
          <div class="appearance-actions"><button id="reset-appearance" type="button">Restablecer valores</button><button id="save-appearance" class="primary" type="submit">Guardar personalización</button></div>
        </form>
      </section>
      <section id="settings-stores" class="card" aria-labelledby="settings-stores-title" hidden>
        <div class="stores-heading"><h2 id="settings-stores-title">Tiendas</h2><div class="stores-heading-actions"><button id="refresh-all-prices" class="store-refresh" type="button" aria-label="Actualizar ahora" title="Actualizar ahora"><ha-icon icon="mdi:refresh" aria-hidden="true"></ha-icon></button><button id="configure-price-schedule" class="store-refresh" type="button" aria-label="Actualización de precios" title="Actualización de precios"><ha-icon icon="mdi:clock-outline" aria-hidden="true"></ha-icon></button></div></div>
        <div class="stores-grid">
        <article class="store-row" id="mercadona-row">
          <img class="store-logo" src="${MERCADONA_LOGO_URL}" alt="Logo de Mercadona" referrerpolicy="no-referrer" loading="lazy" width="56" height="56">
          <div class="store-name"><h3>Mercadona</h3></div>
          <div class="store-controls"><input id="mercadona-enabled" class="store-toggle" type="checkbox" role="switch" aria-label="Habilitar Mercadona"><button id="configure-mercadona" class="store-cog" type="button" aria-label="Ajustes de Mercadona" title="Ajustes de Mercadona"><ha-icon icon="mdi:cog" aria-hidden="true"></ha-icon></button></div>
        </article>
        <article class="store-row" id="carrefour-row"><img class="store-logo" src="https://images.seeklogo.com/logo-png/31/2/carrefour-logo-png_seeklogo-318190.png" alt="Logo de Carrefour" referrerpolicy="no-referrer" loading="lazy" width="56" height="56"><div class="store-name"><h3>Carrefour</h3></div><div class="store-controls"><input id="carrefour-enabled" class="store-toggle" type="checkbox" role="switch" aria-label="Habilitar Carrefour"><button id="configure-carrefour" class="store-cog" type="button" aria-label="Ajustes de Carrefour" title="Ajustes de Carrefour"><ha-icon icon="mdi:cog" aria-hidden="true"></ha-icon></button></div></article>
        <article class="store-row"><img class="store-logo" src="https://almeria.online/wp-content/uploads/2024/09/alcampo-logo.png" alt="Logo de Alcampo" referrerpolicy="no-referrer" loading="lazy" width="56" height="56"><div class="store-name"><h3>Alcampo</h3></div><div class="store-controls"><input id="alcampo-enabled" class="store-toggle" type="checkbox" role="switch" aria-label="Habilitar Alcampo"><button id="configure-alcampo" class="store-cog" type="button" aria-label="Ajustes de Alcampo" title="Ajustes de Alcampo"><ha-icon icon="mdi:cog" aria-hidden="true"></ha-icon></button></div></article>

        </div>
        <div class="stores-footer">Última actualización: <time id="stores-last-updated" title="Última actualización correcta de precios">—</time></div>
        <isl-catalog-sources></isl-catalog-sources>
      </section>
      <dialog id="prices-progress-dialog" aria-labelledby="prices-progress-title">
        <h2 id="prices-progress-title">Actualización de precios</h2>
        <div class="store-progress"><div class="store-progress-track"><progress id="prices-progress-bar" max="1" aria-label="Progreso de actualización de todas las tiendas"></progress><span id="prices-progress-percentage" class="store-progress-percentage" aria-hidden="true">…</span></div><p id="prices-progress-status" role="status">Preparando actualización…</p><p id="prices-progress-time"></p></div>
        <div id="stores-refresh-error" class="notice error" role="alert" hidden></div>
        <div class="appearance-actions"><button id="close-prices-progress" type="button">Cerrar</button></div>
      </dialog>
      <dialog id="price-schedule-dialog" aria-labelledby="price-schedule-title">
        <h2 id="price-schedule-title">Actualización de precios</h2>
        <form id="price-schedule-form">
          <div class="price-config-row"><label for="price-updates-enabled">Actualización automática de precios</label><input id="price-updates-enabled" class="store-toggle" type="checkbox" role="switch" checked></div>
          <div class="price-config-row"><label for="price-update-days">Frecuencia de actualización (días)</label><input id="price-update-days" type="number" min="1" max="3650" step="1" value="1" required></div>
          <div class="price-config-row"><label for="price-update-time">Hora de actualización</label><input id="price-update-time" type="time" required></div><div id="price-schedule-error" class="notice error" role="alert" hidden></div><div class="appearance-actions"><button id="save-price-update-time" class="primary" type="submit">Guardar</button></div></form>
      </dialog>
      <dialog id="carrefour-dialog" aria-labelledby="carrefour-dialog-title">
        <h2 id="carrefour-dialog-title">Carrefour</h2><isl-carrefour-account></isl-carrefour-account>

        <section id="carrefour-products-view"><div id="carrefour-error" class="notice error" role="alert" hidden></div><div id="carrefour-products" class="store-products"></div><p id="carrefour-status" class="store-cache-footer" role="status"></p></section>

      </dialog>
      <dialog id="alcampo-dialog" aria-labelledby="alcampo-title"><h2 id="alcampo-title">Alcampo</h2><isl-alcampo-settings></isl-alcampo-settings><section id="alcampo-products-view"><div id="alcampo-products-error" class="notice error" role="alert" hidden></div><div id="alcampo-products" class="store-products"></div><p id="alcampo-status" class="store-cache-footer" role="status"></p></section></dialog>
      <dialog id="store-dialog" aria-labelledby="store-dialog-title">
        <h2 id="store-dialog-title">Mercadona</h2>

        <div id="store-dialog-error" class="notice error" role="alert" hidden></div>
        <section id="store-products-view">
          <div id="store-products-error" class="notice error" role="alert" hidden></div>
          <div id="store-products" class="store-products"></div>
          <p id="store-products-status" class="store-cache-footer" role="status"></p>
        </section>

      </dialog>
      <section id="settings-logs" class="card" aria-label="Logs" hidden><isl-logs></isl-logs></section>
      <section id="settings-readers" class="card" aria-label="Lectores" hidden><isl-readers></isl-readers></section>
      <section id="settings-community" class="card" aria-labelledby="settings-community-title" hidden>
        <h2 id="settings-community-title">Comunidad</h2>
        <div class="community-export">
          <p id="catalog-export-description">Descarga un archivo JSON con todos los productos de tu catálogo: nombres, traducciones, categorías, iconos o enlaces públicos de imágenes, EAN y opciones de compra con tiendas, URL, marcas, formatos y precios guardados. Puedes compartirlo con Aguacatec para completar el diccionario de productos.</p>
          <button id="export-catalog" class="primary community-action" type="button" aria-describedby="catalog-export-description"><svg viewBox="0 0 512 512" aria-hidden="true"><path d="M256 0c17.7 0 32 14.3 32 32v242.7l73.4-73.4c12.5-12.5 32.8-12.5 45.3 0s12.5 32.8 0 45.3l-128 128c-12.5 12.5-32.8 12.5-45.3 0l-128-128c-12.5-12.5-12.5-32.8 0-45.3s32.8-12.5 45.3 0l73.3 73.4V32c0-17.7 14.3-32 32-32zM64 352v96h384v-96h64v112c0 26.5-21.5 48-48 48H48c-26.5 0-48-21.5-48-48V352h64z"/></svg>Exportar mi catálogo</button>
        </div>
        <p id="catalog-export-error" class="notice error" role="alert" hidden></p>
        <div class="community-export"><p>Este proyecto ha sido desarrollado por la <a href="https://t.me/aguacatec_es/3" target="_blank" rel="noopener noreferrer">comunidad de Aguacatec</a>. Si tienes cualquier duda o sugerencia para mejorar la integración puedes unirte a través de Telegram.</p><a class="community-action community-join" href="https://t.me/aguacatec_es/3" target="_blank" rel="noopener noreferrer"><svg viewBox="0 0 496 512" aria-hidden="true" focusable="false"><!--! Font Awesome Free 6.7.2 by @fontawesome - https://fontawesome.com License - https://fontawesome.com/license/free (Icons: CC BY 4.0, Fonts: SIL OFL 1.1, Code: MIT License) Copyright 2024 Fonticons, Inc. --><path d="M248,8C111.033,8,0,119.033,0,256S111.033,504,248,504,496,392.967,496,256,384.967,8,248,8ZM362.952,176.66c-3.732,39.215-19.881,134.378-28.1,178.3-3.476,18.584-10.322,24.816-16.948,25.425-14.4,1.326-25.338-9.517-39.287-18.661-21.827-14.308-34.158-23.215-55.346-37.177-24.485-16.135-8.612-25,5.342-39.5,3.652-3.793,67.107-61.51,68.335-66.746.153-.655.3-3.1-1.154-4.384s-3.59-.849-5.135-.5q-3.283.746-104.608,69.142-14.845,10.194-26.894,9.934c-8.855-.191-25.888-5.006-38.551-9.123-15.531-5.048-27.875-7.717-26.8-16.291q.84-6.7,18.45-13.7,108.446-47.248,144.628-62.3c68.872-28.647,83.183-33.623,92.511-33.789,2.052-.034,6.639.474,9.61,2.885a10.452,10.452,0,0,1,3.53,6.716A43.765,43.765,0,0,1,362.952,176.66Z"/></svg>Unirme a la comunidad</a></div>
        <div class="community-export"><p>Si quieres apoyar a <a href="https://aguacatec.es/" target="_blank" rel="noopener noreferrer">Aguacatec</a> para que podamos seguir desarrollando proyectos como estos, conseguir contenido exclusivo, participar en sorteos y otras ventajas, puedes hacerte <a href="https://www.patreon.com/c/aguacatec/membership" target="_blank" rel="noopener noreferrer">Patreon</a>.</p><a class="community-action community-patreon" href="https://www.patreon.com/c/aguacatec/membership" target="_blank" rel="noopener noreferrer"><svg viewBox="0 0 512 512" aria-hidden="true" focusable="false"><!--! Font Awesome Free 6.7.2 by @fontawesome - https://fontawesome.com License - https://fontawesome.com/license/free (Icons: CC BY 4.0, Fonts: SIL OFL 1.1, Code: MIT License) Copyright 2024 Fonticons, Inc. --><path d="M489.7 153.8c-.1-65.4-51-119-110.7-138.3C304.8-8.5 207-5 136.1 28.4C50.3 68.9 23.3 157.7 22.3 246.2C21.5 319 28.7 510.6 136.9 512c80.3 1 92.3-102.5 129.5-152.3c26.4-35.5 60.5-45.5 102.4-55.9c72-17.8 121.1-74.7 121-150z"/></svg>Hacerme Patreon</a></div>
      </section>`;
    this._built = true;
    this.shadowRoot.querySelector("#add-list").addEventListener("click", () => {
      const entity = this.shadowRoot.querySelector("#todo-entity").value;
      if (entity) void this._act("add", entity);
    });
    const root = this.shadowRoot;
    const gateways = document.createElement('section');
    gateways.id='settings-gateways';gateways.className='card';gateways.setAttribute('aria-labelledby','gateway-title');
    gateways.innerHTML=`<h2 id="gateway-title">Listas pasarela</h2>
      <p>Envían las nuevas incorporaciones a la lista de la compra vinculada, sin duplicar productos pendientes. Los productos que ya contiene la pasarela al configurarla no se transfieren.</p>
      <form id="gateway-form" class="gateway-add">
        <div><label for="gateway-entity">Entidad todo de la pasarela</label><select id="gateway-entity" required></select></div>
        <div><label for="gateway-target">Lista de destino</label><select id="gateway-target" required></select></div>
        <button id="add-gateway" class="primary" type="submit">Añadir pasarela</button>
        <label class="gateway-cleanup"><input id="gateway-remove" type="checkbox">Eliminar de la pasarela tras transferir</label>
      </form><div id="configured-gateways" class="lists"></div>`;
    root.querySelector('#settings-lists').after(gateways);
    root.querySelector('#gateway-form').addEventListener('submit',event=>{
      event.preventDefault();
      void this._saveRetailSettings(()=>this._data.settings.saveGateway(root.querySelector('#gateway-entity').value,
        root.querySelector('#gateway-target').value,root.querySelector('#gateway-remove').checked));
    });
    const readersTab=document.createElement('button');
    readersTab.id='settings-view-readers';readersTab.type='button';readersTab.setAttribute('aria-label','Lectores');readersTab.setAttribute('aria-pressed','false');
    readersTab.innerHTML='<ha-icon icon="mdi:barcode-scan" aria-hidden="true"></ha-icon><span class="tab-label">Lectores</span>';
    root.querySelector('#settings-view-community').before(readersTab);
    const lidlRow=document.createElement('article');lidlRow.className='store-row';lidlRow.id='lidl-row';lidlRow.innerHTML='<img class="store-logo" src="https://upload.wikimedia.org/wikipedia/commons/9/91/Lidl-Logo.svg" alt="Logo de Lidl" referrerpolicy="no-referrer" loading="lazy" width="56" height="56"><div class="store-name"><h3>Lidl</h3></div><div class="store-controls"><input id="lidl-enabled" class="store-toggle" type="checkbox" role="switch" aria-label="Habilitar Lidl"><button id="configure-lidl" class="store-cog" type="button" aria-label="Ajustes de Lidl" title="Ajustes de Lidl"><ha-icon icon="mdi:cog" aria-hidden="true"></ha-icon></button></div>';root.querySelector('.stores-grid').append(lidlRow);
    const lidlDialog=document.createElement('dialog');lidlDialog.id='lidl-dialog';lidlDialog.setAttribute('aria-label','Lidl');lidlDialog.append(document.createElement('isl-lidl-account'));root.append(lidlDialog);
    root.querySelector('#lidl-enabled').addEventListener('change',()=>void this._saveRetailSettings(()=>this._data.settings.setStoreEnabled('lidl',root.querySelector('#lidl-enabled').checked)));
    root.querySelector('#configure-lidl').addEventListener('click',()=>{lidlDialog.showModal();const account=lidlDialog.querySelector('isl-lidl-account');account.hass=this._data.hass;void account.activate();});
    lidlDialog.addEventListener('close',()=>lidlDialog.querySelector('isl-lidl-account').deactivate());
    this._buildRegionalStores(root);
    this._buildZoneSettings(root);
    installDialogCloseButtons(root);
    installToggleStyles(root);
    root.querySelector("#refresh-all-prices").addEventListener("click",()=>void this._refreshPricesNow());
    const storesGrid=root.querySelector(".stores-grid");
    storesGrid.append(...[...storesGrid.querySelectorAll(".store-row")].sort((a,b)=>
      a.querySelector("h3").textContent.localeCompare(b.querySelector("h3").textContent,"es")));
    for (const store of ["mercadona", "carrefour", "lidl", "alcampo", "consum", "lasirena", "eroski", "dia"]) {
      const row = root.querySelector(`#${store}-enabled`).closest(".store-row");
      const heart = document.createElement("button"); heart.id = `favorite-${store}`; heart.type = "button"; heart.className = "store-cog store-favorite";
      const label = `Marcar ${row.querySelector("h3").textContent} como favorita`;
      heart.setAttribute("aria-label",label); heart.title = label; heart.setAttribute("aria-pressed","false");
      heart.innerHTML = '<ha-icon icon="mdi:heart-outline" aria-hidden="true"></ha-icon>';
      heart.addEventListener("click",()=>void this._saveRetailSettings(()=>this._data.settings.saveFavoriteStore(store)));
      row.querySelector(".store-controls").append(heart);
    }
    root.querySelector("#configure-price-schedule").addEventListener("click",()=>{
      root.querySelector("#price-update-time").value=this._data.settings.priceUpdateTime ?? "00:00";
      root.querySelector("#price-update-days").value=this._data.settings.priceUpdateDays ?? 1;
      root.querySelector("#price-updates-enabled").checked=this._data.settings.priceUpdatesEnabled !== false;
      this._error=""; this._render(); root.querySelector("#price-schedule-dialog").showModal();
    });
    root.querySelector("#price-schedule-form").addEventListener("submit",event=>{event.preventDefault();void this._savePriceSchedule();});
    root.querySelector('#purchase-detection-form').addEventListener('input',()=>{this._purchaseDetectionDirty=true;this._render();});
    root.querySelector('#purchase-zone-persons').addEventListener('change',()=>{this._purchaseDetectionDirty=true;this._render();});
    root.querySelector('#purchase-detection-form').addEventListener('submit',event=>{event.preventDefault();const config={...this._data.settings.purchaseDetection,enabled:root.querySelector('#purchase-detection-enabled').checked,threshold:Number(root.querySelector('#purchase-detection-threshold').value),minimum_minutes:Number(root.querySelector('#purchase-minimum-minutes').value),zone_assignment:root.querySelector('#purchase-zone-assignment').checked,persons:this._selectedPurchasePersons()};void this._saveRetailSettings(async()=>{await this._data.settings.savePurchaseDetection(config);this._purchaseDetectionDirty=false;});});
    root.querySelector("#close-prices-progress").addEventListener("click",()=>root.querySelector("#prices-progress-dialog").close());
    root.querySelector("#prices-progress-dialog").addEventListener("close",()=>clearInterval(this._pricesProgressTimer));
    root.querySelector("#alcampo-enabled").addEventListener("change",()=>void this._saveRetailSettings(()=>this._data.settings.setStoreEnabled("alcampo",root.querySelector("#alcampo-enabled").checked)));
    root.querySelector("#configure-alcampo").addEventListener("click",()=>{root.querySelector("#alcampo-dialog").showModal();const options=root.querySelector("isl-alcampo-settings");options.hass=this._data.hass;options.products=this._data.products??[];void options.activate();});
    root.querySelector("#alcampo-dialog").addEventListener("close",()=>root.querySelector("isl-alcampo-settings")?.deactivate());
    root.querySelector("#alcampo-dialog").addEventListener("cancel",event=>{if(this._busy)event.preventDefault();});
    const alcampoError=document.createElement("div");alcampoError.id="alcampo-error";alcampoError.className="notice error";alcampoError.setAttribute("role","alert");alcampoError.hidden=true;root.querySelector("#alcampo-title").after(alcampoError);
    for (const [id, view] of [["settings-view-lists", "lists"], ["settings-view-appearance", "appearance"], ["settings-view-community", "community"], ["settings-view-stores", "stores"], ["settings-view-logs", "logs"], ["settings-view-readers","readers"], ["settings-view-notifications","notifications"]]) {
      root.querySelector(`#${id}`).addEventListener("click", () => {
        this._view = view;
        if(view === "nutrition")this._nutritionKey=null;
        for (const section of ["lists", "appearance", "community", "stores", "logs", "readers", "notifications"]) {
          root.querySelector(`#settings-${section}`).hidden = view !== section;
          root.querySelector(`#settings-view-${section}`).setAttribute("aria-pressed", String(view === section));
        }
        this._notice = "";
        this._error = "";
        this._render();
        const tabs=root.querySelector(".settings-tabs"),bounds=tabs.getBoundingClientRect(),rect=root.querySelector(`#${id}`).getBoundingClientRect();
        tabs.scrollLeft += rect.left < bounds.left ? rect.left-bounds.left : Math.max(0,rect.right-bounds.right);
      });
    }
    root.querySelector("#carrefour-enabled").addEventListener("change", () => void this._saveRetailSettings(() => this._data.settings.setStoreEnabled("carrefour",root.querySelector("#carrefour-enabled").checked)));
    root.querySelector("#configure-carrefour").addEventListener("click", () => { root.querySelector("#carrefour-dialog").showModal(); const account=root.querySelector("isl-carrefour-account");account.hass=this._data.hass;void account.activate(); });
    root.querySelector("#carrefour-dialog").addEventListener("cancel",event=>{if(this._busy)event.preventDefault();});
    root.querySelector("#carrefour-dialog").addEventListener("close", () => { if (!root.querySelector("#carrefour-dialog").open) { this._carrefourGeneration = (this._carrefourGeneration || 0) + 1; this._carrefourLoading = false; root.querySelector("isl-carrefour-account")?.deactivate(); } });
    root.querySelector("#mercadona-enabled").addEventListener("change",()=>void this._saveRetailSettings(()=>this._data.settings.setStoreEnabled("mercadona",root.querySelector("#mercadona-enabled").checked)));
    root.querySelector("#configure-mercadona").addEventListener("click", () => this._openStore());
    root.querySelector("#store-dialog").addEventListener("cancel", event => { if (this._busy) event.preventDefault(); });
    root.querySelector("#store-dialog").addEventListener("close", () => {
      if (root.querySelector("#store-dialog").open) return;
      this._storeEnableDraft = undefined; this._storeDirty = false;
      this._productsGeneration = (this._productsGeneration || 0) + 1; this._productsLoading = false;
      this._error = ""; this._render();
    });
    root.querySelector("#export-catalog").addEventListener("click", () => void this._exportCatalog());
    root.querySelector("isl-notification-settings").onSave = config => this.onNotifications(config);
    root.querySelector("#appearance-form").addEventListener("input", () => { this._appearanceDirty = true; this._preview(); });
    root.querySelector("#appearance-form").addEventListener("change", () => { this._appearanceDirty = true; this._preview(); });
    root.querySelector("#appearance-form").addEventListener("submit", event => { event.preventDefault(); void this._saveAppearance(); });
    root.querySelector("#reset-appearance").addEventListener("click", () => {
      this._fillAppearance(DEFAULT_APPEARANCE);
      this._appearanceDirty = true;
    });
  }


  _render() {
    if (!this._built || !this._data) return;
    this.shadowRoot.querySelector("isl-notification-settings").data = this._data;
    this._syncLogs();
    this._syncReaders();
    this._syncCatalogSources();

    const { hass, settings } = this._data;
    const root = this.shadowRoot;
    const admin = hass?.user?.is_admin === true;
    const locked = !admin || !settings.loaded || settings.loading || this._busy;
    const detection=settings.purchaseDetection??{enabled:false,threshold:5};
    const universal=Array.isArray(detection.shops);
    if(universal&&!root.querySelector('isl-shopping-places')){
      const places=document.createElement('isl-shopping-places');root.querySelector('#settings-stores').append(places);
      const users=document.createElement('section');users.className='purchase-users';users.style.marginTop='28px';
      const heading=document.createElement('h3');heading.textContent='Usuarios';users.append(heading,root.querySelector('#purchase-persons-label'),root.querySelector('.purchase-detection-settings'));root.querySelector('#settings-stores').append(users);
    }
    if(universal){root.querySelector('#settings-stores-title').textContent='Cuentas';root.querySelector('isl-shopping-places').data=this._data;}

    if(!this._purchaseDetectionDirty){root.querySelector('#purchase-detection-enabled').checked=detection.enabled;root.querySelector('#purchase-detection-threshold').value=String(detection.threshold);root.querySelector('#purchase-zone-assignment').checked=Boolean(detection.zone_assignment);root.querySelector('#purchase-minimum-minutes').value=String(detection.minimum_minutes??5);}
    this._renderPurchasePersons(locked,detection);
    const zonesEnabled=root.querySelector('#purchase-zone-assignment').checked;
    root.querySelector('#purchase-zone-help').hidden=!zonesEnabled;
    root.querySelector('#purchase-zone-assignment').disabled=locked||!root.querySelector('#purchase-detection-enabled').checked;
    this._renderZoneSettings(locked);
    for(const id of ['purchase-detection-enabled','save-purchase-detection'])root.querySelector('#'+id).disabled=locked;
    root.querySelector('#purchase-detection-threshold').disabled=locked||!root.querySelector('#purchase-detection-enabled').checked;
    const refresh = root.querySelector("#refresh-all-prices");
    refresh.disabled = locked || !Object.values(settings.stores ?? {}).some(store=>store.enabled);
    refresh.setAttribute("aria-busy",String(Boolean(this._pricesRefreshing)));
    root.querySelector("#configure-price-schedule").disabled = !settings.loaded || settings.loading || this._busy;
    this._watchPriceStatus();
    const alcampoOptions=root.querySelector("isl-alcampo-settings");if(alcampoOptions)alcampoOptions.products=this._data.products??[];
    this._renderCommunity();
    this._renderPriceTimestamp();
    this._renderGlobalPriceProgress();
    for (const store of ["mercadona", "carrefour", "lidl", "alcampo", "consum", "lasirena", "eroski", "dia"]) {
      if(store==="lidl"){root.querySelector("#lidl-enabled").checked=Boolean(settings.stores?.lidl?.enabled);root.querySelector("#lidl-enabled").disabled=locked;}
      root.querySelector(`#${store}-enabled`).closest(".store-row").dataset.enabled = String(Boolean(settings.stores?.[store]?.enabled));
      const available=universal?["carrefour","lidl"].includes(store):(settings.availableStores??["mercadona","carrefour","consum","lasirena","eroski"]).includes(store);
      root.querySelector(`#${store}-enabled`).closest(".store-row").hidden=!available;
      if(!available){
        const dialog=root.querySelector(store==='mercadona'?'#store-dialog':`#${store}-dialog`);
        if(dialog?.open)dialog.close();
      }
      const storeName=root.querySelector(`#${store}-enabled`).closest('.store-row').querySelector('.store-name');
      let count=storeName.querySelector('.store-linked-count');if(!count){count=document.createElement('span');count.className='store-linked-count';storeName.append(count);}
      const linked=(this._data.products??[]).filter(product=>{const link=product.store_links?.[store];return Boolean(typeof link==='string'?link.trim():link?.id||link?.url)||(this._data.receiptStores?.[product.id]??[]).includes(store);}).length;
      count.textContent=linked+(linked===1?' producto':' productos');
      const favorite = root.querySelector(`#favorite-${store}`);
      favorite.disabled = locked || !settings.stores?.[store]?.enabled;
      const selected = Boolean(settings.stores?.[store]?.enabled && settings.favoriteStore === store);
      favorite.setAttribute("aria-pressed",String(selected));
      favorite.querySelector("ha-icon").setAttribute("icon",selected ? "mdi:heart" : "mdi:heart-outline");
    }
    const error = root.querySelector("#settings-error");
    error.textContent = this._error || settings.error;
    error.hidden = !error.textContent || root.querySelector("#store-dialog").open;
    const status = root.querySelector("#settings-status");
    status.textContent = settings.loading ? "Cargando ajustes…" : this._notice ?? "";
    status.hidden = !status.textContent || (!settings.loading && !root.querySelector("#settings-stores").hidden);
    root.querySelector("#admin-help").hidden = admin;
    const select = root.querySelector("#todo-entity");
    const previous = select.value;
    const candidates = todoEntities(hass).filter(state => !settings.entities.includes(state.entity_id) && !(settings.gatewayLists??[]).some(item=>item.entity_id===state.entity_id));
    select.replaceChildren(...(candidates.length ? candidates.map(state => new Option(
      `${state.attributes.friendly_name ?? state.entity_id} · ${state.entity_id}${isAvailable(state) ? "" : " · No disponible"}`, state.entity_id,
    )) : [new Option("No hay más entidades todo disponibles", "")]));
    if (candidates.some(state => state.entity_id === previous)) select.value = previous;
    select.disabled = locked || !candidates.length;
    root.querySelector("#add-list").disabled = locked || !candidates.length;
    const rows = settings.entities.map(entity => {
      const state = hass?.states[entity];
      const name = state?.attributes.friendly_name ?? entity;
      const row = document.createElement("article");
      row.dataset.entityId = entity;
      const info = document.createElement("div");
      info.className = "list-info";
      const title = document.createElement("h3");
      title.textContent = name;
      const id = document.createElement("p");
      id.className = "entity";
      id.textContent = entity + (isAvailable(state) ? "" : " · No disponible");
      info.append(title, id);
      info.append(this._nameModeOption(entity,locked));
      const actions = document.createElement("div");
      actions.className = "actions";
      for (const [label, action] of [["Quitar", "remove"], ["Hacer principal", "primary"]]) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = `list-action list-${action}`;
        const selected = action === "primary" && entity === settings.primary;
        const icon = document.createElement("ha-icon");
        icon.setAttribute("icon",action === "remove" ? "mdi:delete" : selected ? "mdi:star" : "mdi:star-outline");
        icon.setAttribute("aria-hidden","true");
        button.append(icon);
        button.setAttribute("aria-label", `${label}: ${name}`);
        button.title = action === "primary" && selected ? "Lista principal" : label;
        if (action === "primary") button.setAttribute("aria-pressed",String(selected));
        button.disabled = locked;
        button.addEventListener("click", () => { if (!selected) void this._act(action, entity); });
        actions.append(button);
      }
      row.append(info, actions);
      return row;
    });
    root.querySelector("#configured-lists").replaceChildren(...rows);
    this._renderGateways(locked);
    const carrefour = settings.stores?.carrefour?.enabled === true;
    root.querySelector("#carrefour-enabled").checked = carrefour;
    root.querySelector("#carrefour-enabled").disabled = locked;
    root.querySelector("#alcampo-enabled").checked = settings.stores?.alcampo?.enabled === true;
    root.querySelector("#alcampo-enabled").disabled = locked;
    root.querySelector("#alcampo-error").textContent = this._error || "";
    root.querySelector("#alcampo-error").hidden = !this._error;
    root.querySelector("#save-price-update-time").disabled = locked;
    root.querySelector("#price-update-time").disabled = locked;
    root.querySelector("#price-update-days").disabled = locked;
    root.querySelector("#price-updates-enabled").disabled = locked;
    root.querySelector("#refresh-all-prices").disabled = locked || settings.priceUpdatesEnabled === false;
    root.querySelector("#price-schedule-error").textContent = this._error || "";
    root.querySelector("#price-schedule-error").hidden = !this._error;
    if(!root.querySelector("#price-schedule-dialog").open){
      root.querySelector("#price-update-time").value = settings.priceUpdateTime ?? "00:00";
      root.querySelector("#price-update-days").value = settings.priceUpdateDays ?? 1;
      root.querySelector("#price-updates-enabled").checked = settings.priceUpdatesEnabled !== false;
    }
    root.querySelector("#settings-empty").hidden = settings.entities.length > 0 || settings.loading;
    this._renderRegionalStores(locked);
    this._renderStore();
    const form = root.querySelector("#appearance-form");
    if (!this._appearanceDirty && !this._busy) this._fillAppearance(settings.appearance);
    // Home Assistant's scoped registry does not implement form.elements iteration.
    for (const control of form.querySelectorAll("input, select, textarea, button")) control.disabled = locked;
  }

  _renderStore() {
    const {settings,hass}=this._data, root=this.shadowRoot;
    const locked=hass?.user?.is_admin !== true || !settings.loaded || settings.loading || this._busy;
    root.querySelector("#mercadona-enabled").checked=Boolean(settings.stores?.mercadona?.enabled);
    root.querySelector("#mercadona-enabled").disabled=locked;
    root.querySelector("#configure-mercadona").disabled=!settings.loaded || settings.loading || this._busy;
    root.querySelector("#store-dialog-error").textContent=this._error || "";
    root.querySelector("#store-dialog-error").hidden=!this._error;

  }

  _watchPriceStatus() {
    const connection = this._data?.hass?.connection;
    if (!this.isConnected || !connection || this._priceStatusConnection === connection) return;
    this._stopPriceStatus?.(); this._stopPriceStatus = null;
    this._priceStatusConnection = connection;
    this._lastPriceUpdated = 0;
    this._latestPriceProgress = null;
    const token = this._priceStatusToken = {};
    void connection.subscribeMessage(progress=>{
      if (this._priceStatusToken !== token || !this.isConnected) return;
      if (progress.last_updated !== undefined) this._lastPriceUpdated = progress.last_updated;
      this._latestPriceProgress = progress;
      this._priceProgressReceivedAt = Date.now();
      this._renderPriceTimestamp();
      this._renderGlobalPriceProgress();
    },{type:"improved_shopping_list/settings/store_progress"}).then(stop=>{
      if (this._priceStatusToken !== token || !this.isConnected) stop();
      else this._stopPriceStatus = stop;
    }).catch(()=>{ if (this._priceStatusToken === token) this._priceStatusConnection = null; });
  }

  _renderPriceTimestamp() {
    const node = this.shadowRoot.querySelector("#stores-last-updated");
    const timestamp = Number(this._lastPriceUpdated);
    const date = new Date(timestamp*1000);
    if (!Number.isFinite(timestamp) || timestamp <= 0 || !Number.isFinite(date.getTime())) {
      node.textContent = "—"; node.removeAttribute("datetime"); node.setAttribute("aria-label","Todavía no hay precios actualizados"); return;
    }
    const parts = Object.fromEntries(new Intl.DateTimeFormat("es-ES",{day:"2-digit",month:"2-digit",hour:"2-digit",minute:"2-digit",hourCycle:"h23",timeZone:this._data?.hass?.config?.time_zone}).formatToParts(date).map(part=>[part.type,part.value]));
    node.textContent = `${parts.day}/${parts.month} ${parts.hour}:${parts.minute}`;
    node.dateTime = date.toISOString();
    node.setAttribute("aria-label",`Última actualización correcta de precios: ${node.textContent}`);
  }

  _renderGlobalPriceProgress() {
    const root=this.shadowRoot;
    if(!root.querySelector("#prices-progress-dialog")?.open)return;
    const state=this._latestPriceProgress;
    const bar=root.querySelector("#prices-progress-bar");
    const total=Math.max(0,Number(state?.total)||0), processed=Math.min(total,Math.max(0,Number(state?.processed)||0));
    const preparing=this._pricesRefreshing || state?.phase === "preparing" || this._manualQueued > 0 && !total && !state?.finished_at;
    const hasRun=Boolean(state?.batch_id) || total > 0 || this._manualQueued > 0;
    const empty=!preparing && !state?.running && !hasRun;
    const finished=!preparing && !state?.running && hasRun;
    bar.max=total||1;
    if(preparing)bar.removeAttribute("value");else bar.value=empty?0:processed;
    root.querySelector("#prices-progress-percentage").textContent=preparing?"…":`${finished?100:total&&!empty?Math.round(processed/total*100):0} %`;
    if(finished)bar.value=total||1;
    const names={mercadona:"Mercadona",carrefour:"Carrefour",alcampo:"Alcampo",consum:"Consum",lasirena:"La Sirena",eroski:"Eroski",dia:"DIA"};
    const errors=[...(this._refreshStartErrors??[]),...Object.entries(state?.errors??{}).filter(([store])=>this._data.settings.stores?.[store]?.enabled).map(([store,error])=>storeError(names[store]??store,error))];
    const errorBox=root.querySelector("#stores-refresh-error");errorBox.textContent=[...new Set(errors)].join("\n");errorBox.hidden=!errors.length;
    root.querySelector("#prices-progress-status").textContent=preparing?"Preparando actualización…":empty?(errors.length?"No se ha podido iniciar la revisión.":"No hay productos vinculados pendientes en tus listas."):`${processed} de ${total} referencias procesadas${state?.running?" · La revisión continúa en Home Assistant aunque cierres esta ventana.":" · Revisión finalizada"}`;
    const seconds=Number.isFinite(state?.estimated_seconds)?Math.max(0,Math.ceil(state.estimated_seconds-(Date.now()-(this._priceProgressReceivedAt??Date.now()))/1000)):null;
    root.querySelector("#prices-progress-time").textContent=preparing?"Calculando tiempo restante…":finished?(state?.log_pending?"Resumen pendiente de guardar en Ajustes → Logs → Tiendas.":state?.batch_id?"Resumen disponible en Ajustes → Logs → Tiendas.":""):!state?.running?"":seconds===null?"Calculando tiempo restante…":seconds>0?`Tiempo estimado restante: ${Math.floor(seconds/60)} min ${seconds%60} s`:"Actualización en curso…";
  }

  async _savePriceSchedule() {
    if(this._busy || this._data.hass?.user?.is_admin!==true)return;
    const connection=this._data.hass.connection, value=this.shadowRoot.querySelector("#price-update-time").value;
    const root=this.shadowRoot;
    if(!root.querySelector('#price-schedule-form').reportValidity())return;
    await this._saveRetailSettings(()=>this._data.settings.savePriceSchedule(value,root.querySelector('#price-updates-enabled').checked,Number(root.querySelector('#price-update-days').value)));
    if(this.isConnected && this._data.hass.connection===connection && !this._error)this.shadowRoot.querySelector("#price-schedule-dialog").close();
  }

  async _refreshPricesNow() {
    if (this._data.hass?.user?.is_admin !== true) return;
    const hass = this._data.hass;
    const stores = ["mercadona","carrefour","alcampo","consum","lasirena","eroski","dia"].filter(store=>this._data.settings.stores?.[store]?.enabled);
    if (!stores.length) return;
    const errorBox = this.shadowRoot.querySelector("#stores-refresh-error");
    errorBox.textContent = ""; errorBox.hidden = true;
    this._refreshStartErrors=[]; this._manualQueued=null;
    const dialog=this.shadowRoot.querySelector("#prices-progress-dialog");
    if(!dialog.open)dialog.showModal();
    clearInterval(this._pricesProgressTimer);
    this._pricesProgressTimer=setInterval(()=>this._renderGlobalPriceProgress(),1000);
    if(this._pricesRefreshing || this._latestPriceProgress?.running){this._renderGlobalPriceProgress();return;}
    this._pricesRefreshing = true; this._render();
    try {
      const result = await hass.callWS({type:"improved_shopping_list/settings/refresh_all_prices"});
      if (!this.isConnected || this._data.hass.connection !== hass.connection) return;
      if(result.progress){this._latestPriceProgress=result.progress;this._priceProgressReceivedAt=Date.now();}
      const names = {mercadona:"Mercadona",carrefour:"Carrefour",alcampo:"Alcampo",consum:"Consum",lasirena:"La Sirena",eroski:"Eroski",dia:"DIA"};
      const errors = (result.errors??[]).map(item=>storeError(names[item.store]??item.store,item.error));
      this._refreshStartErrors=errors;
      this._manualQueued=Math.max(0,Number(result.queued)||0);
    } catch(error) {
      if(this.isConnected && this._data.hass.connection===hass.connection){this._refreshStartErrors=[error.message??"No se pudo iniciar la actualización."];this._manualQueued=0;}
    } finally {
      this._pricesRefreshing = false; this._render();
    }
  }

  async _saveRetailSettings(save) {
    if (this._busy || this._data.hass?.user?.is_admin !== true) return;
    this._busy = true; this._error = this._notice = "";
    try { const pending = save(); this._render(); await pending; } catch (error) { this._error = error.message ?? "No se pudieron guardar las tiendas."; }
    finally { this._busy = false; this._render(); }
  }

  async _loadCarrefour() {
    if (this._carrefourLoading) return;
    const root = this.shadowRoot;
    const generation = this._carrefourGeneration = (this._carrefourGeneration || 0) + 1;
    const current = () => this.isConnected && generation === this._carrefourGeneration && root.querySelector("#carrefour-dialog").open;
    this._carrefourLoading = true;
    root.querySelector("#carrefour-status").textContent = "Comprobando catálogo…";
    root.querySelector("#carrefour-error").hidden = true;
    try {
      const data = await this._data.hass.callWS({type:"improved_shopping_list/catalog/store_prices",store:"carrefour"});
      if (!current()) return;
      const error = root.querySelector("#carrefour-error"); error.textContent = data.error ?? ""; error.hidden = !error.textContent;
      root.querySelector("#carrefour-status").textContent = `${data.products.length} precios guardados`;
      root.querySelector("#carrefour-products").replaceChildren(...data.products.map(product => {
        const row = document.createElement("div"); row.className = "store-product";
        const info = document.createElement("div"); const name = document.createElement("strong"); name.textContent = product.name;
        const ean = document.createElement("p"); ean.textContent = `${product.reference_id ? `ID: ${product.reference_id} · ` : ""}EAN: ${product.ean || "No disponible"}${product.checked_at ? ` · Último precio: ${new Date(product.checked_at*1000).toLocaleString("es-ES")}` : ""}`;
        const link = document.createElement("a"); link.textContent = "Ver en Carrefour"; link.href = product.url || product.affiliate_url; link.target = "_blank"; link.rel = "noopener noreferrer";
        const price = document.createElement("strong"); price.textContent = new Intl.NumberFormat("es-ES",{style:"currency",currency:product.currency}).format(Number(product.price));
        info.append(name,ean,link); row.append(info,price); return row;
      }));
    } catch (error) { if (current()) {
      const alert=root.querySelector("#carrefour-error");alert.textContent=error.message??"No se pudieron leer los precios guardados.";alert.hidden=false;
      root.querySelector("#carrefour-status").textContent=`${root.querySelector("#carrefour-products").childElementCount} precios guardados`;
    } } finally { if (current()) this._carrefourLoading=false; }
  }

  _nameModeOption(entity, locked) {
    const label=document.createElement('label');label.className='list-name-mode';
    const input=document.createElement('input');input.type='checkbox';input.checked=this._data.settings.descriptionAsName?.[entity]===true;input.disabled=locked;
    const text=document.createElement('span');text.textContent='Usar la descripción como parte del nombre';
    input.addEventListener('change',()=>void this._saveRetailSettings(()=>this._data.settings.setDescriptionAsName(entity,input.checked)));
    label.append(input,text);return label;
  }

  _selectedPurchasePersons() {
    return Array.from(this.shadowRoot.querySelectorAll('#purchase-zone-persons input:checked'),input=>input.value);
  }

  _renderPurchasePersons(locked, detection) {
    const root=this.shadowRoot, picker=root.querySelector('#purchase-zone-persons');
    const selected=this._purchaseDetectionDirty?this._selectedPurchasePersons():detection.persons??[];
    const states=this._data.hass?.states??{};
    const ids=[...new Set([...Object.keys(states).filter(id=>id.startsWith('person.')),...selected])];
    const name=id=>states[id]?.attributes?.friendly_name??id;
    ids.sort((a,b)=>name(a).localeCompare(name(b),'es'));
    const key=JSON.stringify(ids.map(id=>[id,name(id)]));
    if(picker.dataset.options!==key){
      const choices=ids.map(id=>{
        const label=document.createElement('label');label.className='person-option';
        const input=document.createElement('input');input.type='checkbox';input.value=id;input.name='purchase-person';input.setAttribute('form','purchase-detection-form');
        const text=document.createElement('span');text.textContent=name(id);label.append(input,text);return label;
      });
      if(!choices.length){const empty=document.createElement('p');empty.className='helper';empty.textContent='No hay entidades person disponibles en Home Assistant.';choices.push(empty);}
      picker.querySelector('.person-options').replaceChildren(...choices);picker.dataset.options=key;
    }
    picker.querySelectorAll('input').forEach(input=>{input.checked=selected.includes(input.value);input.disabled=locked;});
    const summary=root.querySelector('#purchase-users-summary');
    summary.textContent=selected.length?selected.map(name).join(', '):'Seleccionar usuarios';
    summary.title=summary.textContent;
  }

  _entityChoices(select, domain, chosen) {
    const states=this._data?.hass?.states??{};
    const entities=[...new Set([...Object.keys(states).filter(id=>id.startsWith(domain+'.')), ...chosen])];
    entities.sort((a,b)=>(states[a]?.attributes?.friendly_name??a).localeCompare(states[b]?.attributes?.friendly_name??b,'es'));
    const key=JSON.stringify(entities.map(id=>[id,states[id]?.attributes?.friendly_name]));
    if(select.dataset.options!==key){select.replaceChildren(...entities.map(id=>new Option(states[id]?.attributes?.friendly_name??id,id)));select.dataset.options=key;}
    for(const option of select.options)option.selected=chosen.includes(option.value);
  }

  _buildZoneSettings(root) {
    for(const store of ['alcampo','carrefour','consum','dia','eroski','lasirena','mercadona']){
      const section=document.createElement('section');section.className='zone-settings';section.dataset.store=store;section.hidden=true;
      const label=document.createElement('label');label.htmlFor='zones-'+store;label.textContent='Zonas de la tienda';
      const select=document.createElement('select');select.id='zones-'+store;select.multiple=true;select.size=4;select.setAttribute('aria-label','Zonas de '+store);
      const help=document.createElement('p');help.textContent='Puedes seleccionar varias zonas. Se usan las visitas del mismo día de las personas elegidas para proponer la tienda y priorizar sus tickets.';
      const save=document.createElement('button');save.type='button';save.className='primary';save.textContent='Guardar zonas';
      select.addEventListener('change',()=>{section.dataset.dirty='true';});
      save.addEventListener('click',()=>void this._saveRetailSettings(async()=>{
        const config=this._data.settings.purchaseDetection??{enabled:false,threshold:5};
        await this._data.settings.savePurchaseDetection({...config,store_zones:{...config.store_zones,[store]:Array.from(select.selectedOptions,option=>option.value)}});
        delete section.dataset.dirty;
      }));
      section.append(label,select,help,save);
      root.querySelector(store==='mercadona'?'#store-dialog':'#'+store+'-dialog').append(section);
    }
  }

  _renderZoneSettings(locked) {
    const config=this._data.settings.purchaseDetection??{};
    for(const section of this.shadowRoot.querySelectorAll('.zone-settings')){
      section.hidden=Array.isArray(config.shops)||!config.zone_assignment;
      const select=section.querySelector('select');
      this._entityChoices(select,'zone',section.dataset.dirty?Array.from(select.selectedOptions,option=>option.value):config.store_zones?.[section.dataset.store]??[]);
      select.disabled=locked;section.querySelector('button').disabled=locked;
    }
  }

  _buildRegionalStores(root) {
    this._regionalDrafts = {};
    for (const [store,name] of [["consum","Consum"],["lasirena","La Sirena"],["eroski","Eroski"],["dia","DIA"]]) {
      root.querySelector(".stores-grid").insertAdjacentHTML("beforeend", `<article class="store-row"><img class="store-logo" src="${new URL(`${store}.${store === "dia" ? "png" : store === "eroski" ? "svg" : "jpg"}`,import.meta.url).href}" alt="Logo de ${name}" loading="lazy" width="56" height="56"><div class="store-name"><h3>${name}</h3></div><div class="store-controls"><input id="${store}-enabled" class="store-toggle" type="checkbox" role="switch" aria-label="Habilitar ${name}"><button id="configure-${store}" class="store-cog" type="button" aria-label="Ajustes de ${name}" title="Ajustes de ${name}"><ha-icon icon="mdi:cog" aria-hidden="true"></ha-icon></button></div></article>`);
      const container = document.createElement("div");
      container.innerHTML = `<dialog id="${store}-dialog" aria-labelledby="${store}-title"><h2 id="${store}-title">${name}</h2><div id="${store}-error" class="notice error" role="alert" hidden></div><section id="${store}-products-view"><div id="${store}-products" class="store-products"></div><p id="${store}-status" class="store-cache-footer" role="status"></p></section></dialog>`;
      root.append(...container.children);
      const dialog = root.querySelector(`#${store}-dialog`);
      if(store==="dia"){const account=document.createElement("isl-dia-prices-settings");dialog.querySelector("h2").after(account);dialog.addEventListener("close",()=>account.deactivate());}
      root.querySelector(`#configure-${store}`).addEventListener("click",()=>this._openRegionalStore(store));
      root.querySelector(`#${store}-enabled`).addEventListener("change",()=>void this._saveRetailSettings(()=>this._data.settings.setStoreEnabled(store,root.querySelector(`#${store}-enabled`).checked)));
      dialog.addEventListener("cancel",event=>{if(this._busy)event.preventDefault();});
      dialog.addEventListener("close",()=>{this._regionalDrafts[store]=null;this._render();});
      this._regionalDrafts[store] = null;
    }
  }

  _openRegionalStore(store) {
    const root = this.shadowRoot, config = this._data.settings.stores?.[store] ?? {};
    this._regionalDrafts[store] = {postal:config.postal_code ?? "", enabled:Boolean(config.enabled)};
    this._error = "";
    root.querySelector(`#${store}-dialog`).showModal();
    if(store==="dia"){const account=root.querySelector("isl-dia-prices-settings");account.hass=this._data.hass;void account.activate();}
    this._render();

  }

  _renderRegionalStores(locked) {
    const root = this.shadowRoot;
    for (const store of ["consum","lasirena","eroski","dia"]) {
      root.querySelector(`#${store}-enabled`).checked = Boolean(this._data.settings.stores?.[store]?.enabled);
      root.querySelector(`#${store}-enabled`).disabled = locked;
      root.querySelector(`#configure-${store}`).disabled = !this._data.settings.loaded || this._data.settings.loading || this._busy;
      const error = root.querySelector(`#${store}-error`);
      error.textContent = this._error || ""; error.hidden = !error.textContent;
    }
  }

  async _loadRegionalProducts(store) {
    const root = this.shadowRoot, draft = this._regionalDrafts[store], connection = this._data.hass.connection;
    const current = () => this.isConnected && this._regionalDrafts[store] === draft && this._data.hass.connection === connection;
    try {
      const data = await this._data.hass.callWS({type:"improved_shopping_list/catalog/store_prices",store});
      if (!current()) return;
      root.querySelector(`#${store}-status`).textContent = `${data.products.length} precios guardados`;
      root.querySelector(`#${store}-products`).replaceChildren(...data.products.map(product=>{
        const row = document.createElement("div"); row.className = "store-product";
        const link = document.createElement("a"); link.textContent = product.name || product.store_name || product.reference_id;
        link.href = product.url; link.target = "_blank"; link.rel = "noopener noreferrer";
        const text = document.createElement("p"); text.textContent = `${new Intl.NumberFormat("es-ES",{style:"currency",currency:product.currency}).format(Number(product.price))} · Último precio: ${new Date(product.checked_at*1000).toLocaleString("es-ES")}`;
        row.append(link,text); return row;
      }));
      if(data.error){const error=root.querySelector(`#${store}-error`);error.textContent=data.error;error.hidden=false;}
    } catch(error) { if(current()){const box=root.querySelector(`#${store}-error`);box.textContent=error.message ?? "No se pudieron leer los precios guardados.";box.hidden=false;} }
  }

  async _loadAlcampo() {
    const root=this.shadowRoot, dialog=root.querySelector("#alcampo-dialog");
    const generation=this._alcampoGeneration=(this._alcampoGeneration||0)+1;
    try {
      const data=await this._data.hass.callWS({type:"improved_shopping_list/catalog/store_prices",store:"alcampo"});
      if(!this.isConnected||!dialog.open||generation!==this._alcampoGeneration)return;
      root.querySelector("#alcampo-status").textContent=`${data.products.length} precios guardados`;
      const error=root.querySelector("#alcampo-products-error");error.textContent=data.error??"";error.hidden=!error.textContent;
      root.querySelector("#alcampo-products").replaceChildren(...data.products.map(product=>{
        const row=document.createElement("div");row.className="store-product";
        const link=document.createElement("a");link.textContent=product.name||product.store_name;link.href=product.url;link.target="_blank";link.rel="noopener noreferrer";
        const text=document.createElement("p");text.textContent=`${new Intl.NumberFormat("es-ES",{style:"currency",currency:product.currency}).format(Number(product.price))} · Último precio: ${new Date(product.checked_at*1000).toLocaleString("es-ES")}`;
        row.append(link,text);return row;
      }));
    } catch(error){if(this.isConnected&&dialog.open&&generation===this._alcampoGeneration){
      const alert=root.querySelector("#alcampo-products-error");alert.textContent=error.message??"No se pudo leer la caché de precios.";alert.hidden=false;
      root.querySelector("#alcampo-status").textContent=`${root.querySelector("#alcampo-products").childElementCount} precios guardados`;
    }}
  }

  _openStore() {
    const root = this.shadowRoot;
    this._error = ""; this._storeDirty = false;
    this._renderStore();
    root.querySelector("#store-dialog").showModal();

  }

  _renderStoreProducts() {
    const root = this.shadowRoot;
    const store = this._data.settings.stores?.mercadona ?? {};
    const data = this._storeProducts?.warehouse === (store.warehouse ?? "") ? this._storeProducts : null;
    const error = root.querySelector("#store-products-error");
    error.textContent = this._productsError || data?.error || "";
    error.hidden = !error.textContent;
    root.querySelector("#store-products-status").textContent = this._productsLoading
      ? "Cargando precios guardados…" : `${data?.products?.length ?? 0} precios guardados`;
    const money = value => new Intl.NumberFormat("es-ES",{style:"currency",currency:"EUR"}).format(value);
    root.querySelector("#store-products").replaceChildren(...(data?.products ?? []).map(product => {
      const row = document.createElement("div"); row.className = "store-product";
      const info = document.createElement("div"); info.className = "store-product-info";
      const name = document.createElement("strong"); name.textContent = product.name;
      const code = document.createElement("p"); code.textContent = `EAN: ${product.ean}`;
      const source = document.createElement("a"); source.textContent = product.store_name || "Ver en Mercadona";
      source.href = product.url || `https://tienda.mercadona.es/product/${encodeURIComponent(product.store_product_id)}`; source.target = "_blank"; source.rel = "noopener noreferrer";
      info.append(name,code,source);
      const prices = document.createElement("div"); prices.className = "store-price";
      const price = document.createElement("strong"); price.textContent = `${product.approximate ? "≈ " : ""}${money(product.price)}`;
      const checked = document.createElement("p"); checked.textContent = `Consultado: ${new Date(product.checked_at*1000).toLocaleString("es-ES")}`;
      prices.append(price);
      if (Number.isFinite(product.reference_price) && product.reference_unit) {
        const reference = document.createElement("p"); reference.textContent = `${money(product.reference_price)}/${product.reference_unit}`; prices.append(reference);
      }
      if (product.available === false) { const unavailable = document.createElement("p"); unavailable.textContent = "No disponible"; prices.append(unavailable); }
      prices.append(checked); row.append(info,prices); return row;
    }));
  }

  async _loadStoreProducts() {
    if (this._productsLoading) return;
    const generation = this._productsGeneration = (this._productsGeneration || 0) + 1;
    const warehouse = this._data.settings.stores?.mercadona?.warehouse ?? "";
    const connection = this._data.hass.connection;
    this._productsLoading = true; this._productsError = ""; this._renderStoreProducts();
    try {
      const data = await this._data.hass.callWS({type:"improved_shopping_list/catalog/store_prices",store:"mercadona"});
      if (generation !== this._productsGeneration || !this.isConnected || connection !== this._data.hass.connection ||
          warehouse !== (this._data.settings.stores?.mercadona?.warehouse ?? "")) return;
      this._storeProducts = data;
    } catch (error) {
      if (generation === this._productsGeneration) this._productsError = error.message ?? "No se pudieron leer los precios guardados.";
    } finally {
      if (generation === this._productsGeneration) { this._productsLoading = false; this._renderStoreProducts(); }
    }
  }

  _fillAppearance(appearance) {
    const form = this.shadowRoot.querySelector("#appearance-form");
    for (const [key, value] of Object.entries(appearance)) form.elements[key].value = value;
    this._preview();
  }

  _readAppearance() {
    const form = this.shadowRoot.querySelector("#appearance-form");
    return {
      gradient_start: form.elements.gradient_start.value,
      quantity_color: form.elements.quantity_color.value,
      stock_gradient_start: form.elements.stock_gradient_start.value,
      stock_gradient_end: form.elements.stock_gradient_end.value,
      recipe_gradient_start: form.elements.recipe_gradient_start.value,
      recipe_gradient_end: form.elements.recipe_gradient_end.value,
      gradient_end: form.elements.gradient_end.value,
      completed_gradient_start: form.elements.completed_gradient_start.value,
      completed_gradient_end: form.elements.completed_gradient_end.value,
      columns: Number(form.elements.columns.value),
      mobile_columns: Number(form.elements.mobile_columns.value),
    };
  }

  _preview() {
    const appearance = this._readAppearance();
    const preview = this.shadowRoot.querySelector("#appearance-preview");
    preview.style.background = `linear-gradient(${appearance.gradient_start},${appearance.gradient_end})`;
    preview.style.color = gradientTextColor(appearance.gradient_start, appearance.gradient_end);
    const stock = this.shadowRoot.querySelector("#stock-appearance-preview");
    stock.style.background = `linear-gradient(${appearance.stock_gradient_start},${appearance.stock_gradient_end})`;
    stock.style.color = "#fff";
    const recipe = this.shadowRoot.querySelector("#recipe-appearance-preview");
    recipe.style.background = `linear-gradient(${appearance.recipe_gradient_start},${appearance.recipe_gradient_end})`;
    recipe.style.color = "#fff";
    const completed = this.shadowRoot.querySelector("#completed-appearance-preview");
    completed.style.background = `linear-gradient(${appearance.completed_gradient_start},${appearance.completed_gradient_end})`;
    completed.style.color = gradientTextColor(appearance.completed_gradient_start, appearance.completed_gradient_end);
  }

  async _exportCatalog() {
    if(this._exportingCatalog || this._data?.hass?.user?.is_admin !== true)return;
    const button=this.shadowRoot.querySelector('#export-catalog'),error=this.shadowRoot.querySelector('#catalog-export-error');
    this._exportingCatalog=true;button.disabled=true;error.hidden=true;
    try {
      const result=await this._data.hass.callWS({type:'improved_shopping_list/catalog/export'});
      const bytes=Uint8Array.from(atob(result.data),char=>char.charCodeAt(0));
      const url=URL.createObjectURL(new Blob([bytes],{type:'application/json;charset=utf-8'}));
      const link=document.createElement('a');link.href=url;link.download='improved-shopping-list-catalog.json';
      this.shadowRoot.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
    } catch {error.textContent='No se ha podido exportar el catálogo. Vuelve a intentarlo.';error.hidden=false;}
    finally {this._exportingCatalog=false;button.disabled=this._data?.hass?.user?.is_admin !== true;}
  }

  _renderCommunity() {
    this.shadowRoot.querySelector('#export-catalog').disabled=this._data?.hass?.user?.is_admin !== true || Boolean(this._exportingCatalog);
  }

  _renderGateways(locked) {
    const root=this.shadowRoot,{hass,settings}=this._data;
    root.querySelector('#settings-gateways').hidden=this._view!=='lists';
    const gateways=settings.gatewayLists??[];
    const sources=new Set(gateways.map(item=>item.entity_id));
    const targets=new Set(gateways.map(item=>item.target_entity));
    const name=entity=>hass?.states[entity]?.attributes.friendly_name??entity;
    const fill=(select,entities,preferred)=>{
      const previous=select.value;
      select.replaceChildren(...(entities.length?entities.map(entity=>new Option(`${name(entity)} · ${entity}`,entity)):[new Option('No hay listas disponibles','')]));
      select.value=entities.includes(previous)?previous:entities.includes(preferred)?preferred:entities[0]??'';
      select.disabled=locked||!entities.length;
    };
    const candidates=todoEntities(hass).map(state=>state.entity_id).filter(entity=>!sources.has(entity)&&!targets.has(entity)&&entity!==settings.primary);
    const destinations=settings.entities.filter(entity=>!sources.has(entity));
    fill(root.querySelector('#gateway-entity'),candidates);
    fill(root.querySelector('#gateway-target'),destinations,settings.primary);
    root.querySelector('#gateway-remove').disabled=locked;
    root.querySelector('#add-gateway').disabled=locked||!candidates.length||!destinations.length;
    root.querySelector('#configured-gateways').replaceChildren(...gateways.map(gateway=>{
      const row=document.createElement('article');row.dataset.entityId=gateway.entity_id;
      const info=document.createElement('div');info.className='list-info';
      const title=document.createElement('h3');title.textContent=name(gateway.entity_id);
      const entity=document.createElement('p');entity.className='entity';entity.textContent=gateway.entity_id;
      info.append(title,entity);
      info.append(this._nameModeOption(gateway.entity_id,locked));
      const options=document.createElement('div');options.className='gateway-options';
      const target=document.createElement('select');target.setAttribute('aria-label',`Lista de destino: ${name(gateway.entity_id)}`);
      fill(target,destinations,gateway.target_entity);target.value=gateway.target_entity;
      const cleanup=document.createElement('label');cleanup.className='gateway-cleanup';
      const check=document.createElement('input');check.type='checkbox';check.checked=gateway.remove_after_transfer;check.disabled=locked;
      cleanup.append(check,document.createTextNode('Eliminar de la pasarela tras transferir'));
      const save=()=>void this._saveRetailSettings(()=>settings.saveGateway(gateway.entity_id,target.value,check.checked));
      target.addEventListener('change',save);check.addEventListener('change',save);
      options.append(target,cleanup);
      const remove=document.createElement('button');remove.type='button';remove.className='list-action list-remove';remove.disabled=locked;
      remove.setAttribute('aria-label',`Quitar pasarela: ${name(gateway.entity_id)}`);remove.title='Quitar pasarela';
      remove.innerHTML='<ha-icon icon="mdi:delete" aria-hidden="true"></ha-icon>';
      remove.addEventListener('click',()=>void this._saveRetailSettings(()=>settings.removeGateway(gateway.entity_id)));
      row.append(info,options,remove);return row;
    }));
  }

  async _saveAppearance() {
    if (this._busy) return;
    const appearance = this._readAppearance();
    this._busy = true;
    this._error = "";
    this._notice = "";
    this._render();
    try {
      await this.onAppearance(appearance);
      this._appearanceDirty = false;
      this._notice = "Personalización guardada.";
    } catch (error) {
      this._error = error.message ?? "No se ha podido guardar la personalización.";
    } finally { this._busy = false; this._render(); }
  }

  async _act(action, entity) {
    if (this._busy) return;
    this._busy = true;
    this._error = "";
    this._notice = "";
    this._render();
    try {
      await this.onAction(action, entity);
      this._notice = "Ajustes guardados.";
    } catch (error) {
      this._error = error.message ?? "No se han podido guardar los ajustes.";
    } finally { this._busy = false; this._render(); }
  }
}

if (!customElements.get("isl-settings")) customElements.define("isl-settings", ImprovedShoppingSettings);
