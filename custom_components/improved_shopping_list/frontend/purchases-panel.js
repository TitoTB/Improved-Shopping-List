import { ListSettingsSession } from "./list-settings-client.js?v=0.25.0";
import { installDialogCloseButtons } from "./dialog-controls.js?v=0.25.0";
import { productNameKey } from "./product-names.js?v=0.25.0";

const node=(tag,cls,text)=>{const el=document.createElement(tag);if(cls)el.className=cls;if(text!==undefined)el.textContent=text;return el;};
const money=value=>new Intl.NumberFormat('es-ES',{style:'currency',currency:'EUR'}).format(value);
const date=value=>new Intl.DateTimeFormat('es-ES',{dateStyle:'short',timeStyle:'short'}).format(new Date(value));
const icon=name=>{const el=node('ha-icon');el.setAttribute('icon',name);el.setAttribute('aria-hidden','true');return el;};

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
    if(!value.active){this._session.stop();this._started=false;this.shadowRoot.querySelector('dialog').close();}
    this._render();
  }
  disconnectedCallback(){this._session.stop();this._started=false;this.shadowRoot.querySelector('dialog')?.close();}
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
      #review-lines{display:grid;gap:12px}.review-line{padding:12px;background:var(--secondary-background-color,#f2f4f3);border-radius:10px}
      .original{display:flex;justify-content:space-between;gap:12px;margin-bottom:10px}.fields{display:grid;grid-template-columns:minmax(0,2fr) minmax(100px,1fr);gap:10px}
      label{display:flex;flex-direction:column;gap:5px;font-size:.9em;min-width:0}.quantity{display:flex;align-items:center;gap:8px}.quantity span{white-space:nowrap}
      .check{flex-direction:row;align-items:center;margin-top:10px}.check input{width:18px;min-height:18px;flex:none}.purchase{margin-top:10px}
      .actions{display:flex;justify-content:flex-end;margin-top:16px}.actions button{border:0;background:#267052;color:white;border-radius:10px;padding:12px 20px}
      ha-icon{--mdc-icon-size:22px;width:22px;height:22px;flex:none}#review-summary{margin:12px 0}.note{font-size:.85em;opacity:.7;margin:10px 0}
      @media(max-width:550px){dialog{padding:18px}.fields{grid-template-columns:minmax(0,1fr)}summary{gap:8px}.original{font-size:.9em}.ticket{padding:12px}}
    </style>
    <input id="ticket-file" type="file" accept="application/pdf,.pdf" hidden>
    <p id="message" class="notice" role="status" hidden></p><div id="history"></div><p id="empty" class="empty" hidden>Todavía no has subido ningún ticket.</p>
    <dialog aria-labelledby="review-title"><form id="review-form"><h2 id="review-title">Revisar ticket</h2><div id="review-summary" class="receipt-info"></div>
      <p class="note">Confirma las correspondencias y las cantidades antes de reponer el stock. Si ya registraste la compra, selecciona esa reposición para corregirla.</p>
      <div id="review-lines"></div><datalist id="receipt-products"></datalist>
      <label class="check" id="save-prices-label"><input id="save-prices" type="checkbox">Actualizar el último precio conocido con los precios del ticket</label>
      <p class="note">Los descuentos generales se conservan en el ticket y no se reparten entre productos.</p>
      <p id="review-error" class="notice error" role="alert" hidden></p><div class="actions"><button id="confirm-ticket" type="submit">Confirmar compra</button></div>
    </form></dialog>`;
    installDialogCloseButtons(this.shadowRoot);
    const root=this.shadowRoot,dialog=root.querySelector('dialog');
    root.querySelector('#ticket-file').addEventListener('change',event=>{const file=event.target.files[0];event.target.value='';if(file)void this._upload(file);});
    root.querySelector('#review-form').addEventListener('submit',event=>{event.preventDefault();void this._confirm();});
    dialog.addEventListener('cancel',event=>{if(this._busy)event.preventDefault();});
    dialog.addEventListener('close',()=>{
      if(this._draft){const token=this._draft.token;this._draft=null;void this._hass.callWS({type:'improved_shopping_list/receipts/discard',token}).catch(()=>{});}
    });
  }
  _setBusy(busy){this._busy=busy;this.dispatchEvent(new CustomEvent('receipt-busy',{detail:busy}));this.shadowRoot.querySelector('#confirm-ticket').disabled=busy;}
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
    const root=this.shadowRoot,{receipt,products,purchases}=this._draft;
    root.querySelector('#review-summary').replaceChildren(node('strong','',receipt.store_name),node('span','',date(receipt.purchased_at)),node('strong','',money(receipt.total)));
    root.querySelector('#receipt-products').replaceChildren(...products.map(product=>new Option(product.name,product.name)));
    this._edits=[];
    root.querySelector('#review-lines').replaceChildren(...receipt.lines.map(line=>{
      const row=node('div','review-line'),original=node('div','original');original.append(node('strong','',line.description),node('span','',`${line.count} × ${money(line.unit_price)} = ${money(line.amount)}`));
      const fields=node('div','fields'),label=node('label','','Producto del catálogo'),search=node('input');search.type='text';search.maxLength=255;search.setAttribute('list','receipt-products');search.autocomplete='off';search.setAttribute('aria-label','Producto para '+line.description);
      const product=products.find(p=>p.id===line.product_id);search.value=product?.name??'';label.append(search);
      const quantityLabel=node('label','','Cantidad que se repone'),quantityWrap=node('div','quantity'),quantity=node('input'),unit=node('span');quantity.type='number';quantity.min='0.001';quantity.max='1000000';quantity.step='0.001';quantity.setAttribute('aria-label','Cantidad para '+line.description);quantity.value=line.quantity??'';unit.textContent=product?.unit??'uds';quantityWrap.append(quantity,unit);quantityLabel.append(quantityWrap);fields.append(label,quantityLabel);
      const checkLabel=node('label','check'),check=node('input');check.type='checkbox';check.checked=Boolean(line.replenish);checkLabel.append(check,document.createTextNode('Reponer stock'));
      const purchaseLabel=node('label','purchase'),purchase=node('select');purchase.setAttribute('aria-label','Reposición de '+line.description);purchaseLabel.append(document.createTextNode('Relacionar con una compra ya registrada'),purchase);
      const edit={id:line.id,product_id:line.product_id,search,quantity,unit,check,purchase,row,purchaseLabel};
      const fillPurchase=()=>{
        const selected=products.find(p=>p.id===edit.product_id),existing=purchase.value;
        const previous=purchases.filter(p=>p.item_id===selected?.stock_id&&p.unit===selected.unit);
        purchase.replaceChildren(...(previous.length?[new Option('Selecciona compra nueva o reposición anterior','__choose__')]:[]),new Option('Registrar una compra nueva',''),...previous.map(p=>new Option(`${date(p.at*1000)} · ${p.quantity} ${p.unit}`,p.id)));
        if([...purchase.options].some(option=>option.value===existing))purchase.value=existing;
        if(previous.length&&existing==='')purchase.value='__choose__';
        const hasStock=Boolean(selected?.stock_id);check.disabled=!hasStock;quantity.disabled=!hasStock;purchaseLabel.hidden=!hasStock||purchase.options.length===1;
        if(!hasStock)check.checked=false;
      };
      search.addEventListener('input',()=>{
        const selected=products.find(p=>productNameKey(p.name)===productNameKey(search.value));edit.product_id=selected?.id??'';unit.textContent=selected?.unit??'uds';
        const scales={g:['mass',1],kg:['mass',1000],ml:['volume',1],cl:['volume',10],l:['volume',1000]},source=scales[line.pack_unit],target=scales[selected?.unit];
        quantity.value=selected?.unit==='uds'?line.count:source&&target&&source[0]===target[0]?Math.round(line.count*line.pack_quantity*source[1]/target[1]*1000)/1000:'';
        check.checked=false;fillPurchase();
      });
      fillPurchase();this._edits.push(edit);row.append(original,fields,checkLabel,purchaseLabel);return row;
    }));
    root.querySelector('#save-prices-label').hidden=!this._pricesEnabled;
    root.querySelector('#save-prices').checked=Boolean(this._pricesEnabled);
    root.querySelector('#review-error').hidden=true;
  }
  async _confirm(){
    if(this._busy||!this._draft)return;
    const root=this.shadowRoot,error=root.querySelector('#review-error');error.hidden=true;
    if(this._edits.some(edit=>edit.check.checked&&edit.purchase.value==='__choose__')){error.textContent='Indica si cada reposición es una compra nueva o corrige una compra ya registrada.';error.hidden=false;return;}
    if(this._edits.some(edit=>edit.check.checked&&(!edit.quantity.value||!edit.quantity.checkValidity()))){error.textContent='Indica una cantidad válida para cada producto que quieras reponer.';error.hidden=false;return;}
    this._setBusy(true);
    try{
      await this._hass.callWS({type:'improved_shopping_list/receipts/confirm',token:this._draft.token,update_prices:this._pricesEnabled&&root.querySelector('#save-prices').checked,
        lines:this._edits.map(edit=>({id:edit.id,product_id:edit.product_id,replenish:edit.check.checked,quantity:edit.check.checked?Number(edit.quantity.value):null,purchase_id:edit.purchase.value}))});
      this._draft=null;root.querySelector('dialog').close();await this._session.refresh();
      this.dispatchEvent(new CustomEvent('receipt-imported'));
    }catch(err){error.textContent=err.message??'No se ha podido guardar el ticket.';error.hidden=false;}
    finally{this._setBusy(false);}
  }
  _render(){
    if(!this._built)return;
    const root=this.shadowRoot,message=root.querySelector('#message');
    const text=this._reading?'Leyendo ticket…':this._error|| (this._history?this._session.error:'') || (this._history&&this._session.loading?'Cargando últimas compras…':'');
    message.textContent=text;message.hidden=!text;message.classList.toggle('error',Boolean(this._error||this._session.error));
    root.querySelector('#history').hidden=!this._history;root.querySelector('#empty').hidden=!this._history||this._session.receipts.length>0||this._session.loading||Boolean(this._session.error);
    if(!this._history)return;
    const expanded=new Set([...root.querySelectorAll('details[open]')].map(el=>el.dataset.id));
    root.querySelector('#history').replaceChildren(...this._session.receipts.map(receipt=>{
      const details=node('details','ticket');details.dataset.id=receipt.id;details.open=expanded.has(receipt.id);
      const summary=node('summary'),title=node('span','title');title.append(node('strong','',receipt.store_name),node('span','muted',date(receipt.purchased_at)+' · '+receipt.article_count+' artículos'));
      summary.append(icon('mdi:receipt-text'),title,node('span','total',money(receipt.total)));details.append(summary);
      for(const line of receipt.lines){const row=node('div','line'),description=node('div');description.append(node('p','',line.description),node('p','muted',`${line.count} × ${money(line.unit_price)}`));
        if(line.replenished)description.append(node('p','muted',`${line.product_name}: ${line.quantity} ${line.unit} repuestos`));
        row.append(description,node('span','',money(line.amount)));details.append(row);}
      if(receipt.discount)details.append(this._totalRow('Descuentos generales',-receipt.discount));
      details.append(this._totalRow('Total',receipt.total));return details;
    }));
  }
  _totalRow(label,value){const row=node('div','totals');row.append(node('span','',label),node('strong','',money(value)));return row;}
}
if(!customElements.get('isl-purchases'))customElements.define('isl-purchases',ImprovedShoppingPurchases);
