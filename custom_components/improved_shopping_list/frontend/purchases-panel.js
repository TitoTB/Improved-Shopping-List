import { ListSettingsSession } from "./list-settings-client.js?v=0.55.0";
import { installDialogCloseButtons } from "./dialog-controls.js?v=0.55.0";
import { productNameKey } from "./product-names.js?v=0.55.0";
import { referenceFor, suggestedContent, referenceContentControls, validReferenceContent, barcodeIdentity, recoveredStockQuantity } from "./reference-formats.js?v=0.55.0";

const node=(tag,cls,text)=>{const el=document.createElement(tag);if(cls)el.className=cls;if(text!==undefined)el.textContent=text;return el;};
const money=value=>new Intl.NumberFormat('es-ES',{style:'currency',currency:'EUR'}).format(value);
const documentDate=receipt=>receipt.document_type==='invoice'?new Intl.DateTimeFormat('es-ES',{dateStyle:'short'}).format(new Date(receipt.purchased_at)):date(receipt.purchased_at);
const localDay=value=>`${value.getFullYear()}-${String(value.getMonth()+1).padStart(2,'0')}-${String(value.getDate()).padStart(2,'0')}`;
const date=value=>new Intl.DateTimeFormat('es-ES',{dateStyle:'short',timeStyle:'short'}).format(new Date(value));
const icon=name=>{const el=node('ha-icon');el.setAttribute('icon',name);el.setAttribute('aria-hidden','true');return el;};

const STORE_LOGOS={
  lidl:'https://upload.wikimedia.org/wikipedia/commons/9/91/Lidl-Logo.svg',carrefour:'https://images.seeklogo.com/logo-png/31/2/carrefour-logo-png_seeklogo-318190.png',
  alcampo:'https://almeria.online/wp-content/uploads/2024/09/alcampo-logo.png',
  ...Object.fromEntries(['mercadona','consum','lasirena','eroski','dia'].map(store=>[store,new URL(store+'.'+(['mercadona','dia'].includes(store)?'png':store==='eroski'?'svg':'jpg'),import.meta.url).href]))
};
const STORE_NAMES={mercadona:"Mercadona",carrefour:"Carrefour",alcampo:"Alcampo",consum:"Consum",lasirena:"La Sirena",eroski:"Eroski",dia:"DIA",lidl:"Lidl"};
const STORE_COLORS={lidl:'#ffcc00',mercadona:'#29975b',carrefour:'#2388dc',alcampo:'#e15150',consum:'#ef9639',lasirena:'#42b9ca',eroski:'#a968bd',dia:'#e2608c'};

class PurchaseSession extends ListSettingsSession {
  constructor(getHass,onChange){super(getHass,onChange,'improved_shopping_list/receipts/');this.receipts=[];this.shops=[];this.ticketAccounts={};}
  _receive(data){this.receipts=data.receipts??[];this.shops=data.shops??[];this.ticketAccounts=data.ticket_accounts??{};this.persons=data.persons??[];this.loaded=true;this.loading=false;this.error='';this.onChange();}
}

class ImprovedShoppingPurchases extends HTMLElement {
  constructor(){
    super();this.attachShadow({mode:'open'});
    this._session=new PurchaseSession(()=>this._hass,()=>this._render());this._busy=false;this._visiblePurchases=10;
  }
  set data(value){
    const changed=this._hass?.connection!==value.hass.connection;
    this._active=value.active;
    this._hass=value.hass;this._history=value.history;this._pricesEnabled=value.pricesEnabled;
    if(!this._built)this._build();
    if(value.active&&this._hass.user?.is_admin===true&&(!this._started||changed)){
      this._started=true;void this._session.start();
    }
    if(!value.active){this._visiblePurchases=10;this._session.stop();this._started=false;this.shadowRoot.querySelectorAll('dialog').forEach(dialog=>dialog.close());}
    this._render();
  }
  disconnectedCallback(){this._session.stop();this._started=false;this.shadowRoot.querySelectorAll('dialog').forEach(dialog=>dialog.close());}
  openPreview(draft){
    if(this._busy||!this._active||this._hass?.user?.is_admin!==true)return false;
    this._draft=draft;this._error='';this._buildReview();this.shadowRoot.querySelector('dialog').showModal();return true;
  }
  chooseFile(){if(!this._busy&&this._hass?.user?.is_admin===true)this.shadowRoot.querySelector('#ticket-file').click();}
  _build(){
    this._built=true;
    this.shadowRoot.innerHTML=`<style>
      .price-line { flex-wrap:wrap; }.reference-content-controls { position:relative;z-index:1;display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:8px;margin-top:12px;flex:1 0 100%;width:100%;min-width:0; }
      .reference-content-controls label { min-width:0;margin:0;font-size:12px; }.reference-content-controls input,.reference-content-controls select { min-width:0;width:100%; }
      .reference-confirm { grid-column:1/-1;display:flex!important;align-items:center;gap:8px; }.reference-confirm input { width:auto!important;min-height:0!important;margin:0!important; }
      :host{display:block;color:inherit;font:inherit}*{box-sizing:border-box}[hidden]{display:none!important}
      .purchase-filters{display:flex;gap:12px;margin:16px 0;flex-wrap:wrap}.purchase-filters label{flex:1;min-width:140px}.shoppers{font-size:12px;opacity:.7}.product-choice{display:flex!important;align-items:center;gap:10px}.product-choice input{width:auto!important}button,input,select{font:inherit;color:inherit}button{cursor:pointer}button:disabled{opacity:.5;cursor:default}
      input,select{width:100%;min-width:0;min-height:42px;border:1px solid var(--divider-color,#d9e0dd);background:var(--card-background-color,#fff);border-radius:8px;padding:8px}
      .notice{padding:12px;border-radius:10px;background:var(--secondary-background-color,#edf2ef)}.error{color:var(--error-color,#d32f2f)}
      #history{display:grid;gap:12px}#more-purchases{display:block;margin:16px auto 0;padding:12px 20px;border:0;border-radius:10px;background:var(--primary-color,#267052);color:white}#more-purchases:focus-visible{outline:3px solid var(--primary-color,#267052);outline-offset:3px}.ticket{border-radius:14px;background:var(--card-background-color,#fff);padding:16px}
      summary{display:flex;align-items:center;gap:12px;cursor:pointer;list-style:none}summary::before{content:'▸'}details[open]>summary::before{content:'▾'}
      .title{display:flex;flex-direction:column;gap:4px;flex:1;min-width:0}.muted{opacity:.65;font-size:.85em}.total{font-weight:750;white-space:nowrap}
      .line{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:12px;padding:10px 0;border-bottom:1px solid var(--divider-color,#d9e0dd)}.line p{margin:3px 0}
      .totals{display:flex;justify-content:space-between;gap:12px;margin-top:14px}.empty{text-align:center;opacity:.7;padding:24px}
      dialog{position:fixed;inset:0;border:0;border-radius:18px;background:var(--card-background-color,#fff);color:inherit;width:min(900px,calc(100vw - 24px));max-height:90vh;padding:24px;overflow:auto}
      dialog::backdrop{background:#0008}h2{font-size:1.25rem;margin:0 40px 16px 0}.receipt-info{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:12px}
      #review-lines{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}#review-lines>.review-group,#review-lines>.select-all-prices,#review-lines>.note{grid-column:1/-1}.review-line{min-width:0}.review-line{border:1px solid var(--divider-color,#d9e0dd);padding:12px;background:var(--secondary-background-color,#f2f4f3);border-radius:10px}
      #review-steps{list-style:none;display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:6px;padding:0;margin:16px 0}#review-steps button{width:100%;padding:10px 6px;border:0;text-align:center;border-radius:8px;font-size:.85em;background:var(--secondary-background-color,#edf2ef)}#review-steps button:disabled{opacity:1;cursor:default}#review-steps button:focus-visible{outline:3px solid var(--primary-color,#267052);outline-offset:2px}#review-steps [data-completed=true]{background:var(--isl-green,#267052);color:white}#review-steps [aria-current=step]{background:#2196f3;color:white;font-weight:700}
      #step-title{margin:18px 0 8px;font-size:1.05em}.association{display:flex;gap:8px;align-items:end}.association label{flex:1}.small-button{display:grid;place-items:center;flex:none;width:42px;height:42px;padding:0;border:0;border-radius:8px;background:var(--primary-color,#267052);color:white}.small-button.clear{background:transparent;color:inherit;border:1px solid var(--divider-color,#d9e0dd)}
      .actions{gap:8px;flex-wrap:wrap}.actions .secondary{background:transparent;color:inherit;border:1px solid var(--divider-color,#d9e0dd)}.previous-price{font-size:.85em;opacity:.7;margin:8px 0}.review-line .check{margin:10px 0}.stock-fields{display:grid;grid-template-columns:minmax(0,2fr) minmax(80px,1fr);gap:10px}.review-summary{line-height:1.6;padding:12px;border-radius:8px;background:var(--secondary-background-color,#edf2ef)}
      .original{display:flex;justify-content:space-between;gap:12px;margin-bottom:10px}.fields{display:grid;grid-template-columns:minmax(0,2fr) minmax(100px,1fr);gap:10px}
      label{display:flex;flex-direction:column;gap:5px;font-size:.9em;min-width:0}.quantity{display:flex;align-items:center;gap:8px}.quantity span{white-space:nowrap}
      .check{flex-direction:row;align-items:center;margin-top:10px}.check input{width:18px;min-height:18px;flex:none}.purchase{margin-top:10px}
      .actions{display:flex;justify-content:flex-end;margin-top:16px}.actions button{border:0;background:#267052;color:white;border-radius:10px;padding:12px 20px}
      .actions #links-only,.actions #stock-only,.actions #prices-only{background:var(--isl-green,#267052);color:white;border:0}.actions .continue{background:#2196f3}
      .review-group{border:1px solid var(--divider-color,#d9e0dd);border-radius:12px;min-width:0}.review-group>summary{justify-content:space-between;padding:14px;font-weight:650}.review-group>summary::before,.review-group[open]>summary::before{content:none}.review-group>summary ha-icon{transition:transform .15s}.review-group[open]>summary ha-icon{transform:rotate(180deg)}.review-group-content{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;padding:0 10px 10px}
      .stock-line-main{display:grid;grid-template-columns:minmax(0,1fr) 90px 80px;gap:10px;align-items:center;min-width:0}.stock-line-name{min-width:0;overflow-wrap:anywhere}.stock-line-name .linked-name{display:block;margin:4px 0 0}.stock-line-main input{text-align:center}.stock-line-unit{text-align:center;overflow-wrap:anywhere;min-width:0}.stock-line{position:relative}.stock-line[data-selected=true]{border-color:#ff9800;background:color-mix(in srgb,var(--secondary-background-color,#f2f4f3) 80%,#ff9800)}.stock-select{position:absolute;inset:0;width:100%;height:100%;padding:0;border:0;border-radius:inherit;background:transparent}.stock-select:focus-visible{outline:3px solid #ff9800;outline-offset:-3px}.stock-line-main{position:relative;pointer-events:none}.stock-line-main input{pointer-events:auto}.stock-line input:disabled,.stock-line select:disabled{pointer-events:none}.stock-line .purchase{position:relative;pointer-events:auto}.price-product-name{display:flex;align-items:center;gap:10px;min-width:0;overflow-wrap:anywhere}.original>span{flex:none;text-align:right}
      @media(max-width:550px){.stock-line{padding:10px}.stock-line-main{grid-template-columns:minmax(0,1fr) 64px 54px;gap:6px}.stock-line-main .small-button{width:34px;height:42px}.stock-line-main input{padding:8px 3px}.stock-line-name{font-size:.85em}.review-group>summary{padding:12px}}
      ha-icon{--mdc-icon-size:22px;width:22px;height:22px;flex:none}#review-summary{margin:12px 0}.note{font-size:.85em;opacity:.7;margin:10px 0}
      .association-image{display:grid;place-items:center;width:32px;height:32px;flex:none}.association-image img{display:block;width:100%;height:100%;object-fit:contain}
      .receipt-ean{display:block;font-size:12px;opacity:.7;margin-top:4px;overflow-wrap:anywhere}
      .association-row{display:flex;align-items:center;gap:10px;min-width:0}.association-name{flex:1;min-width:0;overflow-wrap:anywhere}.association-name strong{font-size:.95em}.linked-name{display:block;font-size:.8em;opacity:.65;margin:4px 0 0}.association-buttons{display:flex;gap:6px;flex:none;margin-left:auto}
      .small-button.link{background:#2196f3;color:white}.small-button.create{background:var(--isl-green,#267052);color:white}
      #association-dialog{width:min(500px,calc(100vw - 24px))}#association-form label{margin-top:16px}#association-error{margin:12px 0 0}
      @media(max-width:400px){.association-buttons{gap:4px}.association-buttons .small-button{width:34px;height:38px}.association-row{gap:8px}.linked-name{display:block;margin-left:0}}
      @media(max-width:550px){dialog{padding:18px}.fields{grid-template-columns:minmax(0,1fr)}summary{gap:8px}.original{font-size:.9em}.ticket{padding:12px}}

      .stock-line-main{grid-template-columns:32px minmax(0,1fr) minmax(0,.8fr);gap:10px}.stock-quantity{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,.8fr);gap:6px;align-items:center;min-width:0}.stock-quantity input{width:100%;min-width:0;padding-inline:4px}
      .select-all-prices{justify-self:end;margin:0 0 4px;text-align:right}
      .price-line{position:relative}.price-select{position:relative;width:100%;height:auto;min-height:52px;flex:1 0 100%;border:0;border-radius:inherit;background:transparent;padding:0;text-align:left}.price-select:focus-visible{outline:3px solid var(--isl-green,#267052);outline-offset:-3px}.price-line[data-selected=true]{border-color:var(--isl-green,#267052);background:color-mix(in srgb,var(--secondary-background-color,#f2f4f3) 75%,var(--isl-green,#267052))}.price-product-name{position:relative;pointer-events:none}.price-label{min-width:0}.price-value{margin-top:6px}.price-value del{opacity:.6;font-size:.9em;margin-left:6px}.price-product-name strong{display:block}
      @media(max-width:750px){.association-row{flex-wrap:wrap;gap:6px}.association-buttons{width:100%;justify-content:flex-end}.association-buttons .small-button{width:30px;height:34px}.association-buttons ha-icon{--mdc-icon-size:20px;width:20px;height:20px}.association-image{width:26px;height:26px}.stock-line-main{grid-template-columns:20px minmax(0,1fr) minmax(0,1.2fr);gap:4px}.stock-line-main .association-image{width:20px;height:20px}.stock-quantity{gap:3px;font-size:.85em}.stock-quantity input{padding-inline:2px;appearance:textfield}.stock-quantity input::-webkit-inner-spin-button,.stock-quantity input::-webkit-outer-spin-button{-webkit-appearance:none;margin:0}.review-line{padding:8px}.association-name strong,.price-label{font-size:.85em}#review-lines,.review-group-content{gap:8px}.review-group-content{padding:0 8px 8px}}
      .review-summary{padding:18px;border:1px solid var(--divider-color,#d9e0dd);border-radius:14px}.purchase-heading{display:flex;align-items:center;gap:12px}.purchase-heading>ha-icon{color:var(--isl-green,#267052);--mdc-icon-size:28px;width:28px;height:28px}.purchase-heading>div{flex:1;min-width:0}.purchase-heading h3{margin:0;font-size:1.1em}.purchase-heading .muted{display:block;font-size:.85em}.purchase-total{font-size:1.25em;white-space:nowrap}.purchase-stats{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin:18px 0}.purchase-stats>div{display:flex;flex-direction:column;align-items:center;background:var(--card-background-color,#fff);padding:10px 4px;border-radius:10px}.purchase-stats strong{font-size:1.3em;color:var(--isl-green,#267052)}.purchase-stats span{font-size:.8em}.purchase-summary-line{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:10px 0;border-bottom:1px solid var(--divider-color,#d9e0dd)}.purchase-summary-line>div{min-width:0;overflow-wrap:anywhere}.purchase-summary-line .muted{display:block;font-size:.8em}.purchase-summary-line>span{white-space:nowrap}.review-summary>.totals{font-size:1.1em;border-top:2px dashed var(--divider-color,#d9e0dd);padding-top:14px}.purchase-lines{max-height:40vh;overflow:auto}@media(max-width:550px){#review-steps button{font-size:.7em;padding-inline:2px}.review-summary{padding:12px}.purchase-heading{flex-wrap:wrap;gap:8px}.purchase-total{margin-left:auto}.purchase-stats{gap:4px}.purchase-stats span{font-size:.75em}}
      .ticket{display:flex;align-items:center;gap:12px;min-width:0}.store-image{width:42px;height:42px;object-fit:contain;background:white;border-radius:10px;padding:5px;flex:none}.ticket .title{overflow-wrap:anywhere}.ticket .ticket-open{flex:none;width:40px;height:40px;border:0;border-radius:10px;background:var(--secondary-background-color,#edf2ef);display:grid;place-items:center;padding:0}.ticket-open.reviewed{background:var(--isl-green,#267052);color:white}.ticket-open:focus-visible{outline:3px solid var(--primary-color,#267052);outline-offset:2px}#purchase-detail-info{align-items:center;padding-bottom:12px;border-bottom:1px solid var(--divider-color,#d9e0dd)}#purchase-detail-info .total{margin-left:auto}.spending-chart{background:var(--card-background-color,#fff);padding:18px;border-radius:14px;margin-bottom:16px;min-width:0}.spending-chart h3{margin:0 0 4px;font-size:1.05em}.spending-chart .chart-note{font-size:.8em;opacity:.65;margin:0 0 12px}.chart-heading{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}.chart-actions{display:flex;align-items:center;justify-content:flex-end;gap:8px;margin-left:auto;min-width:0;max-width:100%}.chart-navigation{display:flex;align-items:center;gap:6px;min-width:0}.chart-navigation button{flex:none}.upload-ticket{display:grid;place-items:center;flex:none;width:36px;height:36px;padding:0;border:0;border-radius:10px;background:var(--isl-green,#267052);color:#fff}.upload-ticket ha-icon{display:block;width:22px;height:22px;--mdc-icon-size:22px}.upload-ticket:focus-visible{outline:3px solid var(--primary-color,#267052);outline-offset:2px}.chart-period{font-size:.8em;text-align:center}.chart-navigation button{display:grid;place-items:center;width:32px;height:32px;padding:0;border:0;border-radius:8px;background:var(--secondary-background-color,#edf2ef)}.chart-navigation button ha-icon{--mdc-icon-size:22px}.chart-navigation button:focus-visible{outline:3px solid var(--primary-color,#267052);outline-offset:2px}.chart-scroll{width:100%;min-width:0;overflow-x:auto}.chart-range{display:flex;align-items:center;gap:6px;border:0;border-radius:8px;padding:8px;background:var(--secondary-background-color,#edf2ef);font-size:.8em;min-width:0}.chart-range span{overflow-wrap:anywhere}.chart-range ha-icon{flex:none}#purchase-period-dialog{width:min(460px,calc(100vw - 24px))}#purchase-period-form .period-fields{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin-top:20px}.monthly-bars{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));align-items:end;gap:14px;width:100%;padding:8px 0 0;border-bottom:1px solid var(--divider-color,#d9e0dd)}.month-column{min-width:0;text-align:center}.month-total{display:block;font-weight:700;font-size:clamp(.6rem,2vw,.85rem);margin-bottom:8px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.month-stack{height:130px;display:flex;flex-direction:column;justify-content:end;gap:0;background:repeating-linear-gradient(to top,transparent 0,transparent calc(25% - 1px),var(--divider-color,#d9e0dd) 25%);border-bottom:1px solid var(--divider-color,#d9e0dd)}.store-segment{width:70%;margin-inline:auto;flex:none;min-height:0}.month-label{display:block;font-size:.8em;padding:8px 0}.chart-legend{display:flex;flex-wrap:wrap;gap:10px 16px;margin-top:14px}.chart-key{display:inline-flex;align-items:center;gap:6px;font-size:.8em}.chart-swatch{width:10px;height:10px;border-radius:3px;flex:none}@media(max-width:550px){.ticket{gap:8px}.ticket .store-image{width:34px;height:34px}.ticket .ticket-open{width:32px;height:36px}.ticket .title{font-size:.85em}.ticket .total{font-size:.9em}.spending-chart{padding:14px}.monthly-bars{gap:6px}.month-label{font-size:.7em}.chart-period{font-size:.7em}}
      #detected-purchase-dialog{width:min(500px,calc(100vw - 24px))}#detected-purchase-form label{margin-top:16px}#detected-products{max-height:25vh;overflow:auto;padding-left:20px}.ticket.needs-details{border:1px dashed var(--secondary-text-color,#64748b)}.ticket .edit-detection{background:#ffb74d;color:#182b22}.actions .danger{background:#d32f2f;color:#fff}
    .recovery-actions{display:flex;justify-content:flex-start;margin-top:12px}.recovery-actions button{display:flex;align-items:center;gap:8px;border:0;border-radius:10px;padding:10px 14px;background:#2196f3;color:#fff}.recovery-choice{display:flex;align-items:center;justify-content:space-between;gap:12px;width:100%;margin-top:8px;padding:12px;border:1px solid var(--divider-color,#d9e0dd);border-radius:10px;background:var(--secondary-background-color,#edf2ef);color:inherit;text-align:left}.zone-candidates{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:18px}.zone-store-choice{display:inline-flex;align-items:center;justify-content:center;gap:8px;min-width:0;flex:1;padding:10px;border:1px solid var(--divider-color,#d9e0dd);border-radius:10px;background:var(--secondary-background-color,#edf2ef)}.zone-store-choice:focus-visible{outline:3px solid var(--primary-color,#267052);outline-offset:2px}.zone-store-choice[aria-pressed=true]{background:var(--primary-color,#267052);color:white}.zone-store-choice .store-image{width:28px;height:28px;flex:none}
    </style>
    <input id="ticket-file" type="file" accept="application/pdf,.pdf" hidden>
    <p id="message" class="notice" role="status" hidden></p><section id="spending-chart" class="spending-chart" aria-label="Gasto mensual por tienda" hidden></section><div class="purchase-filters"><label>Tienda<select id="filter-shop" aria-label="Filtrar por tienda"><option value="">Todas las tiendas</option></select></label><label>Usuario<select id="filter-person" aria-label="Filtrar por usuario"><option value="">Todos los usuarios</option></select></label></div><div id="history"></div><button id="more-purchases" type="button" hidden>Mostrar más</button><p id="empty" class="empty" hidden>Todavía no has subido ningún ticket.</p>
    <dialog aria-labelledby="review-title"><form id="review-form"><h2 id="review-title">Revisar ticket</h2><div id="review-summary" class="receipt-info"></div>
      <ol id="review-steps" aria-label="Pasos de revisión del ticket"><li><button type="button">1. Vinculación</button></li><li><button type="button">2. Stock</button></li><li><button type="button">3. Precios</button></li><li><button type="button">4. Resumen</button></li></ol><h3 id="step-title"></h3><p id="step-help" class="note"></p>
      <div id="review-lines"></div><div id="review-result" class="review-summary" hidden></div>
      <p id="review-error" class="notice error" role="alert" hidden></p><div class="actions"><button id="previous-step" class="secondary" type="button">Anterior</button><button id="links-only" type="button">Guardar vinculaciones y cerrar</button><button id="stock-only" type="button" hidden>Añadir stock y cerrar</button><button id="prices-only" type="button" hidden>Actualizar precios y cerrar</button><button id="confirm-ticket" type="submit">Continuar</button></div>
    </form></dialog>
    <dialog id="association-dialog" aria-labelledby="association-title"><form id="association-form">
      <h2 id="association-title">Vincular producto</h2>
      <label for="association-search">Producto del catálogo</label><input id="association-search" type="text" list="association-products" maxlength="255" autocomplete="off" required><datalist id="association-products"></datalist>
      <p id="association-error" class="notice error" role="alert" hidden></p>
      <div class="actions"><button id="confirm-association" type="submit">Vincular</button></div>
    </form></dialog>
    <dialog id="purchase-detail" aria-labelledby="purchase-detail-title"><h2 id="purchase-detail-title">Detalle de la compra</h2><div id="purchase-detail-info" class="receipt-info"></div><div id="purchase-detail-lines"></div></dialog><dialog id="detected-purchase-dialog" aria-labelledby="detected-purchase-title"><h2 id="detected-purchase-title">Compra detectada</h2><form id="detected-purchase-form"><p id="detected-date" class="muted"></p><p id="detected-zone-help" class="note" hidden></p><div id="detected-zone-candidates" class="zone-candidates" hidden></div><label>Tienda<select id="detected-store" aria-label="Tienda" required><option value="">Selecciona una tienda</option><option value="alcampo">Alcampo</option><option value="carrefour">Carrefour</option><option value="consum">Consum</option><option value="dia">DIA</option><option value="eroski">Eroski</option><option value="lasirena">La Sirena</option><option value="mercadona">Mercadona</option><option value="lidl">Lidl</option><option value="other">Otra tienda</option></select></label><div class="recovery-actions"><button id="recover-detected" type="button"><ha-icon icon="mdi:receipt-text"></ha-icon>Recuperar compra</button></div><p id="detected-recovery-help" class="note"></p><div id="detected-recovery-results"></div><label id="detected-other-label" hidden>Nombre de la tienda<input id="detected-other" maxlength="100"></label><label>Compradores<select id="detected-shoppers" multiple aria-label="Compradores"></select></label><label>Importe total (€)<input id="detected-total" type="number" min="0" max="1000000" step="0.01" required></label><p class="note">Completa los datos de la compra. No se modifican el stock ni los precios de los productos.</p><ul id="detected-products"></ul><p id="detected-error" class="error" role="alert" hidden></p><div class="actions"><button id="discard-detection" class="danger" type="button">Eliminar detección</button><button type="submit">Guardar</button></div></form></dialog>`;
    const rangeDialog=document.createElement('dialog');rangeDialog.id='purchase-period-dialog';rangeDialog.setAttribute('aria-labelledby','purchase-period-title');rangeDialog.innerHTML=`<h2 id="purchase-period-title">Periodo de compras</h2><form id="purchase-period-form"><div class="period-fields"><label>Fecha de inicio<input id="purchase-start" type="date" required></label><label>Fecha de fin<input id="purchase-end" type="date" required></label></div><div class="actions"><button type="submit">Aplicar</button></div></form>`;this.shadowRoot.append(rangeDialog);
    const quantityDialog=document.createElement('dialog');quantityDialog.id='quantity-progress';quantityDialog.setAttribute('aria-labelledby','quantity-progress-title');quantityDialog.innerHTML='<h2 id="quantity-progress-title">Completando cantidades</h2><progress max="100" value="0" style="width:100%;height:26px;accent-color:#2196f3" aria-label="Progreso de cantidades"></progress><p class="quantity-progress-label" role="status"></p>';this.shadowRoot.append(quantityDialog);
    installDialogCloseButtons(this.shadowRoot);
    const root=this.shadowRoot,dialog=root.querySelector('dialog');
    root.querySelector('#purchase-period-form').addEventListener('submit',event=>{
      event.preventDefault();const from=root.querySelector('#purchase-start'),to=root.querySelector('#purchase-end');to.setCustomValidity('');
      if(!from.value||!to.value)return;
      if(from.value>to.value){to.setCustomValidity('La fecha de fin debe ser igual o posterior a la de inicio.');to.reportValidity();return;}
      this._spendingRange={from:from.value,to:to.value};root.querySelector('#purchase-period-dialog').close();this._render();
    });
    root.querySelector('#purchase-end').addEventListener('input',event=>event.target.setCustomValidity(''));
    root.querySelector('#purchase-start').addEventListener('input',()=>root.querySelector('#purchase-end').setCustomValidity(''));
    root.querySelector('#detected-store').addEventListener('change',()=>this._detectedStoreFields());
    root.querySelector('#recover-detected').onclick=()=>void this._searchDetectedTickets();
    root.querySelector('#detected-purchase-form').addEventListener('submit',event=>{event.preventDefault();void this._saveDetectedPurchase();});
    root.querySelector('#discard-detection').addEventListener('click',()=>{if(window.confirm('¿Eliminar esta compra detectada? No se modificará el stock.'))void this._saveDetectedPurchase(true);});
    root.querySelector('#detected-purchase-dialog').addEventListener('cancel',event=>{if(this._busy)event.preventDefault();});
    root.querySelector('#ticket-file').addEventListener('change',event=>{const file=event.target.files[0];event.target.value='';if(file)void this._upload(file);});
    root.querySelector('#review-form').addEventListener('submit',event=>{event.preventDefault();void this._advance();});
    root.querySelector('#more-purchases').addEventListener('click',()=>{this._visiblePurchases+=10;this._render();});
    root.querySelector('#previous-step').addEventListener('click',()=>this._goToStep(this._step-1));
    root.querySelectorAll('#review-steps button').forEach((button,index)=>button.addEventListener('click',()=>this._goToStep(index)));
    root.querySelector('#links-only').addEventListener('click',()=>void this._saveLinks(true));
    root.querySelector('#stock-only').addEventListener('click',()=>void this._confirm(false));
    root.querySelector('#prices-only').addEventListener('click',()=>void this._confirm());
    dialog.addEventListener('cancel',event=>{if(this._busy)event.preventDefault();});
    root.querySelector('#association-form').addEventListener('submit',event=>{event.preventDefault();this._confirmAssociation();});
    root.querySelector('#association-dialog').addEventListener('close',()=>{this._associationEdit=null;});
    dialog.addEventListener('close',()=>{
      root.querySelector('#association-dialog').close();
      if(this._draft){const token=this._draft.token;this._draft=null;void this._hass.callWS({type:'improved_shopping_list/receipts/discard',token}).catch(()=>{});}
    });
  }
  _setBusy(busy){this._busy=busy;const upload=this.shadowRoot.querySelector('#upload-ticket');if(upload)upload.disabled=busy||this._hass?.user?.is_admin!==true;this.dispatchEvent(new CustomEvent('receipt-busy',{detail:busy}));this.shadowRoot.querySelectorAll('dialog button,dialog input,dialog select').forEach(el=>{el.disabled=busy||el.dataset.locked==='true';});this._updateRecoveryControl();}
  async _upload(file){
    if(this._busy)return;
    this._error='';
    if(!file.name.toLowerCase().endsWith('.pdf')||file.size>2*1024*1024){this._error='Sube un PDF de hasta 2 MB.';this._render();return;}
    this._setBusy(true);this._reading=true;this._render();
    try{
      const encoded=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result.split(',')[1]);reader.onerror=()=>reject(new Error('No se ha podido leer el archivo.'));reader.readAsDataURL(file);});
      this._draft=await this._hass.callWS({type:'improved_shopping_list/receipts/preview',pdf:encoded});
      if(!this.isConnected||!this._active){const token=this._draft.token;this._draft=null;void this._hass.callWS({type:'improved_shopping_list/receipts/discard',token}).catch(()=>{});return;}
      this._buildReview();this.shadowRoot.querySelector('dialog').showModal();
    }catch(error){this._error=error.message??'No se ha podido leer el ticket.';}
    finally{this._reading=false;this._setBusy(false);this._render();}
  }
  _buildReview(){
    const root=this.shadowRoot,{receipt,products}=this._draft,used=new Set();
    root.querySelector('#review-summary').replaceChildren(node('strong','',receipt.store_name+(receipt.provisional_store?' · Provisional':receipt.zone_candidates?.length>1&&receipt.needs_details?' · Tiendas por confirmar':'')+(receipt.document_type==='invoice'?' · Factura':'')),node('span','',documentDate(receipt)),node('strong','',money(receipt.total)));
    this._step=this._draft.reprocess?2:0;
    root.querySelector('#review-title').textContent=this._draft.reprocess?'Reprocesar ticket':'Revisar ticket';
    this._reviewGroups={};
    this._lidlMetadataDone=new Map();
    root.querySelector('#review-lines').replaceChildren();
    this._edits=receipt.lines.map(line=>{
      const candidate=products.find(p=>p.id===line.product_id&&!used.has(p.id)),product=line.matched===false?null:candidate;if(product)used.add(product.id);
      return {line,id:line.id,product_id:product?.id??'',search:candidate?.name??'',
        replenish:!this._draft.reprocess&&Boolean(product?.stock_id),quantity:product?this._defaultQuantity(line,product):null,
        unit:product?.unit??'uds',purchase_id:null,save_price:Boolean(this._pricesEnabled),packageFormat:this._lineFormat(line,product)};
    });
    root.querySelector('#review-error').hidden=true;this._renderStep();if(this._draft.warning)this._errorMessage(this._draft.warning);
    const token=this._draft.token;
    this._packageMetadataTask=Promise.resolve().then(()=>this._loadPackageMetadata(token));
  }
  _defaultQuantity(line,product){return recoveredStockQuantity(line,product,this._draft.receipt.store)??(product.stock_id?product.refill_quantity:this._quantity(line,product.unit)??product.refill_quantity)??null;}
  async _completeQuantities(){
    if(this._draft?.reprocess||this._draft?.receipt.store!=='carrefour')return;
    const token=this._draft.token,edits=this._edits.filter(edit=>edit.product_id&&!edit.quantityEdited&&edit.line.purchased_quantity==null&&recoveredStockQuantity(edit.line,this._product(edit),'carrefour')==null);
    if(!edits.length)return;
    const dialog=this.shadowRoot.querySelector('#quantity-progress');
    dialog.querySelector('h2').textContent='Completando cantidades';
    const progress=dialog.querySelector('progress'),label=dialog.querySelector('.quantity-progress-label');dialog.showModal();
    try{
      for(let index=0;index<edits.length;index++){
        if(this._draft?.token!==token||!this.isConnected)return;
        const edit=edits[index],product=this._product(edit);
        progress.value=index/edits.length*100;label.textContent=`${index} de ${edits.length} · Completando cantidad de ${edit.line.description}`;
        try{
          const result=await this._hass.callWS({type:'improved_shopping_list/receipts/estimate_quantity',token,line_id:edit.id,product_id:edit.product_id});
          if(this._draft?.token!==token)return;
          if(result.quantity>0&&result.unit&&!edit.quantityEdited){
            edit.line.purchased_quantity=result.quantity;edit.line.purchased_unit=result.unit;edit.line.quantity_estimated=Boolean(result.estimated);
            if(!product.stock_id)edit.unit=result.unit;
            const quantity=recoveredStockQuantity(edit.line,{...product,unit:edit.unit},'carrefour');
            if(quantity!=null){edit.quantity=quantity;edit.quantityEstimated=Boolean(result.estimated);}
          }else if(result.reason)edit.quantityReason=result.reason;
        }catch(error){edit.quantityReason=error.message??'No se ha podido calcular la cantidad.';}
        progress.value=(index+1)/edits.length*100;label.textContent=`${index+1} de ${edits.length}`;
      }
    }finally{dialog.close();}
  }
  _lineFormat(line,product){
    if(line.ticket_measure_price&&line.purchased_quantity!=null)return {content_quantity:null,content_unit:'',content_confirmed:false};
    const ref=referenceFor(product,this._draft.receipt.store,line),hint=suggestedContent(line);
    const saved=ref?.content_confirmed&&!this._draft.reprocess;
    return {content_quantity:saved?ref.content_quantity:hint.quantity??ref?.content_quantity??null,content_unit:saved?ref.content_unit:hint.unit||ref?.content_unit||'',content_confirmed:Boolean(saved)};
  }
  async _loadPackageMetadata(token){
    const cache=new Map();
    for(const edit of this._edits){
      if(this._draft?.token!==token||!this.isConnected)return;
      const code=edit.line.ean,identity=barcodeIdentity(code);
      if(edit.line.ticket_measure_price||!edit.product_id||!identity||edit.packageFormat.content_confirmed||validReferenceContent(edit.packageFormat))continue;
      try{
        if(!cache.has(identity))cache.set(identity,await this._hass.callWS({type:'improved_shopping_list/catalog/nutriscore',code}));
        if(this._draft?.token!==token||!this.isConnected)return;
        const data=cache.get(identity),format={content_quantity:data.content_quantity,content_unit:data.content_unit};
        if(!edit.packageFormat.content_confirmed&&validReferenceContent(format)){
          // OFF quantities already describe the complete package, including multipacks.
          edit.line.pack_quantity=format.content_quantity;edit.line.pack_unit=format.content_unit;
          edit.packageFormat={...format,content_confirmed:false};
          if(!edit.quantityEdited){edit.quantity=this._defaultQuantity(edit.line,this._product(edit));edit.quantityEstimated=Boolean(edit.line.quantity_estimated);}
          if(this._step===1||this._step===2)this._renderStep();
        }
      }catch{/* Missing optional metadata must not prevent receipt review. */}
    }
    if(this._draft?.token===token&&this._draft.receipt.store==='lidl')await this._loadLidlMetadata(token);
  }
  async _loadLidlMetadata(token){
    const edits=this._edits.filter(edit=>edit.product_id&&this._lidlMetadataDone.get(edit.id)!==edit.product_id);
    if(!edits.length)return;
    const dialog=this.shadowRoot.querySelector('#quantity-progress'),progress=dialog.querySelector('progress'),label=dialog.querySelector('.quantity-progress-label');
    dialog.querySelector('h2').textContent='Completando datos de Lidl';if(!dialog.open)dialog.showModal();
    try{
      for(let index=0;index<edits.length;index++){
        if(this._draft?.token!==token||!this.isConnected)return;
        const edit=edits[index],productId=edit.product_id;
        progress.value=index/edits.length*100;label.textContent=`${index} de ${edits.length} · ${edit.line.description}`;
        try{
          const data=await this._hass.callWS({type:'improved_shopping_list/receipts/lidl_metadata',token,line_id:edit.id,product_id:productId});
          if(this._draft?.token!==token||!this.isConnected)return;
          if(edit.product_id!==productId)continue;
          this._lidlMetadataDone.set(edit.id,productId);
          if(data.url){edit.lidlMetadata=data;}
          const format={content_quantity:data.content_quantity,content_unit:data.content_unit};
          if(!edit.line.ticket_measure_price&&!edit.packageEdited&&!validReferenceContent(edit.packageFormat)&&validReferenceContent(format)){
            edit.packageFormat={...format,content_confirmed:false};
            edit.line.pack_quantity=format.content_quantity;edit.line.pack_unit=format.content_unit;
            if(!edit.quantityEdited)edit.quantity=this._defaultQuantity(edit.line,this._product(edit));
          }
        }catch{/* Keep manual review available when a listing cannot be read. */}
        progress.value=(index+1)/edits.length*100;label.textContent=`${index+1} de ${edits.length}`;
      }
    }finally{
      if(this._draft?.token===token){dialog.close();this._renderStep();}
    }
  }
  _quantity(line,unit){
    if(line.purchased_quantity!=null){
      const scales={g:['mass',1],kg:['mass',1000],ml:['volume',1],cl:['volume',10],l:['volume',1000],uds:['count',1]},source=scales[line.purchased_unit],target=scales[unit];
      if(source&&target&&source[0]===target[0])return Math.round(line.purchased_quantity*source[1]/target[1]*1000)/1000;
    }
    if(unit==='uds')return line.count;
    const scales={g:['mass',1],kg:['mass',1000],ml:['volume',1],cl:['volume',10],l:['volume',1000]},source=scales[line.pack_unit],target=scales[unit];
    return source&&target&&source[0]===target[0]&&line.pack_quantity?Math.round(line.count*line.pack_quantity*source[1]/target[1]*1000)/1000:null;
  }
  _product(edit){return this._draft.products.find(p=>p.id===edit.product_id);}
  _updateOptions(options){
    for(const edit of this._edits){
      const before=this._product(edit),after=options.products.find(p=>p.id===edit.product_id);
      if(after&&before&&(before.unit!==after.unit||before.stock_id!==after.stock_id)){
        edit.unit=after.unit;edit.quantity=this._defaultQuantity(edit.line,after);edit.replenish=Boolean(after.stock_id);edit.purchase_id=null;
      }
    }
    Object.assign(this._draft,options);
  }
  _errorMessage(message){const error=this.shadowRoot.querySelector('#review-error');error.textContent=message;error.hidden=!message;}
  _button(name,mdi,action,cls='small-button'){
    const button=node('button',cls);button.type='button';button.title=name;button.setAttribute('aria-label',name);button.append(icon(mdi));button.addEventListener('click',action);return button;
  }
  _chooseProduct(edit,product){
    if(product&&this._edits.some(other=>other!==edit&&other.product_id===product.id)){
      edit.product_id='';this._errorMessage('Este producto ya está vinculado a otra línea. Libera primero esa vinculación.');return false;
    }
    const changed=edit.product_id!==(product?.id??'');edit.product_id=product?.id??'';
    if(changed){if(edit.line.quantity_estimated){delete edit.line.purchased_quantity;delete edit.line.purchased_unit;delete edit.line.quantity_estimated;}edit.quantityEdited=false;edit.quantityEstimated=false;edit.unit=product?.unit??'uds';edit.quantity=product?this._defaultQuantity(edit.line,product):null;edit.replenish=Boolean(product?.stock_id);edit.purchase_id=null;edit.packageFormat=this._lineFormat(edit.line,product);}
    this._errorMessage('');return true;
  }
  _goToStep(step){
    if(this._draft?.reprocess)return;
    if(this._busy||!this._draft||!Number.isInteger(step)||step<0||step>=this._step)return;
    this._step=step;this._errorMessage('');this._renderStep();
  }
  _renderStep(){
    if(!this._draft)return;
    const root=this.shadowRoot,step=this._step;
    const reprocess=Boolean(this._draft.reprocess);
    root.querySelector('#review-steps').hidden=reprocess;
    root.querySelectorAll('#review-steps button').forEach((button,index)=>{
      if(index===step)button.setAttribute('aria-current','step');else button.removeAttribute('aria-current');
      button.dataset.completed=String(index<step);button.dataset.locked=String(index>=step);button.disabled=this._busy||index>=step;
    });
    root.querySelector('#step-title').hidden=true;
    root.querySelector('#step-title').textContent='';
    root.querySelector('#step-help').textContent=[
      'Vincula los productos detectados en el ticket con los de tu catálogo. Si no existen, puedes crear un producto nuevo o simplemente ignorarlos.',
      'Marca aquellos productos que quieres añadir al registro de stock.',
      this._pricesEnabled?'Selecciona los productos cuyo precio quieres actualizar en el catálogo, para esta tienda.':'Los precios están desactivados en Ajustes. Puedes confirmar las vinculaciones y la reposición sin guardar precios.'
    ][step];
    if(step===2&&this._draft.receipt.document_type==='invoice'&&this._pricesEnabled)root.querySelector('#step-help').textContent+=' El precio sugerido es el PVP unitario antes de descuentos y no incluye el envío.';
    if(step===2)root.querySelector('#step-help').textContent+=' El contenido corresponde a un envase de ese EAN; si es un pack, indica el contenido total del pack.';
    if(reprocess)root.querySelector('#step-help').textContent='Revisa el contenido de un envase de cada EAN. En los packs, indica su contenido total. Se guardarán sus alternativas en el catálogo y, si los precios están activados, el precio del ticket, conservando cualquier precio más reciente.';
    root.querySelector('#step-help').hidden=step===3;
    root.querySelector('#review-summary').hidden=step===3;
    root.querySelector('#previous-step').hidden=step===0||reprocess;root.querySelector('#links-only').hidden=step!==0||reprocess;
    root.querySelector('#previous-step').textContent=step===1?'Volver a vinculación':'Anterior';
    root.querySelector('#stock-only').hidden=step!==1;
    root.querySelector('#prices-only').hidden=step!==2||!this._pricesEnabled||reprocess;
    root.querySelector('#confirm-ticket').textContent=reprocess?'Guardar datos':step===3?'Confirmar compra':'Continuar';
    root.querySelector('#confirm-ticket').classList.toggle('continue',step!==3);
    for(const group of root.querySelectorAll('#review-lines .review-group'))this._reviewGroups[group.dataset.group]=group.open;
    const container=root.querySelector('#review-lines');container.replaceChildren();container.hidden=step===3;
    const grouped=step<2?node('details','review-group'):null;
    const groupedContent=step<2?node('div','review-group-content'):null;
    if(grouped){grouped.dataset.group=step===0?'links':'stock';grouped.id=step===0?'linked-products-group':'unregistered-stock-group';grouped.open=Boolean(this._reviewGroups[grouped.dataset.group]);}
    if(step===2&&this._pricesEnabled&&!reprocess){
      const allLabel=node('label','check select-all-prices'),all=node('input');all.type='checkbox';
      const linked=this._edits.filter(edit=>this._product(edit));all.checked=linked.length>0&&linked.every(edit=>edit.save_price);all.indeterminate=linked.some(edit=>edit.save_price)&&!all.checked;
      all.addEventListener('change',()=>{for(const edit of linked)edit.save_price=all.checked;this._renderStep();});
      allLabel.append(all,document.createTextNode('Seleccionar todos los precios'));container.append(allLabel);
    }
    for(const edit of step===3?[]:this._edits){
      const product=this._product(edit);if(step>0&&!product&&!reprocess)continue;
      const row=node('div','review-line');row.dataset.lineId=edit.id;
      if(step===0)this._associationRow(row,edit);
      if(step===1)this._stockRow(row,edit,product);
      if(step===2&&reprocess&&!product){this._associationRow(row,edit);container.append(row);continue;}
      if(step===2){
        row.classList.add('price-line');
        const toggle=node('button','price-select');toggle.type='button';toggle.setAttribute('aria-label','Guardar precio de '+product.name);
        const selected=Boolean(edit.save_price&&this._pricesEnabled);toggle.setAttribute('aria-pressed',String(selected));row.dataset.selected=String(selected);
        toggle.dataset.locked=String(!this._pricesEnabled||reprocess);toggle.disabled=!this._pricesEnabled||reprocess;
        toggle.addEventListener('click',()=>{
          if(this._busy||!this._pricesEnabled)return;
          edit.save_price=!edit.save_price;this._renderStep();
          [...root.querySelectorAll('.review-line')].find(line=>line.dataset.lineId===String(edit.id))?.querySelector('.price-select')?.focus();
        });
        const name=node('div','price-product-name'),label=node('div','price-label'),price=node('div','price-value',money(edit.line.unit_price));
        const ref=referenceFor(product,this._draft.receipt.store,edit.line),previous=product.reference_prices?.find(offer=>ref?.id&&offer.commercial_reference_id===ref.id||edit.line.ean&&offer.ean===edit.line.ean)?.price??(product.reference_prices?null:product.price);
        if(previous!=null&&Math.round(previous*100)!==Math.round(edit.line.unit_price*100))price.append(node('del','', '('+money(previous)+')'));
        label.append(node('strong','',product.name),price);name.append(this._productImage(product),label);toggle.append(name);row.append(toggle);
        if(edit.line.ticket_measure_price){const rate=edit.line.ticket_measure_price;row.append(node('p','note',edit.line.purchased_quantity+' '+edit.line.purchased_unit+' · '+money(rate.price)+'/'+rate.unit));}
        else row.append(referenceContentControls(edit.packageFormat,()=>{edit.packageEdited=true;}));
        if(edit.lidlMetadata?.url)row.append(node('p','note',edit.lidlMetadata.format_provisional?'Formato propuesto desde una oferta de Lidl. Confirma que coincide con el envase comprado.':'Datos recuperados de la ficha de Lidl.'));
      }
      if(grouped&&(step===0?Boolean(product):!product?.stock_id))groupedContent.append(row);
      else container.append(row);
    }
    if(groupedContent?.childElementCount){
      const summary=node('summary');summary.append(node('span','',(step===0?'Productos vinculados':'Productos sin stock registrado')+' ('+groupedContent.childElementCount+')'),icon('mdi:chevron-down'));
      grouped.append(summary,groupedContent);container.append(grouped);
    }
    if(step>0&&!this._edits.some(edit=>edit.product_id))container.append(node('p','note','No hay productos vinculados en este ticket.'));

    const result=root.querySelector('#review-result');result.hidden=step!==3;
    if(step===3)this._renderPurchaseSummary(result);
    root.querySelectorAll('dialog button,dialog input,dialog select').forEach(el=>{el.disabled=this._busy||el.dataset.locked==='true';});
  }
  _renderPurchaseSummary(result){
    const receipt=this._draft.receipt;
    const heading=node('div','purchase-heading'),identity=node('div');
    identity.append(node('h3','','Resumen de la compra'),node('span','muted',receipt.store_name+' · '+documentDate(receipt)));
    heading.append(icon('mdi:receipt-check'),identity,node('strong','purchase-total',money(receipt.total)));
    const stats=node('div','purchase-stats');
    for(const [label,value] of [
      ['Vinculados',this._edits.filter(e=>e.product_id).length],
      ['Para reponer',this._edits.filter(e=>e.product_id&&e.replenish).length],
      ['Precios actualizados',this._edits.filter(e=>e.product_id&&e.save_price&&this._pricesEnabled).length]
    ]){const stat=node('div');stat.append(node('strong','',value),node('span','',label));stats.append(stat);}
    const lines=node('div','purchase-lines');
    for(const edit of this._edits){
      const product=this._product(edit),line=node('div','purchase-summary-line'),detail=node('div');
      detail.append(node('strong','',product?.name||edit.line.description));
      const actions=[];
      if(product&&edit.replenish)actions.push('Stock: +'+edit.quantity+' '+edit.unit);
      if(product&&edit.save_price&&this._pricesEnabled)actions.push('Precio: '+money(edit.line.unit_price));
      if(!product)actions.push('Sin vincular');
      if(actions.length)detail.append(node('span','muted',actions.join(' · ')));
      line.append(detail,node('span','',money(edit.line.amount)));lines.append(line);
    }
    if(receipt.shipping)lines.append(this._totalRow('Gastos de envío',receipt.shipping));
    if(receipt.discount)lines.append(this._totalRow('Descuentos generales',-receipt.discount));
    result.replaceChildren(heading,stats,lines,this._totalRow('Total de la compra',receipt.total));
  }
  _productImage(product){
    const media=node('span','association-image'),fallback=icon(product.icon||'mdi:shopping');
    let source='';try{const url=new URL(product.image_url||'',location.origin);if(product.image_url&&['http:','https:'].includes(url.protocol))source=url.href;}catch{ /* Invalid image uses the product icon. */ }
    if(source){const image=node('img');image.src=source;image.alt='';image.loading='lazy';image.referrerPolicy='no-referrer';image.addEventListener('error',()=>image.replaceWith(fallback),{once:true});media.append(image);}
    else media.append(fallback);
    return media;
  }
  _associationRow(row,edit){
    row.classList.add('association-row');
    const name=node('div','association-name');name.append(node('strong','',edit.line.description));
    if(edit.line.ean)name.append(node('span','receipt-ean','EAN: '+edit.line.ean));
    const product=this._product(edit);
    if(product){
      row.append(this._productImage(product));name.append(node('span','linked-name','→ '+product.name));
    }
    const buttons=node('div','association-buttons');
    const link=this._button('Vincular producto para '+edit.line.description,'mdi:link-variant',()=>this._openAssociation(edit),'small-button link');
    link.setAttribute('aria-pressed',String(Boolean(product)));
    const create=this._button('Crear producto para '+edit.line.description,'mdi:plus-thick',()=>void this._createProduct(edit),'small-button create');
    buttons.append(link,create);row.append(name,buttons);
  }
  _openAssociation(edit){
    if(this._busy)return;
    this._associationEdit=edit;
    const root=this.shadowRoot;
    root.querySelector('#association-title').textContent='Vincular '+edit.line.description;
    const search=root.querySelector('#association-search');search.value=this._product(edit)?.name??'';
    root.querySelector('#association-products').replaceChildren(...this._draft.products
      .filter(product=>!this._edits.some(other=>other!==edit&&other.product_id===product.id))
      .map(product=>new Option(product.name,product.name)));
    root.querySelector('#association-error').hidden=true;
    root.querySelector('#association-dialog').showModal();search.focus();
  }
  _confirmAssociation(){
    const edit=this._associationEdit;if(this._busy||!this._draft||!edit)return;
    const root=this.shadowRoot,search=root.querySelector('#association-search');
    const product=this._draft.products.find(p=>productNameKey(p.name)===productNameKey(search.value));
    const error=root.querySelector('#association-error');
    error.textContent=!product?'Selecciona un producto del catálogo.':this._edits.some(other=>other!==edit&&other.product_id===product.id)?'Este producto ya está vinculado a otra línea. Libera primero esa vinculación.':'';
    error.hidden=!error.textContent;if(error.textContent)return;
    if(this._chooseProduct(edit,product)){edit.search=product.name;root.querySelector('#association-dialog').close();this._renderStep();}
  }
  _stockRow(row,edit,product){
    row.classList.add('stock-line');
    const main=node('div','stock-line-main'),name=node('div','stock-line-name');
    name.append(node('strong','',edit.line.description),node('span','linked-name','→ '+product.name));
    const quantity=node('input');
    quantity.type='number';quantity.min='0.001';quantity.max='1000000';quantity.step='0.001';quantity.value=edit.quantity??'';quantity.setAttribute('aria-label','Cantidad para '+edit.line.description);
    quantity.dataset.locked=String(!edit.replenish);quantity.disabled=!edit.replenish;
    quantity.addEventListener('input',()=>{edit.quantity=quantity.value===''?null:Number(quantity.value);edit.quantityEdited=true;edit.quantityEstimated=false;row.querySelector('.estimated-quantity')?.remove();});
    let unit;
    if(product.stock_id){unit=node('span','stock-line-unit',product.unit);unit.title='Unidades: '+product.unit;}
    else{
      unit=node('input');unit.type='text';unit.value=edit.unit;unit.maxLength=32;unit.setAttribute('aria-label','Unidades para '+edit.line.description);
      unit.dataset.locked=String(!edit.replenish);unit.disabled=!edit.replenish;
      unit.addEventListener('change',()=>{edit.unit=unit.value.trim();edit.quantity=this._quantity(edit.line,edit.unit);this._renderStep();});
    }
    const toggle=node('button','stock-select');toggle.type='button';toggle.setAttribute('aria-label',(product.stock_id?'Reponer stock: ':'Incluir en Stock: ')+product.name);
    toggle.setAttribute('aria-pressed',String(edit.replenish));row.dataset.selected=String(edit.replenish);
    toggle.addEventListener('click',()=>{
      if(this._busy)return;
      edit.replenish=!edit.replenish;this._errorMessage('');this._renderStep();
      [...this.shadowRoot.querySelectorAll('.review-line')].find(line=>line.dataset.lineId===String(edit.id))?.querySelector('.stock-select')?.focus();
    });
    const fields=node('div','stock-quantity');fields.append(quantity,unit);main.append(this._productImage(product),name,fields);row.append(toggle,main);
    if(edit.quantityEstimated)row.append(node('small','estimated-quantity','Cantidad estimada'));
    if(edit.quantityReason){const note=node('small','note',edit.quantityReason);row.append(note);}
    const previous=this._draft.purchases.filter(p=>p.item_id===product.stock_id&&p.unit===product.unit);
    if(previous.length){
      const purchaseLabel=node('label','purchase'),purchase=node('select');purchase.setAttribute('aria-label','Reposición de '+edit.line.description);
      purchase.replaceChildren(new Option('Selecciona compra nueva o reposición anterior','__choose__'),new Option('Registrar una compra nueva',''),...previous.map(p=>new Option(`${date(p.at*1000)} · ${p.quantity} ${p.unit}`,p.id)));
      purchase.value=edit.purchase_id??'__choose__';purchase.dataset.locked=String(!edit.replenish);purchase.disabled=!edit.replenish;
      purchase.addEventListener('change',()=>{edit.purchase_id=purchase.value;});purchaseLabel.append(document.createTextNode('Relacionar con una compra ya registrada'),purchase);row.append(purchaseLabel);
    }
  }
  async _createProduct(edit){
    if(this._busy)return;this._errorMessage('');this._setBusy(true);
    try{
      if(!this.createProduct)throw new Error('No se ha podido abrir la ficha del producto.');
      const product=await this.createProduct(edit.line.description);if(!product||!this._draft)return;
      const options=await this._hass.callWS({type:'improved_shopping_list/receipts/options',token:this._draft.token});this._updateOptions(options);
      if(this._chooseProduct(edit,this._draft.products.find(p=>p.id===product.id))){edit.search=product.name;}
      this._renderStep();
    }catch(error){this._errorMessage(error.message??'No se ha podido crear el producto.');}
    finally{this._setBusy(false);}
  }
  _validateLinks(){
    const seen=new Set();
    for(const edit of this._edits){
      if(edit.product_id&&seen.has(edit.product_id)){this._errorMessage('Dos líneas del mismo ticket no pueden vincularse al mismo producto.');return false;}
      if(edit.product_id)seen.add(edit.product_id);
    }
    return true;
  }
  _revealStockLine(edit){
    const row=[...this.shadowRoot.querySelectorAll('.review-line')].find(line=>line.dataset.lineId===String(edit.id));
    const group=row?.closest('.review-group');if(group)group.open=true;
  }
  _validateStock(){
    for(const edit of this._edits.filter(e=>e.product_id&&e.replenish)){
      if(!Number.isFinite(edit.quantity)||edit.quantity<=0||edit.quantity>1000000||Math.abs(edit.quantity*1000-Math.round(edit.quantity*1000))>.00001||!edit.unit.trim()){
        this._revealStockLine(edit);this._errorMessage('Indica cantidades válidas, con hasta tres decimales, y sus unidades para todos los productos que se reponen.');return false;
      }
      const product=this._product(edit),previous=this._draft.purchases.filter(p=>p.item_id===product.stock_id&&p.unit===product.unit);
      if(previous.length&&(edit.purchase_id===null||edit.purchase_id==='__choose__')){this._revealStockLine(edit);this._errorMessage('Indica si cada reposición es una compra nueva o corrige una compra ya registrada.');return false;}
    }
    return true;
  }
  async _saveLinks(only=false){
    if(this._busy||!this._draft||!this._validateLinks())return;this._setBusy(true);this._errorMessage('');
    try{
      const options=await this._hass.callWS({type:'improved_shopping_list/receipts/link',token:this._draft.token,lines:this._edits.map(e=>({id:e.id,product_id:e.product_id}))});
      this._updateOptions(options);
      if(only){this.shadowRoot.querySelector('dialog').close();this._render();}
      else{const token=this._draft.token;this._packageMetadataTask=Promise.resolve(this._packageMetadataTask).then(()=>this._loadPackageMetadata(token));await this._packageMetadataTask;await this._completeQuantities();this._step=1;this._renderStep();}
    }catch(error){this._errorMessage(error.message??'No se han podido guardar las vinculaciones.');}
    finally{this._setBusy(false);}
  }
  async _advance(){
    if(this._busy||!this._draft)return;this._errorMessage('');
    if(this._draft.reprocess){await this._confirm();return;}
    if(this._step===0){await this._saveLinks();return;}
    if(this._step===1){
      if(this._validateStock()){
        const token=this._draft.token;this._setBusy(true);this.shadowRoot.querySelector('#confirm-ticket').textContent='Completando formatos…';
        try{await this._packageMetadataTask;if(this._draft?.token===token){this._step=2;this._renderStep();}}finally{this._setBusy(false);}
      }
      return;
    }
    if(this._step===2){this._step=3;this._renderStep();return;}
    await this._confirm();
  }
  async _confirm(updatePrices=Boolean(this._pricesEnabled)){
    if(this._busy||!this._draft||!this._validateLinks()||(!this._draft.reprocess&&!this._validateStock()))return;
    this._setBusy(true);
    try{
      const token=this._draft.token;
      await this._packageMetadataTask;
      if(this._draft?.token!==token)return;
      if(this._draft.reprocess){
        await this._hass.callWS({type:'improved_shopping_list/receipts/reprocess',token,lines:this._edits.map(edit=>({id:edit.id,product_id:edit.product_id,pack_quantity:validReferenceContent(edit.packageFormat)?edit.packageFormat.content_quantity:null,pack_unit:validReferenceContent(edit.packageFormat)?edit.packageFormat.content_unit:''}))});
      }else await this._hass.callWS({type:'improved_shopping_list/receipts/confirm',token:this._draft.token,update_prices:Boolean(updatePrices&&this._pricesEnabled),
        lines:this._edits.map(edit=>({id:edit.id,product_id:edit.product_id,replenish:Boolean(edit.product_id&&edit.replenish),quantity:edit.replenish?edit.quantity:null,unit:edit.unit,purchase_id:edit.purchase_id??'',save_price:Boolean(edit.product_id&&edit.save_price&&updatePrices&&this._pricesEnabled),quantity_edited:Boolean(edit.quantityEdited),pack_quantity:validReferenceContent(edit.packageFormat)?edit.packageFormat.content_quantity:null,pack_unit:validReferenceContent(edit.packageFormat)?edit.packageFormat.content_unit:''}))});
      this._draft=null;this.shadowRoot.querySelector('dialog').close();await this._session.refresh();this.dispatchEvent(new CustomEvent('receipt-imported'));
    }catch(error){this._errorMessage(error.message??'No se ha podido guardar el ticket.');}
    finally{this._setBusy(false);}
  }
  _render(){
    if(!this._built)return;
    const root=this.shadowRoot,message=root.querySelector('#message');
    const text=this._reading?'Leyendo ticket…':this._error|| (this._history?this._session.error:'') || (this._history&&this._session.loading?'Cargando compras…':'');
    message.textContent=text;message.hidden=!text;message.classList.toggle('error',Boolean(this._error||this._session.error));
    root.querySelector('#history').hidden=!this._history;root.querySelector('#empty').hidden=true;
    root.querySelector('#spending-chart').hidden=!this._history;
    root.querySelector('#more-purchases').hidden=true;
    if(!this._history)return;
    for(const [id,values] of [['filter-shop',new Map(this._session.receipts.map(receipt=>[receipt.shop_id||receipt.store,receipt.shop_name||receipt.store_name]))],['filter-person',new Map(this._session.receipts.flatMap(receipt=>(receipt.shoppers??[]).map(person=>[person,this._hass.states[person]?.attributes?.friendly_name??person])))]]){
      const select=root.querySelector('#'+id),selected=select.value,first=select.options[0].textContent;
      select.replaceChildren(new Option(first,''),...[...values].sort((a,b)=>a[1].localeCompare(b[1],'es')).map(([value,name])=>new Option(name,value)));select.value=selected;select.onchange=()=>{this._visiblePurchases=10;this._render();};
    }
    const period=this._renderSpendingChart();
    const periodKey=period?period.from+':'+period.until:'';
    if(this._purchasePeriod!==periodKey){this._purchasePeriod=periodKey;this._visiblePurchases=10;}
    const receipts=this._session.receipts.filter(receipt=>{
      const when=new Date(receipt.purchased_at).getTime();
      return period&&when>=period.from&&when<period.until&&(!root.querySelector('#filter-shop').value||(receipt.shop_id||receipt.store)===root.querySelector('#filter-shop').value)&&(!root.querySelector('#filter-person').value||(receipt.shoppers??[]).includes(root.querySelector('#filter-person').value));
    }).sort((a,b)=>new Date(b.purchased_at)-new Date(a.purchased_at));
    const empty=root.querySelector('#empty');
    empty.textContent=this._session.receipts.length?'No hay compras registradas en este periodo.':'Todavía no has subido ningún ticket.';
    empty.hidden=receipts.length>0||this._session.loading||Boolean(this._session.error);
    root.querySelector('#more-purchases').hidden=receipts.length<=this._visiblePurchases;
    root.querySelector('#history').replaceChildren(...receipts.slice(0,this._visiblePurchases).map(receipt=>{
      const card=node('article','ticket'+(receipt.needs_details?' needs-details':''));card.dataset.id=receipt.id;
      const title=node('div','title');title.append(node('strong','',(receipt.shop_name||receipt.store_name)+(receipt.document_type==='invoice'?' · Factura':'')),node('span','muted',documentDate(receipt)+(receipt.article_count==null?'':' · '+receipt.article_count+' artículos')));
      const open=this._button('Ver ticket de '+receipt.store_name+' del '+documentDate(receipt),'mdi:receipt-text',()=>receipt.summary_only?void this._reviewPending(receipt):this._openPurchaseDetail(receipt),'ticket-open'+(!receipt.summary_only?' reviewed':''));
      if(receipt.shoppers?.length)title.append(node('span','shoppers',receipt.shoppers.map(person=>this._hass.states[person]?.attributes?.friendly_name??person).join(', ')));if(receipt.allocation_pending)title.append(node('small','muted','Productos pendientes de repartir'));
      card.style.borderLeft=receipt.shop_color?'4px solid '+receipt.shop_color:'';
      card.append(this._receiptImage(receipt),title,node('span','total',receipt.total==null?'Importe pendiente':money(receipt.total)));if(!receipt.summary_only||receipt.pending_review||(['carrefour','dia','lidl'].includes(receipt.store)&&receipt.account_key&&receipt.ticket_available!==false))card.append(open);if(receipt.detected_purchase)card.append(this._button(receipt.needs_details?'Completar compra detectada':'Editar compra detectada','mdi:pencil',()=>this._editDetectedPurchase(receipt),'ticket-open edit-detection'));return card;
    }));
  }
  _detectedStoreFields(){const root=this.shadowRoot;this._recoveryToken=null;root.querySelector('#detected-recovery-results').replaceChildren();this._updateRecoveryControl();const other=root.querySelector('#detected-store').value==='other';root.querySelector('#detected-other-label').hidden=!other;root.querySelector('#detected-other').required=other;for(const button of root.querySelectorAll('.zone-store-choice'))button.setAttribute('aria-pressed',String(button.dataset.store===root.querySelector('#detected-store').value));}
  _editDetectedPurchase(receipt){
    if(this._busy)return;this._detectedReceipt=receipt.id;const root=this.shadowRoot;
    root.querySelector('#detected-date').textContent=documentDate(receipt)+' · '+receipt.article_count+' productos completados';
    const shopSelect=root.querySelector('#detected-store');shopSelect.querySelectorAll('[data-shop]').forEach(n=>n.remove());for(const shop of this._session.shops){const option=new Option(shop.name,'shop:'+shop.id);option.dataset.shop='true';shopSelect.append(option);}shopSelect.value=receipt.shop_id&&this._session.shops.some(shop=>shop.id===receipt.shop_id)?'shop:'+receipt.shop_id:receipt.store==='unknown'?'':STORE_NAMES[receipt.store]?receipt.store:'other';
    root.querySelector('#detected-other').value=receipt.store.startsWith('other:')||receipt.shop_id&&!this._session.shops.some(shop=>shop.id===receipt.shop_id)?receipt.store_name:'';
    root.querySelector('#detected-total').value=receipt.total==null?'':String(receipt.total);const people=root.querySelector('#detected-shoppers');people.replaceChildren(...[...new Set([...(this._session.persons??[]),...(receipt.shoppers??[])])].map(person=>{const option=new Option(this._hass.states[person]?.attributes?.friendly_name??person,person);option.selected=(receipt.shoppers??[]).includes(person);return option;}));
    const candidates=receipt.needs_details?(receipt.zone_candidates??[]):[];
    const choices=root.querySelector('#detected-zone-candidates');choices.hidden=!candidates.length;
    const hint=root.querySelector('#detected-zone-help');hint.hidden=!candidates.length;hint.textContent=candidates.length===1?'Tienda propuesta por presencia en su zona. Puedes confirmarla o elegir otra.':'Se han registrado visitas a varias tiendas ese día. Selecciona dónde hiciste la compra.';
    choices.replaceChildren(...candidates.map(store=>{const name=STORE_NAMES[store]??store,button=node('button','zone-store-choice');button.type='button';button.dataset.store=store;button.setAttribute('aria-label',name);button.append(this._storeImage(store,name),node('span','',name));button.addEventListener('click',()=>{root.querySelector('#detected-store').value=store;this._detectedStoreFields();});return button;}));
    const completed=new Set((receipt.completed_products??[]).map(p=>p.key));root.querySelector('#detected-products').replaceChildren(...(receipt.candidate_products??receipt.completed_products??[]).map(product=>{const li=node('li'),label=node('label','product-choice');if(product.key){const input=node('input');input.type='checkbox';input.dataset.productKey=product.key;input.checked=completed.has(product.key);label.append(input);}label.append(document.createTextNode(product.name));li.append(label);return li;}));
    root.querySelector('#detected-error').hidden=true;this._detectedStoreFields();root.querySelector('#detected-purchase-dialog').showModal();
  }
  _updateRecoveryControl(){
    const root=this.shadowRoot;if(!this._built)return;const selected=root.querySelector('#detected-store').value,shop=this._session.shops.find(shop=>selected==='shop:'+shop.id),account=shop?shop.account:selected;
    root.querySelector('#recover-detected').disabled=this._busy||!this._session.ticketAccounts[account];
    root.querySelector('#detected-recovery-help').textContent=!selected?'Elige una tienda para buscar su ticket.':!this._session.ticketAccounts[account]?'La tienda debe tener una cuenta conectada en Ajustes → Tiendas.':'Busca los tickets de ese día. La recuperación manual no necesita esperar a la consulta automática.';
  }
  async _searchDetectedTickets(){
    if(this._busy||!this._detectedReceipt)return;const root=this.shadowRoot;this._setBusy(true);root.querySelector('#detected-error').hidden=true;root.querySelector('#detected-recovery-results').replaceChildren();
    try{
      const result=await this._hass.callWS({type:'improved_shopping_list/receipts/search_detection_ticket',receipt_id:this._detectedReceipt,store:root.querySelector('#detected-store').value});
      if(!this.isConnected||!this._active||!root.querySelector('#detected-purchase-dialog').open)return;
      this._recoveryToken=result.recovery_token;
      if(result.purchases.length===1){await this._openRecoveredTicket(result.purchases[0].id);return;}
      const results=root.querySelector('#detected-recovery-results');results.append(node('p','note',result.purchases.length?'Elige el ticket que corresponde a esta compra.':'No se han encontrado tickets pendientes de revisión para ese día en esta cuenta. Puedes completar la compra manualmente o subir el ticket.'));
      for(const purchase of result.purchases){const button=this._button('Revisar ticket del '+date(purchase.purchased_at)+' · '+money(purchase.amount),'mdi:receipt-text',()=>void this._reviewDetectedTicket(purchase.id),'recovery-choice');button.append(node('span','',date(purchase.purchased_at)),node('strong','',money(purchase.amount)));results.append(button);}
    }catch(error){root.querySelector('#detected-error').textContent=error.message??'No se ha podido recuperar la compra.';root.querySelector('#detected-error').hidden=false;}
    finally{this._setBusy(false);}
  }
  async _reviewDetectedTicket(id){
    if(this._busy)return;this._setBusy(true);const root=this.shadowRoot;root.querySelector('#detected-error').hidden=true;
    try{await this._openRecoveredTicket(id);}catch(error){root.querySelector('#detected-error').textContent=error.message??'No se ha podido recuperar el ticket.';root.querySelector('#detected-error').hidden=false;}finally{this._setBusy(false);}
  }
  async _openRecoveredTicket(id){
    const root=this.shadowRoot;await this._hass.callWS({type:'improved_shopping_list/receipts/preview_detection_ticket',recovery_token:this._recoveryToken,purchase_id:id});
    root.querySelector('#detected-purchase-dialog').close();this._detectedReceipt=null;this._recoveryToken=null;
    if(this.isConnected&&this._active)await this._session.refresh();
  }
  async _saveDetectedPurchase(discard=false){
    if(this._busy||!this._detectedReceipt)return;const root=this.shadowRoot;this._setBusy(true);
    try{
      await this._hass.callWS({type:'improved_shopping_list/receipts/'+(discard?'discard_detection':'complete_detection'),receipt_id:this._detectedReceipt,
        ...(discard?{}:{store:root.querySelector('#detected-store').value,total:Number(root.querySelector('#detected-total').value),store_name:root.querySelector('#detected-other').value,...(this._session.persons?.length?{shoppers:Array.from(root.querySelector('#detected-shoppers').selectedOptions,o=>o.value)}:{}),...(root.querySelector('#detected-products [data-product-key]')?{product_keys:Array.from(root.querySelectorAll('#detected-products input:checked'),n=>n.dataset.productKey)}:{})})});
      root.querySelector('#detected-purchase-dialog').close();this._detectedReceipt=null;await this._session.refresh();
    }catch(error){const message=root.querySelector('#detected-error');message.textContent=error.message??'No se ha podido guardar la compra.';message.hidden=false;}
    finally{this._setBusy(false);}
  }
  async _reviewPending(receipt){
    if(this._busy)return;
    this._setBusy(true);this._error='';
    try{const draft=await this._hass.callWS({type:receipt.pending_review?'improved_shopping_list/receipts/review_saved':'improved_shopping_list/'+receipt.store+'_account/preview_saved',receipt_id:receipt.id});this._draft=draft;this._buildReview();this.shadowRoot.querySelector('dialog').showModal();}
    catch(error){this._error=error.message??'No se ha podido abrir el ticket.';this._render();}
    finally{this._setBusy(false);}
  }
  _receiptImage(receipt){if(!receipt.shop_image)return this._storeImage(receipt.store,receipt.store_name);const image=node('img','store-image');image.src=receipt.shop_image;image.alt=receipt.shop_name||receipt.store_name;image.referrerPolicy='no-referrer';image.onerror=()=>image.replaceWith(icon('mdi:store'));return image;}
  _storeImage(store,name){
    if(store==='unknown')return icon('mdi:help-circle-outline');
    if(!STORE_LOGOS[store])return icon('mdi:store');
    const image=node('img','store-image');image.src=STORE_LOGOS[store];image.alt=name;image.loading='lazy';image.referrerPolicy='no-referrer';
    image.addEventListener('error',()=>image.replaceWith(icon('mdi:store')),{once:true});return image;
  }
  _openPurchaseDetail(receipt){
    const root=this.shadowRoot;
    root.querySelector('#purchase-detail-info').replaceChildren(this._storeImage(receipt.store,receipt.store_name),node('strong','',receipt.store_name),node('span','muted',documentDate(receipt)),node('strong','total',money(receipt.total)));
    const container=root.querySelector('#purchase-detail-lines');container.replaceChildren();
    for(const line of receipt.lines){
      const row=node('div','line'),description=node('div');description.append(node('p','',line.description),node('p','muted',line.count+' × '+money(line.unit_price)));
      if(line.ean)description.append(node('p','muted','EAN: '+line.ean));
      if(line.line_discount)description.append(node('p','muted','Descuento de línea: −'+money(line.line_discount)));
      if(line.replenished)description.append(node('p','muted',line.product_name+': '+line.quantity+' '+line.unit+' repuestos'));
      row.append(description,node('span','',money(line.amount)));container.append(row);
    }
    if(receipt.shipping)container.append(this._totalRow('Gastos de envío',receipt.shipping));
    if(receipt.discount)container.append(this._totalRow('Descuentos generales',-receipt.discount));
    container.append(this._totalRow('Total',receipt.total));
    if(this._hass?.user?.is_admin===true){const actions=node('div','actions'),button=node('button','','Reprocesar datos');button.type='button';button.addEventListener('click',()=>void this._reprocessSaved(receipt));actions.append(button);container.append(actions);}
    root.querySelector('#purchase-detail').showModal();
  }
  async _reprocessSaved(receipt){
    if(this._busy)return;this._setBusy(true);this._error='';
    try{
      const draft=await this._hass.callWS({type:'improved_shopping_list/receipts/review_saved',receipt_id:receipt.id});
      if(!this.isConnected||!this._active)return;
      this.shadowRoot.querySelector('#purchase-detail').close();this._draft=draft;this._buildReview();this.shadowRoot.querySelector('dialog').showModal();this._setBusy(true);
      await this._packageMetadataTask;
      if(this._draft?.token===draft.token)this._renderStep();
    }catch(error){this._error=error.message??'No se ha podido reprocesar el ticket.';this._render();}
    finally{this._setBusy(false);}
  }
  _purchaseRange(){
    const now=new Date(),from=this._spendingRange?new Date(this._spendingRange.from+'T00:00:00'):new Date(now.getFullYear(),now.getMonth()-5,1);
    const to=this._spendingRange?new Date(this._spendingRange.to+'T00:00:00'):new Date(now.getFullYear(),now.getMonth()+1,0);
    const until=new Date(to);until.setDate(until.getDate()+1);
    return {from:from.getTime(),until:until.getTime(),first:from,last:to,start:from.getFullYear()*12+from.getMonth(),end:to.getFullYear()*12+to.getMonth()};
  }
  _openPurchasePeriod(){
    const root=this.shadowRoot,range=this._purchaseRange();root.querySelector('#purchase-start').value=localDay(range.first);root.querySelector('#purchase-end').value=localDay(range.last);root.querySelector('#purchase-end').setCustomValidity('');root.querySelector('#purchase-period-dialog').showModal();
  }
  _renderSpendingChart(){
    const chart=this.shadowRoot.querySelector('#spending-chart'),months=new Map(),stores=new Map(),shopColors=new Map(),range=this._purchaseRange();
    for(const receipt of this._session.receipts){
      if(this.shadowRoot.querySelector('#filter-shop').value&&(receipt.shop_id||receipt.store)!==this.shadowRoot.querySelector('#filter-shop').value||this.shadowRoot.querySelector('#filter-person').value&&!(receipt.shoppers??[]).includes(this.shadowRoot.querySelector('#filter-person').value))continue;
      const when=new Date(receipt.purchased_at),cents=Math.round(Number(receipt.total)*100);
      if(!Number.isFinite(when.getTime())||when.getTime()<range.from||when.getTime()>=range.until||!Number.isFinite(cents)||cents<0)continue;
      const key=when.getFullYear()+'-'+String(when.getMonth()+1).padStart(2,'0');
      if(!months.has(key))months.set(key,{date:new Date(when.getFullYear(),when.getMonth(),1),total:0,stores:new Map()});
      const store=receipt.shop_id||receipt.store,month=months.get(key);if(receipt.total==null)continue;month.total+=cents;month.stores.set(store,(month.stores.get(store)||0)+cents);stores.set(store,receipt.shop_name||receipt.store_name);if(receipt.shop_color)shopColors.set(store,receipt.shop_color);
    }
    chart.hidden=!this._history;chart.replaceChildren();if(chart.hidden)return;
    const {start,end}=range,visible=[];
    for(let index=start;index<=end;index++){
      const date=new Date(Math.floor(index/12),index%12,1),key=date.getFullYear()+'-'+String(date.getMonth()+1).padStart(2,'0');
      visible.push([key,months.get(key)||{date,total:0,stores:new Map()}]);
    }
    const sortedStores=[...stores].sort((a,b)=>a[1].localeCompare(b[1],'es'));
    const palette=['#607d8b','#9e8048','#6978c8'];
    const colors=new Map(sortedStores.map(([store],index)=>[store,shopColors.get(store)||STORE_COLORS[store]||palette[index%palette.length]]));
    const heading=node('div','chart-heading'),navigation=this._button('Seleccionar periodo de compras','mdi:calendar-range',()=>this._openPurchasePeriod(),'chart-range');
    const format=new Intl.DateTimeFormat('es-ES',{day:'2-digit',month:'2-digit',year:'numeric'});
    navigation.append(node('span','',format.format(range.first)+' – '+format.format(range.last)));
    const actions=node('div','chart-actions'),upload=this._button('Subir ticket','mdi:file-upload',()=>this.chooseFile(),'upload-ticket');upload.id='upload-ticket';upload.title='Subir ticket PDF';upload.disabled=this._busy||this._hass?.user?.is_admin!==true;
    actions.append(navigation,upload);heading.append(node('h3','','Gasto mensual'),actions);
    const bars=node('div','monthly-bars'),scroll=node('div','chart-scroll');
    bars.style.gridTemplateColumns=`repeat(${visible.length},minmax(0,1fr))`;if(visible.length>12)bars.style.minWidth=(visible.length*50)+'px';
    const maximum=Math.max(1,...visible.map(([,month])=>month.total));
    for(const [key,month] of visible){
      const label=new Intl.DateTimeFormat('es-ES',{month:'short',year:'2-digit'}).format(month.date),column=node('div','month-column');column.dataset.month=key;column.dataset.total=String(month.total/100);
      const stack=node('div','month-stack'),descriptions=[];
      for(const [store,name] of sortedStores){
        const amount=month.stores.get(store)||0;if(!amount)continue;
        const segment=node('div','store-segment');segment.dataset.store=store;segment.dataset.amount=String(amount/100);segment.style.height=(amount/maximum*100)+'%';segment.style.background=colors.get(store);segment.title=name+': '+money(amount/100);stack.append(segment);descriptions.push(segment.title);
      }
      column.setAttribute('role','img');column.setAttribute('aria-label',label+': '+money(month.total/100)+'. '+descriptions.join('; '));column.append(node('span','month-total',money(month.total/100)),stack,node('span','month-label',label));bars.append(column);
    }
    const legend=node('div','chart-legend');
    for(const [store,name] of sortedStores){const key=node('span','chart-key'),swatch=node('span','chart-swatch');swatch.style.background=colors.get(store);key.append(swatch,document.createTextNode(name));legend.append(key);}
    scroll.append(bars);chart.append(heading,node('p','chart-note','Importes de las compras registradas, por tienda'),scroll,legend);
    return range;
  }
  _totalRow(label,value){const row=node('div','totals');row.append(node('span','',label),node('strong','',money(value)));return row;}
}
if(!customElements.get('isl-purchases'))customElements.define('isl-purchases',ImprovedShoppingPurchases);
