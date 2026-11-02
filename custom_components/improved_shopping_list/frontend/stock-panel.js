import './meal-consumption.js?v=0.81.0';
/** Pantry UI, forms and calculations loaded only when Stock is opened. */
import { imageSource, normalizedName, productNameKey } from './product-display.js?v=0.81.0';
import { installDialogCloseButtons } from './dialog-controls.js?v=0.81.0';
const stockQuantity = (item, now=Date.now()/1000) => {
  if(item.mode!=='perishable')return item.quantity;
  if(item.quantity<=0||item.expired)return 0;
  if(!item.expires_at)return item.quantity;
  const start=item.quantity_at||item.expires_at-(item.days??7)*86400;
  if(item.expires_at<=now||item.expires_at<=start)return 0;
  return Math.round(item.quantity*Math.max(0,Math.min(1,(item.expires_at-now)/(item.expires_at-start)))*1000)/1000;
};
const stockRemaining = (item, now=Date.now()/1000) => Math.max(0,Math.min(100,stockQuantity(item,now)/((item.full_quantity??item.refill_quantity)||1)*100));


const stockEditorStyles=`
#stock-editor-dialog{--stock-editor-field:color-mix(in srgb,var(--card-background-color,#fff) 92%,#000);--stock-editor-border:color-mix(in srgb,var(--divider-color,#dfe7e1) 80%,var(--primary-text-color,#20352d) 20%);width:min(600px,calc(100vw - 28px));padding:0;border-radius:20px;box-shadow:0 18px 48px #0003;}
#stock-editor-form{min-width:0;padding:24px;}
#stock-editor-title,.stock-editor-sr{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip-path:inset(50%);white-space:nowrap;}
#stock-editor-form .stock-editor-header{display:flex;align-items:center;gap:14px;padding-right:30px;margin-bottom:22px;}
#stock-editor-media{display:grid;place-items:center;width:54px;height:54px;flex:none;border-radius:16px;background:var(--stock-editor-field);overflow:hidden;}
#stock-editor-media img{width:100%;height:100%;object-fit:contain;padding:8px;}
#stock-editor-media ha-icon{display:flex;align-items:center;justify-content:center;--mdc-icon-size:34px;width:34px;height:34px;line-height:0;}
.stock-editor-identity{min-width:0;overflow-wrap:anywhere;}.stock-editor-identity p{margin:0 0 3px;font-size:11px;color:var(--secondary-text-color,#63766b);}
#stock-editor-name{display:block;font-size:23px;font-weight:650;line-height:1.25;letter-spacing:-.4px;}
#stock-editor-form label{font-size:12px;font-weight:550;line-height:1.45;color:var(--secondary-text-color,#63766b);}
#stock-editor-form input:not([type=checkbox]),#stock-editor-form select{min-width:0;width:100%;height:44px;margin:7px 0 0;padding:10px 12px;border:1px solid var(--stock-editor-border);border-radius:10px;background:var(--stock-editor-field);color:var(--primary-text-color,#20352d);font:inherit;}
#stock-editor-form select{appearance:none;-webkit-appearance:none;padding-right:34px;background-image:linear-gradient(45deg,transparent 35%,currentColor 35%,currentColor 65%,transparent 65%),linear-gradient(135deg,transparent 35%,currentColor 35%,currentColor 65%,transparent 65%);background-position:right 17px center,right 12px center;background-size:5px 5px;background-repeat:no-repeat;}
#stock-editor-form input:disabled,#stock-editor-form select:disabled{opacity:.5;}
#stock-editor-form .stock-current-card{--stock-current-start:color-mix(in srgb,var(--isl-stock-gradient-start,#f59a23) var(--stock-draft-percent,100%),#d32f2f);--stock-current-end:color-mix(in srgb,var(--isl-stock-gradient-end,#c65b0c) var(--stock-draft-percent,100%),#b52a27);padding:18px;border:1px solid color-mix(in srgb,var(--stock-current-start) 45%,var(--stock-editor-border));border-radius:14px;background:color-mix(in srgb,var(--stock-current-start) 9%,var(--card-background-color,#fff));}
.stock-current-caption{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:10px;font-size:12px;}
#stock-editor-percent{font-size:12px;font-weight:650;font-variant-numeric:tabular-nums;white-space:nowrap;}
.stock-current-values{display:flex;align-items:center;justify-content:center;gap:10px;margin:4px 0 16px;}
#stock-editor-form .stock-quantity-editor{grid-template-columns:36px minmax(0,1fr) 36px;align-items:center;gap:4px;min-width:0;max-width:240px;flex:1;}
#stock-editor-form .stock-quantity-editor button{display:grid;place-items:center;width:36px;height:36px;min-height:36px;padding:0;border:1px solid var(--stock-editor-border);border-radius:10px;background:var(--stock-editor-field);color:inherit;}
#stock-editor-form .stock-quantity-editor button ha-icon{display:flex;align-items:center;justify-content:center;width:20px;height:20px;--mdc-icon-size:20px;line-height:0;}
#stock-editor-form .stock-quantity-editor input{height:52px;margin:0;padding:0;background:transparent;border:0;font-size:34px;font-weight:650;line-height:1.2;letter-spacing:-1px;text-align:center;}
#stock-editor-form .stock-editor-unit{flex:0 0 90px;min-width:0;}
#stock-editor-form .stock-editor-unit select{margin:0;text-align:center;text-align-last:center;}
.stock-current-card.custom-unit .stock-current-values{flex-wrap:wrap;}#stock-editor-form .stock-current-card.custom-unit .stock-editor-unit{flex-basis:100%;}
.stock-editor-progress{height:9px;border-radius:99px;overflow:hidden;background:color-mix(in srgb,var(--stock-current-start) 22%,var(--stock-editor-field));}
.stock-editor-progress-fill{width:var(--stock-draft-percent,100%);height:100%;border-radius:inherit;background:linear-gradient(90deg,var(--stock-current-start),var(--stock-current-end));}
#stock-custom-unit-label{display:block;margin-top:14px;}
#stock-editor-form>.stock-form-fields{grid-template-columns:minmax(0,1fr);gap:16px;margin:22px 0;}
.stock-editor-section-title{display:flex;align-items:center;gap:8px;margin:0;font-size:13px;font-weight:650;}
.stock-editor-section-title ha-icon{display:flex;align-items:center;justify-content:center;width:18px;height:18px;--mdc-icon-size:18px;color:var(--secondary-text-color,#63766b);line-height:0;}
#stock-editor-form .stock-editor-row{display:grid;grid-template-columns:minmax(0,1fr) minmax(140px,45%);align-items:center;gap:16px;}
#stock-editor-form .stock-editor-row select{margin:0;}
#stock-editor-form .stock-form-fields .stock-form-fields{margin:0;gap:14px;}
#stock-editor-form .stock-expiry-refill{gap:14px;}
#stock-editor-form .stock-number-field{display:flex;align-items:center;width:100%;min-width:0;height:44px;margin-top:7px;background:var(--stock-editor-field);border:1px solid var(--stock-editor-border);border-radius:10px;}
#stock-editor-form .stock-number-field input{min-width:0;flex:1;width:100%;height:42px;margin:0;border:0;background:transparent;text-align:center;padding:9px;appearance:textfield;}
#stock-editor-form .stock-number-field input::-webkit-inner-spin-button,#stock-editor-form .stock-number-field input::-webkit-outer-spin-button{-webkit-appearance:none;margin:0;}
#stock-editor-form .stock-number-field>span{flex:none;max-width:65px;padding-right:12px;font-size:12px;font-weight:400;overflow:hidden;text-overflow:ellipsis;}
#stock-editor-form .stock-reorder-row{border-top:1px solid var(--stock-editor-border);margin-top:2px;padding-top:18px;grid-template-columns:minmax(0,1fr) 96px;}
#stock-editor-form .stock-reorder-row .check{font-weight:400;}
#stock-editor-form .stock-reorder-row .stock-number-field{margin-top:0;}
#stock-editor-form .stock-reorder-row:has(#stock-threshold-label[hidden]){grid-template-columns:minmax(0,1fr);}
#stock-editor-form>.dialog-actions{margin:0 -24px -24px;padding:16px 24px;border-top:1px solid var(--stock-editor-border);gap:10px;align-items:stretch;}
#stock-editor-form>.dialog-actions button{display:flex;align-items:center;justify-content:center;gap:7px;min-height:44px;padding:10px 12px;border-radius:10px;font-size:13px;font-weight:600;}
#stock-editor-form #delete-stock-from-editor{color:var(--error-color,#d32f2f);background:transparent;border:1px solid color-mix(in srgb,var(--error-color,#d32f2f) 45%,var(--stock-editor-border));}
#stock-editor-form #delete-stock-from-editor ha-icon{display:flex;align-items:center;justify-content:center;width:17px;height:17px;--mdc-icon-size:17px;line-height:0;}
#stock-editor-form #save-stock-config{background:#267052;color:#fff;border:0;}
@media(max-width:500px){#stock-editor-form{padding:18px 16px;}#stock-editor-form .stock-editor-header{gap:12px;margin-bottom:18px;}#stock-editor-form .stock-current-card{padding:14px;}#stock-editor-form .stock-editor-row{grid-template-columns:minmax(0,1fr);gap:7px;}#stock-editor-form .stock-current-values{gap:8px;}#stock-editor-form .stock-editor-unit{flex-basis:78px;}#stock-editor-form .stock-quantity-editor{grid-template-columns:34px minmax(0,1fr) 34px;}#stock-editor-form .stock-quantity-editor button{width:34px;}#stock-editor-form .stock-expiry-refill{gap:10px;}#stock-editor-form .stock-reorder-row{grid-template-columns:minmax(0,1fr) 78px;}#stock-editor-form input:not([type=checkbox]),#stock-editor-form select{font-size:16px;}#stock-editor-form .stock-quantity-editor input{font-size:32px;}#stock-editor-form>.dialog-actions{margin:0 -16px -18px;padding:14px 16px;}}
`;


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
      const progress=['perishable','usage','meals'].includes(item.mode);
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
    const meals=root.querySelector('isl-meal-consumption');meals.hass=this._hass;meals.wholeNumbers=true;meals.reset(config.meal_rules??[]);
    this._stockDraftBasis=config.reorder_basis??'quantity';
    this._stockDraftMinimum=Math.round(config.reorder_at);this._stockDraftPercent=Math.round(config.reorder_percent??0);this._stockDraftMode=config.mode;
    for(const key of ['quantity','mode','days','refill_quantity','reorder_at','usage_entity','usage_state','usage_amount'])form.elements[key].value=config[key];
    for(const key of ['quantity','days','refill_quantity','reorder_at','usage_amount'])form.elements[key].value=Math.max(Number(form.elements[key].min),Math.round(Number(config[key])));
    if(this._stockUsesPercent(config.mode))form.elements.reorder_at.value=this._stockDraftPercent;
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
    root.querySelector('#stock-editor-name').textContent=item.name;
    const product=[...this._catalogProducts.values()].find(product=>product.id===item.catalog_product_id)??this._catalogProducts.get(productNameKey(item.name));
    const category=this._catalogCategories.get(normalizedName(product?.category));
    const media=root.querySelector('#stock-editor-media'),fallback=document.createElement('ha-icon');fallback.setAttribute('icon',product?.icon||category?.icon||'mdi:package-variant');fallback.setAttribute('aria-hidden','true');
    const source=imageSource(product?.image_url);if(source){const image=document.createElement('img');image.src=source;image.alt='';image.referrerPolicy='no-referrer';image.addEventListener('error',()=>image.replaceWith(fallback),{once:true});media.replaceChildren(image);}else media.replaceChildren(fallback);

    this._updateStockForm();root.querySelector('#stock-editor-dialog').showModal();
  }

  _stockUsesPercent(mode){return mode==='perishable'||mode!=='manual'&&this._stockDraftBasis==='percent';}

  _updateStockDraftSummary(){
    const root=this.shadowRoot,form=root.querySelector('#stock-editor-form');
    const quantity=Math.max(0,Number(form.elements.quantity.value)||0),editing=this._stockEditing??{},refill=Math.max(.001,quantity>Math.round(editing.quantity)?quantity:(editing.full_quantity??editing.refill_quantity??quantity));
    const percent=Math.max(0,Math.min(100,quantity/refill*100)),unit=form.elements.unit.value==='custom'?form.elements.custom_unit.value.trim():form.elements.unit.value;
    const card=root.querySelector('#stock-current-card');card.style.setProperty('--stock-draft-percent',percent+'%');card.classList.toggle('custom-unit',form.elements.unit.value==='custom');
    const label=Math.round(percent)+' % restante',status=root.querySelector('#stock-editor-percent');if(status.textContent!==label)status.textContent=label;
    root.querySelector('#stock-editor-progress').setAttribute('aria-valuenow',String(Math.round(percent)));
    root.querySelectorAll('[data-stock-editor-unit]').forEach(span=>{span.textContent=unit;span.title=unit;});
    root.querySelector('#stock-editor-minimum-unit').textContent=this._stockUsesPercent(form.elements.mode.value)?'%':unit;
  }


  _updateStockForm() {
    const root=this.shadowRoot,form=root.querySelector('#stock-editor-form'),locked=this._busy||this._hass.user?.is_admin!==true;
    const custom=form.elements.unit.value==='custom',usage=form.elements.mode.value==='usage',perishable=form.elements.mode.value==='perishable',percent=this._stockUsesPercent(form.elements.mode.value);
    const meals=root.querySelector('isl-meal-consumption');meals.hass=this._hass;meals.unit=custom?form.elements.custom_unit.value.trim():form.elements.unit.value;meals.active=form.elements.mode.value==='meals';
    root.querySelector('#stock-custom-unit-label').hidden=!custom;
    root.querySelector('#stock-target-label').hidden=(this._settings.entities??[]).length<=1;
    root.querySelector('#stock-days-label').hidden=!perishable;root.querySelector('#stock-usage-fields').hidden=!usage;
    root.querySelector('#stock-threshold-title').textContent=percent ? 'Mínimo (%)' : 'Stock mínimo';
    form.elements.reorder_at.setAttribute('aria-label',percent ? 'Porcentaje mínimo restante (%)' : 'Stock mínimo');
    form.elements.reorder_at.max=percent ? '100' : '1000000';
    root.querySelector('#stock-threshold-label').hidden=!form.elements.reorder_enabled.checked;
    for(const input of form.querySelectorAll('input,select,button'))input.disabled=locked;
    form.elements.custom_unit.required=custom;form.elements.days.disabled=locked||!perishable;
    for(const key of ['usage_entity','usage_state','usage_amount']){form.elements[key].disabled=locked||!usage;form.elements[key].required=usage;}
    form.elements.reorder_at.disabled=locked||!form.elements.reorder_enabled.checked;
    form.elements.list_entity.required=perishable||form.elements.reorder_enabled.checked;
    this._updateStockDraftSummary();
  }

  async _saveStockConfig() {
    if(this._busy||!this._stockEditing||this._hass.user?.is_admin!==true)return;
    const root=this.shadowRoot,form=root.querySelector('#stock-editor-form');
    if(!form.reportValidity())return;
    const value=key=>form.elements[key].value;
    const meals=root.querySelector('isl-meal-consumption');
    let mealRules;try{mealRules=value('mode')==='meals'?meals.validate():meals.value;}catch(error){const notice=root.querySelector('#stock-editor-error');notice.textContent=error.message;notice.hidden=false;return;}
    const config={quantity:Number(value('quantity')),quantity_changed:Number(value('quantity'))!==Math.round(this._stockEditing.quantity),unit:value('unit')==='custom'?value('custom_unit').trim():value('unit'),
      mode:value('mode'),days:Number(value('days')),refill_quantity:Number(value('refill_quantity')),
      reorder_enabled:form.elements.reorder_enabled.checked,
      reorder_at:this._stockUsesPercent(value('mode')) ? this._stockDraftMinimum : Number(value('reorder_at')),
      reorder_percent:this._stockUsesPercent(value('mode')) ? Number(value('reorder_at')) : this._stockDraftPercent,
      list_entity:value('list_entity'),usage_entity:value('usage_entity').trim(),usage_state:value('usage_state'),usage_amount:Number(value('usage_amount')),meal_rules:mealRules,reorder_basis:this._stockUsesPercent(value('mode'))?'percent':'quantity'};
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
  template.innerHTML=`<style>${stockEditorStyles}</style>        <dialog id="stock-add-dialog" aria-labelledby="stock-add-title"><form id="stock-add-form"><h2 id="stock-add-title">Añadir producto al stock</h2><label>Nombre del producto<input name="name" type="text" maxlength="255" list="stock-add-products" autocomplete="off" required></label><datalist id="stock-add-products"></datalist><p id="stock-add-error" class="notice error" role="alert" hidden></p><div class="dialog-actions"><button id="stock-add-submit" type="submit">Añadir</button></div></form></dialog>
        <dialog id="stock-editor-dialog" aria-labelledby="stock-editor-title">
          <form id="stock-editor-form"><h2 id="stock-editor-title">Configurar Stock</h2>
          <div class="stock-editor-header"><div id="stock-editor-media" aria-hidden="true"></div><div class="stock-editor-identity"><p>Stock</p><strong id="stock-editor-name"></strong></div></div><p id="stock-editor-error" class="notice error" role="alert" hidden></p>
          <section id="stock-current-card" class="stock-current-card">
            <div class="stock-current-caption"><label for="stock-editor-quantity">Stock actual</label><span id="stock-editor-percent" aria-live="polite"></span></div>
            <div class="stock-current-values"><div class="stock-quantity-editor"><button id="stock-draft-minus" type="button" aria-label="Disminuir stock"><ha-icon icon="mdi:minus" aria-hidden="true"></ha-icon></button><input id="stock-editor-quantity" name="quantity" aria-label="Stock actual" type="number" min="0" max="1000000" step="1" required><button id="stock-draft-plus" type="button" aria-label="Incrementar stock"><ha-icon icon="mdi:plus" aria-hidden="true"></ha-icon></button></div>
            <label class="stock-editor-unit"><span class="stock-editor-sr">Unidades</span><select name="unit" aria-label="Unidades"><option value="uds">uds</option><option value="kg">kg</option><option value="g">g</option><option value="l">l</option><option value="ml">ml</option><option value="custom">Personalizadas</option></select></label></div>
            <div id="stock-editor-progress" class="stock-editor-progress" role="progressbar" aria-label="Stock disponible" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0"><div class="stock-editor-progress-fill"></div></div>
            <label id="stock-custom-unit-label" hidden>Unidad personalizada<input name="custom_unit" maxlength="32" placeholder="Por ejemplo, Latas"></label>
          </section>
          <div class="stock-form-fields">
            <h3 class="stock-editor-section-title wide"><ha-icon icon="mdi:reload" aria-hidden="true"></ha-icon>Control y reposición</h3>
            <label class="wide stock-editor-row">Control del stock<select name="mode" aria-label="Control del stock"><option value="manual">Manual / lectores</option><option value="perishable">Perecedero</option><option value="usage">Consumo registrado</option><option value="meals">Consumo por rutinas</option></select></label>
            <div id="stock-usage-fields" class="wide" hidden><div class="stock-form-fields">
              <label class="wide">Entidad de consumo<input name="usage_entity" list="stock-usage-entities" placeholder="Por ejemplo, binary_sensor.lavadora"></label><datalist id="stock-usage-entities"></datalist>
              <label>Estado que representa un uso<input name="usage_state" maxlength="255" placeholder="Por ejemplo, on"></label>
              <label>Cantidad consumida por uso<span class="stock-number-field"><input name="usage_amount" aria-label="Cantidad consumida por uso" type="number" min="1" max="1000000" step="1" required><span data-stock-editor-unit></span></span></label>
            </div></div>
            <isl-meal-consumption class="wide" hidden></isl-meal-consumption>
            <div class="stock-expiry-refill wide">
              <label id="stock-days-label" hidden>Caduca cada<span class="stock-number-field"><input name="days" aria-label="Caduca cada cuántos días desde la compra" type="number" min="1" max="3650" step="1" required><span>días</span></span></label>
              <label>Cantidad predeterminada de reposición<span class="stock-number-field"><input name="refill_quantity" aria-label="Cantidad predeterminada de reposición" type="number" min="1" max="1000000" step="1" required><span data-stock-editor-unit></span></span></label>
            </div>
            <div class="stock-reorder-row wide">
              <label class="check"><input name="reorder_enabled" type="checkbox">Añadir a la lista cuando el stock llegue al mínimo</label>
              <label id="stock-threshold-label" hidden><span id="stock-threshold-title" class="stock-editor-sr">Stock mínimo</span><span class="stock-number-field"><input name="reorder_at" type="number" min="0" max="1000000" step="1" required><span id="stock-editor-minimum-unit"></span></span></label>
            </div>
            <label id="stock-target-label" class="wide stock-editor-row">Lista para reponer<select name="list_entity" aria-label="Lista para reponer"></select></label>
          </div><div class="dialog-actions"><button id="delete-stock-from-editor" type="button"><ha-icon icon="mdi:delete" aria-hidden="true"></ha-icon><span>Eliminar</span></button><button id="save-stock-config" type="submit">Guardar</button></div></form>
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
    root.querySelector("#stock-editor-form").addEventListener("input",event=>{if(["quantity","refill_quantity","custom_unit"].includes(event.target.name))this._updateStockDraftSummary();});
    root.querySelector("#stock-editor-form").addEventListener("change",event=>{
      if(event.target.name === "mode") {
        const form=event.currentTarget,percent=this._stockUsesPercent(form.elements.mode.value);
        if(this._stockUsesPercent(this._stockDraftMode))this._stockDraftPercent=Number(form.elements.reorder_at.value);
        else this._stockDraftMinimum=Number(form.elements.reorder_at.value);
        form.elements.reorder_at.value=percent ? this._stockDraftPercent : this._stockDraftMinimum;
        this._stockDraftMode=form.elements.mode.value;
      }
      this._updateStockForm();
    });
    root.querySelector("#stock-editor-dialog").addEventListener("cancel",event=>{if(this._busy)event.preventDefault();});
    for(const [id,delta] of [["stock-draft-minus",-1],["stock-draft-plus",1]])root.querySelector('#'+id).addEventListener("click",()=>{
      const input=root.querySelector('#stock-editor-form').elements.quantity;
      input.value=String(Math.min(1000000,Math.max(0,Math.round(Number(input.value)+delta))));
      this._updateStockDraftSummary();
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
