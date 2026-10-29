import { installToggleStyles } from './toggle-styles.js?v=0.50.4';
class DiaPricesSettings extends HTMLElement {
  constructor(){super();this.attachShadow({mode:'open'});this._status={refresh_enabled:false,days:30};this._generation=0;}
  set hass(value){this._hass=value;if(!this._built)this._build();this._render();}
  disconnectedCallback(){this.deactivate();}
  deactivate(){this._generation++;this._loaded=false;}
  async activate(){
    const generation=++this._generation;this._error='';this._loaded=false;this._render();
    if(this._hass?.user?.is_admin!==true)return;
    try{const status=await this._call('status');if(generation===this._generation){this._status=status;this._loaded=true;}}
    catch(error){if(generation===this._generation)this._error=error.message??'No se han podido cargar las opciones de DIA.';}
    if(generation===this._generation)this._render();
  }
  _call(action,fields={}){return this._hass.callWS({type:'improved_shopping_list/dia/prices/'+action,...fields});}
  _build(){
    this._built=true;this.shadowRoot.innerHTML=`<style>
      :host{display:block;color:inherit;font:inherit}*{box-sizing:border-box}[hidden]{display:none!important}
      .options{display:grid;gap:18px;margin-top:24px}.row{display:flex;align-items:center;justify-content:space-between;gap:16px}
      .help{font-size:12px;line-height:1.5;opacity:.7;margin:5px 0 0}label,input{font:inherit;color:inherit}
      .toggle{appearance:none;width:38px;height:22px;min-height:22px;flex:none;border:0;border-radius:20px;padding:3px;background:var(--switch-unchecked-track-color,#64748b);cursor:pointer;margin:0}
      .toggle:before{content:"";display:block;width:16px;height:16px;border-radius:50%;background:white;transition:transform .15s}
      .toggle:checked{background:var(--isl-green,#267052)}.toggle:checked:before{transform:translateX(16px)}
      input:disabled{opacity:.45;cursor:default}input:focus-visible{outline:3px solid var(--primary-color,#267052);outline-offset:3px}
      .period{display:flex;align-items:center;gap:8px;flex:none}.days{width:68px;min-height:38px;padding:6px;border:1px solid var(--divider-color,#d9e0dd);border-radius:8px;background:var(--card-background-color,#fff);text-align:center}
      .error{font-size:13px;line-height:1.5;color:var(--error-color,#d32f2f);overflow-wrap:anywhere;margin:16px 0 0}
      @media(max-width:420px){.row{gap:10px;font-size:.9em}.period{gap:6px}.days{width:54px}}
    </style><p class="help">Vincula cada producto manualmente con su enlace o ID de DIA en la ficha del catálogo. Se guarda la referencia interna; no se utiliza como EAN.</p>
    <div class="options"><div><div class="row"><label for="refresh-enabled">Actualizar precios cada</label><div class="period"><input id="days" class="days" type="number" min="1" max="3650" step="1" value="30" aria-label="Periodo de actualización de DIA en días"><span>días</span><input id="refresh-enabled" class="toggle" type="checkbox" role="switch" aria-label="Actualizar precios periódicamente" aria-describedby="refresh-help"></div></div><p id="refresh-help" class="help">Actualiza los productos vinculados mediante su referencia web, repartiendo las consultas durante el periodo. Se usa una ubicación fija y se conserva el último precio conocido.</p></div></div><p id="error" class="error" role="alert" hidden></p>`;
    installToggleStyles(this.shadowRoot);
    for(const id of ['refresh-enabled','days'])this.shadowRoot.querySelector('#'+id).addEventListener('change',()=>void this._save());
  }
  async _save(){
    if(this._busy||!this._loaded||this._hass?.user?.is_admin!==true)return;
    const r=this.shadowRoot,days=Number(r.querySelector('#days').value);
    if(!Number.isInteger(days)||days<1||days>3650){this._error='Indica un periodo entre 1 y 3650 días.';this._renderError();return;}
    const generation=this._generation,options={refresh_enabled:r.querySelector('#refresh-enabled').checked,days};
    this._busy=true;this._error='';this._lock();this._renderError();
    try{const status=await this._call('options',{options});if(generation===this._generation)this._status=status;}
    catch(error){if(generation===this._generation)this._error=error.message??'No se han podido guardar las opciones de DIA.';}
    finally{this._busy=false;if(generation===this._generation)this._render();}
  }
  _lock(){this.shadowRoot.querySelectorAll('input').forEach(input=>input.disabled=this._busy||!this._loaded||this._hass?.user?.is_admin!==true);}
  _renderError(){const el=this.shadowRoot.querySelector('#error');el.textContent=this._error||this._status.error||'';el.hidden=!el.textContent;}
  _render(){if(!this._built)return;const r=this.shadowRoot;r.querySelector('#refresh-enabled').checked=Boolean(this._status.refresh_enabled);r.querySelector('#days').value=this._status.days??30;this._lock();this._renderError();}
}
if(!customElements.get('isl-dia-prices-settings'))customElements.define('isl-dia-prices-settings',DiaPricesSettings);
