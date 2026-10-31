const el=(tag,text)=>{const n=document.createElement(tag);if(text!=null)n.textContent=text;return n;};
class MealConsumption extends HTMLElement {
  constructor(){super();this.attachShadow({mode:'open'});this._rules=[];this.routines=[];this.generation=0;}
  connectedCallback(){if(!this.built){this.built=true;this.shadowRoot.innerHTML=`<style>:host{display:block;font:inherit;color:inherit}[hidden]{display:none!important}*{box-sizing:border-box}p{font-size:13px;line-height:1.5}.error{color:var(--error-color,#d32f2f)}details{padding:10px;border:1px solid var(--divider-color,#dfe7e1);border-radius:10px;margin:10px 0}summary{font-weight:600;cursor:pointer}.meal{margin-top:14px;border-top:1px solid var(--divider-color,#dfe7e1);padding-top:10px}.row{display:flex;align-items:center;justify-content:space-between;gap:12px}.check{display:flex;align-items:center;gap:8px;flex:1}input{font:inherit;color:inherit;background:transparent;border:1px solid var(--divider-color,#dfe7e1);border-radius:8px;padding:8px;min-height:40px;max-width:100%;width:100px;text-align:center}input[type=checkbox]{width:20px;min-height:20px;margin:0;flex:none;accent-color:#267052}input:disabled{opacity:.5}label{font-size:13px}.person{display:flex;justify-content:space-between;align-items:center;gap:10px;margin-top:10px}.note{font-size:12px;opacity:.7}.delete{background:#d32f2f;color:white;border:0;border-radius:8px;padding:8px;cursor:pointer}</style><p>Se descuenta por cada persona que esté en casa a la hora de la comida. Configura personas y horarios en Ajustes → Rutinas.</p><p id="status" role="status"></p><div id="rows"></div>`;this.render();}}
  set hass(value){this._hass=value;}
  reset(rules=[]){this.generation++;this._rules=structuredClone(rules);this.loaded=false;this.loading=false;this._active=false;if(this.built)this.render();}
  set active(value){this._active=Boolean(value);this.hidden=!this._active;if(this._active&&!this.loaded&&!this.loading)void this.load();}
  get value(){return structuredClone(this._rules);}
  change(){this.dispatchEvent(new Event('change',{bubbles:true,composed:true}));}
  async load(){
    if(!this.built||!this._hass)return;const generation=this.generation;this.loading=true;const status=this.shadowRoot.querySelector('#status');status.className='';status.textContent='Cargando rutinas…';
    try{const data=await this._hass.callWS({type:'improved_shopping_list/routines/get'});if(generation!==this.generation)return;this.routines=data.routines??[];this.loaded=true;status.textContent=this.routines.length?'':'Crea una rutina en Ajustes → Rutinas para seleccionar comidas.';this.render();}
    catch(error){if(generation===this.generation){status.textContent=error.message;status.className='error';}}
    finally{if(generation===this.generation)this.loading=false;}
  }
  validate(){
    if(!this.loaded)throw new Error('Espera a que se carguen las rutinas.');
    if(!this._rules.length)throw new Error('Selecciona al menos una comida para este producto.');
    const invalid=[...this.shadowRoot.querySelectorAll('input:not(:disabled)')].find(input=>!input.checkValidity());
    if(invalid){invalid.closest('details')?.setAttribute('open','');invalid.reportValidity();throw new Error('Revisa las cantidades de consumo por comidas.');}
    return this.value;
  }
  render(){
    if(!this.built)return;const rows=[];const known=new Set();
    for(const routine of this.routines){
      const group=el('details'),title=el('summary',routine.name+(routine.enabled?'':' · Desactivada'));group.append(title);
      for(const meal of routine.meals){
        const key=routine.id+'|'+meal.id;known.add(key);let rule=this._rules.find(r=>r.routine_id===routine.id&&r.meal_id===meal.id);
        const row=el('div');row.className='meal';const line=el('div');line.className='row';const label=el('label');label.className='check';const box=el('input');box.type='checkbox';box.checked=Boolean(rule);box.setAttribute('aria-label',routine.name+' · '+meal.name);label.append(box,el('span',meal.name+' · '+meal.time+(meal.enabled?'':' · Desactivada')));
        const quantity=el('input');quantity.type='number';quantity.min='.001';quantity.max='1000000';quantity.step='.001';quantity.required=true;quantity.value=rule?.amount??1;quantity.disabled=!rule;quantity.setAttribute('aria-label','Cantidad por persona en '+routine.name+' · '+meal.name);
        const people=el('details');people.hidden=!rule;people.append(el('summary','Cantidades distintas por persona'));
        for(const person of routine.persons){const personLabel=el('label');personLabel.className='person';const input=el('input');input.type='number';input.min='0';input.max='1000000';input.step='.001';input.dataset.person=person;input.value=rule?.person_amounts?.[person]??'';input.placeholder='Predeterminada';input.disabled=!rule;const name=this._hass?.states[person]?.attributes?.friendly_name??person;input.setAttribute('aria-label','Cantidad de '+name+' en '+meal.name);input.addEventListener('input',()=>{if(!rule)return;rule.person_amounts??={};if(input.value==='')delete rule.person_amounts[person];else rule.person_amounts[person]=Number(input.value);this.change();});personLabel.append(el('span',name),input);people.append(personLabel);}
        box.addEventListener('change',()=>{
          if(box.checked){rule={routine_id:routine.id,meal_id:meal.id,amount:Number(quantity.value)||1,person_amounts:Object.fromEntries([...people.querySelectorAll('input')].filter(input=>input.value!=='').map(input=>[input.dataset.person,Number(input.value)]))};this._rules.push(rule);}else{this._rules=this._rules.filter(r=>r!==rule);rule=null;}
          quantity.disabled=!box.checked;people.hidden=!box.checked;for(const input of people.querySelectorAll('input'))input.disabled=!box.checked;this.change();
        });
        quantity.addEventListener('input',()=>{if(rule){rule.amount=Number(quantity.value);this.change();}});
        line.append(label,quantity);row.append(line,el('p','Cantidad en las unidades de Stock, por persona y comida.'),people);group.append(row);
      }rows.push(group);
    }
    for(const rule of this._rules.filter(r=>!known.has(r.routine_id+'|'+r.meal_id))){const row=el('p','Comida de una rutina no disponible. No se descontará stock. '),remove=el('button','Quitar asignación');remove.type='button';remove.className='delete';remove.addEventListener('click',()=>{this._rules=this._rules.filter(r=>r!==rule);this.change();this.render();});row.append(remove);rows.push(row);}
    this.shadowRoot.querySelector('#rows').replaceChildren(...rows);
  }
}
customElements.define('isl-meal-consumption',MealConsumption);
