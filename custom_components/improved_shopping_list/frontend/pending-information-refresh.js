import { installDialogCloseButtons } from './dialog-controls.js?v=0.64.0';
const PREFIX='improved_shopping_list/catalog/refresh_pending/';

class PendingInformationRefresh extends HTMLElement {
  constructor(){super();this.attachShadow({mode:'open'});this._state={phase:'idle',running:false,total:0,processed:0};this._generation=0;this._version=0;}
  set data(value){
    this._data=value;if(!this._built)this._build();
    if(!value?.active){this._stop();this.shadowRoot.querySelector('dialog').close();}
    else if(this._connection!==value.hass?.connection){this._stop();this._connection=value.hass?.connection;void this._read();}
    this._render();
  }
  disconnectedCallback(){this._stop();this.shadowRoot.querySelector('dialog')?.close();}
  _stop(){this._generation++;clearTimeout(this._timer);this._timer=null;this._connection=null;}
  _build(){
    this.shadowRoot.innerHTML=`<style>
      :host{display:inline-flex;margin-left:auto;font:inherit;color:inherit}*{box-sizing:border-box}button{font:inherit;border:0;border-radius:10px;padding:9px 12px;color:#fff;background:#198bf0;display:inline-flex;align-items:center;gap:7px;cursor:pointer;white-space:nowrap;font-size:13px}button:disabled{opacity:.5;cursor:default}ha-icon{width:19px;height:19px;--mdc-icon-size:19px}dialog{font:inherit;color:var(--primary-text-color,#182b22);background:var(--card-background-color,#fff);border:0;border-radius:18px;padding:28px;width:560px;max-width:calc(100vw - 24px)}dialog::backdrop{background:rgba(0,0,0,.5)}h3{margin:0 32px 20px 0;font-size:20px}p{text-align:center;font-size:13px;font-weight:400;line-height:1.5}.track{height:28px;border-radius:16px;overflow:hidden;position:relative;background:rgba(0,0,0,.16)}progress{display:block;width:100%;height:100%;border:0;appearance:none;background:transparent}progress::-webkit-progress-bar{background:transparent}progress::-webkit-progress-value{background:#198bf0;border-radius:16px}progress::-moz-progress-bar{background:#198bf0}#percentage{position:absolute;inset:0;display:grid;place-items:center;color:white;font-weight:700}#errors{color:var(--error-color,#d32f2f);font-size:13px;font-weight:400}#error{color:var(--error-color,#d32f2f)}@media(max-width:520px){button{padding:8px;font-size:12px}h3{font-size:18px}dialog{padding:22px}}
    </style><button id="start" type="button"><ha-icon icon="mdi:refresh" aria-hidden="true"></ha-icon>Recuperar datos</button><dialog aria-labelledby="pending-refresh-title"><h3 id="pending-refresh-title">Recuperación de datos</h3><div class="track"><progress max="1" value="0" aria-label="Progreso de recuperación de datos"></progress><span id="percentage">0 %</span></div><p id="status" role="status"></p><p id="current"></p><p id="error" role="alert" hidden></p><ul id="errors"></ul></dialog>`;
    installDialogCloseButtons(this.shadowRoot);
    this.shadowRoot.addEventListener('click',event=>{event.stopPropagation();event.preventDefault();});
    this.shadowRoot.querySelector('#start').addEventListener('click',()=>void this._open());
    this.shadowRoot.querySelector('dialog').addEventListener('close',()=>{clearTimeout(this._timer);this._timer=null;});
    this._built=true;
  }
  async _read(){
    if(this._reading||!this._data?.active)return;
    const generation=this._generation,version=this._version;this._reading=true;
    try{const state=await this._data.hass.callWS({type:PREFIX+'status'});if(generation===this._generation&&version===this._version){this._state=state;this._error='';this._render();}}
    catch{if(generation===this._generation){this._error='No se ha podido consultar el progreso. Reintentando…';this._render();}}
    finally{this._reading=false;if(this._data?.active&&this.shadowRoot.querySelector('dialog').open&&this._state.running)this._timer=setTimeout(()=>void this._read(),2000);}
  }
  async _open(){
    if(this._busy)return;
    const dialog=this.shadowRoot.querySelector('dialog');if(!dialog.open)dialog.showModal();
    this._busy=true;this._error='';this._version++;const generation=this._generation;this._render();
    try{const state=await this._data.hass.callWS({type:PREFIX+'start'});if(generation===this._generation){this._state=state;this._render();}}
    catch(error){this._error=error.message||'No se ha podido iniciar la recuperación.';}
    finally{this._busy=false;this._render();if(this._data?.active&&dialog.open&&this._state.running&&!this._timer)this._timer=setTimeout(()=>void this._read(),2000);}
  }
  _render(){
    if(!this._built)return;
    const root=this.shadowRoot,s=this._state,total=s.total??0,done=s.processed??0,updated=s.updated_products?.length??0;
    root.querySelector('#start').disabled=this._busy||this._data?.hass?.user?.is_admin!==true||!this._data?.eligible&&!s.running;
    const ratio=total?Math.min(1,done/total):s.phase==='finished'?1:0;
    root.querySelector('progress').value=ratio;root.querySelector('#percentage').textContent=Math.round(ratio*100)+' %';
    root.querySelector('#status').textContent=s.phase==='finished'?`Revisión finalizada · ${updated} producto${updated===1?'':'s'} actualizado${updated===1?'':'s'}${s.skipped?` · ${s.skipped} alternativas omitidas`:''}`:this._busy&&!s.running?'Preparando recuperación…':`${done} de ${total} alternativas revisadas`;
    root.querySelector('#current').textContent=s.current??'';
    root.querySelector('#error').hidden=!this._error;root.querySelector('#error').textContent=this._error??'';
    root.querySelector('#errors').replaceChildren(...(s.errors??[]).map(error=>{const row=document.createElement('li');row.textContent=[error.product,error.message].filter(Boolean).join(': ');return row;}));
  }
}
if(!customElements.get('isl-pending-information-refresh'))customElements.define('isl-pending-information-refresh',PendingInformationRefresh);
