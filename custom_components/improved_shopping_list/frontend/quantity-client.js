import { ListSettingsSession } from './list-settings-client.js?v=0.53.1';

export function purchaseQuantity(product, record) {
  const unit=product?.purchase_unit??record?.unit??'uds';
  const current=record&&(!product||record.unit===unit)?record:null;
  return {quantity:Number(current?.quantity??product?.unit_quantity??1),unit,
    step:Number(product?.quantity_step??current?.step??1),unit_quantity:Number(product?.unit_quantity??1)};
}

export const quantityLabel=value=>`${new Intl.NumberFormat('es-ES',{maximumFractionDigits:3}).format(value.quantity)} ${value.unit}`;

export class QuantitySession extends ListSettingsSession {
  constructor(getHass,onChange){super(getHass,onChange,'improved_shopping_list/quantities/');this.entries={};}
  _receive(data){this.entries=data.entries??{};this.loaded=true;this.loading=false;this.error='';this.onChange();}
  async adjust(entityId,uid,direction){
    const generation=this._generation,revision=++this._revision;
    const data=await this.getHass().callWS({type:'improved_shopping_list/quantities/adjust',entity_id:entityId,uid,direction});
    if(generation===this._generation&&revision===this._revision)this._receive(data);
  }
}
