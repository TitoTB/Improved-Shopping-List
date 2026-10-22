class AlcampoSettings extends HTMLElement {
  constructor(){super();this.attachShadow({mode:'open'});this._status={search_enabled:false,refresh_enabled:false,days:30};this._generation=0;}
  set hass(value){this._hass=value;if(!this._built)this._build();this._render();}
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
      .error{font-size:13px;line-height:1.5;color:var(--error-color,#d32f2f);overflow-wrap:anywhere;margin:16px 0 0}
      @media(max-width:420px){.row{gap:10px;font-size:.9em}.period{gap:6px}.days{width:54px}}
    </style><div class="options"><div><div class="row"><label for="search-enabled">Buscar coincidencias de productos en su catálogo</label><input id="search-enabled" class="toggle" type="checkbox" role="switch" aria-describedby="search-help"></div><p id="search-help" class="help">Busca con nombres comerciales de compras o enlaces guardados de otras tiendas y vincula solo coincidencias de EAN exactas. Incluye los nuevos códigos añadidos; si no hay un nombre comercial, puedes indicar la URL de Alcampo en la ficha del producto.</p></div>
    <div><div class="row"><label for="refresh-enabled">Actualizar precios cada</label><div class="period"><input id="days" class="days" type="number" min="1" max="3650" step="1" value="30" aria-label="Periodo de actualización de Alcampo en días"><span>días</span><input id="refresh-enabled" class="toggle" type="checkbox" role="switch" aria-label="Actualizar precios periódicamente" aria-describedby="refresh-help"></div></div><p id="refresh-help" class="help">Actualiza los productos vinculados mediante su referencia web, repartiendo las consultas durante el periodo. Se usa una ubicación fija y se conserva el último precio conocido.</p></div></div><p id="error" class="error" role="alert" hidden></p>`;
    for(const id of ['search-enabled','refresh-enabled','days'])this.shadowRoot.querySelector('#'+id).addEventListener('change',()=>void this._save());
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
  _lock(){const locked=this._busy||this._hass?.user?.is_admin!==true;this.shadowRoot.querySelectorAll('input').forEach(input=>input.disabled=locked);}
  _renderError(){const el=this.shadowRoot.querySelector('#error');el.textContent=this._error||this._status.error||'';el.hidden=!el.textContent;}
  _render(){if(!this._built)return;const r=this.shadowRoot;r.querySelector('#search-enabled').checked=Boolean(this._status.search_enabled);r.querySelector('#refresh-enabled').checked=Boolean(this._status.refresh_enabled);r.querySelector('#days').value=this._status.days??30;this._lock();this._renderError();}
}
if(!customElements.get('isl-alcampo-settings'))customElements.define('isl-alcampo-settings',AlcampoSettings);
