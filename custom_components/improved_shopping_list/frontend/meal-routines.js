import { installDialogCloseButtons } from './dialog-controls.js?v=0.74.2';
import { installToggleStyles } from './toggle-styles.js?v=0.74.2';
const el=(tag,text)=>{const n=document.createElement(tag);if(text!=null)n.textContent=text;return n;};
const days=['L','M','X','J','V','S','D'];
const defaultEnd=start=>{const [hour,minute]=start.split(':').map(Number);return String((hour+1)%24).padStart(2,'0')+':'+String(minute).padStart(2,'0');};
// Unlike randomUUID(), getRandomValues is available on local HTTP origins.
const mealId=()=>`meal_${Array.from(crypto.getRandomValues(new Uint8Array(16)),n=>n.toString(16).padStart(2,'0')).join('')}`;
class MealRoutinesSettings extends HTMLElement {
  constructor(){super();this.attachShadow({mode:'open'});this.rows=[];}
  connectedCallback(){if(!this.built)this.build();}
  set data(value){this.hass=value?.hass;if(this.built)this.sync();}
  set active(value){const changed=this._active!==Boolean(value);this._active=Boolean(value);if(this.built){if(changed&&this._active)void this.load();if(!this._active)this.shadowRoot.querySelector('dialog').close();}}
  disconnectedCallback(){this._active=false;}
  build(){
    this.built=true;this.shadowRoot.innerHTML=`<style>
      :host{display:block;color:inherit;font:inherit}*{box-sizing:border-box}[hidden]{display:none!important}.card{padding:22px;border:1px solid var(--divider-color,#dfe7e1);border-radius:16px;background:var(--card-background-color,#fff)}
      h2{font-size:20px;margin:0}p{font-size:13px;line-height:1.5;color:var(--secondary-text-color,#63766b)}.heading,.routine,.actions{display:flex;align-items:center;justify-content:space-between;gap:12px}.routine{position:relative;flex-wrap:wrap;border:1px solid var(--divider-color,#dfe7e1);border-radius:12px;padding:12px;margin-top:12px}.routine p{margin:5px 0 0}
      button,input,select{font:inherit;color:inherit;border:1px solid var(--divider-color,#dfe7e1);border-radius:9px;background:transparent;min-height:42px;padding:9px}button{cursor:pointer}button:disabled{opacity:.5;cursor:default}.add,.save{background:#267052;color:white;border:0}.delete{background:#d32f2f;color:white;border:0}ha-icon{display:inline-flex;width:22px;height:22px;--mdc-icon-size:22px}button:has(ha-icon){display:inline-flex;justify-content:center;align-items:center;padding:9px;gap:6px}label{display:block;font-size:13px;font-weight:600}label input:not([type=checkbox]){display:block;width:100%;margin-top:7px}.check{display:flex;align-items:center;gap:8px;font-weight:400}.check input{min-height:20px;width:20px;margin:0;accent-color:#267052}.fields{display:grid;grid-template-columns:minmax(0,1fr);gap:16px;margin:18px 0}.wide{grid-column:1/-1}details{border:1px solid var(--divider-color,#dfe7e1);border-radius:9px;padding:10px;margin-top:7px}summary{cursor:pointer}.people{display:grid;gap:10px;padding-top:12px}.meal{border:1px solid var(--divider-color,#dfe7e1);padding:12px;border-radius:12px;margin:12px 0}.meal-fields{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);align-items:end;gap:10px}.week{display:flex;flex-wrap:wrap;gap:10px;margin-top:10px}.actions{justify-content:flex-end;margin-top:18px}.error{color:var(--error-color,#d32f2f)}dialog{position:fixed;max-width:700px;width:calc(100% - 30px);max-height:88vh;overflow:auto;border:1px solid var(--divider-color,#dfe7e1);border-radius:18px;padding:24px;color:inherit;background:var(--card-background-color,#fff)}dialog::backdrop{background:#0007}@media(max-width:500px){.fields{grid-template-columns:1fr}.meal-fields{grid-template-columns:minmax(0,1fr) minmax(0,1fr)}.meal-name{grid-column:1/-1}.meal-fields label{min-width:0}.meal-fields input{min-width:0}dialog{padding:18px}.routine{align-items:flex-start}}
      .routine>div:first-child{min-width:0;flex:1;overflow-wrap:anywhere}.routine .actions{position:relative;z-index:2;margin:0;flex:none;gap:8px}.routine-open{position:absolute;inset:0;z-index:1;width:100%;height:100%;min-height:0;padding:0;border:0;border-radius:12px;background:transparent}.routine-open:disabled{cursor:default}.routine-footer{justify-content:space-between}.routine-footer .save{margin-left:auto}.routine-toggle{appearance:none;position:relative;width:40px;height:24px;min-height:24px;padding:0;margin:0;flex:none;border:0;border-radius:99px;background:var(--isl-toggle-off-track,var(--switch-unchecked-track-color,#64748b));cursor:pointer}.routine-toggle::before{content:'';position:absolute;left:3px;top:3px;width:18px;height:18px;border-radius:50%;background:white;transition:transform .15s}.routine-toggle:checked{background:#267052}.routine-toggle:checked::before{transform:translateX(16px)}.routine-toggle:disabled{opacity:.5;cursor:default}
      input:focus-visible,button:focus-visible,summary:focus-visible{outline:2px solid var(--primary-color,#267052);outline-offset:2px}
    </style><section class="card"><div class="heading"><h2>Rutinas</h2><button id="new-routine" type="button" class="add" aria-label="Nueva rutina"><ha-icon icon="mdi:plus-thick"></ha-icon></button></div><p id="status" role="status"></p><div id="routines"></div></section>
    <dialog aria-labelledby="routine-title"><form id="routine-form"><h2 id="routine-title">Nueva rutina</h2><div class="fields"><label>Nombre de la rutina<input id="routine-name" maxlength="100" required></label><div class="wide"><span>Personas</span><details id="routine-people"><summary>Seleccionar personas</summary><div class="people"></div></details></div></div><div id="routine-schedule"></div><p id="routine-error" class="error" role="alert" hidden></p><div class="actions routine-footer"><button id="delete-routine" class="delete" type="button" hidden><ha-icon icon="mdi:delete" aria-hidden="true"></ha-icon>Eliminar rutina</button><button class="save" type="submit">Guardar rutina</button></div></form></dialog>`;
    installDialogCloseButtons(this.shadowRoot);installToggleStyles(this.shadowRoot);
    this.shadowRoot.querySelector('#new-routine').addEventListener('click',()=>this.open());
    this.shadowRoot.querySelector('#delete-routine').addEventListener('click',()=>{const row=this.draft;if(this.busy||!row?.id)return;if(confirm('¿Eliminar la rutina «'+row.name+'»?'))void this.write('delete',{routine_id:row.id,revision:row.revision});});
    this.shadowRoot.querySelector('form').addEventListener('submit',event=>{event.preventDefault();void this.save();});
    this.shadowRoot.querySelector('dialog').addEventListener('cancel',event=>{if(this.busy)event.preventDefault();});
    this.sync();if(this._active)void this.load();
  }
  sync(){if(this.built){const locked=this.busy||this.hass?.user?.is_admin!==true;this.shadowRoot.querySelectorAll('#new-routine,#routines button,#routines input,#routines select').forEach(control=>control.disabled=locked);}}
  async load(){
    if(this.loading||this.hass?.user?.is_admin!==true)return;this.loading=true;
    const status=this.shadowRoot.querySelector('#status');status.className='';status.textContent='Cargando rutinas…';
    try{this.rows=(await this.hass.callWS({type:'improved_shopping_list/routines/get'})).routines??[];status.textContent='';this.render();}
    catch(error){status.textContent=error.message;status.className='error';}finally{this.loading=false;}
  }
  render(){
    const root=this.shadowRoot;root.querySelector('#routines').replaceChildren(...this.rows.map(row=>{
      const card=el('article');card.className='routine';const info=el('div');info.append(el('strong',row.name),el('p',`${row.persons.map(id=>this.hass.states[id]?.attributes?.friendly_name??id).join(', ')} · ${row.meals.map(m=>`${m.start_time??m.time} – ${m.end_time??defaultEnd(m.time)} · ${m.days.map(day=>days[day]).join(', ')}`).join(' / ')}${row.enabled?'':' · Desactivada'}`));
      const actions=el('div');actions.className='actions';const toggle=el('input');toggle.type='checkbox';toggle.className='routine-toggle';toggle.setAttribute('role','switch');toggle.setAttribute('aria-label','Activar rutina '+row.name);toggle.checked=row.enabled;toggle.addEventListener('change',()=>{const {updated_at,minimum_minutes,...routine}=row;void this.write('save',{routine:{...routine,enabled:toggle.checked}},false);});
      const open=el('button');open.type='button';open.className='routine-open';open.setAttribute('aria-label','Editar '+row.name);open.addEventListener('click',()=>this.open(row));actions.append(toggle);card.append(info,open,actions);
      return card;
    }));this.sync();
  }
  meal(name,start_time,end_time=defaultEnd(start_time)){return {id:mealId(),name,start_time,end_time,days:[0,1,2,3,4,5,6],enabled:true};}
  open(row){
    if(this.busy||this.hass?.user?.is_admin!==true)return;this.draft=structuredClone(row??{name:'',persons:[],enabled:true,meals:[this.meal('Franja horaria','08:30')]});
    this.draft.meals=this.draft.meals.map(meal=>{const {time,...fields}=meal;const start_time=meal.start_time??time;return {...fields,start_time,end_time:meal.end_time??defaultEnd(start_time)};});
    const root=this.shadowRoot;root.querySelector('#routine-title').textContent=row?'Editar rutina':'Nueva rutina';root.querySelector('#routine-name').value=this.draft.name;root.querySelector('#routine-error').hidden=true;root.querySelector('#delete-routine').hidden=!row?.id;
    const people=[...new Set([...Object.keys(this.hass.states).filter(id=>id.startsWith('person.')),...this.draft.persons])];
    root.querySelector('#routine-people .people').replaceChildren(...(people.length?people.map(id=>{const label=el('label');label.className='check';const box=el('input');box.type='checkbox';box.checked=this.draft.persons.includes(id);box.addEventListener('change',()=>{this.draft.persons=box.checked?[...this.draft.persons,id]:this.draft.persons.filter(p=>p!==id);});label.append(box,el('span',this.hass.states[id]?.attributes?.friendly_name??id));return label;}):[el('p','No hay entidades person disponibles en Home Assistant.')]));
    this.renderSchedule();root.querySelector('dialog').showModal();
  }
  renderSchedule(){
    // Keep existing identifiers and windows so product assignments remain valid.
    this.shadowRoot.querySelector('#routine-schedule').replaceChildren(...this.draft.meals.map((window,index)=>{
      const block=el('section');block.className='schedule';
      const title=el('h3',this.draft.meals.length===1?'Franja horaria':'Franja horaria '+(index+1));
      const fields=el('div');fields.className='meal-fields';
      for(const [field,label] of [['start_time','Inicio'],['end_time','Fin']]){
        const wrap=el('label',label),input=el('input');input.type='time';input.required=true;input.value=window[field];
        input.setAttribute('aria-label',label+(this.draft.meals.length===1?'':' de franja '+(index+1)));
        input.addEventListener('input',()=>window[field]=input.value);wrap.append(input);fields.append(wrap);
      }
      const week=el('div');week.className='week';week.setAttribute('role','group');week.setAttribute('aria-label','Días de la semana'+(this.draft.meals.length===1?'':' de franja '+(index+1)));
      days.forEach((text,day)=>{const label=el('label');label.className='check';const box=el('input');box.type='checkbox';box.checked=window.days.includes(day);box.setAttribute('aria-label',['Lunes','Martes','Miércoles','Jueves','Viernes','Sábado','Domingo'][day]+(this.draft.meals.length===1?'':' de franja '+(index+1)));box.addEventListener('change',()=>{window.days=box.checked?[...window.days,day]:window.days.filter(d=>d!==day);});label.append(box,el('span',text));week.append(label);});
      block.append(title,fields,el('h3','Días de la semana'),week);return block;
    }));
  }
  async save(){
    const root=this.shadowRoot;this.draft.name=root.querySelector('#routine-name').value;
    const error=root.querySelector('#routine-error');
    const message=!this.draft.meals.every(window=>window.days.length)?'Selecciona al menos un día de la semana.':this.draft.meals.some(window=>window.start_time===window.end_time)?'La hora final debe ser distinta de la inicial.':'';
    if(message){error.textContent=message;error.hidden=false;return;}
    const {updated_at,minimum_minutes,...routine}=this.draft;await this.write('save',{routine});
  }
  async write(action,fields,close=true){
    if(this.busy)return;this.busy=true;this.sync();const root=this.shadowRoot;root.querySelectorAll('dialog button').forEach(b=>b.disabled=true);
    try{this.rows=(await this.hass.callWS({type:'improved_shopping_list/routines/'+action,...fields})).routines;if(close)root.querySelector('dialog').close();root.querySelector('#status').textContent='';this.render();}
    catch(error){this.render();const message=root.querySelector(root.querySelector('dialog').open?'#routine-error':'#status');message.textContent=error.message;message.hidden=false;message.className='error';}
    finally{this.busy=false;root.querySelectorAll('dialog button').forEach(b=>b.disabled=false);this.sync();}
  }
}
customElements.define('isl-meal-routines',MealRoutinesSettings);
