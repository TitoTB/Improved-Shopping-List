import { installDialogCloseButtons } from "./dialog-controls.js?v=0.12.0";
import { CatalogSession } from "./catalog-client.js?v=0.12.0";
import { matchCatalogProducts } from "./product-matching.js?v=0.12.0";
import "./category-panel.js?v=0.12.0";
import "./icon-picker.js?v=0.12.0";
import { productNameKey } from "./product-names.js?v=0.12.0";
export { productNameKey };

export const normalizedName = value => String(value ?? "").normalize("NFKC").trim().replace(/\s+/g, " ").toLocaleLowerCase("es");

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function iconButton(mdi, label, className = "") {
  const button = element("button", className);
  button.type = "button";
  button.title = label;
  button.setAttribute("aria-label", label);
  const icon = element("ha-icon");
  icon.setAttribute("icon", mdi);
  icon.setAttribute("aria-hidden", "true");
  button.append(icon);
  return button;
}

export function imageSource(value) {
  if (!value) return "";
  try {
    const url = new URL(value, location.origin);
    return ["http:", "https:"].includes(url.protocol) ? url.href : "";
  } catch { return ""; }
}

class ImprovedShoppingCatalog extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._catalog = new CatalogSession(() => this._hass, () => this._render());
    this._canAdd = false;
    this._notice = "";
    this._view = "products";
    this._pendingNames = new Set();
    this._listItems = [];
  }

  set hass(value) {
    const previous = this._hass?.connection;
    this._hass = value;
    if (this._built) this.shadowRoot.querySelector("isl-icon-picker").hass = value;
    if (previous && previous !== value.connection) this._started = false;
    this._start();
  }

  set canAdd(value) {
    if (this._canAdd === value) return;
    this._canAdd = value;
    this._renderProducts();
  }

  set listName(value) {
    this._listName = value;
    this._renderSuggestions();
  }

  set readerData(value) {
    this._readers = value;
    this._renderReaderActions();
    this._renderSuggestions();
  }

  showSuggestions() { this._switchView("suggestions"); }
  set listEntity(value) { this._listEntity = value; }

  set listItems(value) {
    const signature = JSON.stringify([this._listEntity, (value ?? []).map(item => [item.uid,item.summary,item.status])]);
    if (signature === this._listSignature) return;
    this._listSignature = signature;
    this._listItems = value ?? [];
    this._renderSuggestions();
  }

  set pendingItems(value) {
    const names = new Set((value ?? []).map(item => productNameKey(item.summary)).filter(Boolean));
    const signature = JSON.stringify([...names].sort());
    if (signature === this._pendingSignature) return;
    this._pendingSignature = signature;
    this._pendingNames = names;
    this._renderProducts();
  }

  connectedCallback() {
    if (!this._built) this._build();
    this._start();
  }

  disconnectedCallback() {
    this._catalog.stop();
    this._started = false;
    this.shadowRoot.querySelectorAll("dialog").forEach(dialog => dialog.close());
    this.shadowRoot.querySelector("isl-icon-picker")?.close();
  }

  _start() {
    if (!this.isConnected || !this._built || !this._hass || this._started) return;
    this._started = true;
    void this._catalog.start();
  }

  _build() {
    this.shadowRoot.innerHTML = `
      <style>
        :host { display:block; color:var(--primary-text-color,#20352d); }
        :host([hidden]),[hidden] { display:none !important; }
        * { box-sizing:border-box; }
        button,input,select,textarea { font:inherit; }
        button { cursor:pointer; }
        button:disabled { opacity:.5; cursor:default; }
        button:focus-visible,input:focus-visible,select:focus-visible,textarea:focus-visible { outline:3px solid var(--primary-color,#267052); outline-offset:3px; }
        .heading { display:flex; align-items:center; justify-content:space-between; gap:16px; margin:28px 0 12px; }
        .catalog-toolbar { display:flex; align-items:center; gap:12px; margin:18px 0; }
        .catalog-tools { display:flex; align-items:center; gap:8px; flex-shrink:0; margin-left:auto; }
        .catalog-tabs { display:flex; flex:1; min-width:0; gap:8px; overflow-x:auto; scrollbar-width:thin; }
        .catalog-tabs button { display:inline-flex; align-items:center; gap:6px; flex-shrink:0; white-space:nowrap; }
        .catalog-tabs ha-icon { --mdc-icon-size:20px; width:20px; height:20px; flex:none; }
        .suggestions { display:grid; gap:12px; }
        .suggestion-groups { display:grid; gap:16px; }
        .suggestion-group { border:1px solid var(--divider-color,#dfe7e1); border-radius:14px; background:var(--card-background-color,#fff); min-width:0; }
        .suggestion-group summary { padding:16px; cursor:pointer; font-weight:650; line-height:1.5; overflow-wrap:anywhere; }
        .suggestion-group summary:focus-visible { outline:3px solid var(--primary-color,#267052); outline-offset:3px; border-radius:14px; }
        .suggestion-count { display:inline-block; margin-left:8px; padding:2px 8px; border-radius:20px; font-size:12px; font-weight:500; background:var(--secondary-background-color,#edf4ee); }
        .suggestion-content { padding:0 14px 14px; }
        .suggestion { display:flex; align-items:center; gap:16px; padding:16px; border:1px solid var(--divider-color,#dfe7e1); border-radius:14px; background:var(--card-background-color,#fff); }
        .suggestion h2 { flex:1; font-size:17px; overflow-wrap:anywhere; min-width:0; }
        .suggestion .actions { margin:0; flex-shrink:0; }
        .suggestion .actions button { flex:0 0 40px; width:40px; min-height:40px; padding:8px; }
        .suggestion .actions .danger { background:#b3261e; color:#fff; border:0; }
        .suggestion .actions .link { background:#1976d2; color:#fff; border:0; }
        .link-results { max-height:260px; overflow-y:auto; border:1px solid var(--divider-color,#dfe7e1); border-radius:9px; margin-top:6px; }
        .link-results button { display:block; width:100%; text-align:left; border:0; border-radius:0; overflow-wrap:anywhere; }
        .link-results button:hover,.link-results [aria-selected=true] { background:var(--secondary-background-color,#edf4ee); }
        .link-empty { font-size:13px; margin:8px 0 0; }
        @media(max-width:650px) { .suggestion { flex-wrap:wrap; } .suggestion .actions { margin-left:auto; } }
        .catalog-tabs button[aria-pressed=true] { background:var(--secondary-background-color,#edf4ee); font-weight:650; }
        h1 { font-size:32px; letter-spacing:-.03em; margin:0; }
        h2 { font-size:23px; margin:0; }
        .helper { color:var(--secondary-text-color,#63766b); font-size:13px; line-height:1.6; margin:8px 0 18px; }
        button { min-height:44px; padding:10px 14px; border:1px solid var(--divider-color,#dfe7e1); border-radius:10px; background:transparent; color:inherit; }
        .primary { background:#267052; color:#fff; border:0; font-weight:650; }
        .filters { display:grid; grid-template-columns:2fr 1fr; gap:12px; margin:24px 0 14px; align-items:end; }
        #new-product,#new-catalog-category,#catalog-refresh { display:grid; place-items:center; flex:0 0 44px; width:44px; height:44px; padding:0; }
        #new-product ha-icon,#new-catalog-category ha-icon { --mdc-icon-size:24px; }
        .product-category-controls { display:flex; align-items:end; gap:8px; }
        .product-category-controls select { flex:1; min-width:0; }
        #add-product-category { display:grid; place-items:center; flex:0 0 46px; width:46px; height:46px; padding:0; }
        #add-product-category ha-icon { --mdc-icon-size:22px; }
        label { font-size:13px; font-weight:600; display:block; }
        input,select,textarea { display:block; min-height:46px; width:100%; margin-top:7px; padding:10px 12px; color:inherit; background:var(--card-background-color,#fff); border:1px solid var(--divider-color,#dfe7e1); border-radius:9px; min-width:0; }
        textarea { resize:vertical; min-height:76px; }
        .count { color:var(--secondary-text-color,#63766b); font-size:12px; margin:12px 0; }
        .grid { display:grid; grid-template-columns:repeat(var(--isl-columns,3),minmax(0,1fr)); gap:16px; }
        .product { position:relative; align-self:start; width:100%; aspect-ratio:1 / 1; min-width:0; min-height:0; padding:0; overflow:hidden; background:var(--card-background-color,#fff); border:1px solid var(--divider-color,#dfe7e1); border-radius:16px; text-align:center; container-type:inline-size; }
        .product.in-list { background:linear-gradient(var(--isl-gradient-start,#ee524f),var(--isl-gradient-end,#b52a27)); border-color:var(--isl-gradient-end,#b52a27); }
        .product.in-list,.product.in-list .placeholder,.product.in-list .subtitle,.product.in-list button,.product.in-list ha-icon { color:#fff; }
        .product-top { position:absolute; inset:0; display:flex; flex-direction:column; gap:clamp(2px,2.5cqi,12px); align-items:center; justify-content:center; padding:clamp(4px,5cqi,24px); pointer-events:none; }
        .product-media { display:grid; place-items:center; width:clamp(14px,36cqi,192px); max-width:100%; min-height:0; flex-shrink:1; aspect-ratio:1; }
        .product-name { min-width:0; width:100%; max-width:100%; flex-shrink:0; }
        .image { width:100%; max-width:100%; height:auto; max-height:100%; aspect-ratio:1; object-fit:contain; border-radius:10px; }
        .placeholder { display:grid; place-items:center; color:var(--secondary-text-color,#63766b); }
        .placeholder ha-icon { --mdc-icon-size:clamp(14px,30cqi,160px); width:var(--mdc-icon-size); height:var(--mdc-icon-size); }
        .product .add-product { position:absolute; z-index:1; inset:0; width:100%; height:100%; min-height:0; margin:0; padding:0; border:0; border-radius:inherit; background:transparent; }
        .product .add-product:focus-visible { outline-offset:-3px; }
        .product-controls { position:absolute; z-index:2; top:clamp(3px,4cqi,12px); right:clamp(3px,4cqi,12px); display:flex; gap:clamp(2px,2cqi,6px); }
        .product-controls button { --isl-control-size:clamp(18px,13cqi,32px); display:flex; align-items:center; justify-content:center; appearance:none; -webkit-appearance:none; flex:none; width:var(--isl-control-size); min-width:var(--isl-control-size); max-width:var(--isl-control-size); height:var(--isl-control-size); min-height:var(--isl-control-size); max-height:var(--isl-control-size); aspect-ratio:1; margin:0; padding:0; border:0; border-radius:50%; line-height:0; color:#fff; box-shadow:0 2px 6px rgba(0,0,0,.22); }
        .product-controls .edit-product { background:#f9a825; }
        .product-controls .delete-product { background:#000; }
        .product-controls button:focus-visible { outline-offset:1px; }
        .product-controls ha-icon { --mdc-icon-size:clamp(12px,8cqi,20px); display:flex; align-items:center; justify-content:center; flex:none; width:var(--mdc-icon-size); height:var(--mdc-icon-size); margin:0; padding:0; }
        /* Match List's outer li width, including the Catalog card's two border pixels. */
        .title { display:-webkit-box; -webkit-box-orient:vertical; -webkit-line-clamp:3; overflow:hidden; font-size:clamp(12px,calc((100cqi + 2px) / 10),32px); line-height:1.2; font-weight:650; margin:0; overflow-wrap:anywhere; text-align:center; }
        .subtitle { color:var(--secondary-text-color,#63766b); font-size:12px; margin:4px 0 0; overflow-wrap:anywhere; }
        .tags { display:flex; flex-wrap:wrap; justify-content:center; gap:4px; max-width:100%; max-height:15cqi; overflow:hidden; flex-shrink:0; }
        .tag { padding:2px 5px; border-radius:20px; font-size:clamp(7px,4cqi,11px); background:var(--secondary-background-color,#edf4ee); max-width:100%; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
        .actions { display:flex; gap:8px; margin-top:auto; }
        .actions button { display:inline-flex; align-items:center; justify-content:center; gap:7px; }
        .actions ha-icon { --mdc-icon-size:20px; }
        .actions .primary { flex:1; }
        @container(max-width:140px) { .product .tags { display:none; } .product .title { -webkit-line-clamp:2; } }
        .notice { font-size:13px; line-height:1.6; padding:12px 14px; background:var(--secondary-background-color,#edf4ee); border-radius:10px; margin:14px 0; }
        .error { color:var(--error-color,#bd3636); border:1px solid var(--error-color,#bd3636); }
        .empty { text-align:center; padding:38px 16px; color:var(--secondary-text-color,#63766b); line-height:1.7; border:1px dashed var(--divider-color,#dfe7e1); border-radius:16px; }
        dialog { color:inherit; background:var(--card-background-color,#fff); width:min(640px,calc(100vw - 28px)); max-height:calc(100dvh - 28px); border:1px solid var(--divider-color,#dfe7e1); border-radius:18px; padding:24px; }
        dialog::backdrop { background:rgba(0,0,0,.4); }
        .dialog-heading { display:flex; align-items:center; justify-content:space-between; gap:12px; }
        .product-views { display:flex; flex-wrap:wrap; gap:8px; margin-top:18px; }
        .product-views button { display:inline-flex; align-items:center; justify-content:center; gap:6px; flex:1 1 130px; min-width:0; font-size:13px; padding:10px 8px; }
        .product-views ha-icon { display:flex; align-items:center; justify-content:center; flex:none; width:18px; height:18px; --mdc-icon-size:18px; line-height:0; }
        .product-views [aria-pressed=true] { background:var(--secondary-background-color,#edf4ee); font-weight:650; }
        .recurrence-controls { display:flex; align-items:center; flex-wrap:wrap; gap:8px; margin-top:12px; }
        .recurrence-controls label { display:flex; align-items:center; gap:8px; }
        .recurrence-controls input[type=checkbox] { width:20px; min-height:20px; margin:0; padding:0; accent-color:var(--primary-color,#267052); }
        .recurrence-controls input[type=number] { width:88px; margin:0; }
        .nutriscore-item { display:flex; align-items:center; flex-wrap:wrap; gap:12px; padding:12px 0; border-top:1px solid var(--divider-color,#dfe7e1); }
        .nutriscore-item img { width:130px; height:auto; flex:none; }
        .nutriscore-item p { margin:4px 0; overflow-wrap:anywhere; }
        .nutriscore-item a { color:var(--primary-color,#267052); }
        .fields { display:grid; grid-template-columns:1fr 1fr; gap:16px; margin:22px 0; }
        .wide { grid-column:1/-1; }
        .form-actions { display:flex; justify-content:flex-end; gap:10px; margin-top:22px; }
        @media(max-width:650px) { .filters { grid-template-columns:1fr; } .grid { grid-template-columns:repeat(var(--isl-mobile-columns,1),minmax(0,1fr)); } .heading { gap:10px; flex-wrap:wrap; } h1 { font-size:28px; } dialog { padding:20px; } }
        @media(max-width:650px) { .catalog-toolbar { gap:6px; } .catalog-tabs { gap:4px; } .catalog-tabs button { gap:4px; min-width:36px; justify-content:center; padding:10px 6px; font-size:13px; } .catalog-tabs button[aria-pressed=false] .tab-label { display:none; } }
        @media(max-width:390px) { .fields { grid-template-columns:1fr; } .heading { align-items:flex-start; } .catalog-tabs { gap:3px; } .catalog-tabs button { min-width:32px; padding-inline:4px; } .catalog-tools { gap:4px; } }
      </style>
      <div class="heading"><h1>Catálogo</h1></div>
      <div class="catalog-toolbar">
        <nav class="catalog-tabs" aria-label="Vistas del catálogo"><button id="view-products" aria-label="Productos" aria-pressed="true"><ha-icon icon="mdi:view-grid" aria-hidden="true"></ha-icon><span class="tab-label">Productos</span></button><button id="view-categories" aria-label="Categorías" aria-pressed="false"><ha-icon icon="mdi:label" aria-hidden="true"></ha-icon><span class="tab-label">Categorías</span></button><button id="view-suggestions" aria-label="Sugerencias" aria-pressed="false"><ha-icon icon="mdi:creation" aria-hidden="true"></ha-icon><span class="tab-label">Sugerencias</span></button></nav>
        <div class="catalog-tools"><button id="new-product" class="primary" type="button" aria-label="Nuevo producto" title="Nuevo producto"><ha-icon icon="mdi:plus-thick"></ha-icon></button><button id="new-catalog-category" class="primary" type="button" aria-label="Nueva categoría" title="Nueva categoría" hidden><ha-icon icon="mdi:plus-thick"></ha-icon></button><button id="catalog-refresh" type="button" aria-label="Actualizar catálogo" title="Actualizar catálogo"><ha-icon icon="mdi:refresh"></ha-icon></button></div>
      </div>
      <div id="catalog-error" class="notice error" role="alert" hidden></div>
      <div id="catalog-status" class="notice" role="status" hidden></div>
      <section id="products-view">
      <div class="filters">
        <label class="search">Buscar productos<input id="catalog-search" type="search" placeholder="Nombre, código o etiqueta"></label>
        <label>Categoría<select id="category-filter"><option value="">Todas</option></select></label>
      </div>
      <p id="catalog-count" class="count" aria-live="polite"></p>
      <div id="catalog-grid" class="grid"></div>
      <p id="catalog-empty" class="empty" hidden></p>
      </section>
      <isl-categories id="catalog-categories" embedded hidden></isl-categories>
      <section id="suggestions-view" hidden>
        <p id="suggestions-source" class="helper"></p>
        <div id="suggestions-error" class="notice error" role="alert" hidden></div>
        <div id="suggestions-list" class="suggestion-groups">
          <details id="list-suggestions-group" class="suggestion-group">
            <summary id="list-suggestions-summary">Productos añadidos a la lista<span id="list-suggestions-count" class="suggestion-count">0</span></summary>
            <div class="suggestion-content"><div id="list-suggestions" class="suggestions"></div><p id="list-suggestions-empty" class="helper" hidden>No hay productos de la lista pendientes de incorporar al catálogo.</p></div>
          </details>
          <details id="scan-suggestions-group" class="suggestion-group">
            <summary id="scan-suggestions-summary">Productos escaneados<span id="scan-suggestions-count" class="suggestion-count">0</span></summary>
            <div class="suggestion-content"><div id="scan-suggestions" class="suggestions"></div><p id="scan-suggestions-empty" class="helper" hidden>No hay códigos escaneados pendientes de identificar.</p></div>
          </details>
        </div>
        <p id="suggestions-empty" class="empty" hidden>No hay sugerencias nuevas en esta lista.</p>
      </section>
      <dialog aria-labelledby="product-dialog-title">
        <form id="product-form">
          <div class="dialog-heading"><h2 id="product-dialog-title">Nuevo producto</h2></div>
          <p class="helper">Solo necesitas un nombre para empezar. Puedes completar el resto más adelante.</p>
          <div id="product-error" class="notice error" role="alert" hidden></div>
          <nav class="product-views" aria-label="Vistas de la ficha del producto">
            <button type="button" data-product-view="main" aria-pressed="true" aria-controls="product-main"><ha-icon icon="mdi:package-variant-closed" aria-hidden="true"></ha-icon>Características</button>
            <button type="button" data-product-view="additional" aria-pressed="false" aria-controls="product-additional"><ha-icon icon="mdi:information-outline" aria-hidden="true"></ha-icon>Información adicional</button>
            <button type="button" data-product-view="automation" aria-pressed="false" aria-controls="product-automation"><ha-icon icon="mdi:robot-outline" aria-hidden="true"></ha-icon>Automatización</button>
          </nav>
          <section id="product-main" class="fields" aria-label="Características">
            <label class="wide">Nombre del producto<input name="name" required maxlength="160" placeholder="Por ejemplo, Cacao"></label>
            <isl-icon-picker class="wide"></isl-icon-picker>
            <label class="wide">URL Imagen/Icono<input name="image_url" maxlength="2048" placeholder="https://… o /local/producto.png"></label>
            <div class="wide"><label for="product-category">Categoría</label><div class="product-category-controls"><select id="product-category" name="category"><option value="">Sin categoría</option></select><button id="add-product-category" type="button" aria-label="Nueva categoría" title="Nueva categoría"><ha-icon icon="mdi:plus-thick"></ha-icon></button></div></div>
          </section>
          <section id="product-additional" class="fields" aria-label="Información adicional" hidden>
            <label>Precio orientativo<input name="price" type="number" min="0" max="1000000" step="0.01" placeholder="Sin precio"></label>
            <label>Moneda<select name="currency"><option value="EUR">EUR · Euro</option><option value="USD">USD · Dólar</option><option value="GBP">GBP · Libra</option></select></label>
            <div class="wide"><h3>Vinculaciones con tiendas</h3><div id="product-store-links"></div><div style="display:grid;grid-template-columns:minmax(0,1fr) 44px;gap:8px"><select id="product-link-store" aria-label="Tienda del producto" style="grid-column:1/-1"></select><input id="product-link-value" aria-label="Enlace o ID del producto" maxlength="2048" placeholder="Enlace o ID del producto" style="min-width:0"><button id="add-product-store-link" type="button" aria-label="Añadir vinculación"><ha-icon icon="mdi:plus-thick" aria-hidden="true"></ha-icon></button></div><p class="helper">Los precios se revisan de madrugada cuando el producto está pendiente de comprar. Se conserva el último precio conocido.</p></div>
            <div id="product-nutriscore" class="wide" hidden><h3>Nutri-Score</h3><div id="nutriscore-results"></div></div>
            <div id="product-store-prices" class="wide" hidden><h3>Precios de tiendas</h3><div id="store-price-results"></div></div>
          </section>
          <section id="product-automation" class="fields" aria-label="Automatización" hidden>
            <label class="wide">Código de barras<input name="barcode" type="text" maxlength="1024"></label>
            <label class="wide">Otros códigos de barras o QR<textarea name="barcodes" maxlength="52000" placeholder="Un código por línea"></textarea></label>
            <label class="wide">Etiquetas NFC<textarea name="nfc_tags" maxlength="52000" placeholder="Un identificador por línea"></textarea></label>
            <div class="wide"><h3>Acciones de los lectores</h3><div id="product-reader-actions"></div><p class="helper">La acción se aplica solo al reconocer este producto. Las acciones de stock quedan guardadas para cuando esté disponible el inventario.</p></div>
            <div class="wide" id="product-recurrence"><h3>Recurrencia</h3><div class="recurrence-controls"><label><input name="recurrence_enabled" type="checkbox">Comprar cada</label><input name="recurrence_days" type="number" min="1" max="3650" step="1" value="7" aria-label="Días de recurrencia" disabled required><span>días</span></div><p class="helper">Se añadirá a la lista principal sin duplicar productos pendientes. El periodo empieza al activar la recurrencia o cambiar los días.</p></div>
          </section>
          <div class="form-actions"><button id="cancel-product" type="button">Cancelar</button><button id="save-product" class="primary" type="submit">Guardar producto</button></div>
        </form>
        <isl-categories id="product-category-editor" editor-only></isl-categories>
      </dialog>
      <dialog id="delete-product-dialog" aria-labelledby="delete-product-title">
        <h2 id="delete-product-title">Eliminar producto</h2><p id="delete-product-description"></p>
        <div id="delete-product-error" class="notice error" role="alert" hidden></div>
        <div class="form-actions"><button id="cancel-delete-product" type="button">Cancelar</button><button id="confirm-delete-product" type="button" style="background:#000;color:#fff;border:0">Eliminar producto</button></div>
      </dialog>
      <dialog id="link-code-dialog" aria-labelledby="link-code-title">
        <h2 id="link-code-title">Asignar código a un producto</h2><p id="link-code-description" class="helper"></p>
        <div id="link-code-error" class="notice error" role="alert" hidden></div>
        <div id="link-code-search"></div><p id="link-code-selection" class="helper" role="status"></p>
        <div class="form-actions"><button id="cancel-link-code" type="button">Cancelar</button><button id="confirm-link-code" class="primary" type="button" disabled>Asignar</button></div>
      </dialog>`;
    this._built = true;
    const root = this.shadowRoot;
    installDialogCloseButtons(root);
    root.querySelector("#add-product-store-link").addEventListener("click", () => {
      const store = root.querySelector("#product-link-store").value, value = root.querySelector("#product-link-value").value.trim();
      if (!store || !value) return;
      this._storeLinks[store] = value;
      root.querySelector("#product-link-value").value = "";
      this._renderStoreLinks();
      void this._loadRetailPrices();
    });
    for (const button of root.querySelectorAll("[data-product-view]")) button.addEventListener("click", () => this._switchProductView(button.dataset.productView));
    root.querySelector("#product-form").addEventListener("invalid", event => {
      const panel = event.target.closest("section[id^=product-]");
      if (panel) this._switchProductView(panel.id.slice("product-".length));
    }, true);
    const iconPicker = root.querySelector("isl-icon-picker");
    iconPicker.getQuery = () => {
      const name = root.querySelector("form").elements.name.value;
      return this._editing?.name_en && productNameKey(name) === productNameKey(this._editing.name)
        ? this._editing.name_en : name;
    };
    iconPicker.getSearchOptions = () => {
      const name = root.querySelector("form").elements.name.value;
      const sameProduct = this._editing && productNameKey(name) === productNameKey(this._editing.name);
      return {translate: !sameProduct || !this._editing.name_en, ...(sameProduct ? {product_id:this._editing.id} : {})};
    };
    iconPicker.onSelect = asset => { root.querySelector("form").elements.image_url.value = asset.url; };
    iconPicker.onBusyChange = busy => { root.querySelector("#save-product").disabled = Boolean(this._saving || busy); };
    root.querySelector('[name="name"]').addEventListener("input", () => iconPicker.suggest());
    root.querySelector('[name="image_url"]').addEventListener("input", event => { iconPicker.value = event.target.value; });
    root.querySelector("dialog").addEventListener("close", () => { iconPicker.close(); this._resetNutriscores(); });
    for (const field of ["barcode", "barcodes"]) root.querySelector(`[name=${field}]`).addEventListener("input", () => this._resetNutriscores());
    root.querySelector("#cancel-link-code").addEventListener("click", () => root.querySelector("#link-code-dialog").close());
    root.querySelector("#confirm-link-code").addEventListener("click", () => void this._assignCode());
    root.querySelector("#link-code-dialog").addEventListener("cancel", event => { if (this._linkBusy) event.preventDefault(); });
    root.querySelector("#link-code-dialog").addEventListener("close", () => { if (root.querySelector("#link-code-dialog").open) return; this._linkReading = null; this._linkProductId = null; this._refreshLinkPredictions = null; });
    root.querySelector("#cancel-delete-product").addEventListener("click", () => root.querySelector("#delete-product-dialog").close());
    root.querySelector("#confirm-delete-product").addEventListener("click", () => void this._deleteProduct());
    root.querySelector("#delete-product-dialog").addEventListener("cancel", event => { if (this._deletingProduct) event.preventDefault(); });
    root.querySelector("#new-product").addEventListener("click", () => this._openProduct());
    root.querySelector("#view-products").addEventListener("click", () => this._switchView("products"));
    root.querySelector("#view-categories").addEventListener("click", () => this._switchView("categories"));
    root.querySelector("#view-suggestions").addEventListener("click", () => this._switchView("suggestions"));
    root.querySelector("isl-categories").onSave = category => this._catalog.saveCategory(category);
    root.querySelector("isl-categories").onDelete = category => this._catalog.deleteCategory(category);
    root.querySelector("isl-categories").onClose = () => root.querySelector("#new-catalog-category").focus();
    root.querySelector("#new-catalog-category").addEventListener("click", () => root.querySelector("isl-categories").create());
    const categoryEditor = root.querySelector("#product-category-editor");
    categoryEditor.onSave = async category => {
      const saved = await this._catalog.saveCategory(category);
      root.querySelector("#product-category").value = saved.name;
      return saved;
    };
    categoryEditor.onClose = () => root.querySelector("#add-product-category").focus();
    root.querySelector("#add-product-category").addEventListener("click", () => categoryEditor.create());
    root.querySelector("#catalog-refresh").addEventListener("click", () => void this._catalog.refresh());
    root.querySelector("#catalog-search").addEventListener("input", () => this._renderProducts());
    root.querySelector("#category-filter").addEventListener("change", () => this._renderProducts());
    root.querySelector('[name="recurrence_enabled"]').addEventListener("change", () => {
      root.querySelector('[name="recurrence_days"]').disabled = !root.querySelector('[name="recurrence_enabled"]').checked;
    });
    root.querySelector("#cancel-product").addEventListener("click", () => root.querySelector("dialog").close());
    root.querySelector("dialog").addEventListener("cancel", (event) => { if (this._saving) event.preventDefault(); });
    root.querySelector("#product-form").addEventListener("submit", (event) => { event.preventDefault(); void this._saveProduct(); });
    this.listName = this._listName;
    this._render();
  }

  _switchView(view) {
    this._view = view;
    const root = this.shadowRoot;
    root.querySelector("#products-view").hidden = view !== "products";
    root.querySelector("#new-product").hidden = view !== "products";
    root.querySelector("#new-catalog-category").hidden = view !== "categories";
    root.querySelector("isl-categories").hidden = view !== "categories";
    root.querySelector("#suggestions-view").hidden = view !== "suggestions";
    root.querySelector("#view-products").setAttribute("aria-pressed", String(view === "products"));
    root.querySelector("#view-categories").setAttribute("aria-pressed", String(view === "categories"));
    root.querySelector("#view-suggestions").setAttribute("aria-pressed", String(view === "suggestions"));
    this._notice = "";
    this._render();
  }

  _render() {
    if (!this._built) return;
    const root = this.shadowRoot;
    const error = root.querySelector("#catalog-error");
    error.hidden = !this._catalog.error;
    error.textContent = this._catalog.error;
    const status = root.querySelector("#catalog-status");
    status.hidden = !this._catalog.loading && (this._view === "products" || !this._notice);
    status.textContent = this._catalog.loading ? "Cargando catálogo…" : this._notice;
    root.querySelector("#catalog-refresh").disabled = this._catalog.loading;
    const categories = this._catalog.categories.map(category => category.name).sort((a, b) => a.localeCompare(b, "es"));
    this._fillFilter(root.querySelector("#category-filter"), categories);
    const categorySelect = root.querySelector("[name=category]");
    const selectedCategory = categorySelect.value;
    const options = categories.map(category => new Option(category, category));
    if (selectedCategory && !categories.includes(selectedCategory)) options.push(new Option(`${selectedCategory} · No disponible`, selectedCategory));
    categorySelect.replaceChildren(new Option("Sin categoría", ""), ...options);
    categorySelect.value = selectedCategory;
    root.querySelector("isl-categories").categories = this._catalog.categories;
    this._renderProducts();
    this._renderSuggestions();
    this.dispatchEvent(new CustomEvent("catalog-change", {
      detail: { products: this._catalog.products, categories: this._catalog.categories },
    }));
  }

  _renderSuggestions() {
    if (!this._built) return;
    const root = this.shadowRoot;
    const error = root.querySelector("#suggestions-error");
    error.hidden = !this._suggestionError;
    error.textContent = this._suggestionError ?? "";
    root.querySelector("#suggestions-source").textContent = this._listName
      ? `Productos de «${this._listName}» que todavía no están en tu catálogo y códigos desconocidos de tus lectores.`
      : "Aquí aparecerán los códigos desconocidos de tus lectores. Selecciona una lista para ver también sus productos sugeridos.";
    const excluded = new Set([
      ...this._catalog.products.map(product => productNameKey(product.name)),
      ...this._catalog.dismissedSuggestions.map(productNameKey),
    ]);
    const suggestions = [];
    for (const item of this._listItems) {
      const name = String(item.summary ?? "").trim();
      const key = productNameKey(name);
      if (!key || excluded.has(key)) continue;
      excluded.add(key);
      suggestions.push(name);
    }
    suggestions.sort((a, b) => a.localeCompare(b, "es"));
    const rows = suggestions.map(name => {
      const row = element("article", "suggestion");
      row.append(element("h2", "", name));
      const actions = element("div", "actions");
      for (const [label, mdi, action] of [["Añadir al catálogo", "mdi:plus-thick", "add"], ["Descartar", "mdi:delete", "dismiss"]]) {
        const button = iconButton(mdi, `${label}: ${name}`, action === "add" ? "primary" : "danger");
        button.disabled = Boolean(this._suggestionBusy) || this._catalog.loading || Boolean(this._catalog.error);
        button.addEventListener("click", () => void this._actOnSuggestion(name, action));
        actions.append(button);
      }
      row.append(actions);
      return row;
    });
    const pending = (this._readers?.pending ?? []).filter(item => !this._catalog.products.some(product => {
      const values = item.kind === "nfc" ? product.nfc_tags ?? [] : [product.barcode, ...(product.barcodes ?? [])];
      return values.includes(item.code);
    }));
    root.querySelector("#list-suggestions").replaceChildren(...rows);
    root.querySelector("#scan-suggestions").replaceChildren(...pending.map(item => this._codeSuggestion(item)));
    this._renderLinkDialog();
    root.querySelector("#list-suggestions-count").textContent = String(suggestions.length);
    root.querySelector("#scan-suggestions-count").textContent = String(pending.length);
    root.querySelector("#list-suggestions-empty").hidden = suggestions.length > 0 || this._catalog.loading || Boolean(this._catalog.error);
    root.querySelector("#scan-suggestions-empty").hidden = pending.length > 0 || Boolean(this._readers?.loading) || Boolean(this._readers?.error);
    root.querySelector("#suggestions-empty").hidden = suggestions.length > 0 || pending.length > 0 || this._catalog.loading || Boolean(this._catalog.error);
  }

  _codeSuggestion(item) {
    const row = element("article", "suggestion");
    row.dataset.pendingId=item.id;
    const info = element("div");
    info.style.cssText = "flex:1;min-width:0;overflow-wrap:anywhere";
    const hint = item.identification;
    const found = hint?.status === "found";
    const candidates = matchCatalogProducts(hint, this._catalog.products);
    info.append(element("h2", "", found ? hint.name : item.kind === "nfc" ? "Etiqueta NFC sin identificar" : "Código sin identificar"), element("p", "subtitle", item.code), element("p", "subtitle", item.reader_name));
    if (found) {
      const source = element("a", "subtitle", "Fuente: Open Food Facts (ODbL)");
      source.href = `https://world.openfoodfacts.org/product/${encodeURIComponent(item.code)}`;
      source.target = "_blank"; source.rel = "noopener noreferrer";
      info.append(source);
      if (candidates.length) info.append(element("p", "subtitle", `Posible coincidencia: ${candidates[0].name}`));
    } else if (hint && hint.status !== "unsupported") {
      const message = hint.status === "pending" ? "Consultando Open Food Facts…" : hint.status === "not_found" ? "Sin nombre disponible en Open Food Facts." : "Consulta no disponible. Puedes identificarlo manualmente.";
      info.append(element("p", "subtitle", message));
    }
    const actions = element("div", "actions");
    const add = iconButton("mdi:plus-thick", `Crear producto con el código ${item.code}`, "primary");
    add.addEventListener("click", () => this._openProduct(undefined, "", item));
    const link = iconButton("mdi:view-grid", `Asignar código ${item.code} a un producto del catálogo`, "link");
    link.disabled = !this._catalog.products.length || this._linkBusy;
    if (link.disabled) link.title = "Añade primero un producto al catálogo";
    link.addEventListener("click", () => this._openLinkDialog(item));
    const dismiss = iconButton("mdi:delete", `Descartar código ${item.code}`, "danger");
    dismiss.addEventListener("click", async () => {
      dismiss.disabled = true;
      try { await this._readers.dismiss(item.id); }
      catch(error) { this._suggestionError = error.message ?? "No se ha podido descartar el código."; }
      finally { this._renderSuggestions(); }
    });
    actions.append(add,link,dismiss);row.append(info,actions);return row;
  }

  _productLinkSearch(item) {
    const search = element("div", "link-search");
    const input = element("input");
    input.type = "text";
    input.placeholder = "Buscar un producto del catálogo…";
    input.autocomplete = "off";
    input.setAttribute("aria-label", `Producto para el código ${item.code}`);
    input.setAttribute("role", "combobox");
    input.setAttribute("aria-autocomplete", "list");
    const results = element("div", "link-results");
    results.id = `link-results-${item.id}`;
    results.setAttribute("role", "listbox");
    results.setAttribute("aria-label", "Productos del catálogo");
    input.setAttribute("aria-controls", results.id);
    const empty = element("p", "link-empty", "No hay productos que coincidan con la búsqueda.");
    empty.setAttribute("role", "status");
    let matches = [], active = -1;
    const close = () => {
      results.hidden = true;
      empty.hidden = true;
      input.setAttribute("aria-expanded", "false");
      input.removeAttribute("aria-activedescendant");
    };
    const choose = product => {
      input.value = product.name;
      close();
      this._linkProductId = product.id;
      this._renderLinkDialog();
    };
    const highlight = () => {
      [...results.children].forEach((option, index) => option.setAttribute("aria-selected", String(index === active)));
      if (active < 0) input.removeAttribute("aria-activedescendant");
      else {
        input.setAttribute("aria-activedescendant", results.children[active].id);
        results.children[active].scrollIntoView({block:"nearest"});
      }
    };
    const predict = (expanded = true) => {
      const query = productNameKey(input.value);
      const candidates = matchCatalogProducts(item.identification, this._catalog.products);
      const candidateIds = new Set(candidates.map(product => product.id));
      const products = [...candidates, ...this._catalog.products.filter(product => !candidateIds.has(product.id))];
      matches = products.filter(product => productNameKey(product.name).includes(query)).slice(0, 8);
      active = -1;
      results.replaceChildren(...matches.map((product, index) => {
        const option = element("button", "", `${candidateIds.has(product.id) ? "Sugerido: " : ""}${product.name}`);
        option.type = "button";
        option.id = `${results.id}-${index}`;
        option.tabIndex = -1;
        option.disabled = Boolean(this._linkBusy);
        option.setAttribute("role", "option");
        option.setAttribute("aria-selected", "false");
        option.addEventListener("pointerdown", event => event.preventDefault());
        option.addEventListener("click", () => choose(product));
        return option;
      }));
      results.hidden = !expanded || !matches.length;
      empty.hidden = !expanded || Boolean(matches.length);
      input.setAttribute("aria-expanded", String(!results.hidden));
      input.removeAttribute("aria-activedescendant");
    };
    input.addEventListener("input", () => {
      this._linkProductId = null;
      this._renderLinkDialog();
      predict();
    });
    input.addEventListener("focus", () => predict());
    input.addEventListener("blur", close);
    input.addEventListener("keydown", event => {
      if (event.key === "Escape") { event.preventDefault(); close(); }
      else if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        if (results.hidden) predict();
        if (!matches.length) return;
        active = event.key === "ArrowDown" ? (active + 1) % matches.length : (active < 0 ? matches.length - 1 : (active + matches.length - 1) % matches.length);
        highlight();
      } else if (event.key === "Enter") {
        event.preventDefault();
        if (!results.hidden && active >= 0) choose(matches[active]);
        else if (!results.hidden && matches.length === 1) choose(matches[0]);
      }
    });
    search.append(input, results, empty);
    this._refreshLinkPredictions = () => predict(input.getAttribute("aria-expanded") === "true");
    predict(false);
    return search;
  }

  _openLinkDialog(item) {
    if (this._linkBusy) return;
    const root = this.shadowRoot;
    this._linkReading = structuredClone(item);
    this._linkProductId = null;
    root.querySelector("#link-code-description").textContent = `Código: ${item.code}`;
    root.querySelector("#link-code-error").hidden = true;
    root.querySelector("#link-code-search").replaceChildren(this._productLinkSearch(item));
    root.querySelector("#link-code-dialog").showModal();
    this._renderLinkDialog();
    root.querySelector("#link-code-search input").focus();
  }

  _renderLinkDialog() {
    const root = this.shadowRoot;
    if (!root.querySelector("#link-code-dialog").open) return;
    const product = this._catalog.products.find(product => product.id === this._linkProductId);
    const valid = Boolean(product);
    root.querySelector("#link-code-selection").textContent = valid ? `Producto seleccionado: ${product.name}` : "Selecciona un producto para asignarle el código.";
    root.querySelector("#confirm-link-code").disabled = this._linkBusy || !valid || this._catalog.loading || Boolean(this._catalog.error);
    root.querySelector("#confirm-link-code").textContent = this._linkBusy ? "Asignando…" : "Asignar";
    root.querySelector("#cancel-link-code").disabled = Boolean(this._linkBusy);
    root.querySelector("#link-code-search input").disabled = Boolean(this._linkBusy);
    this._refreshLinkPredictions?.();
  }

  async _assignCode() {
    if (this._linkBusy || !this._linkReading) return;
    const selected = this._catalog.products.find(product => product.id === this._linkProductId);
    if (!selected) { this._renderLinkDialog(); return; }
    // Send editable fields only; use the latest revision and retain all other product data.
    const fields = ["id", "revision", "name", "category", "tags", "barcode", "price", "currency", "image_url", "icon", "notes", "barcodes", "nfc_tags", "reader_actions", "recurrence"];
    const product = Object.fromEntries(fields.filter(key => key in selected).map(key => [key, structuredClone(selected[key])]));
    const reading = this._linkReading;
    if (reading.kind === "barcode" && !product.barcode) product.barcode = reading.code;
    else {
      const field = reading.kind === "nfc" ? "nfc_tags" : "barcodes";
      product[field] = [...(product[field] ?? [])];
      if (!product[field].includes(reading.code) && !(reading.kind === "barcode" && product.barcode === reading.code)) product[field].push(reading.code);
    }
    this._linkBusy = true;
    const root = this.shadowRoot;
    root.querySelector("#link-code-error").hidden = true;
    this._renderLinkDialog();
    try {
      await this._catalog.save(product);
      root.querySelector("#link-code-dialog").close();
      this._notice = "Código asignado al producto.";
    } catch (error) {
      const notice = root.querySelector("#link-code-error");
      notice.textContent = error.message ?? "No se ha podido asignar el código al producto.";
      notice.hidden = false;
    } finally {
      this._linkBusy = false;
      this._render();
    }
  }

  _renderReaderActions() {
    if (!this._built) return;
    const container = this.shadowRoot.querySelector("#product-reader-actions");
    const signature = JSON.stringify((this._readers?.readers ?? []).map(reader => [reader.id, reader.name]));
    if (signature === this._readerSignature) return;
    this._readerSignature = signature;
    const previous = new Map([...container.querySelectorAll("select")].map(select => [select.dataset.readerAction,select.value]));
    const nodes = (this._readers?.readers ?? []).map(reader => {
      const wrap = element("div");wrap.style.marginTop="12px";
      const label = element("label", "", reader.name);
      const select = element("select");
      select.id = `action-${reader.id}`;label.htmlFor=select.id;select.dataset.readerAction=reader.id;
      for (const [value,text] of [["none","Sin acción"],["add_list","Añadir a la lista de la compra"],["stock_remove","Quitar una unidad al stock (próximamente)"],["stock_add","Añadir una unidad al stock (próximamente)"]]) select.append(new Option(text,value));
      select.value=previous.get(reader.id)??"none";wrap.append(label,select);return wrap;
    });
    container.replaceChildren(...(nodes.length ? nodes : [element("p","helper","Añade un lector en el apartado Lectores para configurar sus acciones.")]));
  }

  async _actOnSuggestion(name, action) {
    if (this._suggestionBusy) return;
    if (action === "add") {
      const items = this._listItems.filter(item => productNameKey(item.summary) === productNameKey(name))
        .map(item => ({uid:item.uid,summary:item.summary}));
      this._openProduct(undefined, name, null, {entityId:this._listEntity,items,summary:name});
      return;
    }
    this._suggestionBusy = true;
    this._suggestionError = "";
    this._notice = "";
    this._render();
    try {
      await this._catalog.actOnSuggestion(name, action);
      this._notice = `Sugerencia descartada: ${name}.`;
    } catch (error) {
      this._suggestionError = error.message ?? "No se ha podido guardar el cambio.";
    } finally {
      this._suggestionBusy = false;
      this._render();
    }
  }

  _fillFilter(select, values) {
    const previous = select.value;
    select.replaceChildren(new Option("Todas", ""), ...values.map(value => new Option(value, value)));
    select.value = values.includes(previous) ? previous : "";
  }

  _renderProducts() {
    if (!this._built) return;
    const root = this.shadowRoot;
    const query = root.querySelector("#catalog-search").value.trim().toLocaleLowerCase("es");
    const category = root.querySelector("#category-filter").value;
    const products = this._catalog.products.filter(product =>
      (!category || normalizedName(product.category) === normalizedName(category)) &&
      [product.name, product.barcode, ...(product.barcodes??[]), ...(product.nfc_tags??[]), product.category, ...product.tags].join(" ").toLocaleLowerCase("es").includes(query));
    root.querySelector("#catalog-count").textContent = `${products.length} de ${this._catalog.products.length} productos`;
    root.querySelector("#catalog-grid").replaceChildren(...products.map(product => this._productCard(product)));
    const empty = root.querySelector("#catalog-empty");
    empty.hidden = products.length > 0 || this._catalog.loading || Boolean(this._catalog.error);
    empty.textContent = this._catalog.products.length ? "No hay productos que coincidan con estos filtros." : "Tu catálogo empieza aquí. Añade el primer producto para tenerlo a mano en tu próxima compra.";
  }

  _productCard(product) {
    const card = element("article", "product");
    card.dataset.productId = product.id;
    const inList = this._pendingNames.has(productNameKey(product.name));
    card.classList.toggle("in-list", inList);
    card.dataset.inList = String(inList);
    if (inList) card.setAttribute("aria-description", "Pendiente en la lista seleccionada");
    const category = this._catalog.categories.find(category => normalizedName(category.name) === normalizedName(product.category));
    // A native, transparent button makes the whole surface keyboard accessible.
    // Edit/delete are sibling controls above it, so they never activate list writes.
    const add = element("button", "add-product");
    add.type = "button";
    add.title = inList ? "Este producto ya está en la lista." : this._canAdd ? `Añadir ${product.name} a «${this._listName}»` : "Selecciona una lista disponible en el apartado Lista para añadir productos.";
    add.setAttribute("aria-label", `Añadir ${product.name} a la lista`);
    add.disabled = inList || !this._canAdd || Boolean(this._adding);
    add.addEventListener("click", () => void this._addToList(product));
    card.append(add);
    const top = element("div", "product-top");
    const media = element("div", "product-media");
    const placeholder = element("div", "image placeholder");
    const icon = element("ha-icon");
    icon.setAttribute("icon", product.icon || category?.icon || "mdi:shopping");
    placeholder.append(icon);
    const source = imageSource(product.image_url);
    if (source) {
      const image = element("img", "image");
      image.src = source;
      image.alt = "";
      image.loading = "lazy";
      image.referrerPolicy = "no-referrer";
      image.addEventListener("error", () => image.replaceWith(placeholder), { once: true });
      media.append(image);
    } else media.append(placeholder);
    top.append(media);
    const title = element("div", "product-name");
    title.title = product.name;
    title.append(element("h2", "title", product.name));
    top.append(title);
    card.append(top);
    if (product.tags.length) {
      const tags = element("div", "tags");
      tags.append(...product.tags.map(tag => element("span", "tag", tag)));
      top.append(tags);
    }
    const controls = element("div", "product-controls");
    const edit = iconButton("mdi:note-edit", `Editar ${product.name}`, "edit-product");
    edit.addEventListener("click", event => { event.stopPropagation(); this._openProduct(product); });
    const remove = iconButton("mdi:delete", `Eliminar ${product.name}`, "delete-product");
    remove.addEventListener("click", event => { event.stopPropagation(); this._confirmDeleteProduct(product); });
    controls.append(edit, remove);
    card.append(controls);
    return card;
  }

  _confirmDeleteProduct(product) {
    if (this._saving || this._deletingProduct) return;
    this._deleteTarget = structuredClone(product);
    const root = this.shadowRoot;
    root.querySelector("#delete-product-description").textContent = `Se eliminará «${product.name}» del catálogo y se quitarán sus códigos asociados. Los elementos que ya estén en tus listas se conservarán.`;
    root.querySelector("#delete-product-error").hidden = true;
    root.querySelector("#delete-product-dialog").showModal();
  }

  async _deleteProduct() {
    if (!this._deleteTarget || this._deletingProduct) return;
    const root = this.shadowRoot;
    this._deletingProduct = true;
    root.querySelectorAll("#delete-product-dialog button").forEach(button => { button.disabled = true; });
    root.querySelector("#delete-product-error").hidden = true;
    try {
      await this._catalog.deleteProduct(this._deleteTarget);
      root.querySelector("#delete-product-dialog").close();
      this._notice = "Producto eliminado del catálogo.";
      this._render();
      root.querySelector("#new-product").focus();
    } catch (error) {
      const notice = root.querySelector("#delete-product-error");
      notice.textContent = error.message ?? "No se ha podido eliminar el producto.";
      notice.hidden = false;
    } finally {
      this._deletingProduct = false;
      root.querySelectorAll("#delete-product-dialog button").forEach(button => { button.disabled = false; });
    }
  }

  _switchProductView(view) {
    if (this._saving) return;
    for (const button of this.shadowRoot.querySelectorAll("[data-product-view]")) {
      const selected = button.dataset.productView === view;
      button.setAttribute("aria-pressed", String(selected));
      this.shadowRoot.querySelector(`#${button.getAttribute("aria-controls")}`).hidden = !selected;
    }
    if (view === "additional") { void this._loadNutriscores(); void this._loadRetailPrices(); }
  }

  _resetNutriscores() {
    this._nutriGeneration = (this._nutriGeneration || 0) + 1;
    this._nutriCodesKey = "";
    this.shadowRoot.querySelector("#nutriscore-results").replaceChildren();
    this.shadowRoot.querySelector("#product-nutriscore").hidden = true;
    this.shadowRoot.querySelector("#store-price-results").replaceChildren();
    this.shadowRoot.querySelector("#product-store-prices").hidden = true;
  }

  async _loadRetailPrices() {
    const root = this.shadowRoot, form = root.querySelector("#product-form"), generation = this._nutriGeneration;
    root.querySelector("#store-price-results").replaceChildren();
    root.querySelector("#product-store-prices").hidden = true;
    try {
      const linksKey = JSON.stringify(this._storeLinks ?? {});
      const data = await this._hass.callWS({type:"improved_shopping_list/catalog/store_prices",links:this._storeLinks ?? {},codes:[form.elements.barcode.value,...form.elements.barcodes.value.split(/\r?\n/)].map(value=>value.trim()).filter(Boolean)});
      if (generation !== this._nutriGeneration || linksKey !== JSON.stringify(this._storeLinks ?? {}) || !root.querySelector("dialog").open || !this.isConnected) return;
      const names = {mercadona:"Mercadona",carrefour:"Carrefour",alcampo:"Alcampo"};
      const rows = data.products.map(product => {
        const row = document.createElement("div"); row.className = "nutriscore-item";
        const link = document.createElement("a"); link.textContent = `${names[product.store] ?? product.store}: ${new Intl.NumberFormat("es-ES",{style:"currency",currency:product.currency}).format(Number(product.price))} · ${product.store_name || product.name || "Ver producto"}${product.reference_id ? ` · ID ${product.reference_id}` : ""}`;
        link.href = product.url; link.target = "_blank"; link.rel = "noopener noreferrer";
        const date = document.createElement("p"); date.className = "helper"; date.textContent = `Último precio conocido: ${new Date(product.checked_at*1000).toLocaleString("es-ES")}${product.error ? " · No se pudo actualizar" : ""}${product.available === false ? " · No disponible" : ""}`;
        row.append(link,date); return row;
      });
      root.querySelector("#store-price-results").replaceChildren(...rows);
      root.querySelector("#product-store-prices").hidden = !rows.length;
    } catch { /* Optional store data must never prevent editing. */ }
  }

  _renderStoreLinks() {
    const root = this.shadowRoot, names = {mercadona:"Mercadona",carrefour:"Carrefour",alcampo:"Alcampo"};
    root.querySelector("#product-store-links").replaceChildren(...Object.entries(this._storeLinks).map(([store,value])=>{
      const row = document.createElement("div"); row.className = "product-category-controls";
      row.style.marginBottom = "10px";
      const label = document.createElement("label"); label.textContent = names[store] ?? store; label.style.flex = "1";
      const input = document.createElement("input"); input.value = typeof value === "string" ? value : value.url || value.id; input.maxLength = 2048; input.setAttribute("aria-label",`Enlace o ID de ${names[store]}`);
      input.addEventListener("input",()=>{this._storeLinks[store]=input.value.trim();});
      input.addEventListener("change",()=>void this._loadRetailPrices());
      label.append(input);
      const remove = document.createElement("button"); remove.type = "button"; remove.setAttribute("aria-label",`Quitar vinculación de ${names[store]}`); remove.innerHTML = '<ha-icon icon="mdi:delete" aria-hidden="true"></ha-icon>';
      remove.addEventListener("click",()=>{delete this._storeLinks[store];this._renderStoreLinks();void this._loadRetailPrices();});
      row.append(label,remove);return row;
    }));
    const select = root.querySelector("#product-link-store");
    select.replaceChildren(...Object.entries(names).filter(([key])=>!(key in this._storeLinks)).map(([key,name])=>new Option(name,key)));
    root.querySelector("#add-product-store-link").disabled = !select.options.length;
  }

  async _loadNutriscores() {
    const root = this.shadowRoot;
    const form = root.querySelector("#product-form");
    const seen = new Set();
    const codes = [form.elements.barcode.value, ...form.elements.barcodes.value.split(/\r?\n/)]
      .map(code => code.trim()).filter(code => {
        if (!/^(?:\d{8}|\d{12,14})$/.test(code)) return false;
        const total = [...code.slice(0,-1)].reverse().reduce((sum,digit,index) => sum + Number(digit) * (index % 2 ? 1 : 3),0);
        const key = code.padStart(14,"0");
        if ((10 - total % 10) % 10 !== Number(code.at(-1)) || seen.has(key)) return false;
        seen.add(key);
        return true;
      });
    const key = JSON.stringify(codes);
    if (key === this._nutriCodesKey || !this._hass) return;
    this._resetNutriscores();
    this._nutriCodesKey = key;
    const generation = this._nutriGeneration;
    for (const code of codes) {
      if (generation !== this._nutriGeneration || !root.querySelector("dialog").open || !this.isConnected) return;
      try {
        const result = await this._hass.callWS({type:"improved_shopping_list/catalog/nutriscore",code});
        if (generation !== this._nutriGeneration || !root.querySelector("dialog").open || !this.isConnected) return;
        const data = result.nutriscore;
        if (!data || !/^[a-e]$/.test(data.grade)) continue;
        const row = document.createElement("div"); row.className = "nutriscore-item";
        row.dataset.code = code;
        const image = document.createElement("img");
        image.src = `https://static.openfoodfacts.org/images/attributes/dist/nutriscore-${data.grade}${data.version === "2023" ? "-new-en" : ""}.svg`;
        image.alt = `Nutri-Score ${data.grade.toUpperCase()}`;
        image.referrerPolicy = "no-referrer";
        const info = document.createElement("div");
        const title = document.createElement("p");
        title.textContent = result.product_name ? `${result.product_name} · ${code}` : code;
        const grade = document.createElement("p"); grade.textContent = `Nutri-Score: ${data.grade.toUpperCase()}`;
        const source = document.createElement("a");
        source.textContent = "Open Food Facts · ODbL";
        source.href = `https://world.openfoodfacts.org/product/${code}`;
        source.target = "_blank"; source.rel = "noopener noreferrer";
        info.append(title, grade, source);
        if (Number.isFinite(data.checked_at) && data.checked_at > 0) {
          const date = document.createElement("p"); date.className = "helper";
          date.textContent = `Consultado: ${new Date(data.checked_at * 1000).toLocaleDateString("es-ES")}`;
          info.append(date);
        }
        row.append(image, info);
        root.querySelector("#nutriscore-results").append(row);
        root.querySelector("#product-nutriscore").hidden = false;
      } catch { /* Optional nutrition must never prevent editing or saving. */ }
    }
  }

  _openProduct(product, suggestedName = "", reading = null, listOrigin = null) {
    if (this._saving) return;
    const root = this.shadowRoot;
    const form = root.querySelector("form");
    this._listOrigin = listOrigin;
    form.reset();
    this._resetNutriscores();
    this._switchProductView("main");
    form.elements.name.value = suggestedName;
    if (!product && reading?.identification?.status === "found") {
      const hint = reading.identification;
      form.elements.name.value = hint.name ?? "";
    }
    this._renderReaderActions();
    this._editing = product ? structuredClone(product) : null;
    this._storeLinks = structuredClone(product?.store_links ?? {});
    this._renderStoreLinks();
    form.elements.recurrence_enabled.checked = product?.recurrence?.enabled === true;
    form.elements.recurrence_days.value = product?.recurrence?.days ?? 7;
    form.elements.recurrence_days.disabled = !form.elements.recurrence_enabled.checked;
    root.querySelector("#product-dialog-title").textContent = product ? "Editar producto" : "Nuevo producto";
    root.querySelector("#product-error").hidden = true;
    if (product) {
      for (const key of ["name", "category", "barcode", "price", "image_url"]) form.elements[key].value = product[key] ?? "";
      if (![...form.elements.currency.options].some(option => option.value === product.currency)) form.elements.currency.add(new Option(product.currency, product.currency));
      form.elements.currency.value = product.currency;
      form.elements.barcodes.value = (product.barcodes ?? []).join("\n");
      form.elements.nfc_tags.value = (product.nfc_tags ?? []).join("\n");
    }
    for (const select of root.querySelectorAll("[data-reader-action]")) select.value = product?.reader_actions?.[select.dataset.readerAction] ?? "none";
    if (reading) {
      if (reading.kind === "barcode" && !form.elements.barcode.value) form.elements.barcode.value = reading.code;
      else {
        const field = reading.kind === "nfc" ? "nfc_tags" : "barcodes";
        const values = form.elements[field].value.split(/\r?\n/).filter(Boolean);
        if (!values.includes(reading.code) && !(reading.kind === "barcode" && form.elements.barcode.value === reading.code)) values.push(reading.code);
        form.elements[field].value = values.join("\n");
      }
    }
    const iconPicker = root.querySelector("isl-icon-picker");
    iconPicker.hass = this._hass;
    iconPicker.value = form.elements.image_url.value;
    root.querySelector("dialog").showModal();
    iconPicker.open(iconPicker.getQuery());
    form.elements.name.focus();
  }

  async _saveProduct() {
    if (this._saving) return;
    const root = this.shadowRoot;
    const form = root.querySelector("form");
    const fields = Object.fromEntries(new FormData(form));
    const product = { ...fields, price: fields.price || null, tags: this._editing?.tags ?? [], icon: this._editing?.icon ?? "", notes: this._editing?.notes ?? "" };
    product.store_links = structuredClone(this._storeLinks ?? {});
    for (const key of ["barcodes","nfc_tags"]) product[key] = fields[key].split(/\r?\n/).map(value => value.trim()).filter(Boolean);
    product.recurrence = {enabled:form.elements.recurrence_enabled.checked, days:Number(form.elements.recurrence_days.value) || 7};
    delete product.recurrence_enabled;
    delete product.recurrence_days;
    product.reader_actions = Object.fromEntries([...root.querySelectorAll("[data-reader-action]")].map(select => [select.dataset.readerAction,select.value]));
    if (this._editing) Object.assign(product, { id: this._editing.id, revision: this._editing.revision });
    this._saving = true;
    root.querySelector("isl-icon-picker").disabled = true;
    root.querySelector("#save-product").disabled = true;
    root.querySelector("#cancel-product").disabled = true;
    root.querySelector("#product-error").hidden = true;
    try {
      const saved = await this._catalog.save(product);
      this._editing = structuredClone(saved);
      let renamed = 0;
      if (this._listOrigin && saved.name !== this._listOrigin.summary) {
        try {
          if (!this.onRenameSuggestion) throw new Error("No se ha podido conectar con la lista de origen.");
          renamed = await this.onRenameSuggestion(this._listOrigin, saved.name);
        } catch (error) {
          root.querySelector("#product-dialog-title").textContent = "Editar producto";
          throw new Error(`El producto se ha guardado en el catálogo, pero no se ha podido actualizar su nombre en la lista. ${error.message ?? "Inténtalo de nuevo."}`);
        }
      }
      this._listOrigin = null;
      root.querySelector("dialog").close();
      this._notice = renamed ? "Producto guardado y nombre actualizado en la lista." : "Producto guardado en el catálogo.";
      this._render();
      root.querySelector(this._view === "suggestions" ? "#view-suggestions" : "#new-product").focus();
    } catch (error) {
      const notice = root.querySelector("#product-error");
      notice.textContent = error.message ?? "No se ha podido guardar el producto.";
      notice.hidden = false;
    } finally {
      this._saving = false;
      root.querySelector("isl-icon-picker").disabled = false;
      root.querySelector("#save-product").disabled = false;
      root.querySelector("#cancel-product").disabled = false;
    }
  }

  async _addToList(product) {
    if (!this._canAdd || this._adding || !this.onAdd || this._pendingNames.has(productNameKey(product.name))) return;
    this._adding = product.id;
    this._notice = "";
    this._render();
    try {
      await this.onAdd(product);
    } finally {
      this._adding = undefined;
      this._render();
    }
  }
}

if (!customElements.get("isl-catalog")) customElements.define("isl-catalog", ImprovedShoppingCatalog);
