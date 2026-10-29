/** Package contents are commercial metadata, never pantry refill quantities. */
export const contentUnits={uds:'uds',g:'g',kg:'kg',ml:'ml',cl:'cl',l:'l'};
const scales={uds:['uds',1],g:['kg',.001],kg:['kg',1],ml:['l',.001],cl:['l',.01],l:['l',1]};
const key=value=>String(value??'').normalize('NFD').replace(/\p{M}/gu,'').trim().replace(/\s+/g,' ').toLocaleLowerCase('es');
export function referenceFor(product,store,line){
  const refs=(product?.commercial_references??[]).filter(ref=>ref.active!==false&&(ref.store===store||!ref.store));
  return refs.find(ref=>ref.store===store&&line.reference_id&&ref.reference_id===line.reference_id)
    ??refs.find(ref=>ref.store===store&&line.ean&&ref.ean&&ref.ean.padStart(14,'0')===line.ean.padStart(14,'0'))
    ??refs.find(ref=>!ref.reference_id&&!ref.ean&&ref.store===store&&key(ref.name)===key(line.description||line.name))
    ??refs.find(ref=>!ref.store&&line.ean&&ref.ean.padStart(14,'0')===line.ean.padStart(14,'0'));
}
export function suggestedContent(line){
  const multiple=String(line.description||line.name||'').match(/\b(\d+)\s*[x×]\s*(\d+(?:[.,]\d+)?)\s*(kg|grs?|g|ml|cl|l|uds?|unidades)\b/i);
  if(multiple)return {quantity:Number(multiple[1])*Number(multiple[2].replace(',','.')),unit:({gr:'g',grs:'g',ud:'uds',unidades:'uds'})[multiple[3].toLowerCase()]??multiple[3].toLowerCase()};
  if(Number(line.pack_quantity)>0&&scales[line.pack_unit])return {quantity:Number(line.pack_quantity),unit:line.pack_unit};
  const match=String(line.description||line.name||'').match(/\b(\d+(?:[.,]\d+)?)\s*(kg|grs?|g|ml|cl|litros?|l|uds?\.?|unidades|huevos)\b/i);
  if(!match)return {quantity:null,unit:''};
  const raw=match[2].toLowerCase().replace(/\.$/,'');
  return {quantity:Number(match[1].replace(',','.')),unit:({gr:'g',grs:'g',litro:'l',litros:'l',ud:'uds',unidades:'uds',huevos:'uds'})[raw]??raw};
}
export function packageCost(offer,quantity,unit){
  const pack=scales[offer?.pack_unit],target=scales[unit];
  if(offer&&!offer.format_pending&&pack&&['kg','l'].includes(pack[0])&&unit==='uds'&&quantity>0){const packages=Math.ceil(quantity-1e-9);return {price:Math.round(packages*Number(offer.price)*100)/100,packages};}
  if(!offer||offer.format_pending||!pack||!target||pack[0]!==target[0]||!(Number(offer.pack_quantity)>0)||!(quantity>0))return null;
  const count=Math.ceil(Math.max(0,quantity*target[1]/(Number(offer.pack_quantity)*pack[1])-1e-9));
  return {price:Math.round(count*Number(offer.price)*100)/100,packages:count};
}
export function referenceRate(price,reference){
  const scale=scales[reference.content_unit];
  return reference.content_confirmed&&reference.content_quantity>0&&scale?{price:Number(price)/(reference.content_quantity*scale[1]),unit:scale[0]}:null;
}
export function referenceContentControls(reference,onChange,{confirm=true}={}){
  const row=document.createElement('div');row.className='reference-content-controls';
  const quantityLabel=document.createElement('label');quantityLabel.textContent='Contenido por envase';
  const quantity=document.createElement('input');quantity.type='number';quantity.min='0.001';quantity.max='1000000';quantity.step='any';quantity.value=reference.content_quantity??'';quantity.setAttribute('aria-label','Contenido por envase');quantityLabel.append(quantity);
  const unitLabel=document.createElement('label');unitLabel.textContent='Unidades';
  const unit=document.createElement('select');unit.setAttribute('aria-label','Unidades del envase');unit.append(new Option('Sin confirmar',''),...Object.keys(contentUnits).map(value=>new Option(value,value)));unit.value=reference.content_unit??'';unitLabel.append(unit);
  const checkLabel=document.createElement('label');checkLabel.className='reference-confirm';
  const check=document.createElement('input');check.type='checkbox';check.checked=Boolean(reference.content_confirmed);checkLabel.append(check,document.createTextNode('Formato confirmado'));
  const update=()=>{reference.content_quantity=quantity.value===''?null:Number(quantity.value);reference.content_unit=unit.value;check.disabled=!(reference.content_quantity>0&&reference.content_unit);if(check.disabled)check.checked=false;reference.content_confirmed=confirm?check.checked:!check.disabled;onChange?.();};
  quantity.addEventListener('input',update);unit.addEventListener('change',update);check.addEventListener('change',update);check.disabled=!(reference.content_quantity>0&&reference.content_unit);
  row.append(quantityLabel,unitLabel);if(confirm)row.append(checkLabel);return row;
}
