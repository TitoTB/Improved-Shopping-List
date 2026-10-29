import { purchaseQuantity, quantityLabel } from "./quantity-client.js?v=0.53.1";
import { referenceContentControls, referenceRate, barcodeIdentity, validReferenceContent } from "./reference-formats.js?v=0.53.1";
import { installDialogCloseButtons } from "./dialog-controls.js?v=0.53.1";
import { CatalogSession } from "./catalog-client.js?v=0.53.1";
import { matchCatalogProducts } from "./product-matching.js?v=0.53.1";
import "./category-panel.js?v=0.53.1";
import "./recipe-editor.js?v=0.53.1";
import "./icon-picker.js?v=0.53.1";
import { imageSource, normalizedName, productNameKey, cachedProductPrice, storeProductLink, storeFromProductUrl } from "./product-display.js?v=0.53.1";
export { imageSource, normalizedName, productNameKey, cachedProductPrice };

const MONTHS = ["Enero","Febrero","Marzo","Abril","Mayo","Junio","Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"];
const STORE_NAMES = {mercadona:"Mercadona",carrefour:"Carrefour",alcampo:"Alcampo",consum:"Consum",lasirena:"La Sirena",eroski:"Eroski",dia:"DIA",lidl:"Lidl"};
const storeLogo = store => ({lidl:"https://upload.wikimedia.org/wikipedia/commons/9/91/Lidl-Logo.svg",carrefour:"https://images.seeklogo.com/logo-png/31/2/carrefour-logo-png_seeklogo-318190.png",alcampo:"https://almeria.online/wp-content/uploads/2024/09/alcampo-logo.png"}[store] ?? new URL(`${store}.${store === "mercadona" || store === "dia" ? "png" : store === "eroski" ? "svg" : "jpg"}`,import.meta.url).href);

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

class ImprovedShoppingCatalog extends HTMLElement {
  createProduct(suggestedName) {
    if(this._saving||this._receiptCreate)throw new Error('Espera a que termine la edición del producto.');
    this._receiptCreate=true;this._receiptCreated=null;this._ensureBuilt();
    this.hidden=false;this.setAttribute('receipt-editor','');
    const dialog=this.shadowRoot.querySelector('dialog');
    return new Promise(resolve=>{
      dialog.addEventListener('close',()=>{
        this.removeAttribute('receipt-editor');this.hidden=!this._active;this._receiptCreate=false;
        resolve(this._receiptCreated);
      },{once:true});
      this._openProduct(undefined,suggestedName);
    });
  }
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._catalog = new CatalogSession(() => this._hass, () => this._render());
    this._canAdd = false;
    this._view = "products";
    this._productLayout = "grid";
    try { if (localStorage.getItem("isl-catalog-layout") === "rows") this._productLayout = "rows"; } catch { /* Storage may be disabled. */ }
    this._productOrder = "alphabetical";
    try { if (localStorage.getItem("isl-catalog-order") === "categories") this._productOrder = "categories"; } catch { /* Storage may be disabled. */ }
    this._groupBy = "category";
    try { const saved=localStorage.getItem("isl-catalog-grouping"); if (["suggestions","store"].includes(saved)) this._groupBy = saved; } catch { /* Storage may be disabled. */ }
    this._pendingNames = new Set();
    this._listItems = [];
  }

  set session(value) {
    if (value === this._catalog) return;
    this._catalogUnsubscribe?.();
    if (!this._sharedCatalog) this._catalog.stop();
    this._catalog = value;
    this._sharedCatalog = true;
    this._started = false;
    this._start();
  }

  set hass(value) {
    const previous = this._hass?.connection;
    this._hass = value;
    if (this._built) this.shadowRoot.querySelector("isl-icon-picker").hass = value;
    if (previous && previous !== value.connection) {
      this._stopCodeCapture();
      this._started = false;
    }
    this._start();
  }

  set canAdd(value) {
    if (this._canAdd === value) return;
    this._canAdd = value;
    this._renderProducts();
  }

  set canComplete(value) {
    if (this._canComplete === value) return;
    this._canComplete = value;
    this._renderProducts();
  }

  set listName(value) {
    this._listName = value;
    this._renderSuggestions();
  }

  set readerData(value) {
    this._readers = value;
    this._renderReaderActions();
    this._renderProductCodes();
    this._renderSuggestions();
  }

  get productLayout() { return this._productLayout; }
  set attention(count) {
    this._newProductCount=count;
    const button=this.shadowRoot.querySelector('#view-suggestions');
    if(!button)return;
    button.dataset.attention=String(count>0);
    if(count>0)button.setAttribute('aria-description',`Productos pendientes de añadir al catálogo: ${count}`);else button.removeAttribute('aria-description');
  }
  set active(value) {
    if (this._active === Boolean(value)) return;
    this._active = Boolean(value);
    if (this._active)this._ensureBuilt();
    if (!this._active) this._stopCodeCapture();
    if (this._active) this._render();
  }
  set stores(value) {
    const key=JSON.stringify(value??{});
    if(key===this._storesKey)return;
    this._storesKey=key;this._stores=value??{};this._renderProducts();
  }
  set receiptStores(value) {
    const key=JSON.stringify(value??{});
    if(key===this._receiptStoresKey)return;
    this._receiptStoresKey=key;this._receiptStores=value??{};this._renderProducts();
    if(this._storeLinks&&this.shadowRoot.querySelector("dialog")?.open)this._renderStoreLinks();
  }
  set priceData(value) {
    const key = JSON.stringify(value);
    if (key === this._priceDataKey) return;
    this._priceDataKey = key; this._priceData = value;
    this._renderProducts();
  }
  set quantityData(value) {
    const key=JSON.stringify(value);
    if(key===this._quantityKey)return;
    this._quantityKey=key;this._quantityData=value;this._renderProducts();
  }
  set listEntity(value) { this._listEntity = value; }

  set listItems(value) {
    const signature = JSON.stringify([this._listEntity, (value ?? []).map(item => [item.uid,item.summary,item.status])]);
    if (signature === this._listSignature) return;
    this._listSignature = signature;
    this._listItems = value ?? [];
    this._renderSuggestions();
    this._renderProducts();
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
    if(this._active||this._receiptCreate)this._ensureBuilt();
  }

  _ensureBuilt() {
    if(!this._built)this._build();
    this._start();
    if(!this._seasonTimer){
      this._lastSeasonMonth=this._seasonMonth();
      this._seasonTimer=setInterval(()=>{
        const month=this._seasonMonth();
        if(month!==this._lastSeasonMonth){this._lastSeasonMonth=month;this._renderProducts();}
      },60000);
    }
  }

  disconnectedCallback() {
    this._active = false;
    this._stopCodeCapture();
    clearInterval(this._seasonTimer);this._seasonTimer=null;
    this._catalogUnsubscribe?.();this._catalogUnsubscribe=null;
    if (!this._sharedCatalog) this._catalog.stop();
    this._started = false;
    this.shadowRoot.querySelectorAll("dialog").forEach(dialog => dialog.close());
    this.shadowRoot.querySelector("isl-icon-picker")?.close();
  }

  _start() {
    if (!this.isConnected || !this._built || !this._hass || this._started) return;
    this._started = true;
    if (this._sharedCatalog) {
      this._catalogUnsubscribe ??= this._catalog.subscribe(() => this._render());
      this._render();
    } else void this._catalog.start();
  }

  _build() {
    this.shadowRoot.innerHTML = `
      <style>
        :host { display:block; color:var(--primary-text-color,#20352d); }
        :host([receipt-editor]) { display:contents; }
        :host([receipt-editor]) > :not(style):not(dialog) { display:none!important; }
        :host([hidden]),[hidden] { display:none !important; }
        * { box-sizing:border-box; }
        button,input,select,textarea { font:inherit; }
        button { cursor:pointer; }
        button:disabled { opacity:.5; cursor:default; }
        button:focus-visible,input:focus-visible,select:focus-visible,textarea:focus-visible { outline:3px solid var(--primary-color,#267052); outline-offset:3px; }
        .heading { display:flex; align-items:center; justify-content:space-between; gap:16px; margin:0 0 16px; }
        .heading h1 { flex-shrink:0; }
        .catalog-toolbar { display:flex; align-items:center; gap:12px; min-width:0; margin-left:auto; }
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
        .suggestion .actions .danger { background:#d32f2f; color:#fff; border:0; }
        .suggestion .actions .link { background:#1976d2; color:#fff; border:0; }
        .link-results { max-height:260px; overflow-y:auto; border:1px solid var(--divider-color,#dfe7e1); border-radius:9px; margin-top:6px; }
        .link-results button { display:block; width:100%; text-align:left; border:0; border-radius:0; overflow-wrap:anywhere; }
        .link-results button:hover,.link-results [aria-selected=true] { background:var(--secondary-background-color,#edf4ee); }
        .link-empty { font-size:13px; margin:8px 0 0; }
        @media(max-width:650px) { .suggestion { flex-wrap:wrap; } .suggestion .actions { margin-left:auto; } }
        .catalog-tabs button[aria-pressed=true] { background:var(--secondary-background-color,#edf4ee); font-weight:650; }
        #view-suggestions { position:relative; }
        #view-suggestions[data-attention=true]::after { content:"";position:absolute;top:3px;right:3px;width:8px;height:8px;border-radius:50%;background:#d32f2f;pointer-events:none; }
        h1 { font-size:32px; letter-spacing:-.03em; margin:0; }
        h2 { font-size:23px; margin:0; }
        .helper { color:var(--secondary-text-color,#63766b); font-size:13px; line-height:1.6; margin:8px 0 18px; }
        button { min-height:44px; padding:10px 14px; border:1px solid var(--divider-color,#dfe7e1); border-radius:10px; background:transparent; color:inherit; }
        .primary { background:#267052; color:#fff; border:0; font-weight:650; }
        .filters { display:grid; grid-template-columns:minmax(0,1fr) auto; gap:12px; margin:24px 0 14px; align-items:end; }
        .filters .search { min-width:0; }
        #catalog-search { margin-top:0; height:46px; }
        .catalog-product-controls { display:flex; align-items:center; justify-content:flex-end; gap:8px; min-width:0; }
        #new-product,#new-catalog-category,#toggle-catalog-order,#configure-catalog-grouping,#toggle-catalog-layout { display:grid; place-items:center; flex:0 0 46px; width:46px; height:46px; padding:0; }
        #new-product ha-icon,#new-catalog-category ha-icon,#toggle-catalog-order ha-icon,#configure-catalog-grouping ha-icon,#toggle-catalog-layout ha-icon { --mdc-icon-size:24px; width:24px; height:24px; }
        #toggle-catalog-layout,#toggle-catalog-order,#configure-catalog-grouping { background:var(--card-background-color,#fff); }
        .grouping-options { display:grid; gap:12px; margin-block-start:16px; }
        .grouping-options button { display:flex; align-items:center; gap:10px; text-align:left; }
        .grouping-options button[aria-pressed=true] { background:var(--secondary-background-color,#edf4ee); font-weight:650; }
        .grouping-options ha-icon { width:24px; height:24px; --mdc-icon-size:24px; flex:none; }
        #catalog-grid.grouped { grid-template-columns:minmax(0,1fr); gap:24px; }
        .category-group { min-width:0; border:1px solid var(--divider-color,#dfe7e1); border-radius:14px; background:var(--card-background-color,#fff); }
        .category-group-toggle { display:flex; align-items:center; gap:12px; padding:16px; cursor:pointer; list-style:none; border-radius:14px; }
        .category-group-toggle::-webkit-details-marker { display:none; }
        .category-group-toggle::after { content:''; width:9px; height:9px; flex:none; margin-left:auto; border-right:2px solid currentColor; border-bottom:2px solid currentColor; transform:rotate(45deg); }
        .category-group[open] > .category-group-toggle::after { transform:rotate(225deg); }
        .category-group-toggle:focus-visible { outline:3px solid var(--primary-color,#267052); outline-offset:3px; }
        .category-products { padding:0 16px 16px; }
        .category-group-title { display:flex; align-items:center; gap:8px; margin:0; font-size:18px; overflow-wrap:anywhere; }
        .category-group-title ha-icon { --mdc-icon-size:22px; width:22px; height:22px; flex:none; color:#fff; }
        .category-store-logo { display:block; width:32px; height:32px; aspect-ratio:1; flex:none; padding:0; overflow:hidden; border-radius:50%; background:#fff; }
        .category-store-logo img { display:block; width:100%; height:100%; object-fit:cover; }
        .product-category-controls { display:flex; align-items:end; gap:8px; }
        .product-category-controls select { flex:1; min-width:0; }
        #add-product-category { display:grid; place-items:center; flex:0 0 46px; width:46px; height:46px; padding:0; }
        #add-product-category ha-icon { --mdc-icon-size:22px; }
        .store-link-add { display:grid;grid-template-columns:minmax(0,1fr) auto 46px;grid-template-areas:"url retrieve add";gap:8px;align-items:center;margin-top:7px; }
        #product-link-value { grid-area:url; }#retrieve-product-data { grid-area:retrieve; }#add-product-store-link { grid-area:add; }
        .option-url-row { display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;gap:8px;margin-top:12px; }
        .option-url-row input { margin:0;width:100%;min-width:0; }
        .option-lookup-feedback[data-error="true"],#option-lookup-status[data-error="true"] { color:var(--error-color,#bd3636); }
        .retrieve-option { display:inline-flex;align-items:center;justify-content:center;gap:6px;min-height:46px;padding:8px 10px;font-size:12px;background:var(--primary-color,#267052);color:#fff; }
        .retrieve-option ha-icon { width:18px;height:18px;--mdc-icon-size:18px;flex:none; }
        @media(max-width:550px){.option-url-row{gap:6px;}.retrieve-option{padding:8px;font-size:11px;}.retrieve-option ha-icon{display:none;}}
        .store-link-add input,.store-link-add button { width:100%; min-width:0; height:46px; min-height:46px; margin:0; }
        #add-product-store-link { display:grid; place-items:center; padding:0; }
        #add-product-store-link ha-icon { display:block; width:24px; height:24px; --mdc-icon-size:24px; }
        #product-store-links { display:grid; gap:12px; }
        #pending-formats { display:grid;place-items:center;flex:0 0 46px;width:46px;height:46px;padding:0; }
        #pending-formats[aria-pressed=true] { background:var(--primary-color,#267052);color:#fff; }
        .commercial-reference { padding-top:12px;min-width:0; }
        .product-ean-group { border:1px solid var(--divider-color,#dce4e1);border-radius:12px;padding:12px;margin-top:12px;min-width:0; }
        .product-ean-group > summary { cursor:pointer;font-weight:650;overflow-wrap:anywhere; }
        .product-ean-group .product-option { margin-top:12px; }
        .product-option>summary { display:flex;align-items:center;gap:10px;cursor:pointer;list-style:none;min-width:0; }
        .product-option>summary::-webkit-details-marker { display:none; }
        .product-option>summary::after { content:"";width:8px;height:8px;border-right:2px solid currentColor;border-bottom:2px solid currentColor;transform:rotate(45deg);margin:0 4px 4px auto;flex:none; }
        .product-option[open]>summary::after { transform:rotate(225deg);margin-bottom:0; }
        .product-option>summary:focus-visible { outline:2px solid var(--primary-color,#267052);outline-offset:4px;border-radius:4px; }
        .option-heading { display:block;min-width:0;flex:1; }
        .option-name { font-size:14px;font-weight:650;overflow-wrap:anywhere; }
        .option-store { flex:none; }
        .product-option .option-store img { width:32px;height:32px;object-fit:contain;background:#fff;padding:3px;border-radius:8px;box-sizing:border-box; }
        .option-brand,.option-price { margin-top:12px; }
        .commercial-reference-title { display:flex;gap:8px;align-items:center; }.commercial-reference-title input { min-width:0;flex:1;margin:0; }
        .reference-content-controls { display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:10px;margin-top:12px;min-width:0; }
        .reference-content-controls label { margin:0;min-width:0; }.reference-content-controls input,.reference-content-controls select { width:100%;min-width:0; }
        .reference-confirm { grid-column:1/-1;display:flex!important;align-items:center;gap:8px; }.reference-confirm input { width:auto!important;min-height:0!important;margin:0!important; }
        .product-store-association { padding:14px; border:1px solid var(--divider-color,#dfe7e1); border-radius:12px; min-width:0; background:var(--card-background-color,#fff); }
        .product-store-header { display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:10px; min-width:0; }
        .store-reference { display:flex; align-items:center; gap:9px; min-width:0; font-size:14px; font-weight:650; }
        .store-reference img { width:32px; height:32px; object-fit:contain; background:white; border-radius:8px; padding:3px; flex:none; }
        .association-source { display:flex; align-items:center; flex-wrap:wrap; gap:5px; margin:0 0 0 auto; }
        .association-source span { display:inline-flex; align-items:center; min-height:24px; padding:3px 8px; border-radius:7px; background:var(--secondary-background-color,#edf4ee); font-size:11px; line-height:1.3; color:var(--secondary-text-color,#63766b); }
        .product-store-link { display:grid; grid-template-columns:minmax(0,1fr) 42px; gap:8px; align-items:center; margin-top:12px; }
        .product-store-link input { min-width:0; width:100%; height:44px; min-height:44px; margin:0; font-size:12px; }
        .remove-store-link { display:grid; place-items:center; width:42px; height:44px; min-height:44px; padding:0; background:#d32f2f; color:white; border:0; }
        @media(max-width:420px) { .product-store-association { padding:11px; }.product-store-header { gap:8px; }.store-reference { font-size:13px; }.association-source { gap:4px; }.association-source span { font-size:10px;padding:3px 6px; }.product-store-link { margin-top:10px;gap:6px; } }
        .remove-store-link ha-icon { --mdc-icon-size:22px; width:22px; height:22px; }
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
        .product-controls { position:absolute; z-index:2; top:clamp(3px,4cqi,12px); right:clamp(3px,4cqi,12px); display:none; gap:clamp(2px,2cqi,6px); }
        .product-controls button { --isl-control-size:clamp(18px,13cqi,32px); display:flex; align-items:center; justify-content:center; appearance:none; -webkit-appearance:none; flex:none; width:var(--isl-control-size); min-width:var(--isl-control-size); max-width:var(--isl-control-size); height:var(--isl-control-size); min-height:var(--isl-control-size); max-height:var(--isl-control-size); aspect-ratio:1; margin:0; padding:0; border:0; border-radius:50%; line-height:0; color:#fff; box-shadow:0 2px 6px rgba(0,0,0,.22); }
        .product-controls .edit-product { background:#f9a825; }
        .product-controls button:focus-visible { outline-offset:1px; }
        .product-controls ha-icon { --mdc-icon-size:clamp(12px,8cqi,20px); display:flex; align-items:center; justify-content:center; flex:none; width:var(--mdc-icon-size); height:var(--mdc-icon-size); margin:0; padding:0; }
        .row-meta { display:none; }
        .grid.rows { grid-template-columns:minmax(0,1fr); gap:10px; }
        .rows .product { aspect-ratio:auto; min-height:80px; border-radius:12px; }
        .rows .product-top { position:relative; display:grid; grid-template-columns:48px minmax(0,1fr) auto; gap:12px; min-height:80px; padding:12px 58px 12px 16px; }
        .rows .product-media { width:48px; height:48px; }
        .rows .placeholder ha-icon { --mdc-icon-size:40px; }
        .rows .product-name { text-align:left; }
        .rows .title { font-size:clamp(14px,2.5cqi,18px); -webkit-line-clamp:3; text-align:left; }
        .rows .tags { display:none; }
        .rows .product-controls { display:flex; top:50%; right:12px; transform:translateY(-50%); }
        .rows .product-controls button { --isl-control-size:32px; }
        .rows .product-controls ha-icon { --mdc-icon-size:20px; }
        .rows .row-meta { display:flex; align-items:center; justify-content:flex-end; flex-wrap:wrap; gap:6px; max-width:min(36cqi,260px); }
        .row-price { display:inline-flex; align-items:center; justify-content:center; gap:5px; min-width:0; max-width:100%; padding:6px 9px; border-radius:16px; font-size:12px; line-height:1.2; }
        .row-price { background:var(--secondary-background-color,#edf4ee); white-space:nowrap; }.in-list .row-price { background:rgba(255,255,255,.2); }
        .row-meta ha-icon { --mdc-icon-size:18px; display:flex; align-items:center; justify-content:center; width:18px; height:18px; flex:none; }
        @media(max-width:650px) { .rows .product-top { grid-template-columns:36px minmax(0,1fr) auto; gap:8px; padding:10px 48px 10px 10px; }.rows .product-media { width:36px; height:36px; }.rows .placeholder ha-icon { --mdc-icon-size:32px; }.rows .product-controls { right:8px; }.rows .row-meta { max-width:30cqi; }.row-price { font-size:11px; padding:5px 7px; } }
        .row-quantity { position:relative; z-index:2; pointer-events:auto; display:inline-flex; align-items:center; justify-content:center; flex:none; gap:3px; height:34px; padding:3px; border-radius:16px; background:var(--secondary-background-color,#edf4ee); color:inherit; font-size:12px; font-weight:700; white-space:nowrap; }
        .in-list .row-quantity { background:rgba(255,255,255,.2); }
        .row-quantity button { display:grid; place-items:center; flex:none; width:28px; height:28px; min-height:28px; padding:0; border:0; border-radius:12px; background:transparent; color:inherit; }
        .quantity-value { min-width:0; max-width:9ch; overflow:hidden; text-overflow:ellipsis; }
        .rows .row-meta { max-width:min(45cqi,320px); }
        .rows .row-price { height:34px; box-sizing:border-box; }
        @media(max-width:650px) { .rows .row-meta { max-width:45cqi; } .quantity-value { max-width:5ch; } }
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
        .product-views { display:flex; flex-wrap:wrap; min-width:0; gap:6px; margin-top:18px; overflow-x:auto; scrollbar-width:thin; }
        .product-views button { display:inline-flex; flex:none; align-items:center; justify-content:center; gap:6px; padding:10px; font-size:13px; white-space:nowrap; border:0; background:transparent; }
        .product-views ha-icon { display:flex; align-items:center; justify-content:center; flex:none; width:20px; height:20px; --mdc-icon-size:20px; line-height:0; }
        .product-views button[aria-pressed=true] { background:color-mix(in srgb,var(--card-background-color,#fff) 75%,#000); font-weight:650; }
        #product-form h3 { font-size:15px; font-weight:650; line-height:1.4; margin:0 0 12px; }
        .product-main-row { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); align-items:end; gap:12px; }
        .product-main-row>* { min-width:0; }
        .product-main-row { grid-template-columns:repeat(2,minmax(0,1fr)); }
        @media(max-width:550px) { .product-main-row { gap:6px; }.product-main-row input { padding-inline:6px; }.product-main-row label { font-size:12px; }.product-main-row #add-product-category { flex-basis:28px;width:28px;padding:0; }.product-main-row .product-category-controls { gap:4px; }.product-main-row select { padding-inline:4px; } }

        .recurrence-controls { display:flex; align-items:center; flex-wrap:wrap; gap:8px; margin-top:12px; }
        .recurrence-controls label { display:flex; align-items:center; gap:8px; }
        .recurrence-controls input[type=checkbox] { width:20px; min-height:20px; margin:0; padding:0; accent-color:var(--primary-color,#267052); }
        .recurrence-controls input[type=number] { width:88px; margin:0; }
        .fields { display:grid; grid-template-columns:1fr 1fr; gap:16px; margin:22px 0; }
        .wide { grid-column:1/-1; }
        .form-actions { display:flex; justify-content:flex-end; gap:10px; margin-top:22px; }
        .form-actions.product-actions { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); }
        .product-actions button { min-width:0; padding:10px 8px; }
        .product-actions #save-product { grid-column:2; }
        #delete-product { background:#d32f2f; color:#fff; border:0; }
        @media(max-width:650px) { .filters { gap:8px; } .catalog-product-controls { gap:6px; } #products-view .catalog-product-controls button { flex-basis:40px; width:40px; height:44px; min-height:44px; } #catalog-search { height:44px; min-height:44px; } .grid { grid-template-columns:repeat(var(--isl-mobile-columns,1),minmax(0,1fr)); } .heading { gap:10px; } h1 { font-size:28px; } dialog { padding:20px; } }
        @media(max-width:650px) { .catalog-toolbar { gap:6px; } .catalog-tabs { gap:4px; } .catalog-tabs button { gap:4px; min-width:36px; justify-content:center; padding:10px 6px; font-size:13px; } .catalog-tabs button[aria-pressed=false] .tab-label { display:none; } .catalog-tabs button[aria-pressed=true] { flex-shrink:1; min-width:0; } .catalog-tabs .tab-label { min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; } }
        @media(max-width:390px) { .fields { grid-template-columns:1fr; } .heading { gap:6px; } .heading h1 { font-size:22px; } .catalog-toolbar { gap:4px; } .catalog-tabs { gap:3px; } .catalog-tabs button { min-width:28px; padding-inline:3px; font-size:12px; } .catalog-tabs ha-icon { --mdc-icon-size:18px; width:18px; height:18px; } .catalog-tools { gap:4px; } #new-catalog-category { width:32px; flex-basis:32px; height:44px; } }
        @media(max-width:360px) { .heading { gap:4px; } .heading h1 { font-size:18px; } .catalog-toolbar,.catalog-tabs { gap:2px; } .catalog-tabs button { gap:3px; min-width:24px; padding-inline:2px; } .catalog-tabs ha-icon { --mdc-icon-size:16px; width:16px; height:16px; } #new-catalog-category { width:30px; flex-basis:30px; } }
        .code-list { display:grid; gap:8px; margin:12px 0; }
        .code-row { display:flex; align-items:center; gap:12px; border:1px solid var(--divider-color,#dfe7e1); border-radius:10px; padding:8px 12px; min-width:0; }
        .code-value { flex:1; min-width:0; overflow-wrap:anywhere; user-select:text; }
        .code-remove { display:grid; place-items:center; width:36px; height:36px; min-height:36px; padding:0; border:0; background:#d32f2f; color:white; flex:none; }
        .code-remove ha-icon { width:20px; height:20px; --mdc-icon-size:20px; }
        .code-capture-controls { display:flex; align-items:center; gap:8px; flex-wrap:wrap; }
        .code-capture-controls select { flex:1; min-width:140px; }
        .code-capture-controls button { display:flex; align-items:center; justify-content:center; gap:6px; min-height:44px; }
        .code-capture-controls ha-icon { width:20px; height:20px; --mdc-icon-size:20px; }

        .recipe-card { background:linear-gradient(var(--isl-recipe-gradient-start,#66bb6a),var(--isl-recipe-gradient-end,#2e7d32)); color:#fff; }
        .recipe-card .title,.recipe-card .placeholder { color:inherit; }
        .recipe-card .product-controls { display:flex; }
        .recommendation-criteria { display:grid; grid-template-columns:repeat(min(var(--isl-columns,3),5),minmax(0,1fr)); gap:16px; }
        .recommendation-category-cards { display:contents; }
        .recommendation-criteria .season-criterion { aspect-ratio:1; flex-direction:column; justify-content:center; text-align:center; min-width:0; overflow-wrap:anywhere; }
        .recommendation-icon { display:grid; place-items:center; width:56px; height:56px; border-radius:50%; color:#fff; flex:none; }
        .recommendation-products h2 { display:flex; align-items:center; gap:10px; }
        @media(max-width:650px) { .recommendation-criteria { grid-template-columns:repeat(min(var(--isl-mobile-columns,1),2),minmax(0,1fr)); } .recommendation-criteria .season-criterion { padding:12px; font-size:13px; } }
        .season-criterion { display:flex; align-items:center; gap:14px; padding:24px; background:var(--card-background-color,#fff); font-weight:650; }
        .season-criterion ha-icon { --mdc-icon-size:32px; width:32px; height:32px; }
        .season-toolbar { display:flex; justify-content:flex-end; margin:20px 0; }
        .season-toolbar button { display:flex; align-items:center; gap:8px; background:#d32f2f; color:#fff; border:0; }
        .season-toolbar [aria-pressed=true] { background:#267052; color:white; border-color:transparent; }
        #season-calendar-dialog { width:min(960px,calc(100vw - 32px)); }
        .season-calendar { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:14px; }
        .season-month { border:1px solid var(--divider-color,#dfe7e1); border-radius:12px; padding:12px; min-width:0; }
        .season-month.current { border-color:var(--primary-color,#267052); }
        .season-month-heading { display:flex; align-items:center; justify-content:space-between; gap:6px; margin-bottom:12px; }
        .season-month h3 { font-size:16px; margin:0; }
        .season-month-add { display:grid; place-items:center; width:32px; min-height:32px; padding:0; flex:none; }
        .season-month-products { display:flex; flex-wrap:wrap; gap:10px; }
        .season-product { display:flex; align-items:center; justify-content:flex-start; gap:8px; max-width:100%; min-height:36px; padding:5px 12px 5px 8px; border:0; border-radius:20px; background:#267052; color:#fff; font-size:12px; text-align:left; overflow-wrap:anywhere; }
        .season-product:disabled { opacity:1; }
        .season-product-circle { display:grid; place-items:center; width:14px; height:14px; flex:none; }
        .season-product-circle img { width:100%; height:100%; object-fit:contain; }
        .season-product-circle ha-icon { width:12px; height:12px; --mdc-icon-size:12px; }
        .removing .season-product { background:#d32f2f; }
        .season-product-label { display:block; margin-top:22px; }
        .season-month-options { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:14px; margin:22px 0; border:1px solid var(--divider-color,#dfe7e1); border-radius:10px; padding:16px; }
        .season-month-options label { display:flex; align-items:center; gap:8px; font-size:14px; }
        .season-month-options input { width:18px; height:18px; margin:0; }
        @media(max-width:650px) { .season-calendar { grid-template-columns:repeat(2,minmax(0,1fr)); } .season-month-heading { flex-wrap:wrap; } .season-month h3 { flex:1 0 100%; font-size:14px; } .season-month-add { margin-left:auto; } .season-month-options { grid-template-columns:repeat(2,minmax(0,1fr)); } }
      </style>
      <div class="heading"><h1>Catálogo</h1>
      <div class="catalog-toolbar">
        <nav class="catalog-tabs" aria-label="Vistas del catálogo"><button id="view-products" aria-label="Productos" aria-pressed="true"><ha-icon icon="mdi:view-grid" aria-hidden="true"></ha-icon><span class="tab-label">Productos</span></button><button id="view-categories" aria-label="Categorías" aria-pressed="false"><ha-icon icon="mdi:label" aria-hidden="true"></ha-icon><span class="tab-label">Categorías</span></button><button id="view-recipes" aria-label="Recetas" aria-pressed="false"><ha-icon icon="mdi:chef-hat" aria-hidden="true"></ha-icon><span class="tab-label">Recetas</span></button><button id="view-recommendations" aria-label="Sugerencias" aria-pressed="false"><ha-icon icon="mdi:calendar-star" aria-hidden="true"></ha-icon><span class="tab-label">Sugerencias</span></button><button id="view-suggestions" aria-label="Nuevos" aria-pressed="false"><ha-icon icon="mdi:creation" aria-hidden="true"></ha-icon><span class="tab-label">Nuevos</span></button></nav>
        <div class="catalog-tools"><button id="new-catalog-category" class="primary" type="button" aria-label="Nueva categoría" title="Nueva categoría" hidden><ha-icon icon="mdi:plus-thick"></ha-icon></button></div>
      </div>
      </div>
      <div id="catalog-error" class="notice error" role="alert" hidden></div>
      <div id="catalog-status" class="notice" role="status" hidden></div>
      <section id="products-view">
      <div class="filters">
        <div class="search"><input id="catalog-search" type="search" aria-label="Buscar productos" placeholder="Nombre, código o etiqueta"></div>
        <div class="catalog-product-controls"><button id="new-product" class="primary" type="button" aria-label="Nuevo producto" title="Nuevo producto"><ha-icon icon="mdi:plus-thick" aria-hidden="true"></ha-icon></button><button id="toggle-catalog-order" type="button" aria-label="Agrupar por categorías" title="Agrupar por categorías" aria-pressed="false"><ha-icon icon="mdi:label" aria-hidden="true"></ha-icon></button><button id="configure-catalog-grouping" type="button" aria-label="Cambiar criterio de agrupación" title="Cambiar criterio de agrupación" hidden><ha-icon icon="mdi:tune" aria-hidden="true"></ha-icon></button><button id="toggle-catalog-layout" type="button" aria-label="Cambiar a vista de filas" title="Cambiar a vista de filas"><ha-icon icon="mdi:view-sequential" aria-hidden="true"></ha-icon></button></div>
      </div>
      <div id="catalog-grid" class="grid"></div>
      <p id="catalog-empty" class="empty" hidden></p>
      </section>
      <isl-categories id="catalog-categories" embedded hidden></isl-categories>
      <section id="recipes-view" hidden><div id="recipe-status" class="notice error" role="alert" hidden></div><div id="recipe-grid" class="grid"></div><p id="recipe-empty" class="helper">Crea una receta y selecciona sus ingredientes del catálogo.</p></section>
      <section id="recommendations-view" hidden>
        <div class="recommendation-criteria"><button id="open-seasonal" class="season-criterion" type="button"><ha-icon icon="mdi:calendar-month" aria-hidden="true"></ha-icon><span>Productos de temporada</span></button><div id="recommendation-category-cards" class="recommendation-category-cards"></div></div>
        <isl-categories id="recommendation-category-editor" editor-only product-assignment></isl-categories>
      </section>
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
      </section>
      <isl-recipe-editor></isl-recipe-editor>
      <dialog aria-labelledby="product-dialog-title">
        <form id="product-form">
          <div class="dialog-heading"><h2 id="product-dialog-title">Nuevo producto</h2></div>
          <p class="helper">Solo necesitas un nombre para empezar. Puedes completar el resto más adelante.</p>
          <div id="product-error" class="notice error" role="alert" hidden></div>
          <nav class="product-views" aria-label="Vistas de la ficha del producto">
            <button type="button" data-product-view="main" aria-label="Características" aria-pressed="true" aria-controls="product-main"><ha-icon icon="mdi:package-variant-closed" aria-hidden="true"></ha-icon><span class="tab-label">Características</span></button>
            <button type="button" data-product-view="additional" aria-label="Opciones" aria-pressed="false" aria-controls="product-additional"><ha-icon icon="mdi:format-list-text" aria-hidden="true"></ha-icon><span class="tab-label">Opciones</span></button>
            <button type="button" data-product-view="automation" aria-label="Automatización" aria-pressed="false" aria-controls="product-automation"><ha-icon icon="mdi:robot-outline" aria-hidden="true"></ha-icon><span class="tab-label">Automatización</span></button>
          </nav>
          <section id="product-main" class="fields" aria-label="Características">
            <div class="wide product-main-row">
              <label>Nombre del producto<input name="name" required maxlength="160" placeholder="Por ejemplo, Cacao"></label>
              <div><label for="product-category">Categoría</label><div class="product-category-controls"><select id="product-category" name="category"><option value="">Sin categoría</option></select><button id="add-product-category" type="button" aria-label="Nueva categoría" title="Nueva categoría"><ha-icon icon="mdi:plus-thick"></ha-icon></button></div></div>
            </div>
            <label class="wide">URL Imagen/Icono<input name="image_url" maxlength="2048" placeholder="https://… o /local/producto.png"></label>
            <isl-icon-picker class="wide"></isl-icon-picker>
          </section>
          <section id="product-additional" class="fields" aria-label="Opciones" hidden>
            <div class="wide"><h3 id="product-options-title">Opciones para comprar</h3><div class="store-link-add"><input id="product-link-value" type="url" pattern="https://.*" aria-label="URL del producto" maxlength="2048" placeholder="URL del producto" title="La tienda se detecta automáticamente a partir de la URL."><button id="retrieve-product-data" class="retrieve-option" type="button"><ha-icon icon="mdi:download" aria-hidden="true"></ha-icon>Recuperar datos</button><button id="add-product-store-link" type="button" aria-label="Añadir vinculación"><ha-icon icon="mdi:plus-thick" aria-hidden="true"></ha-icon></button></div><p id="option-lookup-status" class="helper" role="status" aria-live="polite"></p><div id="product-store-links"></div></div>
          </section>
          <section id="product-automation" class="fields" aria-label="Automatización" hidden>
            ${[["barcode","Códigos de barras/QR","mdi:barcode-scan"],["nfc","Etiquetas NFC","mdi:nfc-variant"]].map(([kind,title,icon])=>`<section id="product-${kind}-codes" class="wide product-codes" aria-label="${title}"><h3>${title}</h3><div id="${kind}-code-list" class="code-list"></div><div class="code-capture-controls"><select id="${kind}-capture-reader" aria-label="Lector para ${title}"></select><button id="${kind}-capture-start" type="button"><ha-icon icon="${icon}" aria-hidden="true"></ha-icon>Escanear</button><button id="${kind}-capture-stop" type="button" hidden>Detener</button></div><p id="${kind}-capture-status" class="helper" role="status"></p></section>`).join("")}
            <div class="wide"><h3>Acciones de los lectores</h3><div id="product-reader-actions"></div><p class="helper">La acción se aplica solo al reconocer este producto. Los cambios de stock afectan a la despensa común.</p></div>
            <div class="wide" id="product-recurrence"><h3>Recurrencia</h3><div class="recurrence-controls"><label><input name="recurrence_enabled" type="checkbox">Comprar cada</label><input name="recurrence_days" type="number" min="1" max="3650" step="1" value="7" aria-label="Días de recurrencia" disabled required><span>días</span></div><p class="helper">Comparte el modo Perecedero de Stock: al cumplirse el plazo se pondrá a cero y se añadirá a su lista de reposición, sin duplicados.</p></div>
          </section>
          <div class="form-actions product-actions"><button id="delete-product" type="button" hidden>Eliminar producto</button><button id="save-product" class="primary" type="submit">Guardar producto</button></div>
        </form>
        <isl-categories id="product-category-editor" editor-only></isl-categories>
      </dialog>
      <dialog id="delete-product-dialog" aria-labelledby="delete-product-title">
        <h2 id="delete-product-title">Eliminar producto</h2><p id="delete-product-description"></p>
        <div id="delete-product-error" class="notice error" role="alert" hidden></div>
        <div class="form-actions"><button id="cancel-delete-product" type="button">Cancelar</button><button id="confirm-delete-product" type="button" style="background:#d32f2f;color:#fff;border:0">Eliminar producto</button></div>
      </dialog>
      <dialog id="link-code-dialog" aria-labelledby="link-code-title">
        <h2 id="link-code-title">Asignar código a un producto</h2><p id="link-code-description" class="helper"></p>
        <div id="link-code-error" class="notice error" role="alert" hidden></div>
        <div id="link-code-search"></div><p id="link-code-selection" class="helper" role="status"></p>
        <div class="form-actions"><button id="cancel-link-code" type="button">Cancelar</button><button id="confirm-link-code" class="primary" type="button" disabled>Asignar</button></div>
      </dialog>
      <dialog id="season-calendar-dialog" aria-labelledby="season-calendar-title">
        <h2 id="season-calendar-title">Productos de temporada</h2>
        <div class="season-toolbar"><button id="season-delete-mode" type="button" aria-pressed="false" aria-label="Eliminar productos" title="Eliminar productos"><ha-icon icon="mdi:delete" aria-hidden="true"></ha-icon></button></div>
        <div id="season-error" class="notice error" role="alert" hidden></div><div id="season-calendar" class="season-calendar"></div>
      </dialog>
      <dialog id="season-add-dialog" aria-labelledby="season-add-title">
        <form id="season-add-form"><h2 id="season-add-title">Añadir producto de temporada</h2>
          <label class="season-product-label">Producto o receta del catálogo<input id="season-product-search" type="search" list="season-product-options" autocomplete="off" required placeholder="Buscar producto"></label><datalist id="season-product-options"></datalist>
          <fieldset class="season-month-options"><legend>Meses de temporada</legend></fieldset>
          <div id="season-add-error" class="notice error" role="alert" hidden></div>
          <div class="form-actions"><button id="season-save" class="primary" type="submit">Añadir</button></div>
        </form>
      </dialog>
      <dialog id="catalog-grouping-dialog" aria-labelledby="catalog-grouping-title">
        <h2 id="catalog-grouping-title">Agrupar productos por</h2>
        <div class="grouping-options"><button type="button" data-group-by="category" aria-pressed="true"><ha-icon icon="mdi:label" aria-hidden="true"></ha-icon>Categoría</button><button type="button" data-group-by="suggestions" aria-pressed="false"><ha-icon icon="mdi:calendar-star" aria-hidden="true"></ha-icon>Sugerencias</button><button type="button" data-group-by="store" aria-pressed="false"><ha-icon icon="mdi:store" aria-hidden="true"></ha-icon>Tienda</button></div>
      </dialog>`;
    this._built = true;
    const root = this.shadowRoot;
    installDialogCloseButtons(root);
    const addStoreLink = () => {
      const value = root.querySelector("#product-link-value").value.trim();
      const store = storeFromProductUrl(value);
      if(value&&!store){const status=root.querySelector('#option-lookup-status');status.textContent='Introduce una URL HTTPS de una tienda compatible.';status.dataset.error='true';return;}
      if (!store || !value) return;
      if(!this._storeLinks[store])this._storeLinks[store] = value;
      const url=value.startsWith('https://')?value:'',reference_id=url?'':value;
      let ref=this._commercialReferences.find(ref=>ref.store===store&&(url?ref.url===url:ref.reference_id===reference_id));
      if(!ref){ref={store,name:'',ean:'',reference_id,url,content_quantity:null,content_unit:'',content_confirmed:false};this._commercialReferences.push(ref);}else ref.active=true;
      root.querySelector("#product-link-value").value = "";
      this._renderStoreLinks();
      return ref;
    };
    root.querySelector("#add-product-store-link").addEventListener("click", addStoreLink);
    root.querySelector('#retrieve-product-data').addEventListener('click',()=>{const value=root.querySelector('#product-link-value').value.trim(),ref=addStoreLink();if(ref)void this._retrieveOption(ref,value);});
    root.querySelector("#product-link-value").addEventListener("keydown", event => {
      if (event.key === "Enter" && !event.isComposing) { event.preventDefault(); addStoreLink(); }
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
    root.querySelector('[name="name"]').addEventListener("input", () => { this._updateOptionTitle(); iconPicker.suggest(); });
    root.querySelector('[name="image_url"]').addEventListener("input", event => { iconPicker.value = event.target.value; });
    root.querySelector("dialog").addEventListener("close", () => { this._stopCodeCapture(); iconPicker.close(); this._optionGeneration=(this._optionGeneration||0)+1; this._resetNutriscores(); });
    for (const kind of ["barcode","nfc"]) {
      root.querySelector(`#${kind}-capture-start`).addEventListener("click",()=>void this._startCodeCapture(kind));
      root.querySelector(`#${kind}-capture-stop`).addEventListener("click",()=>this._stopCodeCapture());
    }
    root.querySelector("#cancel-link-code").addEventListener("click", () => root.querySelector("#link-code-dialog").close());
    root.querySelector("#confirm-link-code").addEventListener("click", () => void this._assignCode());
    root.querySelector("#link-code-dialog").addEventListener("cancel", event => { if (this._linkBusy) event.preventDefault(); });
    root.querySelector("#link-code-dialog").addEventListener("close", () => { if (root.querySelector("#link-code-dialog").open) return; this._linkReading = null; this._linkProductId = null; this._refreshLinkPredictions = null; });
    root.querySelector("#cancel-delete-product").addEventListener("click", () => root.querySelector("#delete-product-dialog").close());
    root.querySelector("#confirm-delete-product").addEventListener("click", () => void this._deleteProduct());
    root.querySelector("#delete-product").addEventListener("click", () => { if (this._editing) this._confirmDeleteProduct(this._editing); });
    root.querySelector("#delete-product-dialog").addEventListener("cancel", event => { if (this._deletingProduct) event.preventDefault(); });
    root.querySelector("#new-product").addEventListener("click", () => this._openProduct());
    root.querySelector("#view-products").addEventListener("click", () => this._switchView("products"));
    root.querySelector("#view-categories").addEventListener("click", () => this._switchView("categories"));
    root.querySelector("#view-recipes").addEventListener("click", () => this._switchView("recipes"));
    const recipeEditor = root.querySelector("isl-recipe-editor");
    recipeEditor.onSave = recipe => this._catalog.saveRecipe(recipe);
    recipeEditor.onDelete = recipe => this._catalog.deleteRecipe(recipe);
    recipeEditor.onClose = () => root.querySelector("#new-catalog-category").focus();
    root.querySelector("#view-recommendations").addEventListener("click", () => this._switchView("recommendations"));
    root.querySelector("#open-seasonal").addEventListener("click", () => {
      this._seasonRemoving = false; this._seasonError = ""; this._renderSeasonal();
      root.querySelector("#season-calendar-dialog").showModal();
    });
    root.querySelector("#season-delete-mode").addEventListener("click", () => { this._seasonRemoving = !this._seasonRemoving; this._renderSeasonal(); });
    root.querySelector("#season-add-form").addEventListener("submit", event => { event.preventDefault(); void this._saveSeasonal(); });
    root.querySelector("#season-add-dialog").addEventListener("cancel", event => { if (this._seasonBusy) event.preventDefault(); });
    root.querySelector("#view-suggestions").addEventListener("click", () => this._switchView("suggestions"));
    root.querySelector("isl-categories").onSave = category => this._catalog.saveCategory(category);
    root.querySelector("isl-categories").onDelete = category => this._catalog.deleteCategory(category);
    root.querySelector("isl-categories").onClose = () => root.querySelector("#new-catalog-category").focus();
    root.querySelector("#new-catalog-category").addEventListener("click", () => {
      if (this._view === "recipes") root.querySelector("isl-recipe-editor").open();
      else root.querySelector(this._view === "recommendations" ? "#recommendation-category-editor" : "#catalog-categories").create();
    });
    const suggestionEditor = root.querySelector("#recommendation-category-editor");
    suggestionEditor.onSave = category => this._catalog.saveRecommendationCategory(category);
    suggestionEditor.onDelete = category => this._catalog.deleteRecommendationCategory(category);
    suggestionEditor.onClose = () => root.querySelector("#new-catalog-category").focus();
    const categoryEditor = root.querySelector("#product-category-editor");
    categoryEditor.onSave = async category => {
      const saved = await this._catalog.saveCategory(category);
      root.querySelector("#product-category").value = saved.name;
      return saved;
    };
    categoryEditor.onClose = () => root.querySelector("#add-product-category").focus();
    root.querySelector("#add-product-category").addEventListener("click", () => categoryEditor.create());
    root.querySelector("#toggle-catalog-layout").addEventListener("click", () => {
      this._productLayout = this._productLayout === "grid" ? "rows" : "grid";
      try { localStorage.setItem("isl-catalog-layout", this._productLayout); } catch { /* Storage may be disabled. */ }
      this._renderProducts();
      this.dispatchEvent(new CustomEvent("catalog-layout-change"));
    });
    root.querySelector("#catalog-search").addEventListener("input", () => this._renderProducts());
    root.querySelector("#toggle-catalog-order").addEventListener("click", () => {
      this._productOrder = this._productOrder === "alphabetical" ? "categories" : "alphabetical";
      try { localStorage.setItem("isl-catalog-order", this._productOrder); } catch { /* Storage may be disabled. */ }
      this._renderProducts();
    });
    root.querySelector("#configure-catalog-grouping").addEventListener("click", () => root.querySelector("#catalog-grouping-dialog").showModal());
    const pendingFilter=element('button','','');pendingFilter.type='button';pendingFilter.id='pending-formats';pendingFilter.setAttribute('aria-label','Mostrar formatos pendientes de revisar');pendingFilter.title='Formatos pendientes de revisar';pendingFilter.setAttribute('aria-pressed','false');pendingFilter.innerHTML='<ha-icon icon="mdi:package-variant-closed-alert" aria-hidden="true"></ha-icon>';
    pendingFilter.addEventListener('click',()=>{this._pendingFormats=!this._pendingFormats;pendingFilter.setAttribute('aria-pressed',String(this._pendingFormats));this._renderProducts();});
    root.querySelector('.catalog-product-controls').append(pendingFilter);
    for (const button of root.querySelectorAll("[data-group-by]")) button.addEventListener("click", () => {
      this._groupBy = button.dataset.groupBy;
      try { localStorage.setItem("isl-catalog-grouping", this._groupBy); } catch { /* Storage may be disabled. */ }
      root.querySelector("#catalog-grouping-dialog").close();
      this._renderProducts();
    });
    root.querySelector("#catalog-grouping-dialog").addEventListener("close", () => {
      if (this.isConnected && !root.querySelector("#configure-catalog-grouping").hidden) root.querySelector("#configure-catalog-grouping").focus();
    });
    root.querySelector('[name="recurrence_enabled"]').addEventListener("change", () => {
      root.querySelector('[name="recurrence_days"]').disabled = !root.querySelector('[name="recurrence_enabled"]').checked;
    });
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
    root.querySelector("#new-catalog-category").hidden = !["categories","recommendations","recipes"].includes(view);
    root.querySelector("#new-catalog-category").disabled = ["recommendations","recipes"].includes(view) && !this._hass?.user?.is_admin;
    root.querySelector("#new-catalog-category").setAttribute("aria-label", view === "recipes" ? "Nueva receta" : view === "recommendations" ? "Nueva categoría de sugerencias" : "Nueva categoría");
    root.querySelector("#new-catalog-category").title = view === "recommendations" ? "Nueva categoría de sugerencias" : "Nueva categoría";
    root.querySelector("isl-categories").hidden = view !== "categories";
    root.querySelector("#recipes-view").hidden = view !== "recipes";
    root.querySelector("#view-recipes").setAttribute("aria-pressed",String(view === "recipes"));
    root.querySelector("#recommendations-view").hidden = view !== "recommendations";
    root.querySelector("#view-recommendations").setAttribute("aria-pressed", String(view === "recommendations"));
    root.querySelector("#suggestions-view").hidden = view !== "suggestions";
    root.querySelector("#view-products").setAttribute("aria-pressed", String(view === "products"));
    root.querySelector("#view-categories").setAttribute("aria-pressed", String(view === "categories"));
    root.querySelector("#view-suggestions").setAttribute("aria-pressed", String(view === "suggestions"));
    this._render();
  }

  _render() {
    if (!this._hass || !this._active && !this._receiptCreate) return;
    if (!this._built) return;
    const root = this.shadowRoot;
    const error = root.querySelector("#catalog-error");
    this.attention=this._newProductCount??0;
    error.hidden = !this._catalog.error;
    error.textContent = this._catalog.error;
    const status = root.querySelector("#catalog-status");
    status.hidden = !this._catalog.loading;
    status.textContent = this._catalog.loading ? "Cargando catálogo…" : "";
    const categories = this._catalog.categories.map(category => category.name).sort((a, b) => a.localeCompare(b, "es"));
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

  _seasonEntries() {
    return [...this._catalog.products, ...(this._catalog.recipes ?? []).map(recipe=>({...recipe,_kind:"recipe",displayName:"Receta · "+recipe.name,icon:"mdi:chef-hat",category:"",image_url:"",tags:[]}))];
  }

  _renderRecipes() {
    if (!this._hass || !this._active && !this._receiptCreate) return;
    if (!this._built) return;
    const root=this.shadowRoot, recipes=this._catalog.recipes??[];
    root.querySelector('isl-recipe-editor').products=this._catalog.products;
    root.querySelector('#recipe-grid').replaceChildren(...recipes.map(recipe=>this._recipeCard(recipe)));
    root.querySelector('#recipe-empty').hidden=recipes.length>0;
    const status=root.querySelector('#recipe-status');status.hidden=!this._recipeError;status.textContent=this._recipeError??'';
  }

  _recipeCard(recipe) {
    const card=element('article','product recipe-card');card.dataset.recipeId=recipe.id;
    const add=element('button','add-product');add.type='button';add.setAttribute('aria-label','Añadir receta '+recipe.name+' a la lista');add.disabled=!this._canAdd||Boolean(this._addingRecipe)||!this._hass?.user?.is_admin;
    add.addEventListener('click',()=>void this._addRecipe(recipe));
    const content=element('div','product-top'),media=element('div','product-media'),icon=element('ha-icon');icon.setAttribute('icon','mdi:chef-hat');icon.setAttribute('aria-hidden','true');
    const placeholder=element('div','image placeholder');placeholder.append(icon);
    const source=imageSource(recipe.image_url);
    if(source){const image=element('img','image');image.src=source;image.alt='';image.loading='lazy';image.referrerPolicy='no-referrer';image.addEventListener('error',()=>image.replaceWith(placeholder),{once:true});media.append(image);}
    else media.append(placeholder);
    const title=element('div','product-name');title.append(element('h2','title',recipe.name));content.append(media,title);
    const actions=element('div','product-controls'),edit=iconButton('mdi:note-edit','Editar receta '+recipe.name,'edit-product');edit.disabled=!this._hass?.user?.is_admin;
    edit.addEventListener('click',()=>this.shadowRoot.querySelector('isl-recipe-editor').open(recipe));actions.append(edit);card.append(add,content,actions);return card;
  }

  async _addRecipe(recipe) {
    if(!this._canAdd||this._addingRecipe||!this._listEntity)return;
    this._addingRecipe=recipe.id;this._recipeError='';this._catalog.error='';this._renderProducts();
    try{
      const result=await this._hass.callWS({type:'improved_shopping_list/catalog/recipe/add',recipe_id:recipe.id,revision:recipe.revision,entity_id:this._listEntity});
      if(result.error)throw new Error((result.applied?.length ? 'Se han procesado '+result.applied.length+' ingredientes. ' : '')+result.error);
    }catch(error){this._recipeError=error.message??'No se ha podido añadir la receta.';}
    finally{this._addingRecipe=null;this._renderProducts();if(this._recipeError)this._catalog.error=this._recipeError;this._render();}
  }

  _seasonMonth() {
    try { return Number(new Intl.DateTimeFormat("en", {month:"numeric", timeZone:this._hass?.config?.time_zone}).format(new Date())); }
    catch { return new Date().getMonth() + 1; }
  }

  _renderSeasonal() {
    if (!this._built) return;
    const root = this.shadowRoot, month = this._seasonMonth();
    const products = this._seasonEntries().sort((a,b)=>a.name.localeCompare(b.name,"es",{sensitivity:"base"}));
    const toggle = root.querySelector("#season-delete-mode");
    toggle.setAttribute("aria-pressed", String(Boolean(this._seasonRemoving)));
    toggle.disabled = Boolean(this._seasonBusy) || !this._hass?.user?.is_admin;
    const toggleLabel = this._seasonRemoving ? "Terminar de eliminar" : "Eliminar productos";
    toggle.setAttribute("aria-label", toggleLabel);
    toggle.title = toggleLabel;
    toggle.querySelector("ha-icon").setAttribute("icon", this._seasonRemoving ? "mdi:plus-thick" : "mdi:delete");
    const error = root.querySelector("#season-error");
    error.hidden = !this._seasonError; error.textContent = this._seasonError || "";
    this._renderRecommendationCategories();
    const calendar = root.querySelector("#season-calendar");
    const focused = calendar.contains(root.activeElement) ? root.activeElement?.dataset.seasonKey : null;
    calendar.classList.toggle("removing", Boolean(this._seasonRemoving));
    calendar.replaceChildren(...MONTHS.map((name,index)=>{
      const number = index+1, section = element("section","season-month"), header = element("div","season-month-heading");
      section.dataset.month = number; section.classList.toggle("current", month === number);
      const add = iconButton("mdi:plus-thick", "Añadir producto a " + name, "season-month-add");
      add.dataset.seasonKey = "add-" + number;
      add.disabled = Boolean(this._seasonBusy || this._catalog.loading) || !this._hass?.user?.is_admin || !products.length;
      add.addEventListener("click",()=>this._openSeasonAdd(number));
      header.append(element("h3","",name),add);
      const items = element("div","season-month-products");
      for (const product of products.filter(product=>(product.season_months??[]).includes(number))) {
        const button = element("button","season-product"); button.type = "button";
        button.dataset.seasonKey = product.id + "-" + number;
        button.setAttribute("aria-label", (this._seasonRemoving ? "Eliminar " : "") + product.name + " de " + name);
        button.disabled = !this._seasonRemoving || Boolean(this._seasonBusy) || !this._hass?.user?.is_admin;
        const circle = element("span","season-product-circle"), icon = element("ha-icon");
        const category = this._catalog.categories.find(item=>normalizedName(item.name)===normalizedName(product.category));
        icon.setAttribute("icon",product.icon || category?.icon || "mdi:shopping"); icon.setAttribute("aria-hidden","true");
        const source = imageSource(product.image_url);
        if (source) {
          const image = element("img"); image.src=source; image.alt=""; image.loading="lazy"; image.referrerPolicy="no-referrer";
          image.addEventListener("error",()=>image.replaceWith(icon),{once:true}); circle.append(image);
        } else circle.append(icon);
        button.append(circle,element("span","",product.name));
        button.addEventListener("click",()=>void this._removeSeasonal(product.id,number,product._kind)); items.append(button);
      }
      section.append(header,items); return section;
    }));
    if (focused) [...calendar.querySelectorAll("[data-season-key]")].find(node=>node.dataset.seasonKey===focused)?.focus();
  }

  _renderRecommendationCategories() {
    const root = this.shadowRoot, groups = this._catalog.recommendationCategories ?? [];
    root.querySelector("#recommendation-category-editor").products = this._catalog.products;
    root.querySelector("#recommendation-category-editor").recipes = this._catalog.recipes;
    root.querySelector("#recommendation-category-cards").replaceChildren(...groups.map(group=>{
      const button = element("button","season-criterion"), badge = element("span","recommendation-icon"), icon = element("ha-icon");
      button.type="button"; button.setAttribute("aria-label","Editar categoría de sugerencias " + group.name);
      button.disabled = !this._hass?.user?.is_admin;
      badge.style.backgroundColor=group.color; icon.setAttribute("icon",group.icon); icon.setAttribute("aria-hidden","true");
      badge.append(icon); button.append(badge,element("span","",group.name));
      button.addEventListener("click",()=>root.querySelector("#recommendation-category-editor").edit(group));
      return button;
    }));
  }

  _openSeasonAdd(month) {
    const root = this.shadowRoot;
    root.querySelector("#season-add-form").reset();
    root.querySelector("#season-add-error").hidden = true;
    const options = root.querySelector("#season-product-options");
    options.replaceChildren(...this._seasonEntries().map(product=>new Option(product.displayName ?? product.name,product.displayName ?? product.name)));
    const months = root.querySelector(".season-month-options");
    months.querySelectorAll("label").forEach(label=>label.remove());
    MONTHS.forEach((name,index)=>{
      const label = element("label"), checkbox = element("input");
      checkbox.type="checkbox"; checkbox.name="season_month"; checkbox.value=index+1; checkbox.checked=index+1===month;
      label.append(checkbox,document.createTextNode(name)); months.append(label);
    });
    root.querySelector("#season-add-dialog").showModal(); root.querySelector("#season-product-search").focus();
  }

  async _saveSeasonal() {
    if (this._seasonBusy) return;
    const root = this.shadowRoot, error = root.querySelector("#season-add-error");
    const name = productNameKey(root.querySelector("#season-product-search").value);
    const matches = this._seasonEntries().filter(product=>productNameKey(product.displayName ?? product.name)===name);
    const months = [...root.querySelectorAll('[name="season_month"]:checked')].map(input=>Number(input.value));
    if (matches.length !== 1 || !months.length) {
      error.textContent = matches.length !== 1 ? "Selecciona un producto o receta del catálogo." : "Selecciona al menos un mes.";
      error.hidden = false; return;
    }
    this._seasonBusy = true; root.querySelector("#season-save").disabled = true;
    this._renderSeasonal();
    try {
      if (matches[0]._kind === "recipe") await this._catalog.setRecipeSeasonMonths(matches[0].id,months,true);
      else await this._catalog.setSeasonMonths(matches[0].id,months,true);
      root.querySelector("#season-add-dialog").close();
    } catch (err) { error.textContent = err.message || "No se ha podido guardar la temporada."; error.hidden = false; }
    finally { this._seasonBusy=false; root.querySelector("#season-save").disabled=false; this._renderSeasonal(); }
  }

  async _removeSeasonal(productId, month, kind) {
    if (this._seasonBusy || !this._seasonRemoving) return;
    this._seasonBusy=true; this._seasonError=""; this._renderSeasonal();
    try { if (kind === "recipe") await this._catalog.setRecipeSeasonMonths(productId,[month],false); else await this._catalog.setSeasonMonths(productId,[month],false); }
    catch (err) { this._seasonError=err.message || "No se ha podido quitar el producto de este mes."; }
    finally { this._seasonBusy=false; this._renderSeasonal(); }
  }

  _renderSuggestions() {
    if (!this._hass || !this._active && !this._receiptCreate) return;
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
      const shared = hint.source === "community";
      const source = element("a", "subtitle", shared ? "Fuente: Diccionario comunitario" : "Fuente: Open Food Facts (ODbL)");
      source.href = shared ? "https://github.com/TitoTB/Improved-Shopping-List/tree/data/community" : `https://world.openfoodfacts.org/product/${encodeURIComponent(item.code)}`;
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
    } catch (error) {
      const notice = root.querySelector("#link-code-error");
      notice.textContent = error.message ?? "No se ha podido asignar el código al producto.";
      notice.hidden = false;
    } finally {
      this._linkBusy = false;
      this._render();
    }
  }

  _productCodeKey(kind, code) {
    return kind === "nfc" ? (/^[0-9a-f:-]+$/i.test(code) ? code.replace(/[:-]/g,"").toLowerCase() : code.toLowerCase()) : code;
  }

  _addProductCode(kind, value) {
    if (!this._productCodes || !["barcode","nfc"].includes(kind) || typeof value !== "string") return false;
    const code=value.trim();
    if (!code || code.length>1024 || /[\x00-\x1f]/.test(code)) return false;
    const values=this._productCodes[kind], key=this._productCodeKey(kind,code);
    if (values.some(value=>this._productCodeKey(kind,value)===key)) return false;
    values.push(code);
    this._resetNutriscores();
    return true;
  }

  _renderProductCodes() {
    const root=this.shadowRoot;
    if (!this._built || !root.querySelector("#barcode-code-list")) return;
    const admin=this._hass?.user?.is_admin === true;
    for (const kind of ["barcode","nfc"]) {
      const values=this._productCodes?.[kind] ?? [], readers=(this._readers?.readers??[]).filter(reader=>reader.kind===kind&&reader.enabled);
      const select=root.querySelector(`#${kind}-capture-reader`), previous=this._codeCapture?.kind===kind ? this._codeCapture.readerId : select.value;
      select.replaceChildren(...(readers.length ? readers.map(reader=>new Option(reader.name,reader.id)) : [new Option("No hay lectores activos de este tipo","")]));
      if (readers.some(reader=>reader.id===previous)) select.value=previous;
      select.disabled=!admin||this._saving||Boolean(this._codeCapture)||!readers.length;
      root.querySelector(`#${kind}-code-list`).replaceChildren(...(values.length ? values.map((code,index)=>{
        const row=element("div","code-row");
        row.append(element("span","code-value",code));
        const remove=iconButton("mdi:delete",`Quitar código ${code}`,"code-remove");
        remove.disabled=!admin||this._saving;
        remove.addEventListener("click",()=>{this._productCodes[kind].splice(index,1);this._resetNutriscores();this._renderProductCodes();});
        row.append(remove);return row;
      }) : [element("p","helper",kind==="barcode"?"Sin códigos de barras/QR asociados.":"Sin etiquetas NFC asociadas.")]));
      const capturing=this._codeCapture?.kind===kind;
      root.querySelector(`#${kind}-capture-start`).hidden=capturing;
      root.querySelector(`#${kind}-capture-start`).disabled=!admin||this._saving||Boolean(this._codeCapture)||!readers.length||values.length>=50;
      root.querySelector(`#${kind}-capture-stop`).hidden=!capturing;
      root.querySelector(`#${kind}-capture-status`).textContent=capturing ? "Escanea con el lector seleccionado. Las lecturas se guardarán al guardar el producto. La captura termina tras 60 segundos." : this._scanNotice?.kind===kind ? this._scanNotice.text : readers.length ? "" : "Añade y activa un lector en el apartado Lectores para capturar códigos.";
    }
  }

  _stopCodeCapture() {
    const capture=this._codeCapture;
    this._codeCapture=null;
    if (capture?.stop) { try { Promise.resolve(capture.stop()).catch(()=>{}); } catch { /* Disconnected. */ } }
    this._renderProductCodes();
  }

  async _startCodeCapture(kind) {
    const root=this.shadowRoot, readerId=root.querySelector(`#${kind}-capture-reader`).value;
    if (this._codeCapture || this._saving || this._hass?.user?.is_admin !== true || !readerId || !root.querySelector("dialog").open) return;
    const capture={kind,readerId};this._codeCapture=capture;this._scanNotice=null;this._renderProductCodes();
    try {
      const stop=await this._hass.connection.subscribeMessage(reading=>{
        if (this._codeCapture!==capture) return;
        if (reading.status!=="scanned") {
          this._scanNotice={kind,text:reading.status==="expired"?"Captura finalizada. Pulsa Escanear para continuar.":"La captura se ha detenido."};
          this._stopCodeCapture();return;
        }
        if (reading.kind!==kind || reading.reader_id!==readerId || !root.querySelector("dialog").open) return;
        if (this._productCodes[kind].length>=50) {
          this._scanNotice={kind,text:"Puedes asignar hasta 50 códigos de cada tipo."};this._stopCodeCapture();return;
        }
        this._addProductCode(kind,reading.code);
        this._renderProductCodes();
      },{type:"improved_shopping_list/readers/capture",reader_id:readerId});
      if (this._codeCapture===capture) capture.stop=stop;
      else { try { await stop(); } catch { /* Closed before subscription resolved. */ } }
    } catch(error) {
      if (this._codeCapture===capture) {
        this._scanNotice={kind,text:error.message??"No se pudo iniciar la captura."};this._stopCodeCapture();
      }
    }
  }

  _renderReaderActions() {
    if (!this._built) return;
    const container = this.shadowRoot.querySelector("#product-reader-actions");
    const signature = JSON.stringify((this._readers?.readers ?? []).map(reader => [reader.id, reader.name, reader.default_action]));
    if (signature === this._readerSignature) return;
    this._readerSignature = signature;
    const nodes = (this._readers?.readers ?? []).map(reader => {
      const wrap = element("div");wrap.style.marginTop="12px";
      const label = element("label", "", reader.name);
      const select = element("select");
      select.id = `action-${reader.id}`;label.htmlFor=select.id;select.dataset.readerAction=reader.id;
      const defaults={none:"Sin acción",add_list:"Añadir a la lista",stock_remove:"Quitar stock",stock_add:"Añadir stock"};
      const selected=this._readerActionDraft?.[reader.id] ?? "default";
      for (const [value,text] of [["default",`Usar acción por defecto del lector (${defaults[reader.default_action]??defaults.none})`],["none","Sin acción"],["add_list","Añadir a la lista de la compra"],["stock_remove","Quitar una unidad al stock"],["stock_add","Añadir una unidad al stock"]]) select.append(new Option(text,value,value===selected,value===selected));
      select.addEventListener("change",()=>{
        this._readerActionDraft ??= {};
        if(select.value === "default") delete this._readerActionDraft[reader.id];
        else this._readerActionDraft[reader.id]=select.value;
      });
      wrap.append(label,select);return wrap;
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
    this._render();
    try {
      await this._catalog.actOnSuggestion(name, action);
    } catch (error) {
      this._suggestionError = error.message ?? "No se ha podido guardar el cambio.";
    } finally {
      this._suggestionBusy = false;
      this._render();
    }
  }

  _renderProducts() {
    if (!this._hass || !this._active && !this._receiptCreate) return;
    if (!this._built) return;
    const root = this.shadowRoot;
    const query = productNameKey(root.querySelector("#catalog-search").value);
    const rows = this._productLayout === "rows";
    const grouped = this._productOrder === "categories", grid = root.querySelector("#catalog-grid");
    grid.classList.toggle("rows", rows);
    grid.classList.toggle("grouped", grouped);
    const orderToggle = root.querySelector("#toggle-catalog-order"), orderLabel = grouped ? "Ordenar alfabéticamente" : this._groupBy === "store" ? "Agrupar por tienda" : this._groupBy === "suggestions" ? "Agrupar por sugerencias" : "Agrupar por categorías";
    root.querySelector("#configure-catalog-grouping").hidden = !grouped;
    for (const button of root.querySelectorAll("[data-group-by]")) button.setAttribute("aria-pressed",String(button.dataset.groupBy === this._groupBy));
    orderToggle.setAttribute("aria-label", orderLabel); orderToggle.title = orderLabel;
    orderToggle.setAttribute("aria-pressed", String(grouped));
    orderToggle.querySelector("ha-icon").setAttribute("icon", grouped ? "mdi:sort-alphabetical-ascending" : this._groupBy === "store" ? "mdi:store" : "mdi:label");
    const toggle = root.querySelector("#toggle-catalog-layout"), label = rows ? "Cambiar a vista de cuadrícula" : "Cambiar a vista de filas";
    toggle.setAttribute("aria-label", label); toggle.title = label;
    toggle.querySelector("ha-icon").setAttribute("icon", rows ? "mdi:view-comfy" : "mdi:view-sequential");
    const products = this._catalog.products.filter(product =>(!this._pendingFormats||(product.commercial_references??[]).some(ref=>ref.active!==false&&!ref.content_confirmed))).filter(product =>
      [product.name, product.barcode, ...(product.barcodes??[]), ...(product.nfc_tags??[]), product.category, ...(product.tags??[])].some(value=>productNameKey(value).includes(query)))
      .sort((a,b) => a.name.localeCompare(b.name,"es",{sensitivity:"base"}));
    if (grouped) {
      const expanded = new Set([...grid.querySelectorAll('details.category-group[open]')].map(group=>group.dataset.groupKey));
      const categories = new Map(this._catalog.categories.map(category => [normalizedName(category.name),category.name]));
      const groups = new Map();
      for (const product of products) {
        if (this._groupBy === "store") {
          for (const [store,name] of Object.entries(STORE_NAMES)) {
            const link=product.store_links?.[store];
            const options=(product.commercial_references??[]).filter(ref=>ref.store===store);
            const associated=options.some(ref=>ref.active!==false&&(ref.url||ref.reference_id||ref.ean));
            // Saved purchase options are independent of account/catalog consent.
            // Retain legacy links/tickets only when no explicit options exist.
            if(!associated&&(options.length||!this._stores?.[store]?.enabled||(!(typeof link==="string"?link.trim():link?.id||link?.url)&&!this._receiptStores?.[product.id]?.includes(store))))continue;
            if(!groups.has(store))groups.set(store,{key:store,name,products:[]});
            groups.get(store).products.push(product);
          }
          continue;
        }
        if (this._groupBy === "suggestions") {
          const matches = (this._catalog.recommendationCategories ?? []).filter(group=>group.product_ids.includes(product.id)).map(group=>({key:"custom:"+group.id,name:group.name}));
          if ((product.season_months ?? []).includes(this._seasonMonth())) matches.push({key:"season",name:"Productos de temporada"});
          for (const match of matches) {
            if (!groups.has(match.key)) groups.set(match.key,{...match,products:[]});
            groups.get(match.key).products.push(product);
          }
          continue;
        }
        const key = normalizedName(product.category);
        const name = categories.get(key) || product.category || "Sin categoría";
        if (!groups.has(key)) groups.set(key,{key,name,products:[]});
        groups.get(key).products.push(product);
      }
      grid.replaceChildren(...[...groups.values()].sort((a,b) => Number(!a.key)-Number(!b.key) || a.name.localeCompare(b.name,"es",{sensitivity:"base"})).map(group => {
        const section = element("details","category-group");
        section.dataset.groupKey=this._groupBy+':'+group.key;
        section.open=expanded.has(section.dataset.groupKey);
        section.setAttribute("aria-label",group.name);
        const items = element("div",rows ? "grid rows category-products" : "grid category-products");
        items.append(...group.products.map(product => this._productCard(product)));
        const heading=element("h2","category-group-title");
        if(this._groupBy === "category") {
          const category=this._catalog.categories.find(category=>normalizedName(category.name)===group.key);
          const icon=element("ha-icon");icon.setAttribute("icon",category?.icon || "mdi:label-outline");icon.setAttribute("aria-hidden","true");heading.append(icon);
        }
        if(this._groupBy === "store") {
          const circle=element('span','category-store-logo');circle.setAttribute('aria-hidden','true');
          const image=element('img');image.src=storeLogo(group.key);image.alt='';image.referrerPolicy='no-referrer';circle.append(image);heading.append(circle);
        }
        heading.append(document.createTextNode(group.name+(this._groupBy === "store"?" ("+group.products.length+")":"")));
        const summary=element('summary','category-group-toggle');summary.append(heading);
        section.append(summary,items);
        return section;
      }));
    } else grid.replaceChildren(...products.map(product => this._productCard(product)));
    const empty = root.querySelector("#catalog-empty");
    empty.hidden = grid.childElementCount > 0 || this._catalog.loading || Boolean(this._catalog.error);
    empty.textContent = this._catalog.products.length ? "No hay productos que coincidan con estos filtros." : "Tu catálogo empieza aquí. Añade el primer producto para tenerlo a mano en tu próxima compra.";
    this._renderSeasonal();
    this._renderRecipes();
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
    add.title = inList ? `Marcar ${product.name} como comprado en «${this._listName}»` : this._canAdd ? `Añadir ${product.name} a «${this._listName}»` : "Selecciona una lista disponible en el apartado Lista para añadir productos.";
    add.setAttribute("aria-label", inList ? `Marcar ${product.name} como comprado` : `Añadir ${product.name} a la lista`);
    add.disabled = !(inList ? this._canComplete : this._canAdd) || Boolean(this._adding);
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
    if (this._productLayout === "rows") {
      const metadata = element("div","row-meta");
      const offer = this._priceData?.enabled === false ? null : cachedProductPrice(product,this._priceData?.offers,this._priceData?.favorite);
      if (offer) {
        const badge = element("span","row-price");
        badge.title = offer.store ? `Último precio guardado · ${({mercadona:"Mercadona",carrefour:"Carrefour",alcampo:"Alcampo",consum:"Consum",lasirena:"La Sirena",eroski:"Eroski",dia:"DIA",lidl:"Lidl"})[offer.store] ?? offer.store}` : "Precio manual";
        const icon = element("ha-icon"); icon.setAttribute("icon","mdi:cash-multiple"); icon.setAttribute("aria-hidden","true");
        badge.append(icon,element("span","",new Intl.NumberFormat("es-ES",{style:"currency",currency:offer.currency}).format(Number(offer.price))));
        metadata.append(badge);
      }
      if(this._view === 'products')metadata.append(this._quantityControl(product));
      top.append(metadata);
    }
    card.append(top);
    if (product.tags.length) {
      const tags = element("div", "tags");
      tags.append(...product.tags.map(tag => element("span", "tag", tag)));
      top.append(tags);
    }
    const controls = element("div", "product-controls");
    const edit = iconButton("mdi:note-edit", `Editar ${product.name}`, "edit-product");
    edit.addEventListener("click", event => { event.stopPropagation(); this._openProduct(product); });
    controls.append(edit);
    card.append(controls);
    return card;
  }

  _quantityControl(product) {
    const items=this._listItems.filter(item=>productNameKey(item.summary)===productNameKey(product.name));
    const item=items.find(item=>item.status!=='completed')??items[0];
    const value=purchaseQuantity(product,item ? this._quantityData?.entries?.[item.uid] : null);
    const controls=element('div','row-quantity');controls.setAttribute('role','group');controls.setAttribute('aria-label','Cantidad de '+product.name);
    const label=element('span','quantity-value',quantityLabel(value));label.title=label.textContent;
    const locked=this._quantityData?.locked||!this._quantityData?.loaded||this._quantityData?.loading||this._adjustingQuantity||!item?.uid||!this.onAdjustQuantity||this._hass?.user?.is_admin!==true;
    for(const [direction,icon] of [[-1,'mdi:minus-thick'],[1,'mdi:plus-thick']]){
      const button=iconButton(icon,(direction>0?'Aumentar':'Disminuir')+' cantidad: '+product.name);
      const next=Math.round((value.quantity+direction*value.step)*1000)/1000;
      button.disabled=Boolean(locked||next<=0||next>1000000);
      button.dataset.quantityProduct=product.id;button.dataset.quantityDirection=String(direction);
      button.title=item ? (direction>0?'+':'−')+' '+quantityLabel({quantity:value.step,unit:value.unit}) : 'Añade el producto a la lista para ajustar su cantidad';
      button.addEventListener('click',event=>{event.stopPropagation();void this._adjustQuantity(product,item,direction);});
      if(direction>0)controls.append(label);controls.append(button);
    }
    return controls;
  }

  async _adjustQuantity(product,item,direction) {
    if(this._adjustingQuantity||!item?.uid||!this.onAdjustQuantity)return;
    const entity=this._listEntity;
    this._adjustingQuantity=true;this._catalog.error='';this._renderProducts();
    try { await this.onAdjustQuantity(entity,item.uid,direction); }
    catch(error){this._catalog.error=error.message??'No se ha podido cambiar la cantidad.';}
    finally {
      this._adjustingQuantity=false;this._render();
      if(this._active&&this._listEntity===entity)[...this.shadowRoot.querySelectorAll('[data-quantity-product]')].find(button=>button.dataset.quantityProduct===product.id&&Number(button.dataset.quantityDirection)===direction)?.focus();
    }
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
    root.querySelectorAll("#save-product,#delete-product").forEach(button => { button.disabled = true; });
    root.querySelectorAll("#delete-product-dialog button").forEach(button => { button.disabled = true; });
    root.querySelector("#delete-product-error").hidden = true;
    try {
      await this._catalog.deleteProduct(this._deleteTarget);
      root.querySelector("#delete-product-dialog").close();
      if (this._editing?.id === this._deleteTarget.id) {
        root.querySelector("#product-form").closest("dialog").close();
        this._editing = null;
      }
      this._render();
      root.querySelector("#new-product").focus();
    } catch (error) {
      const notice = root.querySelector("#delete-product-error");
      notice.textContent = error.message ?? "No se ha podido eliminar el producto.";
      notice.hidden = false;
    } finally {
      this._deletingProduct = false;
      root.querySelectorAll("#save-product,#delete-product").forEach(button => { button.disabled = false; });
      root.querySelectorAll("#delete-product-dialog button").forEach(button => { button.disabled = false; });
    }
  }

  _switchProductView(view) {
    if (view !== "automation") this._stopCodeCapture();
    if (this._saving) return;
    for (const button of this.shadowRoot.querySelectorAll("[data-product-view]")) {
      const selected = button.dataset.productView === view;
      button.setAttribute("aria-pressed", String(selected));
      this.shadowRoot.querySelector(`#${button.getAttribute("aria-controls")}`).hidden = !selected;
    }
    if (view === "additional") { this._renderStoreLinks(); void this._loadNutriscores(); }
  }

  _resetNutriscores() {
    this._nutriGeneration = (this._nutriGeneration || 0) + 1;
    this._nutriCodesKey = "";
  }

  _updateOptionTitle() {
    const name=this.shadowRoot.querySelector("#product-form").elements.name.value.trim();
    this.shadowRoot.querySelector("#product-options-title").textContent=name?`Opciones para comprar ${name}`:"Opciones para comprar";
  }

  _renderStoreLinks() {
    this._updateOptionTitle();
    const root = this.shadowRoot, names = {'':'Sin tienda',...STORE_NAMES};
    const receiptStores=this._receiptStores?.[this._editing?.id]??[];
    this._commercialReferences??=[];
    for(const code of this._productCodes?.barcode??[]){if(barcodeIdentity(code)&&!this._commercialReferences.some(ref=>ref.ean&&barcodeIdentity(ref.ean)===barcodeIdentity(code)))this._commercialReferences.push({store:'',ean:code,name:'',reference_id:'',url:'',content_quantity:null,content_unit:'',content_confirmed:false});}
    const stores=[...new Set([...Object.keys(this._storeLinks??{}),...receiptStores,...this._commercialReferences.filter(ref=>ref.active!==false).map(ref=>ref.store)])].filter(store=>store in names).sort((a,b)=>names[a].localeCompare(names[b],"es"));
    const options=stores.flatMap(store=>{
      const refs=this._commercialReferences.filter(ref=>ref.active!==false&&ref.store===store);
      return refs.length?refs.map(ref=>({store,ref})):[{store,ref:null}];
    });
    const cards=options.map(({store,ref},index)=>{
      const value=this._storeLinks[store],fromTicket=receiptStores.includes(store);
      const card=document.createElement('details');card.className='product-store-association product-option';card.dataset.store=store;
      const key=ref?.id||`${store}:${ref?.reference_id||ref?.url||ref?.ean||index}`;card.dataset.optionKey=key;
      card.open=this._expandedOptions?.has(key)??false;
      card.addEventListener('toggle',()=>{this._expandedOptions??=new Set();if(card.open)this._expandedOptions.add(key);else this._expandedOptions.delete(key);});
      const summary=element('summary'),heading=element('span','option-heading');
      const reference = document.createElement("span"); reference.className = "store-reference";
      const image = document.createElement("img"); image.alt = names[store] ?? store; image.referrerPolicy = "no-referrer";
      if(store)image.src = storeLogo(store);else reference.hidden=true;
      reference.append(image);
      reference.classList.add('option-store');
      const title=element('span','option-name',ref?.name|| (ref?.ean?`EAN ${ref.ean}`:ref?.reference_id?`Referencia ${ref.reference_id}`:'Opción sin detalle'));
      const updateSummary=()=>{title.textContent=ref?.name||(ref?.ean?`EAN ${ref.ean}`:ref?.reference_id?`Referencia ${ref.reference_id}`:'Opción sin detalle');};updateSummary();
      heading.append(title);summary.append(reference,heading);
      card.append(summary);
      const source=document.createElement('div');source.className='association-source';
      for(const text of [value?'Web':'',fromTicket?'Ticket/factura confirmado':''].filter(Boolean)){const badge=document.createElement('span');badge.textContent=text;source.append(badge);}
      const header=document.createElement('div');header.className='product-store-header';header.append(source);card.append(header);
      if(ref)card.append(this._commercialReferenceCard(ref,updateSummary));
      return card;
    });
    const groups=new Map();
    options.forEach(({ref},index)=>{const code=barcodeIdentity(ref?.ean??''),key=code?`ean:${code}`:`option:${index}`;if(!groups.has(key))groups.set(key,[]);groups.get(key).push({ref,card:cards[index]});});
    const blocks=[...groups.entries()].map(([key,entries])=>{
      if(entries.length===1)return entries[0].card;
      const group=element('details','product-ean-group');group.dataset.ean=entries[0].ref.ean;
      group.open=this._expandedEANs?.has(key)??false;
      group.addEventListener('toggle',()=>{this._expandedEANs??=new Set();if(group.open)this._expandedEANs.add(key);else this._expandedEANs.delete(key);});
      const title=element('summary','',entries.find(item=>item.ref?.name)?.ref.name||`EAN ${entries[0].ref.ean}`);
      group.append(title,element('p','helper',`EAN: ${entries[0].ref.ean}`),...entries.map(item=>item.card));
      return group;
    });
    root.querySelector('#product-store-links').replaceChildren(...blocks);
    root.querySelector('#retrieve-product-data').disabled=Boolean(this._retrievingOption)||this._hass?.user?.is_admin!==true;
  }

  _commercialReferenceCard(ref,onChange=()=>{}){
    const card=element('div','commercial-reference'),heading=element('div','commercial-reference-title'),name=element('input');
    name.value=ref.name||'';name.maxLength=500;name.placeholder='Nombre comercial';name.setAttribute('aria-label','Nombre comercial');name.addEventListener('input',()=>{ref.name=name.value;onChange();});
    name.readOnly=Boolean(ref.id&&!ref.ean&&!ref.reference_id);
    const remove=element('button','remove-store-link');remove.type='button';remove.setAttribute('aria-label','Desvincular referencia');remove.innerHTML='<ha-icon icon="mdi:delete" aria-hidden="true"></ha-icon>';
    remove.addEventListener('click',()=>{if(!confirm('¿Desvincular esta referencia comercial? Se conserva el historial de compras.'))return;ref.active=false;if(ref.ean){const code=ref.ean.padStart(14,'0');if(!this._commercialReferences.some(item=>item.active!==false&&item.ean?.padStart(14,'0')===code))this._productCodes.barcode=this._productCodes.barcode.filter(value=>value.padStart(14,'0')!==code);}const link=this._storeLinks[ref.store];if(link&&(typeof link==='string'?link===ref.url||link===ref.reference_id:link.id===ref.reference_id))delete this._storeLinks[ref.store];this._renderStoreLinks();this._renderProductCodes();});
    heading.append(name,remove);card.append(heading);
    const brandLabel=element('label','option-brand','Marca'),brand=element('input');brand.value=ref.brand||'';brand.maxLength=160;brand.placeholder='Sin marca informada';brand.addEventListener('input',()=>{ref.brand=brand.value.trim();onChange();});brandLabel.append(brand);card.append(brandLabel);
    {
      const row=element('div','option-url-row');
      const input=element('input');input.type='url';input.pattern='https://.*';input.value=ref.url||'';input.maxLength=2048;input.setAttribute('aria-label',`URL de ${STORE_NAMES[ref.store]??'la opción'}`);
      input.placeholder='URL del producto';
      input.addEventListener('input',()=>{const previous=ref.url||ref.reference_id,value=input.value.trim(),primary=this._storeLinks[ref.store],primaryValue=typeof primary==='string'?primary:primary?.url||primary?.id;if(primaryValue===previous){if(value)this._storeLinks[ref.store]=value;else delete this._storeLinks[ref.store];}ref.url=value.startsWith('https://')?value:'';if(ref.url)ref.reference_id='';onChange();});
      const feedback=element('p','helper option-lookup-feedback');feedback.setAttribute('role','status');feedback.setAttribute('aria-live','polite');feedback.hidden=true;
      const retrieve=element('button','retrieve-option','Recuperar datos');retrieve.type='button';retrieve.dataset.retrieveOption='true';retrieve.disabled=Boolean(this._retrievingOption)||this._hass?.user?.is_admin!==true;retrieve.addEventListener('click',()=>void this._retrieveOption(ref,input.value.trim(),feedback));row.append(input,retrieve);card.append(row,feedback);
      input.addEventListener('keydown',event=>{if(event.key==='Enter'&&!event.isComposing){event.preventDefault();void this._retrieveOption(ref,input.value.trim(),feedback);}});
    }
    card.append(element('p','helper',[ref.ean?'EAN: '+ref.ean:'',ref.reference_id?'ID: '+ref.reference_id:''].filter(Boolean).join(' · ')));
    if(ref.url){const link=element('a','helper','Ver ficha de la tienda');link.href=storeProductLink(ref.store,ref.url);link.target='_blank';link.rel='noopener noreferrer';if(link.href!==ref.url){link.rel+=' sponsored';link.title='Enlace de afiliado de Carrefour';}card.append(link);}
    let renderPrice=()=>{};
    const update=()=>{renderPrice();onChange();};
    card.append(referenceContentControls(ref,update));update();
    const offers=[...(ref.last_price?[ref.last_price]:[]),...(this._priceData?.offers??[]).filter(offer=>offer.catalog_product_id===this._editing?.id&&(offer.commercial_reference_id===ref.id||offer.store===ref.store&&(ref.ean&&offer.ean===ref.ean||ref.reference_id&&offer.reference_id===ref.reference_id)))].sort((a,b)=>(b.checked_at??0)-(a.checked_at??0));
    const priceLabel=element('label','option-price','Precio por envase (€)'),priceInput=element('input');
    priceInput.type='number';priceInput.min='0';priceInput.max='1000000';priceInput.step='0.01';priceInput.inputMode='decimal';priceInput.placeholder='Sin precio';
    priceInput.setAttribute('aria-label','Precio por envase');priceInput.value=offers[0]?.price??'';priceInput.disabled=!ref.store;
    priceLabel.append(priceInput);card.append(priceLabel);
    const priceText=element('p','helper');card.append(priceText);
    let displayedPrice=offers[0];
    renderPrice=()=>{priceText.hidden=!displayedPrice;if(!displayedPrice)return;const money=value=>new Intl.NumberFormat('es-ES',{style:'currency',currency:displayedPrice.currency??'EUR'}).format(value),rate=referenceRate(displayedPrice.price,ref);priceText.textContent='Último precio: '+money(displayedPrice.price)+' / envase';if(rate)priceText.textContent+=' · '+money(rate.price)+' / '+rate.unit;};renderPrice();
    priceInput.addEventListener('input',()=>{
      if(!priceInput.validity.valid)return;
      if(priceInput.value===''){delete ref.last_price;displayedPrice=null;}
      else{ref.last_price={price:priceInput.valueAsNumber,currency:'EUR',checked_at:Date.now()/1000};displayedPrice=ref.last_price;}
      update();
    });
    if(ref.measure_price){const rate=ref.measure_price;card.append(element('p','helper','Precio por unidad de medida: '+new Intl.NumberFormat('es-ES',{style:'currency',currency:'EUR',maximumFractionDigits:4}).format(rate.price)+' / '+rate.quantity+' '+rate.unit));}
    return card;
  }

  async _retrieveOption(ref,value,feedback=null) {
    if(this._retrievingOption||this._hass?.user?.is_admin!==true)return;
    const root=this.shadowRoot,status=root.querySelector('#option-lookup-status'),generation=this._optionGeneration;
    if(!value){status.textContent='Indica la URL del producto para recuperar sus datos.';return;}
    if(!storeFromProductUrl(value)){const target=feedback??status;target.hidden=false;target.dataset.error='true';target.textContent='Introduce una URL HTTPS de una tienda compatible.';return;}
    this._retrievingOption=true;status.textContent='Recuperando datos…';
    status.dataset.error='false';
    if(feedback){feedback.hidden=false;feedback.dataset.error='false';feedback.textContent='Recuperando datos…';}
    root.querySelector('#save-product').disabled=true;
    root.querySelectorAll('.retrieve-option').forEach(button=>{button.disabled=true;});
    try{
      const data=await this._hass.callWS({type:'improved_shopping_list/catalog/retrieve_option',url:value,store:ref.store||'',ean:ref.ean||''});
      if(generation!==this._optionGeneration||!root.querySelector('dialog').open||!this.isConnected)return;
      if((ref.url||ref.reference_id)!==value){status.textContent='El enlace ha cambiado. Pulsa Recuperar datos de nuevo.';return;}
      const previousStore=ref.store,changedStore=previousStore!==data.store;
      if(changedStore){
        const primary=this._storeLinks[previousStore],primaryValue=typeof primary==='string'?primary:primary?.url||primary?.id;
        if(primaryValue&&(primaryValue===value||primaryValue===ref.url||primaryValue===ref.reference_id||primary?.id===ref.reference_id))delete this._storeLinks[previousStore];
        // IDs and last prices are store-specific; keep historical observations intact.
        delete ref.id;delete ref.last_price;delete ref.measure_price;
      }
      const existing=this._commercialReferences.find(item=>item!==ref&&item.active!==false&&item.store===data.store&&(item.reference_id===data.reference_id||item.url===data.url));
      if(existing){this._commercialReferences=this._commercialReferences.filter(item=>item!==ref);ref=existing;}
      Object.assign(ref,{store:data.store,reference_id:data.reference_id,url:data.url,active:true});
      if(data.name)ref.name=data.name;
      if(data.brand)ref.brand=data.brand;
      if(data.image_url)ref.image_url=data.image_url;
      if(data.ean)ref.ean=data.ean;
      if(data.content_quantity>0&&data.content_unit&&!ref.content_confirmed){ref.content_quantity=data.content_quantity;ref.content_unit=data.content_unit;}
      if(Number.isFinite(data.price)&&data.price>=0&&data.currency==='EUR')ref.last_price={price:data.price,currency:data.currency,checked_at:data.checked_at};
      if(data.measure_price)ref.measure_price=data.measure_price;
      if(data.nutriscore?.grade)ref.nutriscore=data.nutriscore;
      if(!this._storeLinks[data.store])this._storeLinks[data.store]=data.url;
      if(data.ean)this._addProductCode('barcode',data.ean);
      const image=root.querySelector('form').elements.image_url;
      if(!image.value&&data.image_url){image.value=data.image_url;root.querySelector('isl-icon-picker').value=data.image_url;}
      this._expandedOptions.add(ref.id||`${ref.store}:${ref.reference_id||ref.url||ref.ean}`);
      if(barcodeIdentity(ref.ean??'')){this._expandedEANs??=new Set();this._expandedEANs.add('ean:'+barcodeIdentity(ref.ean));}
      this._renderStoreLinks();this._renderProductCodes();
      status.textContent=changedStore?`Opción reclasificada en ${STORE_NAMES[data.store]??data.store}. Datos recuperados. Guarda el producto para conservarlos.`:'Datos recuperados. Guarda el producto para conservarlos.';
    }catch(error){if(generation===this._optionGeneration&&root.querySelector('dialog').open){const message=error.message||'No se han podido recuperar los datos. Puedes conservar el enlace y completar la opción manualmente.';status.textContent=feedback?'':message;status.dataset.error=String(!feedback);if(feedback){feedback.hidden=false;feedback.dataset.error='true';feedback.textContent=message;}}}
    finally{
      if(generation===this._optionGeneration){this._retrievingOption=false;root.querySelector('#save-product').disabled=Boolean(this._saving);root.querySelectorAll('.retrieve-option').forEach(button=>{button.disabled=this._hass?.user?.is_admin!==true;});}
    }
  }

  async _loadNutriscores() {
    const root = this.shadowRoot;
    const seen = new Set();
    const codes = [...(this._productCodes?.barcode ?? []),...(this._commercialReferences??[]).filter(ref=>ref.active!==false&&ref.ean).map(ref=>ref.ean)]
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
        const validNutrition=data&&/^[a-e]$/.test(data.grade)&&Number.isFinite(data.checked_at)&&data.checked_at>0;
        let enriched=false;
        for(const ref of this._commercialReferences??[]){
          if(ref.active===false||!ref.ean||barcodeIdentity(ref.ean)!==barcodeIdentity(code))continue;
          if(!ref.brand&&result.brand){ref.brand=result.brand;enriched=true;}
          if(!ref.name&&result.product_name){ref.name=result.product_name;enriched=true;}
          if(ref.content_quantity==null&&!ref.content_confirmed&&result.content_quantity>0&&result.content_unit){ref.content_quantity=result.content_quantity;ref.content_unit=result.content_unit;enriched=true;}
          if(validNutrition&&(!ref.nutriscore||(data.checked_at>=ref.nutriscore.checked_at))){ref.nutriscore={grade:data.grade,checked_at:data.checked_at};enriched=true;}
        }
        if(enriched)this._renderStoreLinks();
        if (!data || !/^[a-e]$/.test(data.grade)) continue;
        this._renderProducts();
        this.dispatchEvent(new CustomEvent("product-nutriscore",{detail:{code,nutriscore:data}}));
      } catch { /* Optional nutrition must never prevent editing or saving. */ }
    }
  }

  _openProduct(product, suggestedName = "", reading = null, listOrigin = null) {
    if (this._saving || this._deletingProduct) return;
    if (this._saving) return;
    const root = this.shadowRoot;
    const form = root.querySelector("form");
    this._listOrigin = listOrigin;
    this._optionGeneration=(this._optionGeneration||0)+1;
    this._stopCodeCapture();
    this._scanNotice = null;
    this._productCodes = {barcode:[],nfc:[]};
    this._readerActionDraft = {...(product?.reader_actions ?? {})};
    this._readerSignature = null;
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
    root.querySelector("#delete-product").hidden = !this._editing;
    this._storeLinks = structuredClone(product?.store_links ?? {});
    this._commercialReferences = structuredClone(product?.commercial_references ?? []);
    this._expandedOptions = new Set();
    this._expandedEANs = new Set();
    this._retrievingOption=false;
    root.querySelector('#option-lookup-status').textContent='';
    root.querySelector('#save-product').disabled=false;
    for(const [store,link] of Object.entries(this._storeLinks)){const value=typeof link==='string'?link:link.url||link.id;if(!this._commercialReferences.some(ref=>ref.store===store&&(ref.url===value||ref.reference_id===value||ref.reference_id===link.id)))this._commercialReferences.push({store,name:'',ean:'',reference_id:typeof link==='string'?(value.startsWith('https://')?'':value):link.id,url:value.startsWith('https://')?value:'',content_quantity:null,content_unit:'',content_confirmed:false});}
    this._renderStoreLinks();
    form.elements.recurrence_enabled.checked = product?.recurrence?.enabled === true;
    form.elements.recurrence_days.value = product?.recurrence?.days ?? 7;
    form.elements.recurrence_days.disabled = !form.elements.recurrence_enabled.checked;
    root.querySelector("#product-dialog-title").textContent = product ? "Editar producto" : "Nuevo producto";
    root.querySelector("#product-error").hidden = true;
    if (product) {
      for (const key of ["name", "category", "image_url"]) form.elements[key].value = product[key] ?? "";
      for (const code of [product.barcode,...(product.barcodes??[])]) this._addProductCode("barcode",code);
      for (const code of product.nfc_tags??[]) this._addProductCode("nfc",code);
    }
    if (reading) this._addProductCode(reading.kind,reading.code);
    this._renderProductCodes();
    const iconPicker = root.querySelector("isl-icon-picker");
    iconPicker.hass = this._hass;
    iconPicker.value = form.elements.image_url.value;
    root.querySelector("dialog").showModal();
    iconPicker.open(iconPicker.getQuery());
    form.elements.name.focus();
  }

  async _saveProduct() {
    if (this._saving || this._deletingProduct || this._retrievingOption) return;
    const root = this.shadowRoot;
    const form = root.querySelector("form");
    const fields = Object.fromEntries(new FormData(form));
    const product = { ...fields, price: this._editing?.price ?? null, currency: this._editing?.currency ?? "EUR", tags: structuredClone(this._editing?.tags ?? []), icon: this._editing?.icon ?? "", notes: this._editing?.notes ?? "" };
    product.purchase_unit=this._editing?.purchase_unit??'uds';
    product.unit_quantity=this._editing?.unit_quantity??1;
    product.quantity_step=this._editing?.quantity_step??1;
    product.store_links = structuredClone(this._storeLinks ?? {});
    product.commercial_references = structuredClone(this._commercialReferences ?? []).map(ref=>({...ref,content_confirmed:validReferenceContent(ref)}));
    product.barcode = this._productCodes.barcode[0] ?? "";
    product.barcodes = this._productCodes.barcode.slice(1);
    product.nfc_tags = [...this._productCodes.nfc];
    product.recurrence = {enabled:form.elements.recurrence_enabled.checked, days:Number(form.elements.recurrence_days.value) || 7};
    delete product.recurrence_enabled;
    delete product.recurrence_days;
    product.reader_actions = {...this._readerActionDraft};
    if (this._editing) Object.assign(product, { id: this._editing.id, revision: this._editing.revision });
    this._stopCodeCapture();
    this._saving = true;
    this._renderProductCodes();
    root.querySelector("isl-icon-picker").disabled = true;
    root.querySelector("#save-product").disabled = true;
    root.querySelector("#delete-product").disabled = true;
    root.querySelector("#product-error").hidden = true;
    try {
      const saved = await this._catalog.save(product);
      this._editing = structuredClone(saved);
      if (this._listOrigin && saved.name !== this._listOrigin.summary) {
        try {
          if (!this.onRenameSuggestion) throw new Error("No se ha podido conectar con la lista de origen.");
          await this.onRenameSuggestion(this._listOrigin, saved.name);
        } catch (error) {
          root.querySelector("#product-dialog-title").textContent = "Editar producto";
          throw new Error(`El producto se ha guardado en el catálogo, pero no se ha podido actualizar su nombre en la lista. ${error.message ?? "Inténtalo de nuevo."}`);
        }
      }
      this._listOrigin = null;
      if(this._receiptCreate)this._receiptCreated=structuredClone(saved);
      root.querySelector("dialog").close();
      this._render();
      root.querySelector(this._view === "suggestions" ? "#view-suggestions" : "#new-product").focus();
    } catch (error) {
      const notice = root.querySelector("#product-error");
      notice.textContent = error.message ?? "No se ha podido guardar el producto.";
      notice.hidden = false;
    } finally {
      this._saving = false;
      this._renderProductCodes();
      root.querySelector("isl-icon-picker").disabled = false;
      root.querySelector("#save-product").disabled = false;
      root.querySelector("#delete-product").disabled = false;
      root.querySelector("#delete-product").hidden = !this._editing;
    }
  }

  async _addToList(product) {
    if (this._adding) return;
    const inList = this._pendingNames.has(productNameKey(product.name));
    const item = inList ? this._listItems?.find(item => item.status !== "completed" && productNameKey(item.summary) === productNameKey(product.name)) : null;
    if (inList ? !this._canComplete || !this.onComplete || !item : !this._canAdd || !this.onAdd) return;
    this._adding = product.id;
    this._render();
    try {
      if (inList) await this.onComplete(item);
      else await this.onAdd(product);
    } finally {
      this._adding = undefined;
      this._render();
    }
  }
}

if (!customElements.get("isl-catalog")) customElements.define("isl-catalog", ImprovedShoppingCatalog);
