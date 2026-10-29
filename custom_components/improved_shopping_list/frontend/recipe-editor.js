/** Recipe editor; ingredient units belong to catalog products. */
import { installDialogCloseButtons } from "./dialog-controls.js?v=0.49.1";
import { productNameKey } from "./product-names.js?v=0.49.1";
const node = (tag, text, className) => { const el=document.createElement(tag); if(text!==undefined)el.textContent=text; if(className)el.className=className; return el; };
class RecipeEditor extends HTMLElement {
  constructor(){super();this.attachShadow({mode:"open"});this.products=[];this._ingredients=[];}
  connectedCallback(){if(!this._built)this._build();}
  disconnectedCallback(){this.shadowRoot.querySelectorAll("dialog").forEach(dialog=>dialog.close());}
  _build(){
    this.shadowRoot.innerHTML = '<style>:host{display:contents;color:var(--primary-text-color,#20352d)}*{box-sizing:border-box}[hidden]{display:none!important}button,input{font:inherit;color:inherit}button{cursor:pointer;min-height:44px;padding:10px 12px;border:1px solid var(--divider-color,#dfe7e1);border-radius:10px;background:transparent}button:disabled{opacity:.5;cursor:default}button:focus-visible,input:focus-visible{outline:3px solid var(--primary-color,#267052);outline-offset:2px}dialog{color:inherit;background:var(--card-background-color,#fff);border:1px solid var(--divider-color,#dfe7e1);border-radius:18px;padding:24px;width:min(640px,calc(100vw - 28px));max-height:calc(100dvh - 28px);overflow:auto}dialog::backdrop{background:rgba(0,0,0,.4)}h2{margin:0;font-size:23px}label{display:block;margin-top:18px;font-size:13px;font-weight:600}input{display:block;width:100%;min-width:0;margin-top:7px;min-height:44px;border:1px solid var(--divider-color,#dfe7e1);border-radius:9px;padding:9px 10px;background:var(--card-background-color,#fff)}.add{display:flex;align-items:end;gap:8px;margin-top:18px}.add label{flex:1;min-width:0;margin:0}.icon-button{display:grid;place-items:center;flex:none;width:38px;min-height:38px;padding:0;border:0}.add button{height:44px}.icon-button ha-icon{width:20px;height:20px;--mdc-icon-size:20px}.primary{background:#267052;color:#fff;border:0}.danger{background:#d32f2f;color:#fff;border:0}.ingredients{display:grid;gap:10px;margin-top:20px}.ingredient{display:grid;grid-template-columns:minmax(0,1fr) 78px 48px 38px;align-items:center;gap:8px;border-bottom:1px solid var(--divider-color,#dfe7e1);padding-bottom:10px;min-width:0}.ingredient input{margin:0;text-align:center;appearance:textfield}.ingredient input::-webkit-inner-spin-button,.ingredient input::-webkit-outer-spin-button{appearance:none;margin:0}.ingredient-name,.unit{overflow-wrap:anywhere;font-size:14px}.unit{font-size:12px;text-align:center}.actions{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin-top:24px}.actions button{min-width:0}.actions #save-recipe{grid-column:2}.error{color:var(--error-color,#bd3636);border:1px solid var(--error-color,#bd3636);border-radius:10px;padding:10px;margin-top:16px;font-size:13px;line-height:1.5}@media(max-width:400px){dialog{padding:20px}.ingredient{grid-template-columns:minmax(0,1fr) 64px 32px 32px;gap:5px}.ingredient .icon-button{width:32px}.ingredient-name{font-size:13px}}</style>'+
      '<dialog id="recipe-dialog" aria-labelledby="recipe-title"><form id="recipe-form"><h2 id="recipe-title">Nueva receta</h2><div id="recipe-error" class="error" role="alert" hidden></div><label>Nombre de la receta<input name="name" required maxlength="160"></label><label>URL Imagen<input name="image_url" maxlength="2048" placeholder="https://… o /local/receta.png"></label><div class="add"><label>Producto del catálogo<input id="recipe-product-search" type="search" list="recipe-product-options" placeholder="Buscar ingrediente" autocomplete="off"></label><datalist id="recipe-product-options"></datalist><button id="add-ingredient" type="button" class="primary icon-button" aria-label="Añadir ingrediente"><ha-icon icon="mdi:plus-thick" aria-hidden="true"></ha-icon></button></div><div id="recipe-ingredients" class="ingredients"></div><div class="actions"><button id="delete-recipe" class="danger" type="button" hidden>Eliminar receta</button><button id="save-recipe" class="primary" type="submit">Guardar receta</button></div></form></dialog>'+
      '<dialog id="delete-recipe-dialog" aria-labelledby="delete-recipe-title"><h2 id="delete-recipe-title">Eliminar receta</h2><p>Se eliminará la receta. Sus productos se conservarán en el catálogo y en las listas.</p><div id="delete-recipe-error" class="error" role="alert" hidden></div><div class="actions"><button id="cancel-delete-recipe" type="button">Cancelar</button><button id="confirm-delete-recipe" class="danger" type="button">Eliminar receta</button></div></dialog>';
    this._built=true; const root=this.shadowRoot; installDialogCloseButtons(root);
    root.querySelector('#add-ingredient').addEventListener('click',()=>this._addIngredient());
    root.querySelector('#recipe-product-search').addEventListener('keydown',event=>{if(event.key==='Enter'&&!event.isComposing){event.preventDefault();this._addIngredient();}});
    root.querySelector('#recipe-form').addEventListener('submit',event=>{event.preventDefault();void this._save();});
    root.querySelector('#delete-recipe').addEventListener('click',()=>{root.querySelector('#delete-recipe-error').hidden=true;root.querySelector('#delete-recipe-dialog').showModal();});
    root.querySelector('#cancel-delete-recipe').addEventListener('click',()=>root.querySelector('#delete-recipe-dialog').close());
    root.querySelector('#confirm-delete-recipe').addEventListener('click',()=>void this._delete());
    root.querySelector('#recipe-dialog').addEventListener('close',()=>this.onClose?.());
    root.querySelectorAll('dialog').forEach(dialog=>dialog.addEventListener('cancel',event=>{if(this._busy)event.preventDefault();}));
  }
  open(recipe){
    if(this._busy)return;
    const root=this.shadowRoot;this._editing=recipe?structuredClone(recipe):null;this._ingredients=structuredClone(recipe?.ingredients??[]);
    root.querySelector('#recipe-form').reset();root.querySelector('[name=name]').value=recipe?.name??'';root.querySelector('[name=image_url]').value=recipe?.image_url??'';
    root.querySelector('#recipe-title').textContent=recipe?'Editar receta':'Nueva receta';root.querySelector('#delete-recipe').hidden=!recipe;
    root.querySelector('#recipe-error').hidden=true;root.querySelector('#recipe-product-options').replaceChildren(...this.products.map(product=>new Option(product.name,product.name)));
    this._renderIngredients();root.querySelector('#recipe-dialog').showModal();root.querySelector('[name=name]').focus();
  }
  _error(message,id='recipe-error'){const error=this.shadowRoot.getElementById(id);error.textContent=message;error.hidden=false;}
  _addIngredient(){
    if(this._busy)return;
    const input=this.shadowRoot.querySelector('#recipe-product-search'),matches=this.products.filter(product=>productNameKey(product.name)===productNameKey(input.value));
    if(matches.length!==1){this._error('Selecciona un producto del catálogo.');return;}
    const product=matches[0];if(this._ingredients.some(item=>item.product_id===product.id)){this._error('Este producto ya está en la receta. Ajusta su cantidad.');return;}
    this._ingredients.push({product_id:product.id,quantity:product.unit_quantity??1,unit:product.purchase_unit??'uds'});input.value='';this.shadowRoot.querySelector('#recipe-error').hidden=true;this._renderIngredients();input.focus();
  }
  _renderIngredients(){
    this.shadowRoot.querySelector('#recipe-ingredients').replaceChildren(...this._ingredients.map((ingredient,index)=>{
      const product=this.products.find(product=>product.id===ingredient.product_id),row=node('div',undefined,'ingredient');row.dataset.productId=ingredient.product_id;
      const amount=node('input');amount.type='number';amount.min='0.001';amount.max='1000000';amount.step='0.001';amount.required=true;amount.value=ingredient.quantity;amount.disabled=this._busy;
      amount.setAttribute('aria-label','Cantidad de '+(product?.name??'producto eliminado'));amount.addEventListener('input',()=>{ingredient.quantity=Number(amount.value);});
      const remove=node('button',undefined,'danger icon-button');remove.type='button';remove.disabled=this._busy;remove.setAttribute('aria-label','Quitar ingrediente '+(product?.name??'eliminado'));
      const icon=node('ha-icon');icon.setAttribute('icon','mdi:delete');icon.setAttribute('aria-hidden','true');remove.append(icon);remove.addEventListener('click',()=>{this._ingredients.splice(index,1);this._renderIngredients();});
      const label=node('span',product?.name??'Producto eliminado','ingredient-name');
      if(product&&(product.purchase_unit??'uds')!==ingredient.unit)label.append(document.createTextNode(' · Revisa las unidades'));
      row.append(label,amount,node('span',ingredient.unit,'unit'),remove);return row;
    }));
  }
  _setBusy(value){this._busy=value;this.shadowRoot.querySelectorAll('button,input').forEach(el=>{el.disabled=value;});}
  async _save(){
    if(this._busy)return;
    if(!this._ingredients.length){this._error('Añade al menos un ingrediente del catálogo.');return;}
    const recipe={name:this.shadowRoot.querySelector('[name=name]').value,image_url:this.shadowRoot.querySelector('[name=image_url]').value,ingredients:structuredClone(this._ingredients)};
    if(this._editing)Object.assign(recipe,{id:this._editing.id,revision:this._editing.revision});
    this._setBusy(true);this.shadowRoot.querySelector('#recipe-error').hidden=true;
    try{await this.onSave(recipe);this.shadowRoot.querySelector('#recipe-dialog').close();}catch(error){this._error(error.message??'No se ha podido guardar la receta.');}finally{this._setBusy(false);}
  }
  async _delete(){
    if(this._busy||!this._editing)return;this._setBusy(true);
    try{await this.onDelete(this._editing);this.shadowRoot.querySelector('#delete-recipe-dialog').close();this.shadowRoot.querySelector('#recipe-dialog').close();}catch(error){this._error(error.message??'No se ha podido eliminar la receta.','delete-recipe-error');}finally{this._setBusy(false);}
  }
}
if(!customElements.get('isl-recipe-editor'))customElements.define('isl-recipe-editor',RecipeEditor);
