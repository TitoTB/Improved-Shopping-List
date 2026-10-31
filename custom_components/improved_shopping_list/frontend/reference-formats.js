/** Package contents are commercial metadata, never pantry refill quantities. */
export const contentUnits={uds:'uds',g:'g',kg:'kg',ml:'ml',cl:'cl',l:'l'};
const scales={uds:['uds',1],g:['kg',.001],kg:['kg',1],ml:['l',.001],cl:['l',.01],l:['l',1]};
const key=value=>String(value??'').normalize('NFD').replace(/\p{M}/gu,'').trim().replace(/\s+/g,' ').toLocaleLowerCase('es');
export function barcodeIdentity(value){
  if(typeof value!=='string'||!/^(?:\d{8}|\d{12,14})$/.test(value)||value.length===13&&value.startsWith('2'))return '';
  const sum=[...value.slice(0,-1)].reverse().reduce((total,digit,index)=>total+Number(digit)*(index%2?1:3),0);
  return (10-sum%10)%10===Number(value.at(-1))?value.padStart(14,'0'):'';
}
export function referenceFor(product,store,line){
  const refs=(product?.commercial_references??[]).filter(ref=>ref.active!==false&&(ref.store===store||!ref.store));
  return refs.find(ref=>ref.store===store&&line.reference_id&&(ref.reference_id===line.reference_id||store==='lidl'&&ref.ticket_reference_id===line.reference_id))
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
  if(weightFormat(reference))return {price:Number(price),unit:'kg'};
  const scale=scales[reference.content_unit];
  return reference.content_confirmed&&reference.content_quantity>0&&scale?{price:Number(price)/(reference.content_quantity*scale[1]),unit:scale[0]}:null;
}
export function validReferenceContent(reference){
  const quantity=reference.content_quantity;
  return Number.isFinite(quantity)&&quantity>0&&quantity<=1000000&&Object.hasOwn(contentUnits,reference.content_unit)&&(reference.content_unit!=='uds'||Number.isInteger(quantity));
}
export function weightFormat(reference){
  return Boolean(reference&&reference.sale_mode!=='package'&&(reference.content_quantity==null||reference.content_quantity==='')&&['g','kg'].includes(reference.content_unit));
}
export function validReferenceFormat(reference){return validReferenceContent(reference)||weightFormat(reference);}
export function receiptCatalogPrice(line,reference){
  const rate=line.ticket_measure_price;
  const weighed=weightFormat(reference)||rate&&['g','kg'].includes(rate.unit)&&line.purchased_quantity!=null||line.quantity_estimated&&['g','kg'].includes(line.purchased_unit)&&!reference?.content_quantity;
  if(!weighed)return line.unit_price;
  if(!rate||!scales[rate.unit]||!(rate.quantity>0)||!(rate.price>0))return null;
  return Math.round(rate.price/(rate.quantity*scales[rate.unit][1])*1000000)/1000000;
}
export function recoveredStockQuantity(line,product,store){
  const target=scales[product?.unit];
  if(!target)return null;
  const convert=(quantity,unit)=>{
    const source=scales[unit];
    return Number.isFinite(quantity)&&quantity>0&&source?.[0]===target[0]?Math.round(quantity*source[1]/target[1]*1000)/1000:null;
  };
  if(line.purchased_quantity!=null)return convert(line.purchased_quantity,line.purchased_unit);
  if(line.pack_quantity>0)return convert(line.count*line.pack_quantity,line.pack_unit);
  const ref=referenceFor(product,store,line);
  // Approximate retail presentation weights are not actual purchased weights.
  if(ref?.content_confirmed&&validReferenceContent(ref)&&!/(?:\bgranel\b|\baprox|\bal peso\b)/i.test(ref.name??''))return convert(line.count*ref.content_quantity,ref.content_unit);
  return null;
}
export function referenceContentControls(reference,onChange){
  const row=document.createElement('div');row.className='reference-content-controls';
  const quantityLabel=document.createElement('label');quantityLabel.textContent='Contenido por envase';
  const quantity=document.createElement('input');quantity.type='number';quantity.min='0.001';quantity.max='1000000';quantity.step='any';quantity.value=reference.content_quantity??'';quantity.setAttribute('aria-label','Contenido por envase');quantityLabel.append(quantity);
  const unitLabel=document.createElement('label');unitLabel.textContent='Unidades';
  const unit=document.createElement('select');unit.setAttribute('aria-label','Unidades del envase');unit.append(new Option('Sin especificar',''),...Object.keys(contentUnits).map(value=>new Option(value,value)));unit.value=reference.content_unit??'';unitLabel.append(unit);
  const update=()=>{reference.content_quantity=quantity.value===''?null:Number(quantity.value);reference.content_unit=unit.value;reference.content_confirmed=validReferenceFormat(reference);onChange?.();};
  quantity.addEventListener('input',update);unit.addEventListener('change',update);
  row.append(quantityLabel,unitLabel);return row;
}


/** Stored information only: never fetch missing prices or borrow another EAN's offer. */
export function pendingProductInformation(product,offers=[]){
  const refs=(product?.commercial_references??[]).filter(ref=>ref.active!==false);
  const validPrice=price=>price?.price!==null&&price?.price!==undefined&&price.price!==''&&Number.isFinite(Number(price.price))&&Number(price.price)>=0&&price.currency==='EUR';
  const prices=offers.filter(offer=>offer.catalog_product_id===product?.id&&validPrice(offer));
  const issues=(refs.length?refs:[null]).map(ref=>{
    const missing=[];
    const measure=ref?.measure_price,hasMeasure=validPrice(measure)&&Number(measure.price)>0&&Number.isFinite(measure.quantity)&&measure.quantity>0&&Object.hasOwn(contentUnits,measure.unit??'');
    const hasPrice=validPrice(ref?.last_price)||hasMeasure||!ref?.store&&validPrice(product)||ref?.store&&prices.some(offer=>{
      if(offer.store!==ref.store)return false;
      const code=barcodeIdentity(ref.ean),offeredCode=barcodeIdentity(offer.ean);
      if(code&&offeredCode&&code!==offeredCode)return false;
      if(ref.id&&offer.commercial_reference_id===ref.id)return true;
      if(code&&offeredCode)return code===offeredCode;
      if(offer.reference_id&&[ref.reference_id,ref.ticket_reference_id].filter(Boolean).includes(offer.reference_id))return true;
      return !offer.commercial_reference_id&&!offer.reference_id&&!offer.ean&&refs.filter(other=>other.store===ref.store).length===1;
    });
    if(!hasPrice)missing.push('price');
    const quantity=ref?.content_quantity,unit=ref?.content_unit;
    if(!weightFormat(ref)&&(!Number.isFinite(quantity)||quantity<=0||quantity>1000000||unit==='uds'&&!Number.isInteger(quantity)))missing.push('content_quantity');
    if(!Object.hasOwn(contentUnits,unit??''))missing.push('content_unit');
    return {reference:ref,missing};
  });
  return issues.every(issue=>issue.missing.length)?issues:[];
}
