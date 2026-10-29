import { installDialogCloseButtons } from "./dialog-controls.js?v=0.48.1";
import { installToggleStyles } from "./toggle-styles.js?v=0.48.1";
export class CarrefourAccountPanel extends HTMLElement {
  get providerId(){return "carrefour";}
  get providerName(){return "Carrefour";}
  constructor(){super();this.attachShadow({mode:'open'});this._status={};this._generation=0;}
  set hass(value){this._hass=value;if(!this._built)this._build();this._render();}
  disconnectedCallback(){this.deactivate();}
  deactivate(){this._generation++;this._active=false;this._busy=false;this.shadowRoot.querySelectorAll('dialog').forEach(d=>d.close());this.shadowRoot.querySelectorAll('input').forEach(i=>i.value='');}
  async activate(){
    this._active=true;this._generation++;const generation=this._generation;this._purchases=[];this._cursor=null;this._error='';
    try{const result=await this._call('status');if(generation!==this._generation)return;this._status=result;}
    catch(error){if(generation===this._generation)this._error=error.message??'No se ha podido consultar la conexión.';}
    this._render();
  }
  _call(action,fields={}){return this._hass.callWS({type:'improved_shopping_list/'+this.providerId+'_account/'+action,...fields});}
  _build(){
    this._built=true;this.shadowRoot.innerHTML=`<style>
      :host{display:block;font:inherit;color:inherit}*{box-sizing:border-box}[hidden]{display:none!important}
      button,input,select{font:inherit;color:inherit;min-height:42px;border:1px solid var(--divider-color,#d9e0dd);border-radius:10px;padding:10px 14px;background:var(--card-background-color,#fff);min-width:0}button{cursor:pointer}button:disabled{opacity:.5;cursor:default}
      .controls,.actions{display:flex;gap:10px;flex-wrap:wrap;margin-top:16px}.actions{justify-content:flex-end}button.primary{background:var(--isl-green,#267052);color:#fff;border:0}.danger{background:#d32f2f;color:white;border:0}
      dialog{position:fixed;inset:0;border:0;border-radius:18px;background:var(--card-background-color,#fff);color:inherit;width:min(650px,calc(100vw - 24px));max-height:90vh;padding:24px;overflow:auto}dialog::backdrop{background:#0008}h2{font-size:20px;margin:0 40px 18px 0}p{font-size:14px;line-height:1.5}.note{opacity:.7}.error{color:var(--error-color,#d32f2f);overflow-wrap:anywhere}
      label{display:flex;flex-direction:column;gap:7px;margin-top:16px}input,select{width:100%}.purchase{display:flex;align-items:center;justify-content:space-between;gap:12px;border:1px solid var(--divider-color,#d9e0dd);border-radius:12px;padding:14px;margin-top:10px}.purchase-copy{min-width:0;overflow-wrap:anywhere}.purchase-copy strong,.purchase-copy span{display:block}.purchase button{flex:none}.purchase-copy span{font-size:13px;opacity:.7;margin-top:4px}
      @media(max-width:500px){dialog{padding:18px}.purchase{flex-wrap:wrap}.controls button{flex:1}}
      .account-footer{display:flex;justify-content:flex-end;align-items:center;gap:10px;flex-wrap:wrap;margin-top:24px}.account-footer #account-email{font-size:.85em;overflow-wrap:anywhere}.option-help{font-size:12px;line-height:1.5;opacity:.7;margin:5px 0 0}.password-help{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-top:8px}.password-help p{font-size:12px;opacity:.7;margin:0}.password-help button{background:transparent;border:0;min-height:32px;padding:4px 0;font-size:12px;white-space:nowrap}.remember{flex-direction:row;align-items:center}.remember input{width:18px;min-height:18px;height:18px;margin:0}.account-top{display:flex;align-items:center;justify-content:flex-end;gap:10px;flex-wrap:wrap;padding-right:30px}.account-top>strong{font-size:20px;margin-right:auto}.account-top #account-email{font-size:.85em;overflow-wrap:anywhere}.account-options{display:grid;gap:14px;margin-top:24px}.account-options label{display:flex;flex-direction:row;align-items:center;justify-content:space-between;gap:16px;margin:0}.account-options input{appearance:none;width:38px;height:22px;min-height:22px;flex:none;border:0;border-radius:20px;padding:3px;background:var(--switch-unchecked-track-color,#64748b);cursor:pointer}.account-options input:before{content:"";display:block;width:16px;height:16px;border-radius:50%;background:white;transition:transform .15s}.account-options input:checked{background:var(--isl-green,#267052)}.account-options input:checked:before{transform:translateX(16px)}.account-options input:disabled{opacity:.45;cursor:default}
    </style>
    <div class="account-top"><strong>${this.providerName}</strong></div><div class="account-options"><div><label>Recuperar compras de los últimos 12 meses<input id="history-enabled" type="checkbox" role="switch" aria-describedby="history-help"></label><p id="history-help" class="option-help">Incorpora a Analítica → Compras las fechas e importes de las compras disponibles de los últimos 12 meses. Revisar sus tickets es opcional.</p></div><div><label>Descargar ticket automáticamente<input id="auto-ticket" type="checkbox" role="switch" aria-describedby="auto-ticket-help"></label><p id="auto-ticket-help" class="option-help">Después de marcar productos como comprados, consulta ${this.providerName} como máximo una vez al día y guarda el último ticket pendiente de revisión, sin modificar stock ni precios.</p></div></div><p class="error" id="status-error" role="alert" hidden></p><div class="account-footer"><span id="account-email"></span><button id="connect" type="button" class="primary">Conectar cuenta</button></div>
    <dialog id="login-dialog" aria-labelledby="login-title"><h2 id="login-title">Conectar cuenta de ${this.providerName}</h2>
      <form id="login-form"><label>Correo<input id="username" type="email" autocomplete="username" maxlength="255" required></label><label>Contraseña<input id="password" type="password" autocomplete="current-password" maxlength="255" required></label><div id="password-help" class="password-help" hidden><p id="password-saved-status" role="status"></p><button id="change-password" type="button">Cambiar contraseña</button></div><label class="remember"><input id="remember-credentials" type="checkbox">Recordar credenciales</label><div class="actions"><button class="primary" type="submit">Conectar</button></div></form>
      <section id="verification" hidden><p>${this.providerName} solicita una verificación adicional.</p><label>Enviar código a<select id="destination"></select></label><div class="actions"><button id="send-code" type="button">Enviar código</button></div><form id="verify-form" hidden><label>Código de verificación<input id="code" type="text" inputmode="numeric" autocomplete="one-time-code" pattern="[0-9]{4,10}" maxlength="10" required></label><div class="actions"><button class="primary" type="submit">Verificar</button></div></form></section>
      <p id="login-error" class="error" role="alert" hidden></p><p id="login-status" role="status"></p>
    </dialog>
`;
    const r=this.shadowRoot;installDialogCloseButtons(r);installToggleStyles(r);
    r.querySelectorAll('dialog').forEach(d=>d.addEventListener('cancel',e=>{if(this._busy)e.preventDefault();}));
    r.querySelector('#login-dialog').addEventListener('close',()=>{r.querySelector('#password').value='';r.querySelector('#code').value='';});
    r.querySelector('#connect').addEventListener('click',()=>{if(this._status.connected){void this._action('disconnect');return;}this._error='';this._editingPassword=false;r.querySelector('#username').value=this._status.remembered_email||'';r.querySelector('#password').value='';r.querySelector('#remember-credentials').checked=Boolean(this._status.credentials_saved);this._credentialFields();this._render();r.querySelector('#login-dialog').showModal();});
    for(const [id,key] of [['history-enabled','history_enabled'],['auto-ticket','auto_ticket']])r.querySelector('#'+id).addEventListener('change',()=>void this._action('options',{options:{history_enabled:false,auto_ticket:false,...this._status.options,[key]:r.querySelector('#'+id).checked}}));
    r.querySelector('#change-password').addEventListener('click',()=>{this._editingPassword=!this._editingPassword;r.querySelector('#password').value='';this._credentialFields();if(this._editingPassword)r.querySelector('#password').focus();});
    for(const id of ['username','remember-credentials'])r.querySelector('#'+id).addEventListener('input',()=>this._credentialFields());
    r.querySelector('#login-form').addEventListener('submit',e=>{e.preventDefault();const username=r.querySelector('#username').value,password=r.querySelector('#password').value;r.querySelector('#password').value='';void this._action('login',{username,password,remember_credentials:r.querySelector('#remember-credentials').checked});});
    r.querySelector('#send-code').addEventListener('click',()=>void this._action('send_code',{destination:r.querySelector('#destination').value}));
    r.querySelector('#verify-form').addEventListener('submit',e=>{e.preventDefault();const code=r.querySelector('#code').value;r.querySelector('#code').value='';void this._action('verify',{code});});
  }
  _credentialFields(){
    const r=this.shadowRoot,s=this._status,remember=r.querySelector('#remember-credentials').checked;
    const available=Boolean(remember&&s.credentials_saved&&r.querySelector('#username').value.trim()===s.remembered_email);
    const saved=available&&!this._editingPassword,password=r.querySelector('#password');
    password.required=!saved;password.readOnly=saved;password.placeholder=saved?'••••••••':'';
    password.setAttribute('aria-describedby','password-saved-status');
    r.querySelector('#password-help').hidden=!available;
    r.querySelector('#password-saved-status').textContent=saved?'Contraseña guardada. Se usará al conectar.':available?'Introduce la nueva contraseña.':'';
    r.querySelector('#change-password').textContent=saved?'Cambiar contraseña':'Usar contraseña guardada';
  }
  async _action(action,fields){
    if(this._busy)return;const generation=this._generation;this._busy=true;this._error='';this._render();
    try{const status=await this._call(action,fields);if(generation!==this._generation)return;this._status=status;if(action==='disconnect'){this._purchases=[];this.shadowRoot.querySelector('#login-dialog').close();}}
    catch(error){if(generation===this._generation)this._error=error.message??'No se ha podido conectar con '+this.providerName+'.';}
    finally{if(generation===this._generation){this._busy=false;this._render();}}
  }
  _render(){
    if(!this._built)return;const r=this.shadowRoot,s=this._status,locked=this._busy||this._hass?.user?.is_admin!==true;
    this._credentialFields();
    r.querySelectorAll('button,input,select').forEach(el=>el.disabled=locked);r.querySelector('#connect').textContent=s.connected?'Desconectar cuenta':'Conectar cuenta';r.querySelector('#connect').className=s.connected?'danger':'primary';r.querySelector('#account-email').textContent=s.connected?(s.email||''):'';for(const [id,key] of [['history-enabled','history_enabled'],['auto-ticket','auto_ticket']]){const input=r.querySelector('#'+id);input.checked=Boolean(s.options?.[key]);input.disabled=locked||!s.connected;}
    r.querySelector('#login-form').hidden=Boolean(s.connected||s.verification_required);r.querySelector('#verification').hidden=!s.verification_required;r.querySelector('#verify-form').hidden=!s.verification_sent;
    const destination=r.querySelector('#destination'),old=destination.value;destination.replaceChildren(...(s.destinations??[]).map(item=>new Option(item.label,item.id)));if([...destination.options].some(o=>o.value===old))destination.value=old;
    r.querySelector('#login-status').textContent=this._syncing?'Incorporando el historial de los últimos 12 meses…':this._busy?'Conectando con '+this.providerName+'…':s.connected?'Cuenta conectada. Puedes revisar sus tickets en Analítica → Compras.':s.verification_sent?'Código solicitado. Introduce el código recibido.':'';
    for(const id of ['status-error','login-error']){r.querySelector('#'+id).textContent=this._error||'';r.querySelector('#'+id).hidden=!this._error;}
  }
}
if(!customElements.get('isl-carrefour-account'))customElements.define('isl-carrefour-account',CarrefourAccountPanel);
