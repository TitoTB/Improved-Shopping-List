import { installDialogCloseButtons } from './dialog-controls.js?v=0.68.0';
const el=(tag,text)=>{const n=document.createElement(tag);if(text!=null)n.textContent=text;return n;};
const days=['L','M','X','J','V','S','D'];
const iconButton=(name,icon)=>{const b=el('button');b.type='button';b.setAttribute('aria-label',name);b.title=name;const i=el('ha-icon');i.setAttribute('icon',icon);i.setAttribute('aria-hidden','true');b.append(i);return b;};
class MealRoutinesSettings extends HTMLElement {
  constructor(){super();this.attachShadow({mode:'open'});this.rows=[];}
  connectedCallback(){if(!this.built)this.build();}
  set data(value){this.hass=value?.hass;if(this.built)this.sync();}
  set active(value){const changed=this._active!==Boolean(value);this._active=Boolean(value);if(this.built){if(changed&&this._active)void this.load();if(!this._active)this.shadowRoot.querySelector('dialog').close();}}
  disconnectedCallback(){this._active=false;}
  build(){
    this.built=true;this.shadowRoot.innerHTML=`<style>
      :host{display:block;color:inherit;font:inherit}*{box-sizing:border-box}[hidden]{display:none!important}.card{padding:22px;border:1px solid var(--divider-color,#dfe7e1);border-radius:16px;background:var(--card-background-color,#fff)}
      h2{font-size:20px;margin:0}p{font-size:13px;line-height:1.5;color:var(--secondary-text-color,#63766b)}.heading,.routine,.actions{display:flex;align-items:center;justify-content:space-between;gap:12px}.routine{border:1px solid var(--divider-color,#dfe7e1);border-radius:12px;padding:12px;margin-top:12px}.routine p{margin:5px 0 0}
      button,input,select{font:inherit;color:inherit;border:1px solid var(--divider-color,#dfe7e1);border-radius:9px;background:transparent;min-height:42px;padding:9px}button{cursor:pointer}button:disabled{opacity:.5;cursor:default}.add,.save{background:#267052;color:white;border:0}.delete{background:#d32f2f;color:white;border:0}ha-icon{display:inline-flex;width:22px;height:22px;--mdc-icon-size:22px}button:has(ha-icon){display:inline-flex;justify-content:center;align-items:center;padding:9px;gap:6px}label{display:block;font-size:13px;font-weight:600}label input:not([type=checkbox]){display:block;width:100%;margin-top:7px}.check{display:flex;align-items:center;gap:8px;font-weight:400}.check input{min-height:20px;width:20px;margin:0;accent-color:#267052}.fields{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin:18px 0}.wide{grid-column:1/-1}details{border:1px solid var(--divider-color,#dfe7e1);border-radius:9px;padding:10px;margin-top:7px}summary{cursor:pointer}.people{display:grid;gap:10px;padding-top:12px}.meal{border:1px solid var(--divider-color,#dfe7e1);padding:12px;border-radius:12px;margin:12px 0}.meal-fields{display:grid;grid-template-columns:minmax(0,1fr) 100px auto;align-items:end;gap:10px}.week{display:flex;flex-wrap:wrap;gap:10px;margin-top:10px}.actions{justify-content:flex-end;margin-top:18px}.error{color:var(--error-color,#d32f2f)}dialog{position:fixed;max-width:700px;width:calc(100% - 30px);max-height:88vh;overflow:auto;border:1px solid var(--divider-color,#dfe7e1);border-radius:18px;padding:24px;color:inherit;background:var(--card-background-color,#fff)}dialog::backdrop{background:#0007}@media(max-width:500px){.fields{grid-template-columns:1fr}.meal-fields{grid-template-columns:minmax(0,1fr) 80px auto}dialog{padding:18px}.routine{align-items:flex-start}}
      input:focus-visible,button:focus-visible,summary:focus-visible{outline:2px solid var(--primary-color,#267052);outline-offset:2px}
    </style><section class="card"><div class="heading"><h2>Rutinas de comidas</h2><button id="new-routine" class="add" aria-label="Nueva rutina"><ha-icon icon="mdi:plus-thick"></ha-icon></button></div><p>Define quién come en casa y a qué horas. Después asigna productos desde Reposición → Consumo por comidas o desde Stock.</p><p id="status" role="status"></p><div id="routines"></div></section>
    <dialog aria-labelledby="routine-title"><form id="routine-form"><h2 id="routine-title">Nueva rutina</h2><div class="fields"><label>Nombre de la rutina<input id="routine-name" maxlength="100" required></label><label>Permanencia mínima en casa (minutos)<input id="routine-minimum" type="number" min="0" max="240" step="1" required></label><label class="check"><input id="routine-enabled" type="checkbox">Rutina activada</label><div class="wide"><span>Personas</span><details id="routine-people"><summary>Seleccionar personas</summary><div class="people"></div></details></div></div><div class="heading"><h3>Comidas</h3><button id="add-meal" type="button" class="add" aria-label="Añadir comida"><ha-icon icon="mdi:plus-thick"></ha-icon></button></div><div id="routine-meals"></div><p id="routine-error" class="error" role="alert" hidden></p><div class="actions"><button class="save" type="submit">Guardar rutina</button></div></form></dialog>`;
    installDialogCloseButtons(this.shadowRoot);
    this.shadowRoot.querySelector('#new-routine').addEventListener('click',()=>this.open());
    this.shadowRoot.querySelector('#add-meal').addEventListener('click',()=>{this.draft.meals.push(this.meal('','14:00'));this.renderMeals();});
    this.shadowRoot.querySelector('form').addEventListener('submit',event=>{event.preventDefault();void this.save();});
    this.shadowRoot.querySelector('dialog').addEventListener('cancel',event=>{if(this.busy)event.preventDefault();});
    this.sync();if(this._active)void this.load();
  }
  sync(){if(this.built)this.shadowRoot.querySelector('#new-routine').disabled=this.busy||this.hass?.user?.is_admin!==true;}
  async load(){
    if(this.loading||this.hass?.user?.is_admin!==true)return;this.loading=true;
    const status=this.shadowRoot.querySelector('#status');status.textContent='Cargando rutinas…';
    try{this.rows=(await this.hass.callWS({type:'improved_shopping_list/routines/get'})).routines??[];status.textContent='';this.render();}
    catch(error){status.textContent=error.message;status.className='error';}finally{this.loading=false;}
  }
  render(){
    const root=this.shadowRoot;root.querySelector('#routines').replaceChildren(...this.rows.map(row=>{
      const card=el('article');card.className='routine';const info=el('div');info.append(el('strong',row.name),el('p',`${row.persons.map(id=>this.hass.states[id]?.attributes?.friendly_name??id).join(', ')} · ${row.meals.filter(m=>m.enabled).length} comidas${row.enabled?'':' · Desactivada'}`));
      const actions=el('div');actions.className='actions';const edit=iconButton('Editar '+row.name,'mdi:pencil'),remove=iconButton('Eliminar '+row.name,'mdi:delete');remove.className='delete';edit.style.background='#ffb74d';edit.style.color='#17212b';edit.style.border='0';
      edit.addEventListener('click',()=>this.open(row));remove.addEventListener('click',()=>{if(confirm('¿Eliminar la rutina «'+row.name+'»?'))void this.write('delete',{routine_id:row.id,revision:row.revision});});actions.append(edit,remove);card.append(info,actions);return card;
    }));this.sync();
  }
  meal(name,time){return {id:crypto.randomUUID(),name,time,days:[0,1,2,3,4,5,6],enabled:true};}
  open(row){
    if(this.busy)return;this.draft=structuredClone(row??{name:'',persons:[],minimum_minutes:15,enabled:true,meals:[this.meal('Desayuno','08:30'),this.meal('Comida','14:30'),this.meal('Cena','21:30')]});
    const root=this.shadowRoot;root.querySelector('#routine-title').textContent=row?'Editar rutina':'Nueva rutina';root.querySelector('#routine-name').value=this.draft.name;root.querySelector('#routine-minimum').value=this.draft.minimum_minutes;root.querySelector('#routine-enabled').checked=this.draft.enabled;root.querySelector('#routine-error').hidden=true;
    const people=[...new Set([...Object.keys(this.hass.states).filter(id=>id.startsWith('person.')),...this.draft.persons])];
    root.querySelector('#routine-people .people').replaceChildren(...(people.length?people.map(id=>{const label=el('label');label.className='check';const box=el('input');box.type='checkbox';box.checked=this.draft.persons.includes(id);box.addEventListener('change',()=>{this.draft.persons=box.checked?[...this.draft.persons,id]:this.draft.persons.filter(p=>p!==id);});label.append(box,el('span',this.hass.states[id]?.attributes?.friendly_name??id));return label;}):[el('p','No hay entidades person disponibles en Home Assistant.')]));
    this.renderMeals();root.querySelector('dialog').showModal();
  }
  renderMeals(){
    this.shadowRoot.querySelector('#routine-meals').replaceChildren(...this.draft.meals.map((meal,index)=>{
      const row=el('div');row.className='meal';const fields=el('div');fields.className='meal-fields';
      const name=el('label','Comida'),input=el('input');input.value=meal.name;input.required=true;input.maxLength=80;input.setAttribute('aria-label','Nombre de comida '+(index+1));input.addEventListener('input',()=>meal.name=input.value);name.append(input);
      const timeLabel=el('label','Hora'),time=el('input');time.type='time';time.required=true;time.value=meal.time;time.setAttribute('aria-label','Hora de comida '+(index+1));time.addEventListener('input',()=>meal.time=time.value);timeLabel.append(time);
      const remove=iconButton('Eliminar comida '+(index+1),'mdi:delete');remove.className='delete';remove.addEventListener('click',()=>{this.draft.meals=this.draft.meals.filter(m=>m!==meal);this.renderMeals();});fields.append(name,timeLabel,remove);
      const week=el('div');week.className='week';days.forEach((text,day)=>{const label=el('label');label.className='check';const box=el('input');box.type='checkbox';box.checked=meal.days.includes(day);box.setAttribute('aria-label',['Lunes','Martes','Miércoles','Jueves','Viernes','Sábado','Domingo'][day]+' de comida '+(index+1));box.addEventListener('change',()=>{meal.days=box.checked?[...meal.days,day]:meal.days.filter(d=>d!==day);});label.append(box,el('span',text));week.append(label);});
      const enabled=el('label');enabled.className='check';const box=el('input');box.type='checkbox';box.checked=meal.enabled;box.setAttribute('aria-label','Activar comida '+(index+1));box.addEventListener('change',()=>meal.enabled=box.checked);enabled.append(box,el('span','Activada'));row.append(fields,week,enabled);return row;
    }));
  }
  async save(){
    const root=this.shadowRoot;this.draft.name=root.querySelector('#routine-name').value;this.draft.minimum_minutes=Number(root.querySelector('#routine-minimum').value);this.draft.enabled=root.querySelector('#routine-enabled').checked;
    const {updated_at,...routine}=this.draft;await this.write('save',{routine});
  }
  async write(action,fields){
    if(this.busy)return;this.busy=true;this.sync();const root=this.shadowRoot;root.querySelectorAll('dialog button').forEach(b=>b.disabled=true);
    try{this.rows=(await this.hass.callWS({type:'improved_shopping_list/routines/'+action,...fields})).routines;root.querySelector('dialog').close();this.render();}
    catch(error){const message=root.querySelector(root.querySelector('dialog').open?'#routine-error':'#status');message.textContent=error.message;message.hidden=false;message.className='error';}
    finally{this.busy=false;root.querySelectorAll('dialog button').forEach(b=>b.disabled=false);this.sync();}
  }
}
customElements.define('isl-meal-routines',MealRoutinesSettings);
