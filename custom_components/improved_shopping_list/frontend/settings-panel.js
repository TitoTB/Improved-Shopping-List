import "./logs-panel.js?v=0.17.0";
import { installDialogCloseButtons } from "./dialog-controls.js?v=0.17.0";
import { todoEntities, isAvailable } from "./todo-client.js?v=0.17.0";
import { DEFAULT_APPEARANCE, gradientTextColor } from "./list-settings-client.js?v=0.17.0";

const MERCADONA_LOGO_URL = new URL("mercadona.png", import.meta.url).href;
const LIDL_LOGO_URL = new URL("lidl.png", import.meta.url).href;

/** Default store navigation: use Mercadona's layout for every store dialog. */
function storeViewTabs(name, productsId, configurationId) {
  return `<nav class="settings-tabs store-view-tabs" aria-label="Vistas de ${name}"><button id="${productsId}" aria-pressed="true" type="button"><ha-icon icon="mdi:view-grid" aria-hidden="true"></ha-icon>Productos</button><button id="${configurationId}" aria-pressed="false" type="button"><ha-icon icon="mdi:cog" aria-hidden="true"></ha-icon>Configuración</button></nav>`;
}

class ImprovedShoppingSettings extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._view = "lists";
  }

  set data(value) { this._data = value; this._render(); }

  set active(value) { this._active = Boolean(value); this._syncLogs(); }

  _syncLogs() {
    const logs = this.shadowRoot.querySelector("isl-logs");
    if (!logs) return;
    if (this._data?.hass) logs.hass = this._data.hass;
    logs.active = Boolean(this._active && this._view === "logs" && this.isConnected);
  }


  connectedCallback() {
    if (!this._built) this._build();
    this._render();
  }

  disconnectedCallback() {
    this.active = false;
    clearInterval(this._pricesProgressTimer);
    this.shadowRoot.querySelector("#prices-progress-dialog")?.close();
    this.shadowRoot.querySelector("#price-schedule-dialog")?.close();
    this._priceStatusToken = null; this._priceStatusConnection = null; this._stopPriceStatus?.(); this._stopPriceStatus = null;
    this._productsLoading = false; this._productsGeneration = (this._productsGeneration || 0) + 1;
    this._carrefourGeneration = (this._carrefourGeneration || 0) + 1; this._carrefourLoading = false; this._alcampoGeneration = (this._alcampoGeneration || 0) + 1;
    this.shadowRoot.querySelector("#alcampo-dialog")?.close(); this.shadowRoot.querySelector("#carrefour-dialog")?.close(); this.shadowRoot.querySelector("#store-dialog")?.close();
    this.shadowRoot.querySelector("#lidl-dialog")?.close(); this._lidlGeneration=(this._lidlGeneration||0)+1;
  }

  _build() {
    this.shadowRoot.innerHTML = `
      <style>
        :host { display:block; color:var(--primary-text-color,#20352d); }
        :host([hidden]),[hidden] { display:none !important; }
        * { box-sizing:border-box; }
        h1 { font-size:32px; letter-spacing:-.03em; margin:28px 0 12px; }
        h2 { font-size:20px; margin:0 0 16px; }
        p { color:var(--secondary-text-color,#63766b); line-height:1.6; font-size:13px; }
        .card { padding:22px; border:1px solid var(--divider-color,#dfe7e1); border-radius:16px; background:var(--card-background-color,#fff); margin-top:20px; }
        button,select,input { font:inherit; min-height:46px; border:1px solid var(--divider-color,#dfe7e1); border-radius:10px; color:inherit; background:transparent; padding:10px 14px; }
        button { cursor:pointer; }
        button:disabled,select:disabled,input:disabled { opacity:.5; cursor:default; }
        button:focus-visible,select:focus-visible,input:focus-visible { outline:3px solid var(--primary-color,#267052); outline-offset:3px; }
        .settings-tabs { display:flex; flex-wrap:wrap; gap:8px; margin:18px 0; }
        .settings-tabs button { display:inline-flex; align-items:center; justify-content:center; gap:8px; }
        .settings-tabs ha-icon { --mdc-icon-size:20px; display:flex; align-items:center; justify-content:center; width:20px; height:20px; flex:none; line-height:0; }
        .settings-tabs [aria-pressed=true] { background:var(--secondary-background-color,#edf4ee); font-weight:650; }
        .appearance-fields { display:grid; grid-template-columns:1fr 1fr; gap:18px; }
        input[type=checkbox] { min-height:20px; width:20px; vertical-align:middle; accent-color:#267052; }
        input[type=color] { display:block; width:100%; padding:5px; cursor:pointer; }
        .appearance-actions { display:flex; justify-content:flex-end; flex-wrap:wrap; gap:10px; margin-top:24px; }
        .preview { display:grid; place-items:center; min-height:120px; border-radius:16px; margin-top:24px; padding:20px; font-weight:650; }
        @media(max-width:540px) { .appearance-fields { grid-template-columns:1fr; } }
        .store-row { display:grid; grid-template-columns:56px minmax(0,1fr) auto; gap:8px 12px; align-items:center; }
        .store-row[data-enabled=false] { opacity:.55; }
        .store-row[data-enabled=true] { background:rgba(38,112,82,.10); }
        #price-schedule-form > label { margin-bottom:12px; }
        #price-update-time { display:block; width:100%; }
        #settings-stores { container-type:inline-size; }
        .stores-grid { display:grid; grid-template-columns:minmax(0,1fr); gap:12px; }
        @container(min-width:800px) { .stores-grid { grid-template-columns:repeat(2,minmax(0,1fr)); } }
        .store-logo { width:56px; height:56px; padding:8px; flex:none; object-fit:contain; border-radius:10px; background:#fff; }
        .store-row .store-logo { grid-column:1; grid-row:1; }
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
        .store-cog ha-icon { display:flex; align-items:center; justify-content:center; width:24px; height:24px; --mdc-icon-size:24px; }
        dialog { color:inherit; background:var(--card-background-color,#fff); width:min(680px,calc(100vw - 28px)); max-height:calc(100dvh - 28px); border:1px solid var(--divider-color,#dfe7e1); border-radius:18px; padding:24px; }
        dialog::backdrop { background:rgba(0,0,0,.4); }
        .store-products { display:grid; gap:12px; margin-top:16px; }.store-product { display:flex; justify-content:space-between; align-items:center; gap:12px; border:1px solid var(--divider-color,#dfe7e1); border-radius:10px; padding:14px; }
        .store-configuration input:not([type=checkbox]), .store-configuration select { display:block; width:100%; }
        .store-cache-footer { text-align:left; margin:16px 0 0; font-size:12px; }
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
        h3 { margin:0; font-size:16px; }
        .entity { margin:5px 0 0; font-size:12px; }
        .badge { display:inline-flex; gap:5px; align-items:center; color:var(--primary-color,#267052); font-size:12px; margin-top:8px; }
        .badge ha-icon { --mdc-icon-size:18px; }
        .actions { display:flex; gap:8px; flex-wrap:wrap; }
        .notice { padding:12px 14px; border-radius:10px; background:var(--secondary-background-color,#edf4ee); font-size:13px; line-height:1.6; margin:14px 0; }
        .error { color:var(--error-color,#bd3636); border:1px solid var(--error-color,#bd3636); }
        @media(max-width:540px) { .card { padding:18px 14px; } .add-row { flex-wrap:wrap; } .select-wrap { flex-basis:100%; } .actions { width:100%; } }
      </style>
      <h1>Ajustes</h1>
      <nav class="settings-tabs" aria-label="Vistas de ajustes"><button id="settings-view-lists" aria-pressed="true"><ha-icon icon="mdi:format-list-checks" aria-hidden="true"></ha-icon>Listas</button><button id="settings-view-appearance" aria-pressed="false"><ha-icon icon="mdi:palette" aria-hidden="true"></ha-icon>Personalización</button><button id="settings-view-stores" aria-pressed="false"><ha-icon icon="mdi:store" aria-hidden="true"></ha-icon>Tiendas</button><button id="settings-view-community" aria-pressed="false"><ha-icon icon="mdi:account-group" aria-hidden="true"></ha-icon>Comunidad</button><button id="settings-view-logs" aria-pressed="false"><ha-icon icon="mdi:format-list-group" aria-hidden="true"></ha-icon>Logs</button></nav>
      <div id="settings-error" class="notice error" role="alert" hidden></div>
      <div id="settings-status" class="notice" role="status" hidden></div>
      <p id="admin-help" hidden>Necesitas una cuenta administradora de Home Assistant para modificar estos ajustes.</p>
      <section id="settings-lists" class="card" aria-labelledby="settings-lists-title">
        <h2 id="settings-lists-title">Listas de la compra</h2>
        <p>Elige las listas que quieres utilizar y marca una como principal. Quitar una lista de aquí conserva su entidad y sus productos en Home Assistant.</p>
        <div class="add-row"><div class="select-wrap"><label for="todo-entity">Entidad todo</label><select id="todo-entity"></select></div><button id="add-list" class="primary">Añadir lista</button></div>
        <div id="configured-lists" class="lists"></div>
        <p id="settings-empty" hidden>No hay listas añadidas. Añade una entidad todo para empezar.</p>
      </section>
      <section id="settings-appearance" class="card" aria-labelledby="settings-appearance-title" hidden>
        <h2 id="settings-appearance-title">Personalización</h2>
        <p>Personaliza las tarjetas del apartado Lista. Pulsa una tarjeta para marcar o desmarcar su compra.</p>
        <form id="appearance-form">
          <div class="appearance-fields">
            <div><label for="gradient-start">Color inicial del degradado</label><input id="gradient-start" name="gradient_start" type="color" value="#ee524f"></div>
            <div><label for="gradient-end">Color final del degradado</label><input id="gradient-end" name="gradient_end" type="color" value="#b52a27"></div>
            <div><label for="completed-gradient-start">Color inicial de Comprados</label><input id="completed-gradient-start" name="completed_gradient_start" type="color" value="#4faba2"></div>
            <div><label for="completed-gradient-end">Color final de Comprados</label><input id="completed-gradient-end" name="completed_gradient_end" type="color" value="#26857c"></div>
            <div><label for="desktop-columns">Productos por fila (ordenador)</label><select id="desktop-columns" name="columns">${[1,2,3,4,5,6].map(value => `<option value="${value}">${value}</option>`).join("")}</select></div>
            <div><label for="mobile-columns">Productos por fila (móvil)</label><select id="mobile-columns" name="mobile_columns">${[1,2,3,4].map(value => `<option value="${value}">${value}</option>`).join("")}</select></div>
          </div>
          <div id="appearance-preview" class="preview">Vista previa de producto pendiente</div>
          <div id="completed-appearance-preview" class="preview">Vista previa de producto comprado</div>
          <div class="appearance-actions"><button id="reset-appearance" type="button">Restablecer valores</button><button id="save-appearance" class="primary" type="submit">Guardar personalización</button></div>
        </form>
      </section>
      <section id="settings-stores" class="card" aria-labelledby="settings-stores-title" hidden>
        <div class="stores-heading"><h2 id="settings-stores-title">Tiendas</h2><div class="stores-heading-actions"><button id="refresh-all-prices" class="store-refresh" type="button" aria-label="Actualizar ahora" title="Actualizar ahora"><ha-icon icon="mdi:refresh" aria-hidden="true"></ha-icon></button><button id="configure-price-schedule" class="store-refresh" type="button" aria-label="Hora de revisión diaria" title="Hora de revisión diaria"><ha-icon icon="mdi:clock-outline" aria-hidden="true"></ha-icon></button></div></div>
        <div class="stores-grid">
        <article class="store-row" id="mercadona-row">
          <img class="store-logo" src="${MERCADONA_LOGO_URL}" alt="Logo de Mercadona" referrerpolicy="no-referrer" loading="lazy" width="56" height="56">
          <div class="store-name"><h3>Mercadona</h3></div>
          <div class="store-controls"><input id="mercadona-enabled" class="store-toggle" type="checkbox" role="switch" aria-label="Habilitar Mercadona"><button id="configure-mercadona" class="store-cog" type="button" aria-label="Ajustes de Mercadona" title="Ajustes de Mercadona"><ha-icon icon="mdi:cog" aria-hidden="true"></ha-icon></button></div>
        </article>
        <article class="store-row" id="carrefour-row"><img class="store-logo" src="https://images.seeklogo.com/logo-png/31/2/carrefour-logo-png_seeklogo-318190.png" alt="Logo de Carrefour" referrerpolicy="no-referrer" loading="lazy" width="56" height="56"><div class="store-name"><h3>Carrefour</h3></div><div class="store-controls"><input id="carrefour-enabled" class="store-toggle" type="checkbox" role="switch" aria-label="Habilitar Carrefour"><button id="configure-carrefour" class="store-cog" type="button" aria-label="Ajustes de Carrefour"><ha-icon icon="mdi:cog" aria-hidden="true"></ha-icon></button></div></article>
        <article class="store-row"><img class="store-logo" src="https://almeria.online/wp-content/uploads/2024/09/alcampo-logo.png" alt="Logo de Alcampo" referrerpolicy="no-referrer" loading="lazy" width="56" height="56"><div class="store-name"><h3>Alcampo</h3></div><div class="store-controls"><input id="alcampo-enabled" class="store-toggle" type="checkbox" role="switch" aria-label="Habilitar Alcampo"><button id="configure-alcampo" class="store-cog" type="button" aria-label="Ajustes de Alcampo"><ha-icon icon="mdi:cog" aria-hidden="true"></ha-icon></button></div></article>

        <article class="store-row" id="lidl-row"><img class="store-logo" src="${LIDL_LOGO_URL}" alt="Logo de Lidl" loading="lazy" width="56" height="56"><div class="store-name"><h3>Lidl</h3></div><div class="store-controls"><input id="lidl-enabled" class="store-toggle" type="checkbox" role="switch" aria-label="Habilitar Lidl"><button id="configure-lidl" class="store-cog" type="button" aria-label="Ajustes de Lidl" title="Ajustes de Lidl"><ha-icon icon="mdi:cog" aria-hidden="true"></ha-icon></button></div></article>
        </div>
        <div class="stores-footer">Última actualización: <time id="stores-last-updated" title="Última actualización correcta de precios">—</time></div>
      </section>
      <dialog id="prices-progress-dialog" aria-labelledby="prices-progress-title">
        <h2 id="prices-progress-title">Actualización de precios</h2>
        <div class="store-progress"><div class="store-progress-track"><progress id="prices-progress-bar" max="1" aria-label="Progreso de actualización de todas las tiendas"></progress><span id="prices-progress-percentage" class="store-progress-percentage" aria-hidden="true">…</span></div><p id="prices-progress-status" role="status">Preparando actualización…</p><p id="prices-progress-time"></p></div>
        <div id="stores-refresh-error" class="notice error" role="alert" hidden></div>
        <div class="appearance-actions"><button id="close-prices-progress" type="button">Cerrar</button></div>
      </dialog>
      <dialog id="price-schedule-dialog" aria-labelledby="price-schedule-title">
        <h2 id="price-schedule-title">Hora de revisión diaria</h2>
        <form id="price-schedule-form"><label for="price-update-time">Hora de revisión diaria</label><input id="price-update-time" type="time" value="01:00" required><div id="price-schedule-error" class="notice error" role="alert" hidden></div><div class="appearance-actions"><button id="save-price-update-time" class="primary" type="submit">Guardar horario</button></div></form>
      </dialog>
      <dialog id="lidl-dialog" aria-labelledby="lidl-title">
        <h2 id="lidl-title">Lidl</h2>
        ${storeViewTabs("Lidl","lidl-products-tab","lidl-config-tab")}
        <section id="lidl-products-view"><div id="lidl-products-error" class="notice error" role="alert" hidden></div><div id="lidl-products" class="store-products"></div><p id="lidl-status" class="store-cache-footer" role="status"></p></section>
        <section id="lidl-config-view" class="store-configuration" hidden><form id="lidl-form"><label for="lidl-region">Región de Lidl</label><select id="lidl-region" required><option value="">Selecciona una región</option></select><p>Selecciona la región de tu compra habitual.</p><div id="lidl-config-error" class="notice error" role="alert" hidden></div><div class="appearance-actions"><button id="save-lidl" class="primary" type="submit">Guardar configuración</button></div></form></section>
      </dialog>
      <dialog id="carrefour-dialog" aria-labelledby="carrefour-dialog-title">
        <h2 id="carrefour-dialog-title">Carrefour</h2>
        ${storeViewTabs("Carrefour","carrefour-products-tab","carrefour-config-tab")}
        <section id="carrefour-products-view"><p>Últimos precios conocidos de las referencias vinculadas.</p><div id="carrefour-error" class="notice error" role="alert" hidden></div><div id="carrefour-products" class="store-products"></div><p id="carrefour-status" class="store-cache-footer" role="status"></p></section>
        <section id="carrefour-config-view" class="store-configuration" hidden><label for="carrefour-sale-point">Centro de Carrefour (sale_point)</label><input id="carrefour-sale-point" type="text" inputmode="numeric" minlength="6" maxlength="6" pattern="[0-9]{6}" placeholder="005290"><p>Identificador de seis dígitos del centro utilizado para consultar precios. Centro predeterminado: 005290. Los precios pueden variar entre centros.</p><div id="carrefour-config-error" class="notice error" role="alert" hidden></div><div class="appearance-actions"><button id="save-carrefour" class="primary" type="button">Guardar configuración</button></div></section>
      </dialog>
      <dialog id="alcampo-dialog" aria-labelledby="alcampo-title"><h2 id="alcampo-title">Alcampo</h2>${storeViewTabs("Alcampo","alcampo-products-tab","alcampo-config-tab")}<section id="alcampo-products-view"><div id="alcampo-products-error" class="notice error" role="alert" hidden></div><div id="alcampo-products" class="store-products"></div><p id="alcampo-status" class="store-cache-footer" role="status"></p></section><section id="alcampo-config-view" class="store-configuration" hidden><label for="alcampo-region">Región de Alcampo</label><input id="alcampo-region" maxlength="36" placeholder="regionId opcional"><p>Si tu consulta utiliza una región, introduce su regionId. Sin región solo se podrá mostrar el precio que devuelva la web sin ubicación seleccionada.</p><div class="appearance-actions"><button id="save-alcampo" class="primary" type="button">Guardar configuración</button></div></section></dialog>
      <dialog id="store-dialog" aria-labelledby="store-dialog-title">
        <h2 id="store-dialog-title">Mercadona</h2>
        ${storeViewTabs("Mercadona","store-view-products","store-view-configuration")}
        <div id="store-dialog-error" class="notice error" role="alert" hidden></div>
        <section id="store-products-view">
          <div id="store-products-error" class="notice error" role="alert" hidden></div>
          <div id="store-products" class="store-products"></div>
          <p id="store-products-status" class="store-cache-footer" role="status"></p>
        </section>
        <section id="store-configuration-view" class="store-configuration" hidden>
          <form id="store-form">
            <p>Introduce tu código postal para obtener el almacén asignado por Mercadona. No necesitas una cuenta.</p>
            <label for="mercadona-postal">Código postal</label>
            <input id="mercadona-postal" type="text" inputmode="numeric" autocomplete="postal-code" maxlength="5" pattern="(?:0[1-9]|[1-4][0-9]|5[0-2])[0-9]{3}" placeholder="28001" required>
            <p id="mercadona-warehouse" role="status"></p>
            <div class="appearance-actions"><button id="save-store" class="primary" type="submit">Comprobar y guardar</button></div>
          </form>
        </section>
      </dialog>
      <section id="settings-logs" class="card" aria-label="Logs" hidden><isl-logs></isl-logs></section>
      <section id="settings-community" class="card" aria-labelledby="settings-community-title" hidden>
        <h2 id="settings-community-title">Comunidad</h2>
        <div class="community-export"><p>Exporta un diccionario con los nombres de tus productos, sus traducciones disponibles y las imágenes locales asignadas. Puedes enviarlo al mantenedor para incorporar las imágenes revisadas al catálogo comunitario, creando un Issue en el <a href="https://github.com/TitoTB/Improved-Shopping-List" target="_blank" rel="noopener noreferrer">repositorio de Github</a>.</p><button id="export-community" class="primary community-action" type="button"><svg viewBox="0 0 512 512" aria-hidden="true" focusable="false"><!--! Font Awesome Free 6.7.2 by @fontawesome - https://fontawesome.com License - https://fontawesome.com/license/free (Icons: CC BY 4.0, Fonts: SIL OFL 1.1, Code: MIT License) Copyright 2024 Fonticons, Inc. --><path d="M288 32c0-17.7-14.3-32-32-32s-32 14.3-32 32l0 242.7-73.4-73.4c-12.5-12.5-32.8-12.5-45.3 0s-12.5 32.8 0 45.3l128 128c12.5 12.5 32.8 12.5 45.3 0l128-128c12.5-12.5 12.5-32.8 0-45.3s-32.8-12.5-45.3 0L288 274.7 288 32zM64 352c-35.3 0-64 28.7-64 64l0 32c0 35.3 28.7 64 64 64l384 0c35.3 0 64-28.7 64-64l0-32c0-35.3-28.7-64-64-64l-101.5 0-45.3 45.3c-25 25-65.5 25-90.5 0L165.5 352 64 352zm368 56a24 24 0 1 1 0 48 24 24 0 1 1 0-48z"/></svg>Exportar mis iconos</button></div>
        <div class="community-export"><p>Este proyecto ha sido desarrollado por la <a href="https://t.me/aguacatec_es/3" target="_blank" rel="noopener noreferrer">comunidad de Aguacatec</a>. Si tienes cualquier duda o sugerencia para mejorar la integración puedes unirte a través de Telegram.</p><a class="community-action community-join" href="https://t.me/aguacatec_es/3" target="_blank" rel="noopener noreferrer"><svg viewBox="0 0 496 512" aria-hidden="true" focusable="false"><!--! Font Awesome Free 6.7.2 by @fontawesome - https://fontawesome.com License - https://fontawesome.com/license/free (Icons: CC BY 4.0, Fonts: SIL OFL 1.1, Code: MIT License) Copyright 2024 Fonticons, Inc. --><path d="M248,8C111.033,8,0,119.033,0,256S111.033,504,248,504,496,392.967,496,256,384.967,8,248,8ZM362.952,176.66c-3.732,39.215-19.881,134.378-28.1,178.3-3.476,18.584-10.322,24.816-16.948,25.425-14.4,1.326-25.338-9.517-39.287-18.661-21.827-14.308-34.158-23.215-55.346-37.177-24.485-16.135-8.612-25,5.342-39.5,3.652-3.793,67.107-61.51,68.335-66.746.153-.655.3-3.1-1.154-4.384s-3.59-.849-5.135-.5q-3.283.746-104.608,69.142-14.845,10.194-26.894,9.934c-8.855-.191-25.888-5.006-38.551-9.123-15.531-5.048-27.875-7.717-26.8-16.291q.84-6.7,18.45-13.7,108.446-47.248,144.628-62.3c68.872-28.647,83.183-33.623,92.511-33.789,2.052-.034,6.639.474,9.61,2.885a10.452,10.452,0,0,1,3.53,6.716A43.765,43.765,0,0,1,362.952,176.66Z"/></svg>Unirme a la comunidad</a></div>
        <div class="community-export"><p>Si quieres apoyar a <a href="https://aguacatec.es/" target="_blank" rel="noopener noreferrer">Aguacatec</a> para que podamos seguir desarrollando proyectos como estos, conseguir contenido exclusivo, participar en sorteos y otras ventajas, puedes hacerte <a href="https://www.patreon.com/c/aguacatec/membership" target="_blank" rel="noopener noreferrer">Patreon</a>.</p><a class="community-action community-patreon" href="https://www.patreon.com/c/aguacatec/membership" target="_blank" rel="noopener noreferrer"><svg viewBox="0 0 512 512" aria-hidden="true" focusable="false"><!--! Font Awesome Free 6.7.2 by @fontawesome - https://fontawesome.com License - https://fontawesome.com/license/free (Icons: CC BY 4.0, Fonts: SIL OFL 1.1, Code: MIT License) Copyright 2024 Fonticons, Inc. --><path d="M489.7 153.8c-.1-65.4-51-119-110.7-138.3C304.8-8.5 207-5 136.1 28.4C50.3 68.9 23.3 157.7 22.3 246.2C21.5 319 28.7 510.6 136.9 512c80.3 1 92.3-102.5 129.5-152.3c26.4-35.5 60.5-45.5 102.4-55.9c72-17.8 121.1-74.7 121-150z"/></svg>Hacerme Patreon</a></div>
      </section>`;
    this._built = true;
    this.shadowRoot.querySelector("#add-list").addEventListener("click", () => {
      const entity = this.shadowRoot.querySelector("#todo-entity").value;
      if (entity) void this._act("add", entity);
    });
    const root = this.shadowRoot;
    installDialogCloseButtons(root);
    root.querySelector("#refresh-all-prices").addEventListener("click",()=>void this._refreshPricesNow());
    const storesGrid=root.querySelector(".stores-grid");
    storesGrid.append(...[...storesGrid.querySelectorAll(".store-row")].sort((a,b)=>
      a.querySelector("h3").textContent.localeCompare(b.querySelector("h3").textContent,"es")));
    for (const store of ["mercadona", "carrefour", "alcampo", "lidl"]) {
      const row = root.querySelector(`#${store}-enabled`).closest(".store-row");
      const heart = document.createElement("button"); heart.id = `favorite-${store}`; heart.type = "button"; heart.className = "store-cog store-favorite";
      const label = `Marcar ${row.querySelector("h3").textContent} como favorita`;
      heart.setAttribute("aria-label",label); heart.title = label; heart.setAttribute("aria-pressed","false");
      heart.innerHTML = '<ha-icon icon="mdi:heart-outline" aria-hidden="true"></ha-icon>';
      heart.addEventListener("click",()=>void this._saveRetailSettings(()=>this._data.settings.saveFavoriteStore(store)));
      row.querySelector(".store-controls").append(heart);
    }
    root.querySelector("#configure-price-schedule").addEventListener("click",()=>{
      root.querySelector("#price-update-time").value=this._data.settings.priceUpdateTime ?? "01:00";
      this._error=""; this._render(); root.querySelector("#price-schedule-dialog").showModal();
    });
    root.querySelector("#price-schedule-form").addEventListener("submit",event=>{event.preventDefault();void this._savePriceSchedule();});
    root.querySelector("#close-prices-progress").addEventListener("click",()=>root.querySelector("#prices-progress-dialog").close());
    root.querySelector("#configure-lidl").addEventListener("click",()=>this._openLidl("products"));
    root.querySelector("#lidl-enabled").addEventListener("change",()=>{
      const enabled=root.querySelector("#lidl-enabled").checked, region=this._data.settings.stores?.lidl?.region_id??"";
      if(enabled&&!region){this._lidlEnableDraft=true;this._openLidl("config");}
      else void this._saveRetailSettings(()=>this._data.settings.saveLidl(enabled,region));
    });
    for(const view of ["products","config"])root.querySelector(`#lidl-${view}-tab`).addEventListener("click",()=>this._switchLidlView(view));
    root.querySelector("#lidl-form").addEventListener("submit",event=>{
      event.preventDefault();
      void this._saveRetailSettings(async()=>{
        await this._data.settings.saveLidl(this._lidlEnableDraft??Boolean(this._data.settings.stores?.lidl?.enabled),root.querySelector("#lidl-region").value);
        this._lidlEnableDraft=undefined;await this._loadLidlData();
      });
    });
    root.querySelector("#lidl-dialog").addEventListener("cancel",event=>{if(this._busy)event.preventDefault();});
    root.querySelector("#lidl-dialog").addEventListener("close",()=>{
      this._lidlGeneration=(this._lidlGeneration||0)+1;this._lidlEnableDraft=undefined;this._error="";this._render();
    });
    root.querySelector("#prices-progress-dialog").addEventListener("close",()=>clearInterval(this._pricesProgressTimer));
    root.querySelector("#alcampo-enabled").addEventListener("change",()=>void this._saveRetailSettings(()=>this._data.settings.saveAlcampo(root.querySelector("#alcampo-enabled").checked,this._data.settings.stores?.alcampo?.region_id ?? "")));
    root.querySelector("#configure-alcampo").addEventListener("click",()=>{root.querySelector("#alcampo-region").value=this._data.settings.stores?.alcampo?.region_id ?? "";showAlcampoView("products");root.querySelector("#alcampo-dialog").showModal();void this._loadAlcampo();});
    root.querySelector("#alcampo-dialog").addEventListener("cancel",event=>{if(this._busy)event.preventDefault();});
    const alcampoError=document.createElement("div");alcampoError.id="alcampo-error";alcampoError.className="notice error";alcampoError.setAttribute("role","alert");alcampoError.hidden=true;root.querySelector("#alcampo-title").after(alcampoError);
    const showAlcampoView = view => {
      for (const name of ["products", "config"]) {
        root.querySelector(`#alcampo-${name}-view`).hidden = name !== view;
        root.querySelector(`#alcampo-${name}-tab`).setAttribute("aria-pressed", String(name === view));
      }
    };
    for(const view of ["products","config"])root.querySelector(`#alcampo-${view}-tab`).addEventListener("click",()=>showAlcampoView(view));
    root.querySelector("#save-alcampo").addEventListener("click",()=>void this._saveRetailSettings(()=>this._data.settings.saveAlcampo(root.querySelector("#alcampo-enabled").checked,root.querySelector("#alcampo-region").value.trim())));
    for (const [id, view] of [["settings-view-lists", "lists"], ["settings-view-appearance", "appearance"], ["settings-view-community", "community"], ["settings-view-stores", "stores"], ["settings-view-logs", "logs"]]) {
      root.querySelector(`#${id}`).addEventListener("click", () => {
        this._view = view;
        for (const section of ["lists", "appearance", "community", "stores", "logs"]) {
          root.querySelector(`#settings-${section}`).hidden = view !== section;
          root.querySelector(`#settings-view-${section}`).setAttribute("aria-pressed", String(view === section));
        }
        this._notice = "";
        this._error = "";
        this._render();
      });
    }
    root.querySelector("#store-form").addEventListener("submit", event => { event.preventDefault(); void this._saveStore(this._storeEnableDraft ?? Boolean(this._data.settings.stores?.mercadona?.enabled), true); });
    root.querySelector("#carrefour-enabled").addEventListener("change", () => void this._saveRetailSettings(() => this._data.settings.saveCarrefour(root.querySelector("#carrefour-enabled").checked)));
    const showCarrefourView = view => {
      for (const name of ["products","config"]) {
        root.querySelector(`#carrefour-${name}-view`).hidden = name !== view;
        root.querySelector(`#carrefour-${name}-tab`).setAttribute("aria-pressed",String(name === view));
      }
    };
    root.querySelector("#carrefour-products-tab").addEventListener("click",()=>showCarrefourView("products"));
    root.querySelector("#carrefour-config-tab").addEventListener("click",()=>showCarrefourView("config"));
    root.querySelector("#configure-carrefour").addEventListener("click", () => { root.querySelector("#carrefour-sale-point").value=this._data.settings.stores?.carrefour?.sale_point ?? "005290"; showCarrefourView("products"); root.querySelector("#carrefour-dialog").showModal(); void this._loadCarrefour(false); });
    root.querySelector("#save-carrefour").addEventListener("click",()=>void this._saveRetailSettings(async()=>{
      await this._data.settings.saveCarrefour(Boolean(this._data.settings.stores?.carrefour?.enabled),root.querySelector("#carrefour-sale-point").value.trim());
      this._carrefourGeneration = (this._carrefourGeneration || 0)+1; this._carrefourLoading = false;
      await this._loadCarrefour(false);
    }));
    root.querySelector("#carrefour-dialog").addEventListener("cancel",event=>{if(this._busy)event.preventDefault();});
    root.querySelector("#carrefour-dialog").addEventListener("close", () => { if (!root.querySelector("#carrefour-dialog").open) { this._carrefourGeneration = (this._carrefourGeneration || 0) + 1; this._carrefourLoading = false; } });
    root.querySelector("#mercadona-enabled").addEventListener("change", () => {
      const enabled = root.querySelector("#mercadona-enabled").checked;
      const store = this._data.settings.stores?.mercadona ?? {};
      if (enabled && !store.postal_code) { this._storeEnableDraft = true; this._openStore("configuration"); }
      else void this._saveStore(enabled, false);
    });
    root.querySelector("#configure-mercadona").addEventListener("click", () => this._openStore("products"));
    root.querySelector("#store-dialog").addEventListener("cancel", event => { if (this._busy) event.preventDefault(); });
    root.querySelector("#store-dialog").addEventListener("close", () => {
      if (root.querySelector("#store-dialog").open) return;
      this._storeEnableDraft = undefined; this._storeDirty = false;
      this._productsGeneration = (this._productsGeneration || 0) + 1; this._productsLoading = false;
      this._error = ""; this._render();
    });
    for (const view of ["products", "configuration"]) root.querySelector(`#store-view-${view}`).addEventListener("click", () => this._switchStoreView(view));
    root.querySelector("#store-form").addEventListener("input", () => { this._storeDirty = true; this._renderStore(); });
    root.querySelector("#export-community").addEventListener("click", () => void this._exportCommunity());
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
    this._syncLogs();
    const { hass, settings } = this._data;
    const root = this.shadowRoot;
    const admin = hass?.user?.is_admin === true;
    const locked = !admin || !settings.loaded || settings.loading || this._busy;
    const refresh = root.querySelector("#refresh-all-prices");
    refresh.disabled = locked || this._pricesRefreshing || !Object.values(settings.stores ?? {}).some(store=>store.enabled);
    refresh.setAttribute("aria-busy",String(Boolean(this._pricesRefreshing)));
    root.querySelector("#configure-price-schedule").disabled = !settings.loaded || settings.loading || this._busy;
    this._watchPriceStatus();
    this._renderPriceTimestamp();
    this._renderGlobalPriceProgress();
    for (const store of ["mercadona", "carrefour", "alcampo", "lidl"]) {
      root.querySelector(`#${store}-enabled`).closest(".store-row").dataset.enabled = String(Boolean(settings.stores?.[store]?.enabled));
      const favorite = root.querySelector(`#favorite-${store}`);
      favorite.disabled = locked || !settings.stores?.[store]?.enabled;
      const selected = Boolean(settings.stores?.[store]?.enabled && settings.favoriteStore === store);
      favorite.setAttribute("aria-pressed",String(selected));
      favorite.querySelector("ha-icon").setAttribute("icon",selected ? "mdi:heart" : "mdi:heart-outline");
    }
    root.querySelector("#export-community").disabled = locked;
    const error = root.querySelector("#settings-error");
    error.textContent = this._error || settings.error;
    error.hidden = !error.textContent || root.querySelector("#store-dialog").open;
    const status = root.querySelector("#settings-status");
    status.textContent = settings.loading ? "Cargando ajustes…" : this._notice ?? "";
    status.hidden = !status.textContent || (!settings.loading && !root.querySelector("#settings-stores").hidden);
    root.querySelector("#admin-help").hidden = admin;
    const select = root.querySelector("#todo-entity");
    const previous = select.value;
    const candidates = todoEntities(hass).filter(state => !settings.entities.includes(state.entity_id));
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
      if (entity === settings.primary) {
        const badge = document.createElement("span");
        badge.className = "badge";
        const icon = document.createElement("ha-icon");
        icon.setAttribute("icon", "mdi:star");
        badge.append(icon, document.createTextNode("Principal"));
        info.append(badge);
      }
      const actions = document.createElement("div");
      actions.className = "actions";
      for (const [label, action] of [["Hacer principal", "primary"], ["Quitar", "remove"]]) {
        if (action === "primary" && entity === settings.primary) continue;
        const button = document.createElement("button");
        button.textContent = label;
        button.setAttribute("aria-label", `${label}: ${name}`);
        button.disabled = locked;
        button.addEventListener("click", () => void this._act(action, entity));
        actions.append(button);
      }
      row.append(info, actions);
      return row;
    });
    root.querySelector("#configured-lists").replaceChildren(...rows);
    const carrefour = settings.stores?.carrefour?.enabled === true;
    root.querySelector("#carrefour-enabled").checked = carrefour;
    root.querySelector("#carrefour-enabled").disabled = locked;
    root.querySelector("#carrefour-sale-point").disabled = locked;
    root.querySelector("#save-carrefour").disabled = locked;
    root.querySelector("#carrefour-config-error").textContent = this._error || "";
    root.querySelector("#carrefour-config-error").hidden = !this._error;
    root.querySelector("#alcampo-enabled").checked = settings.stores?.alcampo?.enabled === true;
    root.querySelector("#alcampo-enabled").disabled = locked;
    root.querySelector("#save-alcampo").disabled = locked;
    root.querySelector("#alcampo-region").disabled = locked;
    root.querySelector("#lidl-enabled").checked = this._lidlEnableDraft ?? (settings.stores?.lidl?.enabled === true);
    root.querySelector("#lidl-enabled").disabled = locked;
    root.querySelector("#configure-lidl").disabled = !settings.loaded || settings.loading || Boolean(this._busy);
    root.querySelector("#lidl-region").disabled = locked;
    root.querySelector("#save-lidl").disabled = locked;
    root.querySelector("#lidl-config-error").textContent = this._error || "";
    root.querySelector("#lidl-config-error").hidden = !this._error;
    root.querySelector("#alcampo-error").textContent = this._error || "";
    root.querySelector("#alcampo-error").hidden = !this._error;
    root.querySelector("#save-price-update-time").disabled = locked;
    root.querySelector("#price-update-time").disabled = locked;
    root.querySelector("#price-schedule-error").textContent = this._error || "";
    root.querySelector("#price-schedule-error").hidden = !this._error;
    if(!root.querySelector("#price-schedule-dialog").open)root.querySelector("#price-update-time").value = settings.priceUpdateTime ?? "01:00";
    root.querySelector("#settings-empty").hidden = settings.entities.length > 0 || settings.loading;
    this._renderStore();
    const form = root.querySelector("#appearance-form");
    if (!this._appearanceDirty && !this._busy) this._fillAppearance(settings.appearance);
    // Home Assistant's scoped registry does not implement form.elements iteration.
    for (const control of form.querySelectorAll("input, select, textarea, button")) control.disabled = locked;
  }

  _renderStore() {
    const { settings, hass } = this._data;
    const root = this.shadowRoot;
    const store = settings.stores?.mercadona ?? {};
    const enabled = root.querySelector("#mercadona-enabled");
    const postal = root.querySelector("#mercadona-postal");
    if (!this._storeDirty && !this._busy) {
      enabled.checked = this._storeEnableDraft ?? (store.enabled === true);
      postal.value = store.postal_code ?? "";
    }
    const locked = hass?.user?.is_admin !== true || !settings.loaded || settings.loading || this._busy;
    enabled.disabled = locked;
    postal.disabled = locked;
    root.querySelector("#configure-mercadona").disabled = !settings.loaded || settings.loading || this._busy;
    root.querySelector("#store-dialog-error").textContent = this._error || "";
    root.querySelector("#store-dialog-error").hidden = !this._error;
    const save = root.querySelector("#save-store");
    save.disabled = locked;
    save.textContent = this._busy ? "Guardando…" : "Comprobar y guardar";
    root.querySelector("#mercadona-warehouse").textContent = store.warehouse
      ? `Configuración guardada: ${store.postal_code} · Almacén: ${store.warehouse}${store.enabled ? "" : " · Deshabilitada"}`
      : "Todavía no se ha configurado un almacén.";
    this._renderStoreProducts();
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
    const preparing=this._pricesRefreshing || this._manualQueued > 0 && !total;
    const empty=!preparing && !state?.running && !this._manualQueued;
    bar.max=total||1;
    if(preparing)bar.removeAttribute("value");else bar.value=empty?0:processed;
    root.querySelector("#prices-progress-percentage").textContent=preparing?"…":`${total&&!empty?Math.round(processed/total*100):0} %`;
    const names={mercadona:"Mercadona",carrefour:"Carrefour",alcampo:"Alcampo",lidl:"Lidl"};
    const errors=[...(this._refreshStartErrors??[]),...Object.entries(state?.errors??{}).filter(([store])=>this._data.settings.stores?.[store]?.enabled).map(([store,error])=>`${names[store]??store}: ${error}`)];
    const errorBox=root.querySelector("#stores-refresh-error");errorBox.textContent=[...new Set(errors)].join(" ");errorBox.hidden=!errors.length;
    root.querySelector("#prices-progress-status").textContent=preparing?"Preparando actualización…":empty?(errors.length?"No se ha podido iniciar la revisión.":"No hay productos vinculados pendientes en tus listas."):`${processed} de ${total} referencias procesadas${state?.running?"":" · Revisión finalizada"}`;
    const seconds=Number.isFinite(state?.estimated_seconds)?Math.max(0,Math.ceil(state.estimated_seconds-(Date.now()-(this._priceProgressReceivedAt??Date.now()))/1000)):null;
    root.querySelector("#prices-progress-time").textContent=preparing?"Calculando tiempo restante…":!state?.running?"":seconds===null?"Calculando tiempo restante…":seconds>0?`Tiempo estimado restante: ${Math.floor(seconds/60)} min ${seconds%60} s`:"Actualización en curso…";
  }

  async _savePriceSchedule() {
    if(this._busy || this._data.hass?.user?.is_admin!==true)return;
    const connection=this._data.hass.connection, value=this.shadowRoot.querySelector("#price-update-time").value;
    await this._saveRetailSettings(()=>this._data.settings.savePriceSchedule(value));
    if(this.isConnected && this._data.hass.connection===connection && !this._error)this.shadowRoot.querySelector("#price-schedule-dialog").close();
  }

  async _refreshPricesNow() {
    if (this._pricesRefreshing || this._data.hass?.user?.is_admin !== true) return;
    const hass = this._data.hass;
    const stores = ["mercadona","carrefour","alcampo","lidl"].filter(store=>this._data.settings.stores?.[store]?.enabled);
    if (!stores.length) return;
    const errorBox = this.shadowRoot.querySelector("#stores-refresh-error");
    errorBox.textContent = ""; errorBox.hidden = true;
    this._refreshStartErrors=[]; this._manualQueued=null;
    const dialog=this.shadowRoot.querySelector("#prices-progress-dialog");
    if(!dialog.open)dialog.showModal();
    clearInterval(this._pricesProgressTimer);
    this._pricesProgressTimer=setInterval(()=>this._renderGlobalPriceProgress(),1000);
    this._pricesRefreshing = true; this._render();
    try {
      const results = await Promise.allSettled(stores.map(async store=>hass.callWS({type:"improved_shopping_list/settings/refresh_prices",store})));
      if (!this.isConnected || this._data.hass.connection !== hass.connection) return;
      const names = {mercadona:"Mercadona",carrefour:"Carrefour",alcampo:"Alcampo",lidl:"Lidl"};
      const errors = results.flatMap((result,index)=>result.status === "rejected" ? [`${names[stores[index]]}: ${result.reason?.message ?? "No se pudo iniciar la actualización."}`] : []);
      this._refreshStartErrors=errors;
      this._manualQueued=results.reduce((count,result)=>count+(result.status==="fulfilled"?Math.max(0,Number(result.value.queued)||0):0),0);
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

  _switchLidlView(view) {
    for(const name of ["products","config"]){
      this.shadowRoot.querySelector(`#lidl-${name}-view`).hidden=name!==view;
      this.shadowRoot.querySelector(`#lidl-${name}-tab`).setAttribute("aria-pressed",String(name===view));
    }
  }

  _openLidl(view) {
    this._error="";
    this.shadowRoot.querySelector("#lidl-region").value=this._data.settings.stores?.lidl?.region_id??"";
    this._switchLidlView(view);this._render();
    this.shadowRoot.querySelector("#lidl-dialog").showModal();
    void this._loadLidlData();
  }

  async _loadLidlData() {
    const root=this.shadowRoot, generation=this._lidlGeneration=(this._lidlGeneration||0)+1;
    const connection=this._data.hass.connection,region=this._data.settings.stores?.lidl?.region_id??"";
    const current=()=>this.isConnected&&root.querySelector("#lidl-dialog").open&&generation===this._lidlGeneration&&connection===this._data.hass.connection;
    root.querySelector("#lidl-status").textContent="Cargando precios guardados…";
    const results=await Promise.allSettled([
      this._data.hass.callWS({type:"improved_shopping_list/settings/lidl_regions"}),
      this._data.hass.callWS({type:"improved_shopping_list/catalog/store_prices",store:"lidl"})]);
    if(!current())return;
    const select=root.querySelector("#lidl-region"),selected=select.value||region,regions=results[0];
    if(regions.status==="fulfilled"){
      select.replaceChildren(new Option("Selecciona una región",""),...regions.value.regions.sort((a,b)=>a.name.localeCompare(b.name,"es")).map(item=>new Option(item.name,item.id)));
      select.value=selected;
    }
    const prices=results[1],error=root.querySelector("#lidl-products-error");
    const message=prices.status==="rejected"?prices.reason?.message:prices.value.error;
    error.textContent=message??"";error.hidden=!error.textContent;
    if(regions.status==="rejected"){
      const alert=root.querySelector("#lidl-config-error");alert.textContent="No se pudieron cargar las regiones de Lidl.";alert.hidden=false;
    }
    if(prices.status==="fulfilled"&&region===(this._data.settings.stores?.lidl?.region_id??"")){
      root.querySelector("#lidl-products").replaceChildren(...prices.value.products.map(product=>{
        const row=document.createElement("div");row.className="store-product";
        const info=document.createElement("div");info.className="store-product-info";
        const link=document.createElement("a");link.textContent=product.name||product.store_name;link.href=product.url;link.target="_blank";link.rel="noopener noreferrer";
        const details=document.createElement("p");details.textContent=`ID: ${product.reference_id} · ${product.region_name||"Lidl"}${product.packaging?" · "+product.packaging:""}`;
        const date=document.createElement("p");date.textContent=`Último precio: ${new Date(product.checked_at*1000).toLocaleString("es-ES")}${product.expired?" · Oferta finalizada":""}`;
        const price=document.createElement("strong");price.textContent=new Intl.NumberFormat("es-ES",{style:"currency",currency:product.currency}).format(Number(product.price));
        info.append(link,details,date);row.append(info,price);return row;
      }));
    }
    root.querySelector("#lidl-status").textContent=`${root.querySelector("#lidl-products").childElementCount} precios guardados`;
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

  async _saveStore(enabled, verify) {
    if (this._busy || this._data?.hass?.user?.is_admin !== true) return;
    const root = this.shadowRoot;
    const postal = verify ? root.querySelector("#mercadona-postal").value.trim() : this._data.settings.stores?.mercadona?.postal_code ?? "";
    this._busy = true;
    this._error = this._notice = "";
    this._render();
    try {
      await this._data.settings.saveStore(enabled, postal, verify);
      this._storeEnableDraft = undefined;
      this._storeDirty = false;
    } catch (error) { this._error = error.message ?? "No se ha podido configurar Mercadona."; }
    finally { this._busy = false; this._render(); }
  }

  _openStore(view) {
    const root = this.shadowRoot;
    this._error = ""; this._storeDirty = false;
    this._renderStore();
    root.querySelector("#store-dialog").showModal();
    this._switchStoreView(view);
  }

  _switchStoreView(view) {
    const root = this.shadowRoot;
    for (const section of ["products", "configuration"]) {
      root.querySelector(`#store-${section}-view`).hidden = view !== section;
      root.querySelector(`#store-view-${section}`).setAttribute("aria-pressed", String(view === section));
    }
    if (view === "products") void this._loadStoreProducts(false);
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
    const completed = this.shadowRoot.querySelector("#completed-appearance-preview");
    completed.style.background = `linear-gradient(${appearance.completed_gradient_start},${appearance.completed_gradient_end})`;
    completed.style.color = gradientTextColor(appearance.completed_gradient_start, appearance.completed_gradient_end);
  }

  async _exportCommunity() {
    if (this._busy || !this._data?.hass?.user?.is_admin) return;
    this._busy = true;
    this._error = this._notice = "";
    this._render();
    let downloadUrl;
    try {
      const result = await this._data.hass.callWS({type:"improved_shopping_list/community/export"});
      const bytes = Uint8Array.from(atob(result.data), character => character.charCodeAt(0));
      downloadUrl = URL.createObjectURL(new Blob([bytes], {type:"application/zip"}));
      const anchor = document.createElement("a");
      anchor.href = downloadUrl;
      anchor.download = "improved-shopping-list-icons.zip";
      this.shadowRoot.append(anchor);
      anchor.click();
      anchor.remove();
      this._notice = `Exportados ${result.entries} registros y ${result.images} imágenes.${result.skipped ? ` No se pudieron incluir ${result.skipped} referencias locales.` : ""}`;
    } catch (error) { this._error = error.message ?? "No se ha podido exportar el diccionario."; }
    finally {
      if (downloadUrl) setTimeout(() => URL.revokeObjectURL(downloadUrl), 60000);
      this._busy = false;
      this._render();
    }
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
