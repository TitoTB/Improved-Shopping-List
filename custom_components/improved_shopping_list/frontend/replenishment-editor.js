import './meal-consumption.js?v=0.71.0';
export const replenishmentMarkup=`<style>
#product-replenishment .replenishment-content>.replenishment-row,#replenishment-fields>.replenishment-row,#replenishment-usage>.replenishment-row{display:grid;grid-template-columns:minmax(0,1fr) minmax(110px,42%);align-items:center;gap:12px;margin:0;grid-column:1/-1;}
#replenishment-fields{grid-template-columns:minmax(0,1fr);gap:16px;margin-top:16px;}
#replenishment-usage{display:grid;grid-template-columns:minmax(0,1fr);gap:12px;}
#product-replenishment .replenishment-row>input,#product-replenishment .replenishment-row>select{width:100%;max-width:none;margin:0;min-width:0;}
#product-replenishment .replenishment-number{display:flex;align-items:center;border:1px solid var(--divider-color,#465269);border-radius:10px;min-width:0;overflow:hidden;}
#product-replenishment .replenishment-number input{width:100%;min-width:0;flex:1;border:0;background:transparent;margin:0;padding-inline:10px;appearance:textfield;}
#product-replenishment .replenishment-number input::-webkit-inner-spin-button,#product-replenishment .replenishment-number input::-webkit-outer-spin-button{-webkit-appearance:none;margin:0;}
#product-replenishment .replenishment-number>span{flex:none;padding-right:10px;font-size:13px;font-weight:400;max-width:60px;overflow:hidden;text-overflow:ellipsis;}
#replenishment-minimum{display:grid;grid-template-columns:minmax(0,1fr) minmax(80px,30%);gap:10px;align-items:center;}
#replenishment-minimum>label{display:flex;align-items:center;gap:8px;margin:0;min-width:0;}
#replenishment-minimum input[type=checkbox]{flex:none;width:20px;min-height:20px;padding:0;margin:0;}
</style><details class="wide replenishment-block" id="product-replenishment"><summary><ha-icon icon="mdi:reload" aria-hidden="true"></ha-icon>Reposición automática</summary><div class="replenishment-content">
  <label class="replenishment-row">Reposición automática<select data-replenishment="mode" aria-label="Reposición automática" disabled><option value="manual">Desactivada</option><option value="perishable">Perecedero</option><option value="usage">Consumo registrado</option><option value="meals">Consumo por comidas</option></select></label>
  <p id="replenishment-status" class="helper" role="status"></p>
  <div id="replenishment-fields" class="fields" hidden>
    <label id="replenishment-days" class="replenishment-row">Comprar cada (días)<input data-replenishment="days" aria-label="Días de recurrencia" type="number" min="1" max="3650" step="1" required></label>
    <div id="replenishment-usage" class="wide" hidden>
      <label class="replenishment-row">Entidad de consumo<input data-replenishment="usage_entity" list="replenishment-entities" required></label><datalist id="replenishment-entities"></datalist>
      <label class="replenishment-row">Estado que representa un uso<input data-replenishment="usage_state" required></label>
      <label class="replenishment-row">Cantidad consumida por uso<span class="replenishment-number"><input data-replenishment="usage_amount" aria-label="Cantidad consumida por uso" type="number" min="0.001" max="1000000" step="0.001" required><span data-stock-unit></span></span></label>
    </div>
    <isl-meal-consumption class="wide" hidden></isl-meal-consumption>
    <label class="replenishment-row">Cantidad predeterminada de reposición<span class="replenishment-number"><input data-replenishment="refill_quantity" aria-label="Cantidad predeterminada de reposición" type="number" min="0.001" max="1000000" step="0.001" required><span data-stock-unit></span></span></label>
    <div id="replenishment-minimum" class="wide"><label><input data-replenishment="reorder_enabled" type="checkbox">Añadir a la lista cuando el stock llegue al mínimo</label><span class="replenishment-number"><input data-replenishment="minimum" aria-label="Mínimo (%)" type="number" min="0" max="100" step="0.001" required><span>%</span></span></div>
    <label id="replenishment-list" class="replenishment-row" hidden>Lista para reponer<select data-replenishment="list_entity" aria-label="Lista para reponer"></select></label>
  </div>
</div></details>`;

const defaults={mode:'manual',days:7,unit:'uds',refill_quantity:1,reorder_enabled:false,reorder_at:0,reorder_percent:0,usage_entity:'',usage_state:'',usage_amount:1,list_entity:''};
export class ReplenishmentEditor {
  constructor(root,getHass){
    this.root=root;this.getHass=getHass;
    root.querySelector("isl-meal-consumption").addEventListener("change",()=>this.dirty=true);
    root.querySelector('#product-replenishment').addEventListener('input',event=>{
      if(!event.target.matches('[data-replenishment]'))return;
      this.dirty=true;
      this.render();
    });
  }
  field(key){return this.root.querySelector(`[data-replenishment="${key}"]`);}
  reset(product){
    this.generation=(this.generation||0)+1;this.product=product;this.loaded=false;this.loading=false;this.dirty=false;this.revision=0;this.listCount=0;
    this.set({...defaults,mode:product?.recurrence?.enabled?'perishable':'manual',days:product?.recurrence?.days??7});
    this.field('mode').disabled=true;this.root.querySelector('#replenishment-status').textContent='';this.root.querySelector('#replenishment-status').classList.remove('error');
  }
  set(config){
    this.config={...defaults,...config};this.revision=config.config_revision??0;
    this.root.querySelector("isl-meal-consumption").reset(config.meal_rules??[]);
    for(const key of Object.keys(defaults)){
      if(['reorder_at','reorder_percent','list_entity','unit'].includes(key))continue;
      if(key==='reorder_enabled')this.field(key).checked=this.config[key];else this.field(key).value=this.config[key];
    }
    const percent=this.config.mode==='perishable'||this.config.reorder_basis==='percent'?this.config.reorder_percent:this.config.reorder_at/this.config.refill_quantity*100;
    this.field('minimum').value=Math.round(percent*1000)/1000;
    this.render();
  }
  async load(){
    if(this.loaded||this.loading)return;this.loading=true;
    const generation=this.generation,hass=this.getHass(),status=this.root.querySelector('#replenishment-status');status.textContent='Cargando reposición…';
    try{
      const [stock,settings]=await Promise.all([hass.callWS({type:'improved_shopping_list/stock/get'}),hass.callWS({type:'improved_shopping_list/settings/get'})]);
      if(generation!==this.generation)return;
      const current=(stock.items??[]).find(item=>this.product?.id&&item.catalog_product_id===this.product.id);
      this.set({...this.config,unit:this.product?.purchase_unit??'uds',...current});
      this.listCount=(settings.entities??[]).length;
      const list=this.field('list_entity'),target=this.listCount===1?settings.entities[0]:current?.list_entity||settings.primary_entity||'';
      list.replaceChildren(...(settings.entities??[]).map(id=>new Option(hass.states[id]?.attributes?.friendly_name??id,id)));
      if(target&&![...list.options].some(option=>option.value===target))list.add(new Option(target+' · No disponible',target));
      if(!list.options.length)list.add(new Option('No hay listas configuradas',''));
      if(target)list.value=target;
      this.root.querySelector('#replenishment-entities').replaceChildren(...Object.entries(hass.states).filter(([id])=>!id.startsWith('todo.')).map(([id,state])=>new Option(state.attributes?.friendly_name??id,id)));
      this.loaded=true;this.field('mode').disabled=false;status.textContent='';this.render();
    }catch(error){if(generation===this.generation){status.textContent=error.message??'No se ha podido cargar la reposición.';status.classList.add('error');}}
    finally{if(generation===this.generation)this.loading=false;}
  }
  render(){
    const mode=this.field('mode').value,active=mode!=='manual',perishable=mode==='perishable',usage=mode==='usage';
    const meals=this.root.querySelector('isl-meal-consumption');meals.hass=this.getHass();meals.unit=this.config.unit;meals.active=this.loaded&&mode==='meals';
    this.root.querySelectorAll('[data-stock-unit]').forEach(span=>{span.textContent=this.config.unit;span.title=this.config.unit;});
    this.root.querySelector('#replenishment-list').hidden=this.listCount<=1;
    this.field('mode').disabled=!this.loaded;
    this.root.querySelector('#replenishment-fields').hidden=!active;
    this.root.querySelector('#replenishment-days').hidden=!perishable;
    this.root.querySelector('#replenishment-usage').hidden=!usage;
    for(const key of ['days','refill_quantity','usage_entity','usage_state','usage_amount','reorder_enabled','minimum','list_entity']){
      this.field(key).disabled=!this.loaded||!active||key==='days'&&!perishable||key.startsWith('usage_')&&!usage||key==='minimum'&&!this.field('reorder_enabled').checked;
    }
    this.field('list_entity').required=active&&this.listCount>1&&(perishable||this.field('reorder_enabled').checked);
  }
  payload(){
    if(!this.dirty)return undefined;
    if(!this.loaded)throw new Error('Espera a que se cargue la reposición.');
    const config={...defaults,...Object.fromEntries(Object.keys(defaults).filter(key=>!['reorder_at','reorder_percent','unit'].includes(key)).map(key=>[key,key==='reorder_enabled'?this.field(key).checked:['days','refill_quantity','usage_amount'].includes(key)?Number(this.field(key).value):this.field(key).value]))};
    config.unit=this.config.unit;config.reorder_at=this.config.reorder_at;config.reorder_percent=Number(this.field('minimum').value);config.reorder_basis=config.mode==='manual'?(this.config.reorder_basis??'quantity'):'percent';
    if(config.mode!=='manual'&&(config.mode==='perishable'||config.reorder_enabled)&&!config.list_entity)throw new Error('Añade una lista de compra en Ajustes → Listas para configurar la reposición.');
    if(config.mode==='manual')config.reorder_enabled=false;
    const meals=this.root.querySelector('isl-meal-consumption');config.meal_rules=config.mode==='meals'?meals.validate():meals.value;
    return {config_revision:this.revision,config};
  }
}
