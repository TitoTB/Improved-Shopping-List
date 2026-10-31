import { CarrefourAccountPanel } from './carrefour-account.js?v=0.67.0';

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
    section.innerHTML=`<style>
      .wizard-steps{display:flex;gap:8px;margin:0 0 20px;padding:0;list-style:none}.wizard-steps li{flex:1;padding:8px;border-radius:10px;font-size:12px;background:var(--secondary-background-color,#64748b22)}.wizard-steps li[aria-current="step"]{background:#168aec;color:white}.wizard-steps li.done{background:var(--isl-green,#267052);color:white}
      #oauth h3{font-size:16px;margin:18px 0 10px}#oauth ol.instructions{padding-left:22px}#oauth li{line-height:1.5;margin-bottom:10px}#oauth code{overflow-wrap:anywhere}#oauth details{margin-top:16px}#oauth summary{cursor:pointer}#oauth-link{display:inline-block;padding:12px 16px;border-radius:10px;background:var(--isl-green,#267052);color:white;text-decoration:none}#oauth-form{margin-top:18px}.wizard-back{margin-right:auto}#oauth-progress{font-size:13px;opacity:.75}
    </style>
    <ol class="wizard-steps" aria-label="Pasos de conexión"><li data-step-label="1">1. Preparar</li><li data-step-label="2">2. Acceder</li><li data-step-label="3">3. Conectar</li></ol>
    <section data-step="1"><h3>Prepara el navegador</h3><p>Haz esta conexión desde un ordenador. Solo tendrás que repetirla si Lidl requiere volver a autorizar la cuenta.</p><ol class="instructions"><li>Abre Lidl con el botón de abajo.</li><li>En la pestaña de Lidl, <strong>antes de iniciar sesión</strong>, abre las <strong>herramientas para desarrolladores</strong> desde el menú del navegador:<ul><li><strong>Chrome:</strong> ⋮ → Más herramientas → Herramientas para desarrolladores.</li><li><strong>Edge:</strong> ⋯ → Más herramientas → Herramientas de desarrollo.</li><li><strong>Firefox:</strong> ☰ → Más herramientas → Herramientas del navegador.</li></ul>También puedes pulsar <strong>F12</strong> (o Ctrl + Mayús + I; en Mac, ⌘ + ⌥ + I).</li><li>Selecciona <strong>Red / Network</strong> y activa <strong>Conservar registro / Preserve log</strong>. Mantén estas herramientas abiertas durante el acceso.</li></ol><p><a id="oauth-link" target="_blank" rel="noopener noreferrer" hidden>Abrir acceso de Lidl</a></p><p class="note">Si la pestaña no se abre, permite las ventanas emergentes o vuelve a pulsar el enlace. Después regresa a Home Assistant para continuar.</p><div class="actions"><button type="button" data-next="2" class="primary">Ya he preparado el navegador</button></div></section>
    <section data-step="2" hidden><h3>Inicia sesión en Lidl</h3><ol class="instructions"><li>Vuelve a la pestaña de Lidl e introduce tu correo y contraseña únicamente en su página oficial.</li><li>Completa la verificación si Lidl la solicita.</li><li>Después puede aparecer una página en blanco, un error o un aviso para abrir la aplicación. <strong>Puede ser el retorno a la aplicación móvil</strong>; el siguiente paso permite comprobarlo.</li></ol><p class="note">Si vuelve a pedirte las credenciales o muestra un error antes de terminar el acceso, todavía no se ha completado la autorización.</p><div class="actions"><button type="button" class="wizard-back" data-back="1">Volver</button><button type="button" data-next="3" class="primary">Ya he iniciado sesión</button></div></section>
    <section data-step="3" hidden><h3>Exporta y selecciona el archivo HAR</h3><ol class="instructions"><li>Vuelve a <strong>Red / Network</strong> en la pestaña de Lidl. Borra cualquier texto del filtro y selecciona <strong>Todo / All</strong> para incluir el acceso completo.</li><li>En <strong>Chrome o Edge</strong>, pulsa el icono de descarga <strong>Exportar HAR / Export HAR</strong> de la barra superior. Si aparece la opción <strong>sanitizado / sanitized</strong>, puedes utilizarla.</li><li>En <strong>Firefox</strong>, haz clic derecho sobre una petición y elige <strong>Guardar todo como HAR / Save All As HAR</strong>. También puede aparecer en el menú de acciones de Red.</li><li>Guarda el archivo <strong>.har</strong> en tu ordenador. Regresa aquí y selecciónalo debajo: la conexión se completará automáticamente si contiene la autorización de este intento.</li></ol>
    <div id="oauth-form"><label>Seleccionar archivo HAR de Lidl<input id="oauth-har" type="file" accept=".har,.json,application/json"></label><p class="note">El archivo se lee solo en este navegador. Solo se envía a Home Assistant la autorización correspondiente a esta conexión.</p><div class="actions"><button type="button" class="wizard-back" data-back="2">Volver</button></div></div>
    <details><summary>No encuentro cómo guardar el archivo</summary><p>Comprueba que estás en Red / Network, en la pestaña de Lidl. Amplía las herramientas si no ves los iconos de la barra. En Chrome y Edge también puedes hacer clic derecho sobre una petición y buscar <strong>Copiar / Copy → Guardar todo como HAR / Save all as HAR</strong>. Guarda el archivo completo, no una sola petición.</p></details><p class="note">Si el archivo no contiene la autorización, ha caducado o pertenece a otro intento, pulsa Reiniciar conexión y repite los pasos con un archivo nuevo. Selecciónalo aquí en cuanto lo guardes.</p></section>
    <p id="oauth-progress" role="status"></p><div class="actions"><button id="oauth-restart" type="button">Reiniciar conexión</button></div>`;
    login.querySelector('#login-form').before(section);
    section.querySelectorAll('[data-next],[data-back]').forEach(button=>button.onclick=()=>this._showStep(Number(button.dataset.next||button.dataset.back)));
    r.querySelector('#oauth-restart').onclick=()=>void this._begin();
    const connect=r.querySelector('#connect'),replacement=connect.cloneNode(true);connect.replaceWith(replacement);
    replacement.onclick=()=>{if(this._status.connected){void this._action('disconnect');return;}void this._begin();};
    r.querySelector('#oauth-har').onchange=async event=>{
      const file=event.target.files?.[0];event.target.value='';if(!file||this._busy||!this._oauthState)return;
      const generation=this._generation,state=this._oauthState;
      try{if(file.size>25*1024*1024)throw new Error('El HAR debe ocupar menos de 25 MB.');const contents=await file.text();if(generation!==this._generation)return;const callback=callbackFromHar(JSON.parse(contents),state);await this._action('finish',{callback});}
      catch(error){if(generation!==this._generation)return;this._error=error instanceof SyntaxError?'No se reconoce el archivo HAR. Selecciona el archivo .har exportado desde Red / Network.':error.message;this._render();}
    };
    login.addEventListener('close',()=>{this._generation++;this._busy=false;r.querySelector('#oauth-har').value='';r.querySelector('#oauth-link').removeAttribute('href');this._oauthState='';});
  }
  _showStep(step){
    const r=this.shadowRoot;
    r.querySelectorAll('[data-step]').forEach(section=>section.hidden=Number(section.dataset.step)!==step);
    r.querySelectorAll('[data-step-label]').forEach(label=>{const n=Number(label.dataset.stepLabel);label.classList.toggle('done',n<step);if(n===step)label.setAttribute('aria-current','step');else label.removeAttribute('aria-current');});
    r.querySelector('#oauth-progress').textContent=`Paso ${step} de 3 · Completa el acceso en diez minutos desde que iniciaste la conexión.`;
    r.querySelector('#login-dialog').scrollTop=0;
  }
  async _begin(){
    if(this._busy)return;
    const generation=++this._generation;this._busy=true;this._error='';this._oauthState='';
    const r=this.shadowRoot,link=r.querySelector('#oauth-link');link.hidden=true;link.removeAttribute('href');r.querySelector('#oauth-har').value='';r.querySelectorAll('#oauth details').forEach(d=>d.open=false);this._showStep(1);this._render();
    const dialog=r.querySelector('#login-dialog');if(!dialog.open)dialog.showModal();
    try{
      const result=await this._call('begin');if(generation!==this._generation)return;
      const url=new URL(result.authorization_url);
      if(url.protocol!=='https:'||url.hostname!=='accounts.lidl.com'||url.pathname!=='/connect/authorize')throw new Error('Dirección de autorización no válida.');
      this._oauthState=url.searchParams.get('state');link.href=url.href;link.hidden=false;
    }catch(error){if(generation===this._generation)this._error=error.message;}
    finally{if(generation===this._generation){this._busy=false;this._render();}}
  }
  async _action(action,fields){await super._action(action,fields);if(action==='finish'&&this._status.connected)this.shadowRoot.querySelector('#login-dialog').close();}
  _render(){
    if(!this._built)return;
    const r=this.shadowRoot,s=this._status,locked=this._busy||this._hass?.user?.is_admin!==true;
    r.querySelectorAll('button,input,select').forEach(el=>el.disabled=locked);
    r.querySelectorAll('[data-next]').forEach(button=>button.disabled=locked||!this._oauthState);
    r.querySelector('#oauth-link').hidden=locked||!this._oauthState;
    r.querySelector('#connect').textContent=s.connected?'Desconectar cuenta':'Conectar cuenta';r.querySelector('#connect').className=s.connected?'danger':'primary';
    r.querySelector('#account-email').textContent=s.connected?(s.email||'Cuenta Lidl conectada'):'';
    for(const [id,key] of [['history-enabled','history_enabled'],['auto-ticket','auto_ticket']]){const input=r.querySelector('#'+id);input.checked=Boolean(s.options?.[key]);input.disabled=locked||!s.connected;}
    r.querySelector('#login-form').hidden=true;r.querySelector('#verification').hidden=true;
    r.querySelector('#login-status').textContent=this._busy?'Consultando Lidl…':s.connected?'Cuenta conectada. Puedes revisar sus tickets en Analítica → Compras.':'';
    for(const id of ['status-error','login-error']){r.querySelector('#'+id).textContent=this._error||'';r.querySelector('#'+id).hidden=!this._error;}
  }
}
if(!customElements.get('isl-lidl-account'))customElements.define('isl-lidl-account',LidlAccountPanel);
