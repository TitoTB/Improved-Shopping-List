import { installDialogCloseButtons } from './dialog-controls.js?v=0.83.1';
import { installToggleStyles } from './toggle-styles.js?v=0.83.1';
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
      :host{display:block;color:inherit;font:inherit;--routine-border:color-mix(in srgb,var(--divider-color,#dfe7e1) 70%,var(--primary-text-color,#20352d) 30%);--routine-field:color-mix(in srgb,var(--card-background-color,#fff) 94%,#000)}*{box-sizing:border-box}[hidden]{display:none!important}
      .card{padding:22px;border:1px solid var(--divider-color,#dfe7e1);border-radius:16px;background:var(--card-background-color,#fff)}h2{font-size:20px;margin:0}h3{font-size:13px;margin:0 0 10px;font-weight:600}p{font-size:13px;line-height:1.5;color:var(--secondary-text-color,#63766b)}#status:empty{display:none}.heading,.actions{display:flex;align-items:center;justify-content:space-between;gap:12px}
      button,input{font:inherit;color:inherit;border:1px solid var(--routine-border);border-radius:10px;background:var(--routine-field);min-height:44px;padding:10px 12px}button{cursor:pointer}button:disabled{opacity:.5;cursor:default}.add,.save{background:#267052;color:#fff;border:0}.heading .add{width:44px;height:44px;padding:10px;flex:none}ha-icon{display:inline-flex;align-items:center;justify-content:center;width:22px;height:22px;--mdc-icon-size:22px;flex:none;line-height:0}button:has(ha-icon){display:inline-flex;justify-content:center;align-items:center;gap:7px}
      :host{container-type:inline-size}.routine{display:flex;align-items:center;position:relative;border:1px solid var(--routine-border);border-radius:12px;padding:12px 72px 12px 16px;margin-top:10px;min-height:68px;background:var(--routine-field)}.routine.inactive .routine-info{opacity:.5}.routine-info{width:100%;display:grid;grid-template-columns:minmax(0,1fr) auto auto;align-items:center;gap:18px;min-width:0}.routine-title{display:flex;align-items:center;gap:10px;min-width:0}.routine-title>ha-icon{width:24px;height:24px;--mdc-icon-size:24px;color:var(--secondary-text-color,#63766b)}.routine-title>div{display:flex;align-items:center;gap:12px;min-width:0}.routine-title strong{display:block;font-size:14px;line-height:1.4;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.routine-times{margin:0;font-size:12px;white-space:nowrap;font-variant-numeric:tabular-nums}.routine-bottom{display:contents}.routine-days{display:flex;align-items:center;gap:4px}.routine-day{display:grid;place-items:center;width:23px;height:26px;border:1px solid var(--routine-border);border-radius:6px;font-size:10px;color:var(--secondary-text-color,#63766b)}.routine-day.selected{background:#267052;color:#fff;border-color:#267052}.routine-every-day{display:block;padding:6px 10px;border-radius:7px;background:color-mix(in srgb,#267052 22%,var(--routine-field));font-size:12px;white-space:nowrap}.routine-people{display:flex;align-items:center;flex-wrap:wrap;justify-content:flex-end;max-width:108px;padding-left:4px;row-gap:4px}.routine-person{display:flex;position:relative;z-index:2;min-width:0;margin-left:-4px;cursor:pointer}.routine-person .avatar{width:28px;height:28px;font-size:10px;border:2px solid var(--routine-field)}.routine .actions{position:absolute;top:50%;right:16px;transform:translateY(-50%);z-index:2;margin:0}.routine-open{position:absolute;inset:0;z-index:1;width:100%;height:100%;min-height:0;padding:0;border:0;border-radius:12px;background:transparent}.routine-open:hover{background:color-mix(in srgb,var(--primary-text-color,#20352d) 3%,transparent)}.routine-open:disabled{cursor:default}
      .routine-toggle{appearance:none;position:relative;width:40px;height:24px;min-height:24px;padding:0;margin:0;flex:none;border:0;border-radius:99px;background:var(--isl-toggle-off-track,var(--switch-unchecked-track-color,#64748b));cursor:pointer}.routine-toggle::before{content:'';position:absolute;left:3px;top:3px;width:18px;height:18px;border-radius:50%;background:white;transition:transform .15s}.routine-toggle:checked{background:#267052}.routine-toggle:checked::before{transform:translateX(16px)}
      .avatar{display:grid;place-items:center;position:relative;overflow:hidden;flex:none;width:34px;height:34px;border-radius:50%;background:var(--secondary-background-color,#e4ece8);color:var(--primary-text-color,#20352d);border:1px solid var(--routine-border);font-size:12px;font-weight:600}.avatar img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}
      dialog{position:fixed;width:min(590px,calc(100% - 28px));max-height:90vh;overflow:auto;border:1px solid var(--routine-border);border-radius:20px;padding:0;color:inherit;background:var(--card-background-color,#fff)}dialog::backdrop{background:#0007}form{padding:24px;min-width:0}.dialog-heading{display:flex;align-items:center;gap:14px;padding-right:32px;margin-bottom:22px}.dialog-heading>ha-icon{width:34px;height:34px;--mdc-icon-size:34px}.dialog-heading h2{font-size:22px}.dialog-heading p{margin:4px 0 0;overflow-wrap:anywhere}.fields{display:grid;gap:20px;margin:0 0 22px}label{display:block;font-size:13px;font-weight:550}label input:not([type=checkbox]){display:block;width:100%;min-width:0;margin-top:7px}.people{display:grid;grid-template-columns:repeat(auto-fit,minmax(105px,1fr));gap:10px}.person-choice{position:relative;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:9px;padding:20px 10px 12px;border:1px solid var(--routine-border);border-radius:12px;cursor:pointer;min-width:0;background:var(--routine-field);text-align:center;overflow-wrap:anywhere}.person-choice:has(input:checked){border-color:#37976e;box-shadow:inset 0 0 0 1px #37976e;background:color-mix(in srgb,#267052 9%,var(--routine-field))}.person-choice .avatar{width:56px;height:56px;font-size:18px}.person-choice input{position:absolute;top:8px;right:8px;width:17px;height:17px;min-height:17px;margin:0;padding:0;accent-color:#267052}
      .schedule+.schedule{margin-top:22px;padding-top:20px;border-top:1px solid var(--routine-border)}.meal-fields{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:14px;margin-bottom:22px}.meal-fields input{text-align:center;font-variant-numeric:tabular-nums}.week{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:8px}.week .check{position:relative;display:block;cursor:pointer}.week input{position:absolute;inset:0;opacity:0;width:100%;height:100%;margin:0;min-height:0;cursor:pointer}.week span{display:grid;place-items:center;min-height:40px;border:1px solid var(--routine-border);border-radius:9px;background:var(--routine-field);font-size:13px;color:var(--secondary-text-color,#63766b)}.week input:checked+span{background:#267052;border-color:#267052;color:#fff}.week input:focus-visible+span{outline:2px solid var(--primary-color,#267052);outline-offset:2px}.error{color:var(--error-color,#d32f2f)}.routine-footer{display:flex;gap:12px;align-items:stretch;justify-content:space-between;border-top:1px solid var(--routine-border);margin:24px -24px -24px;padding:18px 24px}.routine-footer button{flex:1;min-width:0;font-size:13px;font-weight:600}.routine-footer .delete{background:transparent;color:var(--error-color,#d32f2f);border-color:color-mix(in srgb,var(--error-color,#d32f2f) 60%,var(--routine-border))}
      input:focus-visible,button:focus-visible{outline:2px solid var(--primary-color,#267052);outline-offset:2px}@media(max-width:500px){.card{padding:16px}form{padding:20px 16px}.people{grid-template-columns:repeat(auto-fit,minmax(85px,1fr));gap:8px}.person-choice{padding:22px 7px 10px}.person-choice .avatar{width:46px;height:46px}.week{gap:5px}.week span{min-height:36px}.routine-footer{margin:22px -16px -20px;padding:16px}.meal-fields{gap:10px}input{font-size:16px}.dialog-heading h2{font-size:20px}}
      @container(max-width:700px){.routine{padding:12px;min-height:100px}.routine-info{grid-template-columns:minmax(0,1fr) auto;gap:12px 8px}.routine-title{grid-column:1/-1;padding-right:44px}.routine-title>div{display:block}.routine-times{margin-top:3px}.routine .actions{top:16px;right:12px;transform:none}.routine-days{gap:3px}.routine-day{width:20px;height:24px}.routine-people{max-width:76px}.routine-every-day{padding:5px 8px}}
    </style><section class="card"><div class="heading"><h2>Rutinas</h2><button id="new-routine" type="button" class="add" aria-label="Nueva rutina"><ha-icon icon="mdi:plus-thick"></ha-icon></button></div><p id="status" role="status"></p><div id="routines"></div></section>
    <dialog aria-labelledby="routine-title"><form id="routine-form"><div class="dialog-heading"><ha-icon icon="mdi:clock-outline" aria-hidden="true"></ha-icon><div><h2 id="routine-title">Nueva rutina</h2><p id="routine-subtitle" hidden></p></div></div><div class="fields"><label>Nombre de la rutina<input id="routine-name" maxlength="100" required></label><section class="wide" id="routine-people" aria-labelledby="routine-people-title"><h3 id="routine-people-title">Personas</h3><div class="people"></div></section></div><div id="routine-schedule"></div><p id="routine-error" class="error" role="alert" hidden></p><div class="actions routine-footer"><button id="delete-routine" class="delete" type="button" hidden><ha-icon icon="mdi:delete" aria-hidden="true"></ha-icon>Eliminar rutina</button><button class="save" type="submit">Guardar rutina</button></div></form></dialog>`;
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
    const firstTime=row=>row.meals.map(window=>window.start_time??window.time??'24:00').sort()[0]??'24:00';
    const ordered=[...this.rows].sort((a,b)=>firstTime(a).localeCompare(firstTime(b))||a.name.localeCompare(b.name,'es'));
    const root=this.shadowRoot;root.querySelector('#routines').replaceChildren(...ordered.map(row=>{
      const card=el('article');card.className='routine'+(row.enabled?'':' inactive');const info=el('div');info.className='routine-info';
      const title=el('div');title.className='routine-title';const icon=el('ha-icon');icon.setAttribute('icon','mdi:clock-outline');icon.setAttribute('aria-hidden','true');const copy=el('div');copy.append(el('strong',row.name));const times=el('p',row.meals.map(m=>`${m.start_time??m.time} – ${m.end_time??defaultEnd(m.time)}`).join(' / '));times.className='routine-times';copy.append(times);title.append(icon,copy);info.append(title);
      const bottom=el('div');bottom.className='routine-bottom';const week=el('div');week.className='routine-days';const selected=new Set(row.meals.filter(m=>m.enabled!==false).flatMap(m=>m.days));week.setAttribute('aria-label','Días: '+[...selected].sort().map(day=>['Lunes','Martes','Miércoles','Jueves','Viernes','Sábado','Domingo'][day]).join(', '));if(selected.size===7&&row.meals.filter(m=>m.enabled!==false).every(m=>m.days.length===7)){const chip=el('span','Todos los días');chip.className='routine-every-day';week.append(chip);}else days.forEach((day,index)=>{const chip=el('span',day);chip.className='routine-day'+(selected.has(index)?' selected':'');chip.setAttribute('aria-hidden','true');week.append(chip);});const people=el('div');people.className='routine-people';for(const id of row.persons){const person=el('span');person.className='routine-person';person.title=this.personName(id);person.setAttribute('aria-label',this.personName(id));person.setAttribute('role','img');person.append(this.avatar(id));person.addEventListener('click',()=>this.open(row));people.append(person);}bottom.append(week,people);info.append(bottom);
      const actions=el('div');actions.className='actions';const toggle=el('input');toggle.type='checkbox';toggle.className='routine-toggle';toggle.setAttribute('role','switch');toggle.setAttribute('aria-label','Activar rutina '+row.name);toggle.checked=row.enabled;toggle.addEventListener('change',()=>{const {updated_at,minimum_minutes,...routine}=row;void this.write('save',{routine:{...routine,enabled:toggle.checked}},false);});
      const open=el('button');open.type='button';open.className='routine-open';open.setAttribute('aria-label','Editar '+row.name);open.addEventListener('click',()=>this.open(row));actions.append(toggle);card.append(info,open,actions);
      return card;
    }));this.sync();
  }
  personName(id){return this.hass?.states[id]?.attributes?.friendly_name??id;}
  avatar(id){
    const avatar=el('span');avatar.className='avatar';avatar.setAttribute('aria-hidden','true');avatar.textContent=this.personName(id).trim().split(/\s+/).slice(0,2).map(word=>word[0]??'').join('').toLocaleUpperCase('es');
    const picture=this.hass?.states[id]?.attributes?.entity_picture;
    if(picture){try{const source=typeof this.hass.hassUrl==='function'?this.hass.hassUrl(picture):picture;const url=new URL(source,location.origin);if(['http:','https:'].includes(url.protocol)){const image=el('img');image.src=url.href;image.alt='';image.referrerPolicy='no-referrer';image.addEventListener('error',()=>image.remove(),{once:true});avatar.append(image);}}catch{/* Initials remain available for missing or invalid pictures. */}}
    return avatar;
  }
  meal(name,start_time,end_time=defaultEnd(start_time)){return {id:mealId(),name,start_time,end_time,days:[0,1,2,3,4,5,6],enabled:true};}
  open(row){
    if(this.busy||this.hass?.user?.is_admin!==true)return;this.draft=structuredClone(row??{name:'',persons:[],enabled:true,meals:[this.meal('Franja horaria','08:30')]});
    this.draft.meals=this.draft.meals.map(meal=>{const {time,...fields}=meal;const start_time=meal.start_time??time;return {...fields,start_time,end_time:meal.end_time??defaultEnd(start_time)};});
    const root=this.shadowRoot;root.querySelector('#routine-title').textContent=row?'Editar rutina':'Nueva rutina';root.querySelector('#routine-name').value=this.draft.name;root.querySelector('#routine-error').hidden=true;root.querySelector('#delete-routine').hidden=!row?.id;
    const people=[...new Set([...Object.keys(this.hass.states).filter(id=>id.startsWith('person.')),...this.draft.persons])];
    const subtitle=root.querySelector('#routine-subtitle');subtitle.textContent=row?.name??'';subtitle.hidden=!row;
    root.querySelector('#routine-people .people').replaceChildren(...(people.length?people.map(id=>{const label=el('label');label.className='person-choice';const box=el('input');box.type='checkbox';box.checked=this.draft.persons.includes(id);box.setAttribute('aria-label',this.personName(id));box.addEventListener('change',()=>{this.draft.persons=box.checked?[...this.draft.persons,id]:this.draft.persons.filter(p=>p!==id);});label.append(box,this.avatar(id),el('span',this.personName(id)));return label;}):[el('p','No hay entidades person disponibles en Home Assistant.')]));
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
