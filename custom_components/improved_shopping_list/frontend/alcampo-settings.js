import { installToggleStyles } from './toggle-styles.js?v=0.53.4';
class AlcampoSettings extends HTMLElement {
  constructor(){super();this.attachShadow({mode:'open'});this._status={search_enabled:false,refresh_enabled:false,days:30};this._generation=0;this._products=[];}
  set hass(value){this._hass=value;if(!this._built)this._build();this._render();}
  set products(value){
    const key=JSON.stringify((value??[]).map(product=>[product.id,product.name]));if(key===this._productsKey)return;
    this._productsKey=key;this._products=value??[];if(this._built)this._renderProducts();
  }
  disconnectedCallback(){this.deactivate();}
  deactivate(){this._generation++;clearTimeout(this._saveTimer);}
  async activate(){
    const generation=++this._generation;this._error='';
    if(!this._hass?.user?.is_admin){this._render();return;}
    try{const status=await this._call('status');if(generation===this._generation)this._status=status;}
    catch(error){if(generation===this._generation)this._error=error.message??'No se han podido cargar las opciones de Alcampo.';}
    if(generation===this._generation)this._render();
  }
  _call(action,fields={}){return this._hass.callWS({type:'improved_shopping_list/alcampo/'+action,...fields});}
  _build(){
    this._built=true;this.shadowRoot.innerHTML=`<style>
      :host{display:block;color:inherit;font:inherit}*{box-sizing:border-box}[hidden]{display:none!important}
      .options{display:grid;gap:18px;margin-top:24px}.row{display:flex;align-items:center;justify-content:space-between;gap:16px}
      label{font:inherit}.help{font-size:12px;line-height:1.5;opacity:.7;margin:5px 0 0}
      input{font:inherit;color:inherit}.toggle{appearance:none;width:38px;height:22px;min-height:22px;flex:none;border:0;border-radius:20px;padding:3px;background:var(--switch-unchecked-track-color,#64748b);cursor:pointer;margin:0}
      .toggle:before{content:"";display:block;width:16px;height:16px;border-radius:50%;background:white;transition:transform .15s}
      .toggle:checked{background:var(--isl-green,#267052)}.toggle:checked:before{transform:translateX(16px)}
      input:disabled{opacity:.45;cursor:default}input:focus-visible{outline:3px solid var(--primary-color,#267052);outline-offset:3px}
      .period{display:flex;align-items:center;gap:8px;flex:none}.days{width:68px;min-height:38px;padding:6px;border:1px solid var(--divider-color,#d9e0dd);border-radius:8px;background:var(--card-background-color,#fff);text-align:center}
      .test-search{margin-top:24px;padding-top:18px;border-top:1px solid var(--divider-color,#d9e0dd)}.test-search h3{font-size:15px;margin:0 0 12px}.test-controls{display:flex;gap:8px;margin-top:10px}.test-controls select{flex:1;min-width:0;font:inherit;color:inherit;border:1px solid var(--divider-color,#d9e0dd);border-radius:8px;background:var(--card-background-color,#fff);padding:10px}.test-controls button{font:inherit;min-height:42px;border:0;border-radius:8px;padding:10px 16px;background:#2196f3;color:white}.test-controls button:disabled{opacity:.5;cursor:default}.test-result{font-size:13px;overflow-wrap:anywhere;line-height:1.5;margin-top:14px}.test-result pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:11px}.test-result a{color:var(--primary-color,#2196f3)}
      .error{font-size:13px;line-height:1.5;color:var(--error-color,#d32f2f);overflow-wrap:anywhere;margin:16px 0 0}
      @media(max-width:420px){.row{gap:10px;font-size:.9em}.period{gap:6px}.days{width:54px}}
    </style><div class="options"><div><div class="row"><label for="search-enabled">Buscar coincidencias de productos en su catálogo</label><input id="search-enabled" class="toggle" type="checkbox" role="switch" aria-describedby="search-help"></div><p id="search-help" class="help">Busca con nombres comerciales de compras o enlaces guardados de otras tiendas y vincula solo coincidencias de EAN exactas. Incluye los nuevos códigos añadidos; si no hay un nombre comercial, puedes indicar la URL de Alcampo en la ficha del producto.</p></div>
    <div><div class="row"><label for="refresh-enabled">Actualizar precios cada</label><div class="period"><input id="days" class="days" type="number" min="1" max="3650" step="1" value="30" aria-label="Periodo de actualización de Alcampo en días"><span>días</span><input id="refresh-enabled" class="toggle" type="checkbox" role="switch" aria-label="Actualizar precios periódicamente" aria-describedby="refresh-help"></div></div><p id="refresh-help" class="help">Actualiza los productos vinculados mediante su referencia web, repartiendo las consultas durante el periodo. Se usa una ubicación fija y se conserva el último precio conocido.</p></div></div><section class="test-search"><h3>Prueba de búsqueda (temporal)</h3><p class="help">Consulta con el nombre comercial de otra tienda. Muestra hasta tres candidatos pendientes de confirmar por EAN y respeta la pausa de cinco minutos entre peticiones.</p><div class="test-controls"><select id="test-product" aria-label="Producto del catálogo para probar Alcampo"></select><button id="test-search" type="button">Buscar</button></div><div id="test-result" class="test-result" role="status" hidden></div></section><p id="error" class="error" role="alert" hidden></p>`;
    installToggleStyles(this.shadowRoot);
    this.shadowRoot.querySelector('#test-search').addEventListener('click',()=>void this._testSearch());
    this.shadowRoot.querySelector('#test-product').addEventListener('change',()=>this._lock());
    this._renderProducts();
    for(const id of ['search-enabled','refresh-enabled','days'])this.shadowRoot.querySelector('#'+id).addEventListener('change',()=>void this._save());
  }
  _renderProducts(){
    const select=this.shadowRoot.querySelector('#test-product'),selected=select.value;
    const products=[...this._products].sort((a,b)=>a.name.localeCompare(b.name,'es'));
    select.replaceChildren(new Option('Selecciona un producto',''),...products.map(product=>new Option(product.name,product.id)));
    if(products.some(product=>product.id===selected))select.value=selected;
    this._lock();
  }
  async _testSearch(){
    if(this._busy||this._hass?.user?.is_admin!==true)return;
    const productId=this.shadowRoot.querySelector('#test-product').value;if(!productId)return;
    const generation=this._generation;this._busy=true;this._testing=true;this._error='';this._lock();
    const resultBox=this.shadowRoot.querySelector('#test-result');resultBox.replaceChildren();resultBox.hidden=true;
    try{
      const result=await this._call('test_search',{product_id:productId});if(generation!==this._generation)return;
      const message=document.createElement('p');message.textContent=result.status==='paused'?'Consulta en pausa hasta '+new Date(result.next_request*1000).toLocaleString('es-ES')+'.':result.message;
      resultBox.append(message);
      if(result.term){const term=document.createElement('p');term.textContent='Consulta: '+result.term;resultBox.append(term);}
      if(result.eans?.length){const ean=document.createElement('p');ean.textContent='EAN: '+result.eans.join(' · ');resultBox.append(ean);}
      if(result.candidates?.length){const list=document.createElement('ul');for(const candidate of result.candidates){const li=document.createElement('li'),link=document.createElement('a');link.textContent='Referencia '+candidate.reference_id;link.href=candidate.url;link.target='_blank';link.rel='noopener noreferrer';li.append(link);list.append(li);}resultBox.append(list);}
      const details=document.createElement('details'),title=document.createElement('summary'),technical=document.createElement('pre');title.textContent='Información técnica';technical.textContent=JSON.stringify(result,null,2);details.append(title,technical);resultBox.append(details);resultBox.hidden=false;
      const status=await this._call('status');if(generation===this._generation)this._status=status;
    }catch(error){if(generation===this._generation)this._error=error.message??'No se ha podido probar la búsqueda de Alcampo.';}
    finally{this._busy=false;this._testing=false;if(generation===this._generation){this._lock();this._renderError();}}
  }
  async _save(){
    if(this._busy)return;const r=this.shadowRoot,days=Number(r.querySelector('#days').value);
    if(!Number.isInteger(days)||days<1||days>3650){this._error='Indica un periodo entre 1 y 3650 días.';this._renderError();return;}
    const options={search_enabled:r.querySelector('#search-enabled').checked,refresh_enabled:r.querySelector('#refresh-enabled').checked,days};
    const generation=this._generation;this._busy=true;this._error='';this._renderError();this._lock();
    try{const status=await this._call('options',{options});if(generation===this._generation)this._status=status;}
    catch(error){if(generation===this._generation)this._error=error.message??'No se han podido guardar las opciones de Alcampo.';}
    finally{this._busy=false;if(generation===this._generation)this._render();}
  }
  _lock(){const locked=this._busy||this._hass?.user?.is_admin!==true;this.shadowRoot.querySelectorAll('input,select').forEach(input=>input.disabled=locked);const button=this.shadowRoot.querySelector('#test-search');button.disabled=locked||!this.shadowRoot.querySelector('#test-product').value;button.textContent=this._testing?'Buscando…':'Buscar';button.setAttribute('aria-busy',String(Boolean(this._testing)));}
  _renderError(){const el=this.shadowRoot.querySelector('#error');el.textContent=this._error||this._status.error||'';el.hidden=!el.textContent;}
  _render(){if(!this._built)return;const r=this.shadowRoot;r.querySelector('#search-enabled').checked=Boolean(this._status.search_enabled);r.querySelector('#refresh-enabled').checked=Boolean(this._status.refresh_enabled);r.querySelector('#days').value=this._status.days??30;this._lock();this._renderError();}
}
if(!customElements.get('isl-alcampo-settings'))customElements.define('isl-alcampo-settings',AlcampoSettings);
