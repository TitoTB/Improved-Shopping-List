import { ListSettingsSession } from "./list-settings-client.js?v=0.26.0";
import { installDialogCloseButtons } from "./dialog-controls.js?v=0.26.0";
import { productNameKey } from "./product-names.js?v=0.26.0";

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
    if(!value.active){this._session.stop();this._started=false;this.shadowRoot.querySelectorAll('dialog').forEach(dialog=>dialog.close());}
    this._render();
  }
  disconnectedCallback(){this._session.stop();this._started=false;this.shadowRoot.querySelectorAll('dialog').forEach(dialog=>dialog.close());}
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
      #review-steps{list-style:none;display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:6px;padding:0;margin:16px 0}#review-steps li{padding:10px 6px;text-align:center;border-radius:8px;font-size:.85em;background:var(--secondary-background-color,#edf2ef)}#review-steps [aria-current=step]{background:#267052;color:white;font-weight:700}
      #step-title{margin:18px 0 8px;font-size:1.05em}.association{display:flex;gap:8px;align-items:end}.association label{flex:1}.small-button{display:grid;place-items:center;flex:none;width:42px;height:42px;padding:0;border:0;border-radius:8px;background:var(--primary-color,#267052);color:white}.small-button.clear{background:transparent;color:inherit;border:1px solid var(--divider-color,#d9e0dd)}
      .actions{gap:8px;flex-wrap:wrap}.actions .secondary{background:transparent;color:inherit;border:1px solid var(--divider-color,#d9e0dd)}.previous-price{font-size:.85em;opacity:.7;margin:8px 0}.review-line .check{margin:10px 0}.stock-fields{display:grid;grid-template-columns:minmax(0,2fr) minmax(80px,1fr);gap:10px}.review-summary{line-height:1.6;padding:12px;border-radius:8px;background:var(--secondary-background-color,#edf2ef)}
      .original{display:flex;justify-content:space-between;gap:12px;margin-bottom:10px}.fields{display:grid;grid-template-columns:minmax(0,2fr) minmax(100px,1fr);gap:10px}
      label{display:flex;flex-direction:column;gap:5px;font-size:.9em;min-width:0}.quantity{display:flex;align-items:center;gap:8px}.quantity span{white-space:nowrap}
      .check{flex-direction:row;align-items:center;margin-top:10px}.check input{width:18px;min-height:18px;flex:none}.purchase{margin-top:10px}
      .actions{display:flex;justify-content:flex-end;margin-top:16px}.actions button{border:0;background:#267052;color:white;border-radius:10px;padding:12px 20px}
      ha-icon{--mdc-icon-size:22px;width:22px;height:22px;flex:none}#review-summary{margin:12px 0}.note{font-size:.85em;opacity:.7;margin:10px 0}
      .association-row{display:flex;align-items:center;gap:10px;min-width:0}.association-name{flex:1;min-width:0;overflow-wrap:anywhere}.association-name strong{font-size:.95em}.linked-name{font-size:.8em;opacity:.65;margin-left:8px}.association-buttons{display:flex;gap:6px;flex:none;margin-left:auto}
      .small-button.link{background:#2196f3;color:white}.small-button.create{background:var(--isl-green,#267052);color:white}.small-button.ignore{background:transparent;color:inherit;border:0}.small-button.ignore[aria-pressed=true]{background:#d32f2f;color:white}
      #association-dialog{width:min(500px,calc(100vw - 24px))}#association-form label{margin-top:16px}#association-error{margin:12px 0 0}
      @media(max-width:400px){.association-buttons{gap:4px}.association-buttons .small-button{width:34px;height:38px}.association-row{gap:8px}.linked-name{display:block;margin-left:0}}
      @media(max-width:550px){dialog{padding:18px}.fields{grid-template-columns:minmax(0,1fr)}summary{gap:8px}.original{font-size:.9em}.ticket{padding:12px}}
    </style>
    <input id="ticket-file" type="file" accept="application/pdf,.pdf" hidden>
    <p id="message" class="notice" role="status" hidden></p><div id="history"></div><p id="empty" class="empty" hidden>Todavía no has subido ningún ticket.</p>
    <dialog aria-labelledby="review-title"><form id="review-form"><h2 id="review-title">Revisar ticket</h2><div id="review-summary" class="receipt-info"></div>
      <ol id="review-steps"><li>1. Vinculación</li><li>2. Stock</li><li>3. Precios</li></ol><h3 id="step-title"></h3><p id="step-help" class="note"></p>
      <div id="review-lines"></div><div id="review-result" class="review-summary" hidden></div>
      <p id="review-error" class="notice error" role="alert" hidden></p><div class="actions"><button id="links-only" class="secondary" type="button">Guardar solo vinculaciones</button><button id="previous-step" class="secondary" type="button">Anterior</button><button id="confirm-ticket" type="submit">Continuar</button></div>
    </form></dialog>
    <dialog id="association-dialog" aria-labelledby="association-title"><form id="association-form">
      <h2 id="association-title">Vincular producto</h2>
      <label for="association-search">Producto del catálogo</label><input id="association-search" type="text" list="association-products" maxlength="255" autocomplete="off" required><datalist id="association-products"></datalist>
      <p id="association-error" class="notice error" role="alert" hidden></p>
      <div class="actions"><button id="confirm-association" type="submit">Vincular</button></div>
    </form></dialog>`;
    installDialogCloseButtons(this.shadowRoot);
    const root=this.shadowRoot,dialog=root.querySelector('dialog');
    root.querySelector('#ticket-file').addEventListener('change',event=>{const file=event.target.files[0];event.target.value='';if(file)void this._upload(file);});
    root.querySelector('#review-form').addEventListener('submit',event=>{event.preventDefault();void this._advance();});
    root.querySelector('#previous-step').addEventListener('click',()=>{if(!this._busy){this._step--;root.querySelector('#review-error').hidden=true;this._renderStep();}});
    root.querySelector('#links-only').addEventListener('click',()=>void this._saveLinks(true));
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
    this._error='';this._notice='';
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
    root.querySelector('#review-summary').replaceChildren(node('strong','',receipt.store_name),node('span','',date(receipt.purchased_at)),node('strong','',money(receipt.total)));
    this._step=0;this._notice='';
    this._edits=receipt.lines.map(line=>{
      const product=products.find(p=>p.id===line.product_id&&!used.has(p.id));if(product)used.add(product.id);
      return {line,id:line.id,product_id:product?.id??'',search:product?.name??'',ignore:false,
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
  _renderStep(){
    if(!this._draft)return;
    const root=this.shadowRoot,step=this._step;
    root.querySelectorAll('#review-steps li').forEach((li,index)=>{if(index===step)li.setAttribute('aria-current','step');else li.removeAttribute('aria-current');});
    root.querySelector('#step-title').textContent=['Vincular productos','Reponer stock','Actualizar precios'][step];
    root.querySelector('#step-help').textContent=[
      '',
      'Los productos que ya están en Stock vienen marcados. Puedes incluir los demás y confirmar la cantidad. Si ya registraste la compra, selecciona la reposición anterior para corregirla.',
      this._pricesEnabled?'Selecciona los precios que quieres guardar para esta tienda. Se conserva la fecha de compra y los descuentos generales no se reparten entre productos.':'Los precios están desactivados en Ajustes. Puedes confirmar las vinculaciones y la reposición sin guardar precios.'
    ][step];
    root.querySelector('#step-help').hidden=step===0;
    root.querySelector('#previous-step').hidden=step===0;root.querySelector('#links-only').hidden=step!==0;
    root.querySelector('#confirm-ticket').textContent=step===2?'Confirmar compra':'Continuar';
    const container=root.querySelector('#review-lines');container.replaceChildren();
    if(step===2&&this._pricesEnabled){
      const allLabel=node('label','check'),all=node('input');all.type='checkbox';
      const linked=this._edits.filter(edit=>edit.product_id);all.checked=linked.length>0&&linked.every(edit=>edit.save_price);all.indeterminate=linked.some(edit=>edit.save_price)&&!all.checked;
      all.addEventListener('change',()=>{for(const edit of linked)edit.save_price=all.checked;this._renderStep();});
      allLabel.append(all,document.createTextNode('Seleccionar todos los precios'));container.append(allLabel);
    }
    for(const edit of this._edits){
      const product=this._product(edit);if(step>0&&!product)continue;
      const row=node('div','review-line');row.dataset.lineId=edit.id;
      if(step>0){const original=node('div','original');original.append(node('strong','',edit.line.description),node('span','',`${edit.line.count} × ${money(edit.line.unit_price)} = ${money(edit.line.amount)}`));row.append(original);}
      if(step===0)this._associationRow(row,edit);
      if(step===1)this._stockRow(row,edit,product);
      if(step===2){
        const label=node('label','check'),check=node('input');check.type='checkbox';check.checked=edit.save_price&&Boolean(this._pricesEnabled);check.dataset.locked=String(!this._pricesEnabled);check.disabled=!this._pricesEnabled;
        check.addEventListener('change',()=>{edit.save_price=check.checked;this._renderStep();});
        label.append(check,document.createTextNode('Actualizar precio de '+product.name));row.append(label);
        row.append(node('p','previous-price',product.price!=null?`Precio guardado: ${money(product.price)}${product.price_date?' · '+date(product.price_date*1000):''}`:'Sin precio guardado para esta tienda.'));
        row.append(node('strong','',`Precio del ticket: ${money(edit.line.unit_price)} por unidad/envase`));
      }
      container.append(row);
    }
    if(step>0&&!this._edits.some(edit=>edit.product_id))container.append(node('p','note','No hay productos vinculados en este ticket.'));

    const result=root.querySelector('#review-result');result.hidden=step!==2;
    result.replaceChildren(node('strong','','Resumen de la compra'),node('div','',`${this._edits.filter(e=>e.product_id).length} vinculaciones guardadas · ${this._edits.filter(e=>e.product_id&&e.replenish).length} productos para reponer · ${this._edits.filter(e=>e.product_id&&e.save_price&&this._pricesEnabled).length} precios seleccionados`));
    root.querySelectorAll('dialog button,dialog input,dialog select').forEach(el=>{el.disabled=this._busy||el.dataset.locked==='true';});
  }
  _associationRow(row,edit){
    row.classList.add('association-row');
    const name=node('div','association-name');name.append(node('strong','',edit.line.description));
    const product=this._product(edit);
    if(product)name.append(node('span','linked-name','→ '+product.name));
    const buttons=node('div','association-buttons');
    const link=this._button('Vincular producto para '+edit.line.description,'mdi:link-variant',()=>this._openAssociation(edit),'small-button link');
    link.dataset.locked=String(edit.ignore);link.disabled=edit.ignore;link.setAttribute('aria-pressed',String(Boolean(product)));
    const create=this._button('Crear producto para '+edit.line.description,'mdi:plus-thick',()=>void this._createProduct(edit),'small-button create');
    create.dataset.locked=String(edit.ignore);create.disabled=edit.ignore;
    const ignore=this._button('Ignorar '+edit.line.description,'mdi:close',()=>{
      edit.ignore=!edit.ignore;
      if(edit.ignore){edit.ignoredProduct=edit.product_id;edit.product_id='';edit.search='';edit.replenish=false;edit.purchase_id=null;}
      else if(edit.ignoredProduct){
        const previous=this._draft.products.find(p=>p.id===edit.ignoredProduct);
        if(previous&&!this._edits.some(other=>other!==edit&&other.product_id===previous.id)&&this._chooseProduct(edit,previous))edit.search=previous.name;
      }
      this._errorMessage('');this._renderStep();
      [...this.shadowRoot.querySelectorAll('.review-line')].find(line=>line.dataset.lineId===String(edit.id))?.querySelector('.ignore')?.focus();
    },'small-button ignore');
    ignore.setAttribute('aria-pressed',String(edit.ignore));
    buttons.append(link,create,ignore);row.append(name,buttons);
  }
  _openAssociation(edit){
    if(this._busy||edit.ignore)return;
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
    if(this._chooseProduct(edit,product)){edit.search=product.name;edit.ignore=false;root.querySelector('#association-dialog').close();this._renderStep();}
  }
  _stockRow(row,edit,product){
    row.append(node('strong','',product.name));
    const label=node('label','check'),check=node('input');check.type='checkbox';check.checked=edit.replenish;
    check.addEventListener('change',()=>{edit.replenish=check.checked;this._renderStep();});label.append(check,document.createTextNode(product.stock_id?'Reponer stock':'Incluir en Stock'));row.append(label);
    const fields=node('div','stock-fields'),quantityLabel=node('label','','Cantidad que se repone'),quantity=node('input');
    quantity.type='number';quantity.min='0.001';quantity.max='1000000';quantity.step='0.001';quantity.value=edit.quantity??'';quantity.setAttribute('aria-label','Cantidad para '+edit.line.description);
    quantity.dataset.locked=String(!edit.replenish);quantity.disabled=!edit.replenish;quantity.addEventListener('input',()=>{edit.quantity=quantity.value===''?null:Number(quantity.value);});quantityLabel.append(quantity);fields.append(quantityLabel);
    const unitLabel=node('label','','Unidades');
    if(product.stock_id)unitLabel.append(node('span','',product.unit));
    else{const unit=node('input');unit.type='text';unit.value=edit.unit;unit.maxLength=32;unit.setAttribute('aria-label','Unidades para '+edit.line.description);unit.dataset.locked=String(!edit.replenish);unit.disabled=!edit.replenish;
      unit.addEventListener('change',()=>{edit.unit=unit.value.trim();edit.quantity=this._quantity(edit.line,edit.unit);this._renderStep();});unitLabel.append(unit);}
    fields.append(unitLabel);row.append(fields);
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
      if(this._chooseProduct(edit,this._draft.products.find(p=>p.id===product.id))){edit.search=product.name;edit.ignore=false;}
      this._renderStep();
    }catch(error){this._errorMessage(error.message??'No se ha podido crear el producto.');}
    finally{this._setBusy(false);}
  }
  _validateLinks(){
    const seen=new Set();
    for(const edit of this._edits){
      if(!edit.product_id&&!edit.ignore){this._errorMessage('Vincula, crea un producto o marca Ignorar en cada línea del ticket.');return false;}
      if(edit.product_id&&seen.has(edit.product_id)){this._errorMessage('Dos líneas del mismo ticket no pueden vincularse al mismo producto.');return false;}
      if(edit.product_id)seen.add(edit.product_id);
    }
    return true;
  }
  _validateStock(){
    for(const edit of this._edits.filter(e=>e.product_id&&e.replenish)){
      if(!Number.isFinite(edit.quantity)||edit.quantity<=0||edit.quantity>1000000||Math.abs(edit.quantity*1000-Math.round(edit.quantity*1000))>.00001||!edit.unit.trim()){
        this._errorMessage('Indica cantidades válidas, con hasta tres decimales, y sus unidades para todos los productos que se reponen.');return false;
      }
      const product=this._product(edit),previous=this._draft.purchases.filter(p=>p.item_id===product.stock_id&&p.unit===product.unit);
      if(previous.length&&(edit.purchase_id===null||edit.purchase_id==='__choose__')){this._errorMessage('Indica si cada reposición es una compra nueva o corrige una compra ya registrada.');return false;}
    }
    return true;
  }
  async _saveLinks(only=false){
    if(this._busy||!this._draft||!this._validateLinks())return;this._setBusy(true);this._errorMessage('');
    try{
      const options=await this._hass.callWS({type:'improved_shopping_list/receipts/link',token:this._draft.token,lines:this._edits.map(e=>({id:e.id,product_id:e.product_id}))});
      this._updateOptions(options);
      if(only){this._notice='Vinculaciones guardadas. No se han modificado el stock ni los precios.';this.shadowRoot.querySelector('dialog').close();this._render();}
      else{this._step=1;this._renderStep();}
    }catch(error){this._errorMessage(error.message??'No se han podido guardar las vinculaciones.');}
    finally{this._setBusy(false);}
  }
  async _advance(){
    if(this._busy||!this._draft)return;this._errorMessage('');
    if(this._step===0){await this._saveLinks();return;}
    if(this._step===1){if(this._validateStock()){this._step=2;this._renderStep();}return;}
    await this._confirm();
  }
  async _confirm(){
    if(this._busy||!this._draft||!this._validateLinks()||!this._validateStock())return;
    this._setBusy(true);
    try{
      await this._hass.callWS({type:'improved_shopping_list/receipts/confirm',token:this._draft.token,update_prices:Boolean(this._pricesEnabled),
        lines:this._edits.map(edit=>({id:edit.id,product_id:edit.product_id,replenish:Boolean(edit.product_id&&edit.replenish),quantity:edit.replenish?edit.quantity:null,unit:edit.unit,purchase_id:edit.purchase_id??'',save_price:Boolean(edit.product_id&&edit.save_price&&this._pricesEnabled)}))});
      this._draft=null;this.shadowRoot.querySelector('dialog').close();await this._session.refresh();this.dispatchEvent(new CustomEvent('receipt-imported'));
    }catch(error){this._errorMessage(error.message??'No se ha podido guardar el ticket.');}
    finally{this._setBusy(false);}
  }
  _render(){
    if(!this._built)return;
    const root=this.shadowRoot,message=root.querySelector('#message');
    const text=this._reading?'Leyendo ticket…':this._error||this._notice|| (this._history?this._session.error:'') || (this._history&&this._session.loading?'Cargando últimas compras…':'');
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
