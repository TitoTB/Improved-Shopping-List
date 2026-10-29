/** Pantry UI, forms and calculations loaded only when Stock is opened. */
import { imageSource, normalizedName, productNameKey } from './product-display.js?v=0.52.0';
import { installDialogCloseButtons } from './dialog-controls.js?v=0.52.0';
const stockQuantity = (item, now=Date.now()/1000) => {
  if(item.mode!=='perishable')return item.quantity;
  if(item.quantity<=0||item.expired)return 0;
  if(!item.expires_at)return item.quantity;
  const start=item.quantity_at||item.expires_at-(item.days??7)*86400;
  if(item.expires_at<=now||item.expires_at<=start)return 0;
  return Math.round(item.quantity*Math.max(0,Math.min(1,(item.expires_at-now)/(item.expires_at-start)))*1000)/1000;
};
const stockRemaining = (item, now=Date.now()/1000) => Math.max(0,Math.min(100,stockQuantity(item,now)/(item.refill_quantity??1)*100));


class StockView {
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
      quantity.append(node("strong","stock-amount",new Intl.NumberFormat('es-ES',{maximumFractionDigits:0}).format(stockQuantity(item,now))+' '+(item.unit??'uds')),document.createTextNode(' '));
      quantity.setAttribute('aria-label',`Stock de ${item.name}: ${Math.round(stockQuantity(item,now))} ${item.unit??'uds'}`);
      const life=node('span','stock-life',`(${Math.round(percent)}%)`);
      if(progress){
        life.setAttribute('role','progressbar');life.setAttribute('aria-label','Stock restante');
        life.setAttribute('aria-valuemin','0');life.setAttribute('aria-valuemax','100');life.setAttribute('aria-valuenow',String(Math.round(percent)));
      }
      quantity.append(life);
      open.append(media,text,quantity);card.append(open);
      if(this._stockLayout==='rows'){
        const controls=node('div','stock-controls');
        controls.append(button('decrease','mdi:minus',`Quitar una unidad de ${item.name}`,locked||stockQuantity(item,now)===0,()=>void this._runAction(()=>this._stock.adjust(item,-1),'Stock actualizado.')),
          button('increase','mdi:plus',`Añadir una unidad de ${item.name}`,locked||stockQuantity(item,now)>=1000000,()=>void this._runAction(()=>this._stock.adjust(item,1),'Stock actualizado.')));
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
    this._stockEditing={...item,quantity:stockQuantity(item)};
    const defaults={unit:'uds',mode:'manual',days:7,refill_quantity:1,reorder_enabled:false,reorder_at:0,usage_entity:'',usage_state:'',usage_amount:1};
    const config={...defaults,...this._stockEditing};
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
    const config={quantity:Number(value('quantity')),quantity_changed:Number(value('quantity'))!==this._stockEditing.quantity,unit:value('unit')==='custom'?value('custom_unit').trim():value('unit'),
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

}

export function installStockView(panel) {
  if(panel._stockViewReady)return;
  for(const name of Object.getOwnPropertyNames(StockView.prototype))if(name!=='constructor')panel[name]=StockView.prototype[name];
  const root=panel.shadowRoot,template=document.createElement('template');
  template.innerHTML=`        <dialog id="stock-add-dialog" aria-labelledby="stock-add-title"><form id="stock-add-form"><h2 id="stock-add-title">Añadir producto al stock</h2><label>Nombre del producto<input name="name" type="text" maxlength="255" list="stock-add-products" autocomplete="off" required></label><datalist id="stock-add-products"></datalist><p id="stock-add-error" class="notice error" role="alert" hidden></p><div class="dialog-actions"><button id="stock-add-submit" type="submit">Añadir</button></div></form></dialog>
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
          </div><div class="dialog-actions"><button id="delete-stock-from-editor" type="button">Eliminar</button><button id="save-stock-config" type="submit">Guardar</button></div></form>
        </dialog>
        <dialog id="stock-remove-dialog" aria-labelledby="stock-remove-title"><h2 id="stock-remove-title">Eliminar de Stock</h2><p id="stock-remove-description"></p><p id="stock-remove-error" class="notice error" role="alert" hidden></p><div class="dialog-actions"><button id="cancel-stock-remove" type="button">Cancelar</button><button id="confirm-stock-remove" type="button">Eliminar producto</button></div></dialog>
`;
  root.querySelector('main').append(template.content);
  installDialogCloseButtons(root);
  installStockEvents.call(panel,root);
  panel._stockViewReady=true;
}
function installStockEvents(root) {
    root.querySelector('#add-stock').addEventListener('click',()=>this._openStockAdd());
    root.querySelector('#stock-add-form').addEventListener('submit',event=>{event.preventDefault();void this._addStockProduct();});
    root.querySelector('#stock-add-dialog').addEventListener('cancel',event=>{if(this._busy)event.preventDefault();});
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
}
