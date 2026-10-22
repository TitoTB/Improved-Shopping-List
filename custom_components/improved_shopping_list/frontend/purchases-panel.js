import { ListSettingsSession } from "./list-settings-client.js?v=0.34.0";
import { installDialogCloseButtons } from "./dialog-controls.js?v=0.34.0";
import { productNameKey } from "./product-names.js?v=0.34.0";

const node=(tag,cls,text)=>{const el=document.createElement(tag);if(cls)el.className=cls;if(text!==undefined)el.textContent=text;return el;};
const money=value=>new Intl.NumberFormat('es-ES',{style:'currency',currency:'EUR'}).format(value);
const documentDate=receipt=>receipt.document_type==='invoice'?new Intl.DateTimeFormat('es-ES',{dateStyle:'short'}).format(new Date(receipt.purchased_at)):date(receipt.purchased_at);
const date=value=>new Intl.DateTimeFormat('es-ES',{dateStyle:'short',timeStyle:'short'}).format(new Date(value));
const icon=name=>{const el=node('ha-icon');el.setAttribute('icon',name);el.setAttribute('aria-hidden','true');return el;};

const STORE_LOGOS={
  carrefour:'https://images.seeklogo.com/logo-png/31/2/carrefour-logo-png_seeklogo-318190.png',
  alcampo:'https://almeria.online/wp-content/uploads/2024/09/alcampo-logo.png',
  ...Object.fromEntries(['mercadona','consum','lasirena','eroski','dia'].map(store=>[store,new URL(store+'.'+(['mercadona','dia'].includes(store)?'png':store==='eroski'?'svg':'jpg'),import.meta.url).href]))
};
const STORE_COLORS={mercadona:'#29975b',carrefour:'#2388dc',alcampo:'#e15150',consum:'#ef9639',lasirena:'#42b9ca',eroski:'#a968bd',dia:'#e2608c'};

class PurchaseSession extends ListSettingsSession {
  constructor(getHass,onChange){super(getHass,onChange,'improved_shopping_list/receipts/');this.receipts=[];}
  _receive(data){this.receipts=data.receipts??[];this.loaded=true;this.loading=false;this.error='';this.onChange();}
}

class ImprovedShoppingPurchases extends HTMLElement {
  constructor(){
    super();this.attachShadow({mode:'open'});
    this._session=new PurchaseSession(()=>this._hass,()=>this._render());this._busy=false;
  }
  set data(value){
    const changed=this._hass?.connection!==value.hass.connection;
    this._active=value.active;
    this._hass=value.hass;this._history=value.history;this._pricesEnabled=value.pricesEnabled;
    if(!this._built)this._build();
    if(value.active&&this._hass.user?.is_admin===true&&(!this._started||changed)){
      this._started=true;void this._session.start();
    }
    if(!value.active){this._session.stop();this._started=false;this.shadowRoot.querySelectorAll('dialog').forEach(dialog=>dialog.close());}
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
      :host{display:block;color:inherit;font:inherit}*{box-sizing:border-box}[hidden]{display:none!important}
      button,input,select{font:inherit;color:inherit}button{cursor:pointer}button:disabled{opacity:.5;cursor:default}
      input,select{width:100%;min-width:0;min-height:42px;border:1px solid var(--divider-color,#d9e0dd);background:var(--card-background-color,#fff);border-radius:8px;padding:8px}
      .notice{padding:12px;border-radius:10px;background:var(--secondary-background-color,#edf2ef)}.error{color:var(--error-color,#d32f2f)}
      #history{display:grid;gap:12px}.ticket{border-radius:14px;background:var(--card-background-color,#fff);padding:16px}
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
      .price-line{position:relative}.price-select{position:absolute;inset:0;width:100%;height:100%;border:0;border-radius:inherit;background:transparent;padding:0}.price-select:focus-visible{outline:3px solid var(--isl-green,#267052);outline-offset:-3px}.price-line[data-selected=true]{border-color:var(--isl-green,#267052);background:color-mix(in srgb,var(--secondary-background-color,#f2f4f3) 75%,var(--isl-green,#267052))}.price-product-name{position:relative;pointer-events:none}.price-label{min-width:0}.price-value{margin-top:6px}.price-value del{opacity:.6;font-size:.9em;margin-left:6px}.price-product-name strong{display:block}
      @media(max-width:750px){.association-row{flex-wrap:wrap;gap:6px}.association-buttons{width:100%;justify-content:flex-end}.association-buttons .small-button{width:30px;height:34px}.association-buttons ha-icon{--mdc-icon-size:20px;width:20px;height:20px}.association-image{width:26px;height:26px}.stock-line-main{grid-template-columns:20px minmax(0,1fr) minmax(0,1.2fr);gap:4px}.stock-line-main .association-image{width:20px;height:20px}.stock-quantity{gap:3px;font-size:.85em}.stock-quantity input{padding-inline:2px;appearance:textfield}.stock-quantity input::-webkit-inner-spin-button,.stock-quantity input::-webkit-outer-spin-button{-webkit-appearance:none;margin:0}.review-line{padding:8px}.association-name strong,.price-label{font-size:.85em}#review-lines,.review-group-content{gap:8px}.review-group-content{padding:0 8px 8px}}
      .review-summary{padding:18px;border:1px solid var(--divider-color,#d9e0dd);border-radius:14px}.purchase-heading{display:flex;align-items:center;gap:12px}.purchase-heading>ha-icon{color:var(--isl-green,#267052);--mdc-icon-size:28px;width:28px;height:28px}.purchase-heading>div{flex:1;min-width:0}.purchase-heading h3{margin:0;font-size:1.1em}.purchase-heading .muted{display:block;font-size:.85em}.purchase-total{font-size:1.25em;white-space:nowrap}.purchase-stats{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin:18px 0}.purchase-stats>div{display:flex;flex-direction:column;align-items:center;background:var(--card-background-color,#fff);padding:10px 4px;border-radius:10px}.purchase-stats strong{font-size:1.3em;color:var(--isl-green,#267052)}.purchase-stats span{font-size:.8em}.purchase-summary-line{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:10px 0;border-bottom:1px solid var(--divider-color,#d9e0dd)}.purchase-summary-line>div{min-width:0;overflow-wrap:anywhere}.purchase-summary-line .muted{display:block;font-size:.8em}.purchase-summary-line>span{white-space:nowrap}.review-summary>.totals{font-size:1.1em;border-top:2px dashed var(--divider-color,#d9e0dd);padding-top:14px}.purchase-lines{max-height:40vh;overflow:auto}@media(max-width:550px){#review-steps button{font-size:.7em;padding-inline:2px}.review-summary{padding:12px}.purchase-heading{flex-wrap:wrap;gap:8px}.purchase-total{margin-left:auto}.purchase-stats{gap:4px}.purchase-stats span{font-size:.75em}}
      .ticket{display:flex;align-items:center;gap:12px;min-width:0}.store-image{width:42px;height:42px;object-fit:contain;background:white;border-radius:10px;padding:5px;flex:none}.ticket .title{overflow-wrap:anywhere}.ticket .ticket-open{flex:none;width:40px;height:40px;border:0;border-radius:10px;background:var(--secondary-background-color,#edf2ef);display:grid;place-items:center;padding:0}.ticket-open.reviewed{background:var(--isl-green,#267052);color:white}.ticket-open:focus-visible{outline:3px solid var(--primary-color,#267052);outline-offset:2px}#purchase-detail-info{align-items:center;padding-bottom:12px;border-bottom:1px solid var(--divider-color,#d9e0dd)}#purchase-detail-info .total{margin-left:auto}.spending-chart{background:var(--card-background-color,#fff);padding:18px;border-radius:14px;margin-bottom:16px;min-width:0}.spending-chart h3{margin:0 0 4px;font-size:1.05em}.spending-chart .chart-note{font-size:.8em;opacity:.65;margin:0 0 12px}.chart-heading{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}.chart-navigation{display:flex;align-items:center;gap:6px}.chart-period{font-size:.8em;text-align:center}.chart-navigation button{display:grid;place-items:center;width:32px;height:32px;padding:0;border:0;border-radius:8px;background:var(--secondary-background-color,#edf2ef)}.chart-navigation button ha-icon{--mdc-icon-size:22px}.chart-navigation button:focus-visible{outline:3px solid var(--primary-color,#267052);outline-offset:2px}.chart-scroll{width:100%;min-width:0}.monthly-bars{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));align-items:end;gap:14px;width:100%;padding:8px 0 0;border-bottom:1px solid var(--divider-color,#d9e0dd)}.month-column{min-width:0;text-align:center}.month-total{display:block;font-weight:700;font-size:clamp(.6rem,2vw,.85rem);margin-bottom:8px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.month-stack{height:130px;display:flex;flex-direction:column;justify-content:end;gap:0;background:repeating-linear-gradient(to top,transparent 0,transparent calc(25% - 1px),var(--divider-color,#d9e0dd) 25%);border-bottom:1px solid var(--divider-color,#d9e0dd)}.store-segment{width:70%;margin-inline:auto;flex:none;min-height:0}.month-label{display:block;font-size:.8em;padding:8px 0}.chart-legend{display:flex;flex-wrap:wrap;gap:10px 16px;margin-top:14px}.chart-key{display:inline-flex;align-items:center;gap:6px;font-size:.8em}.chart-swatch{width:10px;height:10px;border-radius:3px;flex:none}@media(max-width:550px){.ticket{gap:8px}.ticket .store-image{width:34px;height:34px}.ticket .ticket-open{width:32px;height:36px}.ticket .title{font-size:.85em}.ticket .total{font-size:.9em}.spending-chart{padding:14px}.monthly-bars{gap:6px}.month-label{font-size:.7em}.chart-period{font-size:.7em}}
    </style>
    <input id="ticket-file" type="file" accept="application/pdf,.pdf" hidden>
    <p id="message" class="notice" role="status" hidden></p><section id="spending-chart" class="spending-chart" aria-label="Gasto mensual por tienda" hidden></section><div id="history"></div><p id="empty" class="empty" hidden>Todavía no has subido ningún ticket.</p>
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
    <dialog id="purchase-detail" aria-labelledby="purchase-detail-title"><h2 id="purchase-detail-title">Detalle de la compra</h2><div id="purchase-detail-info" class="receipt-info"></div><div id="purchase-detail-lines"></div></dialog>`;
    installDialogCloseButtons(this.shadowRoot);
    const root=this.shadowRoot,dialog=root.querySelector('dialog');
    root.querySelector('#ticket-file').addEventListener('change',event=>{const file=event.target.files[0];event.target.value='';if(file)void this._upload(file);});
    root.querySelector('#review-form').addEventListener('submit',event=>{event.preventDefault();void this._advance();});
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
  _setBusy(busy){this._busy=busy;this.dispatchEvent(new CustomEvent('receipt-busy',{detail:busy}));this.shadowRoot.querySelectorAll('dialog button,dialog input,dialog select').forEach(el=>{el.disabled=busy||el.dataset.locked==='true';});}
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
    root.querySelector('#review-summary').replaceChildren(node('strong','',receipt.store_name+(receipt.document_type==='invoice'?' · Factura':'')),node('span','',documentDate(receipt)),node('strong','',money(receipt.total)));
    this._step=0;
    this._reviewGroups={};
    root.querySelector('#review-lines').replaceChildren();
    this._edits=receipt.lines.map(line=>{
      const candidate=products.find(p=>p.id===line.product_id&&!used.has(p.id)),product=line.matched===false?null:candidate;if(product)used.add(product.id);
      return {line,id:line.id,product_id:product?.id??'',search:candidate?.name??'',
        replenish:Boolean(product?.stock_id),quantity:product?line.quantity??this._quantity(line,product.unit):null,
        unit:product?.unit??'uds',purchase_id:null,save_price:Boolean(this._pricesEnabled)};
    });
    root.querySelector('#review-error').hidden=true;this._renderStep();
  }
  _quantity(line,unit){
    if(unit==='uds')return line.count;
    const scales={g:['mass',1],kg:['mass',1000],ml:['volume',1],cl:['volume',10],l:['volume',1000]},source=scales[line.pack_unit],target=scales[unit];
    return source&&target&&source[0]===target[0]&&line.pack_quantity?Math.round(line.count*line.pack_quantity*source[1]/target[1]*1000)/1000:null;
  }
  _product(edit){return this._draft.products.find(p=>p.id===edit.product_id);}
  _updateOptions(options){
    for(const edit of this._edits){
      const before=this._product(edit),after=options.products.find(p=>p.id===edit.product_id);
      if(after&&before&&(before.unit!==after.unit||before.stock_id!==after.stock_id)){
        edit.unit=after.unit;edit.quantity=this._quantity(edit.line,after.unit);edit.replenish=Boolean(after.stock_id);edit.purchase_id=null;
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
    if(changed){edit.unit=product?.unit??'uds';edit.quantity=product?this._quantity(edit.line,edit.unit):null;edit.replenish=Boolean(product?.stock_id);edit.purchase_id=null;}
    this._errorMessage('');return true;
  }
  _goToStep(step){
    if(this._busy||!this._draft||!Number.isInteger(step)||step<0||step>=this._step)return;
    this._step=step;this._errorMessage('');this._renderStep();
  }
  _renderStep(){
    if(!this._draft)return;
    const root=this.shadowRoot,step=this._step;
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
    root.querySelector('#step-help').hidden=step===3;
    root.querySelector('#review-summary').hidden=step===3;
    root.querySelector('#previous-step').hidden=step===0;root.querySelector('#links-only').hidden=step!==0;
    root.querySelector('#previous-step').textContent=step===1?'Volver a vinculación':'Anterior';
    root.querySelector('#stock-only').hidden=step!==1;
    root.querySelector('#prices-only').hidden=step!==2||!this._pricesEnabled;
    root.querySelector('#confirm-ticket').textContent=step===3?'Confirmar compra':'Continuar';
    root.querySelector('#confirm-ticket').classList.toggle('continue',step!==3);
    for(const group of root.querySelectorAll('#review-lines .review-group'))this._reviewGroups[group.dataset.group]=group.open;
    const container=root.querySelector('#review-lines');container.replaceChildren();container.hidden=step===3;
    const grouped=step<2?node('details','review-group'):null;
    const groupedContent=step<2?node('div','review-group-content'):null;
    if(grouped){grouped.dataset.group=step===0?'links':'stock';grouped.id=step===0?'linked-products-group':'unregistered-stock-group';grouped.open=Boolean(this._reviewGroups[grouped.dataset.group]);}
    if(step===2&&this._pricesEnabled){
      const allLabel=node('label','check select-all-prices'),all=node('input');all.type='checkbox';
      const linked=this._edits.filter(edit=>this._product(edit));all.checked=linked.length>0&&linked.every(edit=>edit.save_price);all.indeterminate=linked.some(edit=>edit.save_price)&&!all.checked;
      all.addEventListener('change',()=>{for(const edit of linked)edit.save_price=all.checked;this._renderStep();});
      allLabel.append(all,document.createTextNode('Seleccionar todos los precios'));container.append(allLabel);
    }
    for(const edit of step===3?[]:this._edits){
      const product=this._product(edit);if(step>0&&!product)continue;
      const row=node('div','review-line');row.dataset.lineId=edit.id;
      if(step===0)this._associationRow(row,edit);
      if(step===1)this._stockRow(row,edit,product);
      if(step===2){
        row.classList.add('price-line');
        const toggle=node('button','price-select');toggle.type='button';toggle.setAttribute('aria-label','Guardar precio de '+product.name);
        const selected=Boolean(edit.save_price&&this._pricesEnabled);toggle.setAttribute('aria-pressed',String(selected));row.dataset.selected=String(selected);
        toggle.dataset.locked=String(!this._pricesEnabled);toggle.disabled=!this._pricesEnabled;
        toggle.addEventListener('click',()=>{
          if(this._busy||!this._pricesEnabled)return;
          edit.save_price=!edit.save_price;this._renderStep();
          [...root.querySelectorAll('.review-line')].find(line=>line.dataset.lineId===String(edit.id))?.querySelector('.price-select')?.focus();
        });
        const name=node('div','price-product-name'),label=node('div','price-label'),price=node('div','price-value',money(edit.line.unit_price));
        if(product.price!=null)price.append(node('del','', '('+money(product.price)+')'));
        label.append(node('strong','',product.name),price);name.append(this._productImage(product),label);row.append(toggle,name);
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
      ['Precios',this._edits.filter(e=>e.product_id&&e.save_price&&this._pricesEnabled).length]
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
    quantity.addEventListener('input',()=>{edit.quantity=quantity.value===''?null:Number(quantity.value);});
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
      const product=await this.createProduct(edit.search||edit.line.description);if(!product||!this._draft)return;
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
      else{this._step=1;this._renderStep();}
    }catch(error){this._errorMessage(error.message??'No se han podido guardar las vinculaciones.');}
    finally{this._setBusy(false);}
  }
  async _advance(){
    if(this._busy||!this._draft)return;this._errorMessage('');
    if(this._step===0){await this._saveLinks();return;}
    if(this._step===1){if(this._validateStock()){this._step=2;this._renderStep();}return;}
    if(this._step===2){this._step=3;this._renderStep();return;}
    await this._confirm();
  }
  async _confirm(updatePrices=Boolean(this._pricesEnabled)){
    if(this._busy||!this._draft||!this._validateLinks()||!this._validateStock())return;
    this._setBusy(true);
    try{
      await this._hass.callWS({type:'improved_shopping_list/receipts/confirm',token:this._draft.token,update_prices:Boolean(updatePrices&&this._pricesEnabled),
        lines:this._edits.map(edit=>({id:edit.id,product_id:edit.product_id,replenish:Boolean(edit.product_id&&edit.replenish),quantity:edit.replenish?edit.quantity:null,unit:edit.unit,purchase_id:edit.purchase_id??'',save_price:Boolean(edit.product_id&&edit.save_price&&updatePrices&&this._pricesEnabled)}))});
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
    root.querySelector('#spending-chart').hidden=!this._history||!this._session.receipts.length;
    if(!this._history)return;
    const period=this._renderSpendingChart();
    const receipts=this._session.receipts.filter(receipt=>{
      const date=new Date(receipt.purchased_at),month=date.getFullYear()*12+date.getMonth();
      return period&&month>=period.start&&month<=period.end;
    });
    const empty=root.querySelector('#empty');
    empty.textContent=this._session.receipts.length?'No hay compras registradas en este periodo.':'Todavía no has subido ningún ticket.';
    empty.hidden=receipts.length>0||this._session.loading||Boolean(this._session.error);
    root.querySelector('#history').replaceChildren(...receipts.map(receipt=>{
      const card=node('article','ticket');card.dataset.id=receipt.id;
      const title=node('div','title');title.append(node('strong','',receipt.store_name+(receipt.document_type==='invoice'?' · Factura':'')),node('span','muted',documentDate(receipt)+(receipt.article_count==null?'':' · '+receipt.article_count+' artículos')));
      const open=this._button('Ver ticket de '+receipt.store_name+' del '+documentDate(receipt),'mdi:receipt-text',()=>receipt.summary_only?void this._reviewPending(receipt):this._openPurchaseDetail(receipt),'ticket-open'+(!receipt.summary_only?' reviewed':''));
      card.append(this._storeImage(receipt.store,receipt.store_name),title,node('span','total',money(receipt.total)));if(!receipt.summary_only||receipt.pending_review||(receipt.store==='carrefour'&&receipt.account_key&&receipt.ticket_available!==false))card.append(open);return card;
    }));
  }
  async _reviewPending(receipt){
    if(this._busy)return;
    this._setBusy(true);this._error='';
    try{const draft=await this._hass.callWS({type:receipt.pending_review?'improved_shopping_list/receipts/review_saved':'improved_shopping_list/carrefour_account/preview_saved',receipt_id:receipt.id});this._draft=draft;this._buildReview();this.shadowRoot.querySelector('dialog').showModal();}
    catch(error){this._error=error.message??'No se ha podido abrir el ticket.';this._render();}
    finally{this._setBusy(false);}
  }
  _storeImage(store,name){
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
    container.append(this._totalRow('Total',receipt.total));root.querySelector('#purchase-detail').showModal();
  }
  _renderSpendingChart(){
    const chart=this.shadowRoot.querySelector('#spending-chart'),months=new Map(),stores=new Map();
    for(const receipt of this._session.receipts){
      const when=new Date(receipt.purchased_at),cents=Math.round(Number(receipt.total)*100);
      if(!Number.isFinite(when.getTime())||!Number.isFinite(cents)||cents<0)continue;
      const key=when.getFullYear()+'-'+String(when.getMonth()+1).padStart(2,'0');
      if(!months.has(key))months.set(key,{date:new Date(when.getFullYear(),when.getMonth(),1),total:0,stores:new Map()});
      const month=months.get(key);month.total+=cents;month.stores.set(receipt.store,(month.stores.get(receipt.store)||0)+cents);
      stores.set(receipt.store,receipt.store_name);
    }
    chart.hidden=!this._history||months.size===0;chart.replaceChildren();if(chart.hidden)return;
    const now=new Date(),latest=now.getFullYear()*12+now.getMonth();
    const earliest=Math.min(...[...months.values()].map(month=>month.date.getFullYear()*12+month.date.getMonth()));
    const maximumOffset=Math.ceil(Math.max(0,latest-5-earliest)/6)*6;
    this._spendingOffset=Math.min(this._spendingOffset||0,maximumOffset);
    const end=latest-this._spendingOffset,start=end-5,visible=[];
    for(let index=start;index<=end;index++){
      const date=new Date(Math.floor(index/12),index%12,1),key=date.getFullYear()+'-'+String(date.getMonth()+1).padStart(2,'0');
      visible.push([key,months.get(key)||{date,total:0,stores:new Map()}]);
    }
    const sortedStores=[...stores].sort((a,b)=>a[1].localeCompare(b[1],'es'));
    const palette=['#607d8b','#9e8048','#6978c8'];
    const colors=new Map(sortedStores.map(([store],index)=>[store,STORE_COLORS[store]||palette[index%palette.length]]));
    const heading=node('div','chart-heading'),navigation=node('div','chart-navigation');
    const previous=this._button('Mostrar seis meses anteriores','mdi:chevron-left',()=>{this._spendingOffset+=6;this._render();});
    const next=this._button('Mostrar seis meses siguientes','mdi:chevron-right',()=>{this._spendingOffset=Math.max(0,this._spendingOffset-6);this._render();});
    previous.disabled=this._spendingOffset>=maximumOffset;next.disabled=this._spendingOffset===0;
    const format=new Intl.DateTimeFormat('es-ES',{month:'short',year:'numeric'});
    const period=node('span','chart-period',format.format(visible[0][1].date)+' – '+format.format(visible[5][1].date));period.setAttribute('aria-live','polite');
    navigation.append(previous,period,next);heading.append(node('h3','','Gasto mensual'),navigation);
    const bars=node('div','monthly-bars'),scroll=node('div','chart-scroll');
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
    return {start,end};
  }
  _totalRow(label,value){const row=node('div','totals');row.append(node('span','',label),node('strong','',money(value)));return row;}
}
if(!customElements.get('isl-purchases'))customElements.define('isl-purchases',ImprovedShoppingPurchases);
