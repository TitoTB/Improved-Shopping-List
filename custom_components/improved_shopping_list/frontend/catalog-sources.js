import { installDialogCloseButtons } from './dialog-controls.js?v=0.53.0';
import { installToggleStyles } from './toggle-styles.js?v=0.53.0';

class CatalogSourcesPanel extends HTMLElement {
  constructor(){super();this.attachShadow({mode:'open'});this._state={enabled:false,phase:'idle',total:0,processed:0,errors:[]};this._generation=0;}
  set data(value){this._data=value;if(!this._built)this._build();this._render();this._watch();}
  set active(value){this._active=Boolean(value);if(this._active){this._watch();}else{this._stop();this.shadowRoot.querySelector('dialog')?.close();}}
  connectedCallback(){if(!this._built)this._build();this._watch();}
  disconnectedCallback(){this._stop();this.shadowRoot.querySelector('dialog')?.close();}
  _stop(){this._generation++;this._unsubscribe?.();this._unsubscribe=null;this._connection=null;clearInterval(this._clock);this._clock=null;}
  async _watch(){
    const hass=this._data?.hass;
    if(!this.isConnected||!this._active||!hass?.connection||this._connection===hass.connection)return;
    this._stop();this._connection=hass.connection;const generation=this._generation;
    try{
      const stop=await hass.connection.subscribeMessage(state=>{if(generation===this._generation){this._state=state;this._render();}},{type:'improved_shopping_list/catalog_sources/subscribe'});
      if(generation!==this._generation){stop();return;}this._unsubscribe=stop;
    }catch{if(generation===this._generation){this._connection=null;this._error='No se ha podido consultar el catálogo de Alcampo.';this._render();}}
  }
  _build(){
    this.shadowRoot.innerHTML=`<style>
      :host{display:block;margin-top:28px;color:var(--primary-text-color,#182b22);font-family:inherit}*{box-sizing:border-box}h3{font-size:18px;margin:0 0 16px}h4{font-size:16px;margin:0}.row{display:flex;align-items:center;gap:16px;padding:16px;border:1px solid var(--divider-color,#dce4e1);border-radius:14px;background:var(--secondary-background-color,#f4f8f6)}.row[data-enabled="true"]{background:rgba(38,112,82,.12)}.logo{width:56px;height:56px;object-fit:contain;padding:8px;background:#fff;border-radius:10px;flex:none}.name{flex:1;min-width:0}.controls{display:flex;align-items:center;gap:12px}button{border:0;background:transparent;color:inherit;cursor:pointer;padding:6px;display:grid;place-items:center}button:disabled{opacity:.5;cursor:default}ha-icon{width:24px;height:24px;--mdc-icon-size:24px}input[role="switch"]{appearance:none;width:44px;height:26px;border:0;border-radius:20px;background:#64748b;cursor:pointer;position:relative;margin:0}input[role="switch"]::after{content:'';position:absolute;left:3px;top:3px;width:20px;height:20px;border-radius:50%;background:#fff}input[role="switch"]:checked{background:#267052}input[role="switch"]:checked::after{transform:translateX(18px)}input:disabled{opacity:.5;cursor:default}dialog{color:inherit;background:var(--card-background-color,#fff);border:0;border-radius:18px;padding:28px;width:560px;max-width:calc(100vw - 24px)}dialog::backdrop{background:rgba(0,0,0,.5)}dialog h3{padding-right:30px}.track{position:relative;height:28px;background:rgba(0,0,0,.16);border-radius:16px;overflow:hidden}progress{display:block;width:100%;height:100%;border:0;appearance:none;background:transparent}progress::-webkit-progress-bar{background:transparent}progress::-webkit-progress-value{background:#198bf0;border-radius:16px}progress::-moz-progress-bar{background:#198bf0}#percentage{position:absolute;inset:0;display:grid;place-items:center;color:#fff;font-weight:700;text-shadow:0 1px 2px #222}p{font-size:13px;line-height:1.5}dialog p{text-align:center}.error{color:var(--error-color,#d32f2f)}#issues p{text-align:left}#helper{margin:8px 0 0;color:var(--secondary-text-color,#667)}@media(min-width:800px){.row{max-width:calc(50% - 6px)}}
    </style><h3>Catálogos</h3><article class="row" data-enabled="false"><img class="logo" src="https://almeria.online/wp-content/uploads/2024/09/alcampo-logo.png" alt="Logo de Alcampo" referrerpolicy="no-referrer" loading="lazy"><div class="name"><h4>Alcampo</h4></div><div class="controls"><input id="enabled" type="checkbox" role="switch" aria-label="Completar productos con Alcampo"><button id="progress" type="button" aria-label="Ver progreso de Alcampo" title="Ver progreso"><ha-icon icon="mdi:progress-clock" aria-hidden="true"></ha-icon></button></div></article><p id="helper">Completa opciones de compra por EAN con enlaces, precios y datos disponibles de Alcampo.</p><p id="error" class="error" role="alert" hidden></p><dialog aria-labelledby="catalog-progress-title"><h3 id="catalog-progress-title">Catálogo de Alcampo</h3><div class="track"><progress max="1" value="0" aria-label="Progreso del catálogo de Alcampo"></progress><span id="percentage">0 %</span></div><p id="status" role="status"></p><p id="current"></p><p id="wait"></p><div id="issues" class="error"></div></dialog>`;
    installToggleStyles(this.shadowRoot);installDialogCloseButtons(this.shadowRoot);
    this.shadowRoot.querySelector('#enabled').addEventListener('change',()=>void this._toggle());
    this.shadowRoot.querySelector('#progress').addEventListener('click',()=>this._open());
    this.shadowRoot.querySelector('dialog').addEventListener('close',()=>{clearInterval(this._clock);this._clock=null;});this._built=true;
  }
  _open(){const dialog=this.shadowRoot.querySelector('dialog');if(!dialog.open)dialog.showModal();clearInterval(this._clock);this._clock=setInterval(()=>this._render(),1000);this._render();}
  async _toggle(){
    if(this._busy||this._data?.hass?.user?.is_admin!==true)return;
    const enabled=this.shadowRoot.querySelector('#enabled').checked;
    if(enabled)this._open();this._busy=true;this._error='';this._render();
    try{this._state=await this._data.hass.callWS({type:'improved_shopping_list/catalog_sources/set',enabled});}
    catch{this._error='No se ha podido guardar la opción del catálogo de Alcampo.';}
    finally{this._busy=false;this._render();}
  }
  _render(){
    if(!this._built)return;
    const root=this.shadowRoot,s=this._state,total=s.total??0,done=s.processed??0;
    root.querySelector('#enabled').checked=Boolean(s.enabled);root.querySelector('#enabled').disabled=this._busy||this._data?.hass?.user?.is_admin!==true;
    root.querySelector('.row').dataset.enabled=String(Boolean(s.enabled));
    root.querySelector('#error').hidden=!this._error;root.querySelector('#error').textContent=this._error??'';
    const finished=s.phase==='finished',ratio=total?done/total:finished?1:0;
    root.querySelector('progress').value=ratio;root.querySelector('#percentage').textContent=Math.round(ratio*100)+' %';
    root.querySelector('#status').textContent=s.phase==='preparing'?'Buscando coincidencias por EAN…':!s.enabled?'Catálogo desactivado.':finished&&!total?'No hay nuevas coincidencias pendientes de consultar.':`${done} de ${total} EAN revisados · ${s.updated??0} productos completados${finished?' · Revisión finalizada':''}`;
    root.querySelector('#current').textContent=s.current??'';
    const seconds=Math.max(0,Math.ceil((s.phase==='paused'?s.retry_at:s.next_request??0)-Date.now()/1000));
    root.querySelector('#wait').textContent=seconds&&(s.phase==='waiting'||s.phase==='paused')?`${s.phase==='paused'?'Consultas pausadas':'Siguiente petición'}: ${Math.floor(seconds/60)} min ${seconds%60} s`:(s.running?'Las consultas continúan en Home Assistant aunque cierres este popup.':'');
    const issues=[...(s.errors??[]),...(this._error?[{message:this._error}]:[])];
    root.querySelector('#issues').replaceChildren(...issues.map(item=>{const p=document.createElement('p');p.textContent=[item.product,item.message].filter(Boolean).join(': ');return p;}));
  }
}
if(!customElements.get('isl-catalog-sources'))customElements.define('isl-catalog-sources',CatalogSourcesPanel);
