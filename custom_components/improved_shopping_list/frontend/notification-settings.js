/** Notification rule settings; delivery runs in Home Assistant, not in the panel. */
import { installToggleStyles } from './toggle-styles.js?v=0.62.0';
const DEFAULTS={catalog_new:{enabled:false,threshold:0,targets:[],title:'Productos nuevos',message:'Hay {cantidad} productos nuevos pendientes de incluir en el catálogo.'},shopping_list:{enabled:false,threshold:10,targets:[],title:'Lista de la compra',message:'{lista} tiene {cantidad} productos pendientes.'},low_stock:{enabled:false,threshold:3,targets:[],title:'Stock bajo',message:'Hay {cantidad} productos con stock bajo: {productos}.'}};
const RESERVED=new Set(['notify','send_message','persistent_notification','reload']);
function node(tag,text,className){const el=document.createElement(tag);if(text!==undefined)el.textContent=text;if(className)el.className=className;return el;}
function targets(hass){
  const result=[];
  for(const [service,info] of Object.entries(hass?.services?.notify??{})){
    if(!RESERVED.has(service))result.push({id:'service:notify.'+service,name:info.name||service.replace(/^mobile_app_/, '').replaceAll('_',' ')});
  }
  for(const state of Object.values(hass?.states??{}))if(state.entity_id?.startsWith('notify.'))result.push({id:'entity:'+state.entity_id,name:state.attributes?.friendly_name??state.entity_id});
  return result.sort((a,b)=>a.name.localeCompare(b.name,'es',{sensitivity:'base'}));
}
class NotificationSettings extends HTMLElement{
  constructor(){super();this.attachShadow({mode:'open'});this._dirty=false;}
  set data(value){this._data=value;this._render();}
  connectedCallback(){if(!this._built)this._build();this._render();}
  _build(){
    this.shadowRoot.innerHTML='<style>:host{display:block;color:var(--primary-text-color,#20352d)}*{box-sizing:border-box}[hidden]{display:none!important}h2{font-size:20px;margin:0}h2 ha-icon{width:24px;height:24px;--mdc-icon-size:24px}button,input,textarea{font:inherit;color:inherit}input,textarea{display:block;width:100%;min-width:0;min-height:44px;border:1px solid var(--divider-color,#dfe7e1);border-radius:9px;padding:10px 12px;background:var(--card-background-color,#fff)}textarea{resize:vertical;min-height:90px}button{cursor:pointer;min-height:44px;padding:10px 14px;border:0;border-radius:10px;background:#267052;color:#fff}button:disabled,input:disabled,textarea:disabled{opacity:.55;cursor:default}input:focus-visible,textarea:focus-visible,button:focus-visible{outline:3px solid var(--primary-color,#267052);outline-offset:3px}.rules{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}.rule{padding:22px;background:var(--card-background-color,#fff);border:1px solid var(--divider-color,#dfe7e1);border-radius:16px;min-width:0}.rule-heading{display:flex;align-items:center;justify-content:space-between;gap:12px}.rule-heading h2{display:flex;align-items:center;gap:8px}.toggle{appearance:none;width:42px;height:24px;min-height:24px;padding:0;border:0;border-radius:20px;background:#b3261e;cursor:pointer;position:relative;flex:none}.toggle:checked{background:#267052}.toggle:before{content:"";position:absolute;width:18px;height:18px;top:3px;left:3px;border-radius:50%;background:#fff;transition:transform .15s}.toggle:checked:before{transform:translateX(18px)}label{display:block;font-size:13px;font-weight:600;margin-top:16px}label input,label textarea{margin-top:7px}.threshold{display:flex;align-items:center;gap:12px}.threshold span{flex:1;min-width:0}.threshold input{width:86px;flex:none;margin-top:0}.helper{font-size:13px;line-height:1.6;color:var(--secondary-text-color,#63766b);margin:12px 0 0}fieldset{min-width:0;border:1px solid var(--divider-color,#dfe7e1);border-radius:10px;margin:18px 0 0;padding:12px}legend{font-size:13px;font-weight:600}.destinations{max-height:210px;overflow:auto}.target{display:flex;align-items:center;gap:10px;margin:0;padding:8px 0;overflow-wrap:anywhere}.target input{width:18px;height:18px;min-height:18px;margin:0;padding:0;flex:none}.target small{display:block;font-weight:400;font-size:11px;opacity:.7}.actions{display:flex;justify-content:flex-end;margin-top:20px}.error{border:1px solid var(--error-color,#bd3636);color:var(--error-color,#bd3636);border-radius:10px;padding:12px;margin-top:16px;font-size:13px}@media(max-width:800px){.rules{grid-template-columns:1fr}}@media(max-width:400px){.rule{padding:16px}.rule-heading h2{font-size:18px}}</style><form id="notifications-form"><div class="rules"></div><p class="helper">Puedes usar {lista}, {cantidad}, {limite} y {productos} en el título y el mensaje. Se avisa una vez al superar el límite; el aviso se reactiva al volver a ese límite o por debajo.</p><div id="notifications-error" class="error" role="alert" hidden></div><div class="actions"><button id="save-notifications" type="submit">Guardar notificaciones</button></div></form>';
    this._built=true;const root=this.shadowRoot;installToggleStyles(root);
    for(const [key,name,icon,description] of [['shopping_list','Lista de la compra','mdi:format-list-checks','Un aviso independiente para cada lista configurada. Se cuentan los productos pendientes, sin sumar sus cantidades.'],['low_stock','Stock bajo','mdi:package-variant','Se cuentan los productos que han alcanzado su mínimo de stock o han caducado, igual que en el indicador de stock bajo.'],['catalog_new','Productos nuevos','mdi:creation','Productos de las listas configuradas aún no incluidos en el catálogo y códigos escaneados sin vincular, como en Catálogo → Pendiente. Se excluyen los descartados y se unifican los nombres repetidos entre listas.']]){
      const section=node('section',undefined,'rule');section.dataset.rule=key;section.setAttribute('aria-label',name);
      const heading=node('div',undefined,'rule-heading'),title=node('h2'),symbol=node('ha-icon');symbol.setAttribute('icon',icon);symbol.setAttribute('aria-hidden','true');title.append(symbol,document.createTextNode(name));
      const enabled=node('input',undefined,'toggle');enabled.type='checkbox';enabled.name=key+'_enabled';enabled.setAttribute('aria-label','Activar aviso de '+name);heading.append(title,enabled);
      section.append(heading,node('p',description,'helper'));
      const threshold=node('label',undefined,'threshold');threshold.append(node('span','Avisar con más de este número de productos'));
      const number=node('input');number.type='number';number.name=key+'_threshold';number.min='0';number.max='100000';number.step='1';number.required=true;number.setAttribute('aria-label','Límite de productos de '+name);threshold.append(number);section.append(threshold);
      const destinations=node('fieldset'),legend=node('legend','Dispositivos'),list=node('div',undefined,'destinations');list.dataset.targets=key;destinations.append(legend,list);section.append(destinations);
      for(const field of ['title','message']){const label=node('label',field==='title'?'Título':'Mensaje'),input=node(field==='title'?'input':'textarea');input.name=key+'_'+field;input.maxLength=field==='title'?160:2000;label.append(input);section.append(label);}
      root.querySelector('.rules').append(section);
    }
    root.querySelector('form').addEventListener('input',()=>{this._dirty=true;this._requirements();});
    root.querySelector('form').addEventListener('change',()=>{this._dirty=true;this._requirements();});
    root.querySelector('form').addEventListener('submit',event=>{event.preventDefault();void this._save();});
  }
  _requirements(){for(const key of Object.keys(DEFAULTS))this.shadowRoot.querySelector('[name='+key+'_message]').required=this.shadowRoot.querySelector('[name='+key+'_enabled]').checked;}
  _render(){
    if(!this._built||!this._data)return;
    const root=this.shadowRoot,options=targets(this._data.hass),config=this._data.settings?.notifications??DEFAULTS;
    for(const key of Object.keys(DEFAULTS)){
      const rule={...DEFAULTS[key],...config[key]},section=root.querySelector('[data-rule='+key+']'),list=section.querySelector('.destinations');
      const selected=new Set(this._dirty?[...list.querySelectorAll('input:checked')].map(input=>input.value):rule.targets);
      if(!this._dirty&&!this._busy){for(const field of ['threshold','title','message'])section.querySelector('[name='+key+'_'+field+']').value=rule[field];section.querySelector('[name='+key+'_enabled]').checked=rule.enabled;}
      const available=[...options];for(const id of selected)if(!available.some(option=>option.id===id))available.push({id,name:id.split(':').slice(1).join(':')+' · No disponible'});
      const signature=JSON.stringify(available);
      if(list.dataset.signature!==signature){list.dataset.signature=signature;list.replaceChildren(...available.map(option=>{const label=node('label',undefined,'target'),input=node('input');input.type='checkbox';input.value=option.id;const text=node('span',option.name);text.append(node('small',option.id.split(':').slice(1).join(':')));label.append(input,text);return label;}));if(!available.length)list.append(node('p','No hay dispositivos de notificación disponibles. Añade un destino de notificaciones en Home Assistant.','helper'));}
      for(const input of list.querySelectorAll('input'))input.checked=selected.has(input.value);
    }
    this._requirements();const locked=this._busy||this._data.hass?.user?.is_admin!==true;
    root.querySelectorAll('input,textarea,button').forEach(control=>{control.disabled=locked;});
  }
  async _save(){
    if(this._busy||this._data?.hass?.user?.is_admin!==true)return;
    const root=this.shadowRoot,config={};
    for(const key of Object.keys(DEFAULTS)){const rule={};for(const field of ['title','message'])rule[field]=root.querySelector('[name='+key+'_'+field+']').value;rule.enabled=root.querySelector('[name='+key+'_enabled]').checked;rule.threshold=Number(root.querySelector('[name='+key+'_threshold]').value);rule.targets=[...root.querySelector('[data-targets='+key+']').querySelectorAll('input:checked')].map(input=>input.value);config[key]=rule;}
    this._busy=true;root.querySelector('#notifications-error').hidden=true;this._render();
    try{await this.onSave(config);this._dirty=false;}catch(error){const notice=root.querySelector('#notifications-error');notice.textContent=error.message??'No se han podido guardar las notificaciones.';notice.hidden=false;}finally{this._busy=false;this._render();}
  }
}
if(!customElements.get('isl-notification-settings'))customElements.define('isl-notification-settings',NotificationSettings);
