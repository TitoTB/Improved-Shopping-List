export const replenishmentMarkup=`<details class="wide replenishment-block" id="product-replenishment"><summary><ha-icon icon="mdi:reload" aria-hidden="true"></ha-icon>Reposición automática</summary><div class="replenishment-content">
  <label class="replenishment-row">Reposición automática<select data-replenishment="mode" aria-label="Reposición automática" disabled><option value="manual">Desactivada</option><option value="perishable">Perecedero</option><option value="usage">Consumo registrado</option></select></label>
  <p id="replenishment-status" class="helper" role="status"></p>
  <div id="replenishment-fields" class="fields" hidden>
    <label id="replenishment-days">Comprar cada (días)<input data-replenishment="days" aria-label="Días de recurrencia" type="number" min="1" max="3650" step="1" required></label>
    <label>Cantidad predeterminada de reposición<input data-replenishment="refill_quantity" type="number" min="0.001" max="1000000" step="0.001" required></label>
    <label>Unidades de Stock<input data-replenishment="unit" maxlength="32" required></label>
    <div id="replenishment-usage" class="fields wide" hidden>
      <label class="wide">Entidad de consumo<input data-replenishment="usage_entity" list="replenishment-entities" required></label><datalist id="replenishment-entities"></datalist>
      <label>Estado que representa un uso<input data-replenishment="usage_state" required></label>
      <label>Cantidad consumida por uso<input data-replenishment="usage_amount" type="number" min="0.001" max="1000000" step="0.001" required></label>
    </div>
    <label class="wide replenishment-row"><span>Añadir a la lista cuando el stock llegue al mínimo</span><input data-replenishment="reorder_enabled" type="checkbox"></label>
    <label id="replenishment-minimum"><span>Mínimo (%)</span><input data-replenishment="minimum" aria-label="Mínimo (%)" type="number" min="0" max="100" step="0.001" required></label>
    <label>Lista para reponer<select data-replenishment="list_entity"></select></label>
  </div>
</div></details>`;

const defaults={mode:'manual',days:7,unit:'uds',refill_quantity:1,reorder_enabled:false,reorder_at:0,reorder_percent:0,usage_entity:'',usage_state:'',usage_amount:1,list_entity:''};
export class ReplenishmentEditor {
  constructor(root,getHass){
    this.root=root;this.getHass=getHass;
    root.querySelector('#product-replenishment').addEventListener('input',event=>{
      if(!event.target.matches('[data-replenishment]'))return;
      this.dirty=true;
      if(event.target.dataset.replenishment==='mode'){
        this.minimums[this.lastMode==='perishable'?'percent':'quantity']=Number(this.field('minimum').value);
        this.lastMode=this.field('mode').value;
        this.field('minimum').value=this.minimums[this.lastMode==='perishable'?'percent':'quantity'];
      }
      this.render();
    });
  }
  field(key){return this.root.querySelector(`[data-replenishment="${key}"]`);}
  reset(product){
    this.generation=(this.generation||0)+1;this.product=product;this.loaded=false;this.loading=false;this.dirty=false;this.revision=0;
    this.set({...defaults,mode:product?.recurrence?.enabled?'perishable':'manual',days:product?.recurrence?.days??7});
    this.field('mode').disabled=true;this.root.querySelector('#replenishment-status').textContent='';this.root.querySelector('#replenishment-status').classList.remove('error');
  }
  set(config){
    this.config={...defaults,...config};this.revision=config.config_revision??0;
    for(const key of Object.keys(defaults)){
      if(['reorder_at','reorder_percent','list_entity'].includes(key))continue;
      if(key==='reorder_enabled')this.field(key).checked=this.config[key];else this.field(key).value=this.config[key];
    }
    this.minimums={percent:this.config.reorder_percent,quantity:this.config.reorder_at};this.lastMode=this.config.mode;
    this.field('minimum').value=this.config.mode==='perishable'?this.config.reorder_percent:this.config.reorder_at;
    this.render();
  }
  async load(){
    if(this.loaded||this.loading)return;this.loading=true;
    const generation=this.generation,hass=this.getHass(),status=this.root.querySelector('#replenishment-status');status.textContent='Cargando reposición…';
    try{
      const [stock,settings]=await Promise.all([hass.callWS({type:'improved_shopping_list/stock/get'}),hass.callWS({type:'improved_shopping_list/settings/get'})]);
      if(generation!==this.generation)return;
      const current=(stock.items??[]).find(item=>this.product?.id&&item.catalog_product_id===this.product.id);
      this.set({...this.config,...current});
      const list=this.field('list_entity'),target=current?.list_entity||settings.primary_entity||'';
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
    this.field('mode').disabled=!this.loaded;
    this.root.querySelector('#replenishment-fields').hidden=!active;
    this.root.querySelector('#replenishment-days').hidden=!perishable;
    this.root.querySelector('#replenishment-usage').hidden=!usage;
    for(const key of ['days','refill_quantity','unit','usage_entity','usage_state','usage_amount','reorder_enabled','minimum','list_entity']){
      this.field(key).disabled=!this.loaded||!active||key==='days'&&!perishable||key.startsWith('usage_')&&!usage||key==='minimum'&&!this.field('reorder_enabled').checked;
    }
    this.field('list_entity').required=active&&(perishable||this.field('reorder_enabled').checked);
    const label=perishable?'Mínimo (%)':'Stock mínimo';this.field('minimum').setAttribute('aria-label',label);this.field('minimum').max=perishable?'100':'1000000';
    this.root.querySelector('#replenishment-minimum > span').textContent=label;
    this.root.querySelector('#replenishment-minimum').hidden=!this.field('reorder_enabled').checked;
  }
  payload(){
    if(!this.dirty)return undefined;
    if(!this.loaded)throw new Error('Espera a que se cargue la reposición.');
    const config={...defaults,...Object.fromEntries(Object.keys(defaults).filter(key=>!['reorder_at','reorder_percent'].includes(key)).map(key=>[key,key==='reorder_enabled'?this.field(key).checked:['days','refill_quantity','usage_amount'].includes(key)?Number(this.field(key).value):this.field(key).value]))};
    const perishable=config.mode==='perishable';config.reorder_at=perishable?this.minimums.quantity:Number(this.field('minimum').value);config.reorder_percent=perishable?Number(this.field('minimum').value):this.minimums.percent;
    if(config.mode==='manual')config.reorder_enabled=false;
    return {config_revision:this.revision,config};
  }
}
