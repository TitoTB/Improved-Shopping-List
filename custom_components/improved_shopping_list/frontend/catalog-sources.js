import { installDialogCloseButtons } from './dialog-controls.js?v=0.73.1';
import { installToggleStyles } from './toggle-styles.js?v=0.73.1';

class CatalogSourcesPanel extends HTMLElement {
  constructor(){super();this.attachShadow({mode:'open'});this._state={enabled:false,phase:'idle',total:0,processed:0,errors:[]};this._generation=0;this._stateVersion=0;this._pollGeneration=0;}
  set data(value){this._data=value;if(!this._built)this._build();this._render();this._watch();}
  set active(value){this._active=Boolean(value);if(this._active){this._watch();}else{this._stop();this.shadowRoot.querySelectorAll('dialog').forEach(dialog=>dialog.close());}for(const child of this.shadowRoot.querySelectorAll('.catalog-grid > :not(.row)'))child.active=this._active;}
  connectedCallback(){if(!this._built)this._build();this._watch();}
  disconnectedCallback(){this._stop();this.shadowRoot.querySelectorAll('dialog').forEach(dialog=>dialog.close());}
  _stop(){this._stopProgressPolling();this._generation++;this._unsubscribe?.();this._unsubscribe=null;this._connection=null;}
  async _watch(){
    const hass=this._data?.hass;
    if(!this.isConnected||!this._active||!hass?.connection||this._connection===hass.connection)return;
    this._stop();this._connection=hass.connection;const generation=this._generation;
    try{
      const stop=await hass.connection.subscribeMessage(state=>{if(generation===this._generation){this._receive(state);}},{type:'improved_shopping_list/catalog_sources/subscribe',source:this._source??'alcampo'});
      if(generation!==this._generation){stop();return;}this._unsubscribe=stop;
    }catch{if(generation===this._generation){this._connection=null;this._error='No se ha podido consultar este catálogo.';this._render();}}
  }
  _receive(state){
    if(!state||typeof state!=='object')return;
    this._stateVersion++;this._state=state;this._progressError='';this._render();
  }
  _stopProgressPolling(){clearTimeout(this._pollTimer);this._pollTimer=null;this._pollGeneration++;}
  _syncProgressPolling(){
    const open=this.shadowRoot.querySelector('#catalog-progress-dialog')?.open;
    if(!this.isConnected||!this._active||!open||!this._data?.hass||(!this._state.enabled&&!this._busy)||this._state.phase==='finished'||this._state.phase==='error'){
      this._stopProgressPolling();return;
    }
    if(this._pollTimer||this._pollPending)return;
    this._pollTimer=setTimeout(()=>{this._pollTimer=null;void this._refreshProgress();},this._state.phase==='paused'?10000:2000);
  }
  async _refreshProgress(){
    if(this._pollPending)return;
    const generation=this._pollGeneration,version=this._stateVersion;
    this._pollPending=true;
    try{
      const state=await this._data.hass.callWS({type:'improved_shopping_list/catalog_sources/status',source:this._source??'alcampo'});
      if(generation===this._pollGeneration&&this.shadowRoot.querySelector('#catalog-progress-dialog')?.open&&version===this._stateVersion)this._receive(state);
    }catch{
      if(generation===this._pollGeneration&&this.shadowRoot.querySelector('#catalog-progress-dialog')?.open){this._progressError='No se ha podido actualizar el progreso. Reintentando…';this._render();}
    }finally{this._pollPending=false;this._syncProgressPolling();}
  }
  _build(){
    this.shadowRoot.innerHTML=`<style>
      :host{display:block;margin-top:28px;color:var(--primary-text-color,#182b22);font-family:inherit}*{box-sizing:border-box}h3{font-size:18px;margin:0 0 16px}h4{font-size:16px;margin:0}.row{display:flex;align-items:center;gap:16px;padding:16px;border:1px solid var(--divider-color,#dce4e1);border-radius:14px;background:var(--secondary-background-color,#f4f8f6);min-width:0;height:100%}.catalog-grid{display:grid;grid-template-columns:minmax(0,1fr);gap:12px}.catalog-grid > :not(.row){margin-top:0;min-width:0}.row[data-enabled="true"]{background:rgba(38,112,82,.12)}.logo{width:56px;height:56px;object-fit:contain;padding:8px;background:#fff;border-radius:10px;flex:none}.name{flex:1;min-width:0}.controls{display:flex;align-items:center;gap:12px}button{border:0;background:transparent;color:inherit;cursor:pointer;padding:6px;display:grid;place-items:center}button:disabled{opacity:.5;cursor:default}ha-icon{width:24px;height:24px;--mdc-icon-size:24px}input[role="switch"]{appearance:none;width:44px;height:26px;border:0;border-radius:20px;background:#64748b;cursor:pointer;position:relative;margin:0}input[role="switch"]::after{content:'';position:absolute;left:3px;top:3px;width:20px;height:20px;border-radius:50%;background:#fff}input[role="switch"]:checked{background:#267052}input[role="switch"]:checked::after{transform:translateX(18px)}input:disabled{opacity:.5;cursor:default}dialog{color:inherit;background:var(--card-background-color,#fff);border:0;border-radius:18px;padding:28px;width:560px;max-width:calc(100vw - 24px)}dialog::backdrop{background:rgba(0,0,0,.5)}dialog h3{padding-right:30px}.option-setting{display:flex;align-items:center;justify-content:space-between;gap:20px;margin-top:20px}.track[data-indeterminate=true]::before{content:"";position:absolute;inset-block:0;width:35%;border-radius:16px;background:#198bf0;animation:catalog-working 1.4s ease-in-out infinite alternate}@keyframes catalog-working{from{left:0}to{left:65%}}.track{position:relative;height:28px;background:rgba(0,0,0,.16);border-radius:16px;overflow:hidden}progress{display:block;width:100%;height:100%;border:0;appearance:none;background:transparent}progress::-webkit-progress-bar{background:transparent}progress::-webkit-progress-value{background:#198bf0;border-radius:16px}progress::-moz-progress-bar{background:#198bf0}#percentage{position:absolute;inset:0;display:grid;place-items:center;color:#fff;font-weight:700;text-shadow:0 1px 2px #222}p{font-size:13px;line-height:1.5}dialog p{text-align:center}.error{color:var(--error-color,#d32f2f)}#issues p{text-align:left}@media(min-width:800px){.catalog-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
    </style><h3>Catálogos</h3><article class="row" data-enabled="false"><img class="logo" src="https://almeria.online/wp-content/uploads/2024/09/alcampo-logo.png" alt="Logo de Alcampo" referrerpolicy="no-referrer" loading="lazy"><div class="name"><h4>Alcampo</h4></div><div class="controls"><input id="enabled" type="checkbox" role="switch" aria-label="Completar productos con Alcampo"><button id="configure" type="button" aria-label="Configurar catálogo de Alcampo" title="Configurar catálogo de Alcampo"><ha-icon icon="mdi:cog" aria-hidden="true"></ha-icon></button></div></article><p id="error" class="error" role="alert" hidden></p><dialog id="catalog-progress-dialog" aria-labelledby="catalog-progress-title"><h3 id="catalog-progress-title">Catálogo de Alcampo</h3><div class="track"><progress max="1" value="0" aria-label="Progreso del catálogo de Alcampo"></progress><span id="percentage">0 %</span></div><p id="status" role="status"></p><p id="current"></p><div id="issues" class="error"></div></dialog><dialog id="catalog-options-dialog" aria-labelledby="catalog-options-title"><h3 id="catalog-options-title">Catálogo de Alcampo</h3><label class="option-setting"><span>Mostrar tienda en el catálogo</span><input id="show-store" type="checkbox" role="switch" aria-label="Mostrar tienda en el catálogo"></label><p id="options-error" class="error" role="alert" hidden></p></dialog>`;
    if(['masymas','bm','consum','lasirena','eroski'].includes(this._source)){
      const name={masymas:'Masymas',bm:'BM',consum:'Consum',lasirena:'La Sirena',eroski:'Eroski'}[this._source];
      this.shadowRoot.innerHTML=this.shadowRoot.innerHTML.replaceAll('Alcampo',name).replace('<h3>Catálogos</h3>','').replace('https://almeria.online/wp-content/uploads/2024/09/alcampo-logo.png',new URL(this._source+(this._source==='eroski'?'.svg':['consum','lasirena'].includes(this._source)?'.jpg':'.png'),import.meta.url).href);
    }else if(this._source==='mercadona'){
      this.shadowRoot.innerHTML=this.shadowRoot.innerHTML.replaceAll('Alcampo','Mercadona').replace('<h3>Catálogos</h3>','').replace('https://almeria.online/wp-content/uploads/2024/09/alcampo-logo.png',new URL('mercadona.png',import.meta.url).href);
    }else if(this._source==='elcorteingles'){
      this.shadowRoot.innerHTML=this.shadowRoot.innerHTML.replaceAll('Alcampo','El Corte Inglés').replace('<h3>Catálogos</h3>','').replace('https://almeria.online/wp-content/uploads/2024/09/alcampo-logo.png','https://img.samsungapps.com/productNew/000005314762/SPA/IconImage_20241028224125253_NEW_WAP_ICON_512_512.png');
    }else{
      const grid=document.createElement('div');grid.className='catalog-grid';
      const row=this.shadowRoot.querySelector('.row');row.before(grid);grid.append(row,...['mercadona','masymas','bm','consum','lasirena','eroski'].map(store=>document.createElement(`isl-${store}-catalog`)));
    }
    installToggleStyles(this.shadowRoot);installDialogCloseButtons(this.shadowRoot);
    this.shadowRoot.querySelector('#catalog-progress-dialog').addEventListener('close',()=>this._stopProgressPolling());
    this.shadowRoot.querySelector('#enabled').addEventListener('change',()=>void this._toggle());
    this.shadowRoot.querySelector('#configure').addEventListener('click',()=>{this._optionsError='';this._render();this.shadowRoot.querySelector('#catalog-options-dialog').showModal();});
    this.shadowRoot.querySelector('#show-store').addEventListener('change',()=>void this._toggleVisibility());
    this._built=true;
  }
  _open(){const dialog=this.shadowRoot.querySelector('#catalog-progress-dialog');if(!dialog.open)dialog.showModal();this._render();}
  async _toggle(){
    if(this._busy||this._data?.hass?.user?.is_admin!==true)return;
    const enabled=this.shadowRoot.querySelector('#enabled').checked;
    this._pendingEnabled=enabled;this._busy=true;this._error='';if(enabled)this._open();this._render();
    const version=this._stateVersion,generation=this._generation;
    try{const state=await this._data.hass.callWS({type:'improved_shopping_list/catalog_sources/set',enabled,source:this._source??'alcampo'});if(version===this._stateVersion&&generation===this._generation)this._receive(state);}
    catch{this._error='No se ha podido guardar la opción del catálogo.';}
    finally{this._busy=false;delete this._pendingEnabled;this._render();}
  }
  async _toggleVisibility(){
    if(this._settingsBusy||this._data?.hass?.user?.is_admin!==true)return;
    const show_store=this.shadowRoot.querySelector('#show-store').checked;
    this._pendingShowStore=show_store;this._settingsBusy=true;this._optionsError='';this._render();
    const version=this._stateVersion,generation=this._generation;
    try{const state=await this._data.hass.callWS({type:'improved_shopping_list/catalog_sources/visibility',show_store,source:this._source??'alcampo'});if(version===this._stateVersion&&generation===this._generation)this._receive(state);}
    catch{this._optionsError='No se ha podido guardar la visibilidad de la tienda.';}
    finally{this._settingsBusy=false;delete this._pendingShowStore;this._render();}
  }
  _render(){
    if(!this._built)return;
    for(const child of this.shadowRoot.querySelectorAll('.catalog-grid > :not(.row)')){child.data=this._data;child.active=this._active;}
    const root=this.shadowRoot,s=this._state,total=s.total??0,done=s.processed??0;
    root.querySelector('#enabled').checked=Boolean(this._pendingEnabled??s.enabled);root.querySelector('#enabled').disabled=this._busy||this._data?.hass?.user?.is_admin!==true;
    root.querySelector('#configure').disabled=this._data?.hass?.user?.is_admin!==true;
    root.querySelector('#show-store').checked=Boolean(this._pendingShowStore??s.show_store);root.querySelector('#show-store').disabled=this._settingsBusy||this._data?.hass?.user?.is_admin!==true;
    root.querySelector('#options-error').hidden=!this._optionsError;root.querySelector('#options-error').textContent=this._optionsError??'';
    root.querySelector('.row').dataset.enabled=String(Boolean(s.enabled));
    root.querySelector('#error').hidden=!this._error;root.querySelector('#error').textContent=this._error??'';
    const finished=s.phase==='finished',ratio=total?done/total:finished?1:0,unknown=!total&&!finished&&!['paused','error'].includes(s.phase)&&(s.enabled||this._pendingEnabled);
    root.querySelector('.track').dataset.indeterminate=String(Boolean(unknown));
    if(unknown)root.querySelector('progress').removeAttribute('value');else root.querySelector('progress').value=ratio;
    root.querySelector('#percentage').textContent=unknown?'…':Math.round(ratio*100)+' %';
    root.querySelector('#status').textContent=s.phase==='paused'?'Revisión en pausa temporal.':unknown?'Preparando revisión…':!s.enabled?'Catálogo desactivado.':finished&&!total?(s.updated?`${s.updated} productos completados`:'No hay nuevas coincidencias pendientes de consultar.'):`${done} de ${total} EAN revisados · ${s.updated??0} productos completados${finished?' · Revisión finalizada':''}`;
    if(s.phase==='error')root.querySelector('#status').textContent='No se ha podido completar la revisión.';
    if(finished&&!total&&s.ean_summary){
      const {catalog_eans:codes,matched_eans:matched}=s.ean_summary;
      root.querySelector('#status').textContent=!codes?'No hay códigos EAN válidos en tu catálogo.':matched===0?`No hay coincidencias exactas para los ${codes} EAN de tu catálogo.`:s.updated?`${s.updated} productos completados · ${matched} EAN coincidentes.`:`${matched} EAN coincidentes. No hay cambios pendientes para esas coincidencias.`;
    }
    root.querySelector('#current').textContent=s.current??'';
    const issues=[...(s.errors??[]),...(this._error?[{message:this._error}]:[]),...(this._progressError?[{message:this._progressError}]:[])];
    root.querySelector('#issues').replaceChildren(...issues.map(item=>{const p=document.createElement('p');p.textContent=[item.product,item.message].filter(Boolean).join(': ');return p;}));
    this._syncProgressPolling();
  }
}

for(const store of ['masymas','bm','consum','lasirena','eroski']){
  if(!customElements.get(`isl-${store}-catalog`))customElements.define(`isl-${store}-catalog`,class extends CatalogSourcesPanel{constructor(){super();this._source=store;}});
}

class MercadonaCatalogPanel extends CatalogSourcesPanel { constructor(){super();this._source='mercadona';} }
if(!customElements.get('isl-mercadona-catalog'))customElements.define('isl-mercadona-catalog',MercadonaCatalogPanel);

class ECICatalogPanel extends CatalogSourcesPanel { constructor(){super();this._source='elcorteingles';} }
if(!customElements.get('isl-eci-catalog'))customElements.define('isl-eci-catalog',ECICatalogPanel);

if(!customElements.get('isl-catalog-sources'))customElements.define('isl-catalog-sources',CatalogSourcesPanel);
