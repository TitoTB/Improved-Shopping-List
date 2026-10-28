import { CarrefourAccountPanel } from './carrefour-account.js?v=0.43.0';

// Only the matching native callback is submitted; a selected HAR stays in this browser.
export function callbackFromHar(har, state) {
  const entries=har?.log?.entries;
  if(!Array.isArray(entries))throw new Error('No se reconoce el archivo HAR.');
  for(const entry of [...entries].reverse()){
    const candidates=[entry.request?.url,...(entry.response?.headers??[]).filter(h=>h.name?.toLowerCase()==='location').map(h=>h.value)];
    for(const value of candidates){
      try{const url=new URL(value);if(url.protocol==='com.lidlplus.app:'&&url.host==='callback'&&url.searchParams.get('state')===state&&url.searchParams.has('code'))return url.href;}catch{}
    }
  }
  throw new Error('El archivo no contiene el retorno de esta conexión. Inicia sesión desde el enlace de este popup y exporta ese registro.');
}

class LidlAccountPanel extends CarrefourAccountPanel {
  get providerId(){return 'lidl';}
  get providerName(){return 'Lidl';}
  _build(){
    super._build();const r=this.shadowRoot;
    r.querySelector('#login-form').hidden=true;r.querySelector('#verification').hidden=true;
    const login=r.querySelector('#login-dialog'),section=document.createElement('section');section.id='oauth';
    section.innerHTML=`<p>Inicia sesión en la página oficial de Lidl. Home Assistant guardará una sesión renovable; no necesita tu contraseña.</p><p class="note">Lidl devuelve el acceso a su aplicación móvil. Si el navegador queda en blanco, copia la dirección que empieza por <code>com.lidlplus.app://callback</code> desde Red/Network → respuesta de autorización → Location. También puedes seleccionar el archivo HAR de ese acceso: se leerá solo en este navegador.</p><p><a id="oauth-link" target="_blank" rel="noopener noreferrer" hidden>Abrir acceso de Lidl</a></p><form id="oauth-form"><label>Dirección de retorno<input id="oauth-callback" type="text" autocomplete="off" spellcheck="false" maxlength="20000" required></label><label>O seleccionar el HAR de este acceso<input id="oauth-har" type="file" accept=".har,.json,application/json"></label><div class="actions"><button class="primary" type="submit">Completar conexión</button></div></form>`;
    login.querySelector('#login-form').before(section);
    const connect=r.querySelector('#connect'),replacement=connect.cloneNode(true);connect.replaceWith(replacement);
    replacement.onclick=()=>{if(this._status.connected){void this._action('disconnect');return;}void this._begin();};
    r.querySelector('#oauth-form').onsubmit=event=>{event.preventDefault();const callback=r.querySelector('#oauth-callback').value;r.querySelector('#oauth-callback').value='';void this._action('finish',{callback});};
    r.querySelector('#oauth-har').onchange=async event=>{
      const file=event.target.files?.[0];event.target.value='';if(!file)return;
      try{if(file.size>25*1024*1024)throw new Error('El HAR debe ocupar menos de 25 MB.');const callback=callbackFromHar(JSON.parse(await file.text()),this._oauthState);await this._action('finish',{callback});}
      catch(error){this._error=error.message;this._render();}
    };
    login.addEventListener('close',()=>{r.querySelector('#oauth-callback').value='';r.querySelector('#oauth-link').removeAttribute('href');this._oauthState='';});
  }
  async _begin(){
    if(this._busy)return;
    const tab=window.open('about:blank','_blank');if(tab)tab.opener=null;
    const generation=this._generation;this._busy=true;this._error='';this._render();
    const r=this.shadowRoot;r.querySelector('#login-dialog').showModal();
    try{
      const result=await this._call('begin');if(generation!==this._generation){tab?.close();return;}
      const url=new URL(result.authorization_url);
      if(url.protocol!=='https:'||url.hostname!=='accounts.lidl.com'||url.pathname!=='/connect/authorize')throw new Error('Dirección de autorización no válida.');
      this._oauthState=url.searchParams.get('state');const link=r.querySelector('#oauth-link');link.href=url.href;link.hidden=false;
      if(tab)tab.location.href=url.href;
    }catch(error){tab?.close();if(generation===this._generation)this._error=error.message;}
    finally{if(generation===this._generation){this._busy=false;this._render();}}
  }
  async _action(action,fields){await super._action(action,fields);if(action==='finish'&&this._status.connected)this.shadowRoot.querySelector('#login-dialog').close();}
  _render(){
    if(!this._built)return;
    const r=this.shadowRoot,s=this._status,locked=this._busy||this._hass?.user?.is_admin!==true;
    r.querySelectorAll('button,input,select').forEach(el=>el.disabled=locked);
    r.querySelector('#connect').textContent=s.connected?'Desconectar cuenta':'Conectar cuenta';r.querySelector('#connect').className=s.connected?'danger':'primary';
    r.querySelector('#account-email').textContent=s.connected?(s.email||'Cuenta Lidl conectada'):'';
    for(const [id,key] of [['history-enabled','history_enabled'],['auto-ticket','auto_ticket']]){const input=r.querySelector('#'+id);input.checked=Boolean(s.options?.[key]);input.disabled=locked||!s.connected;}
    r.querySelector('#login-form').hidden=true;r.querySelector('#verification').hidden=true;
    r.querySelector('#login-status').textContent=this._busy?'Consultando Lidl…':s.connected?'Cuenta conectada. Puedes revisar sus tickets en Analítica → Compras.':'';
    for(const id of ['status-error','login-error']){r.querySelector('#'+id).textContent=this._error||'';r.querySelector('#'+id).hidden=!this._error;}
  }
}
if(!customElements.get('isl-lidl-account'))customElements.define('isl-lidl-account',LidlAccountPanel);
