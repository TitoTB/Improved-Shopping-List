import { ListSettingsSession } from "./list-settings-client.js?v=0.57.2";

export class StockSession extends ListSettingsSession {
  constructor(getHass, onChange) {
    super(getHass,onChange,"improved_shopping_list/stock/");
    this.items=[];this.receiptStores={};
  }
  _receive(data) {
    this.items=data.items??[];this.receiptStores=data.receipt_stores??{};
    this.loaded=true;this.loading=false;this.error="";this.onChange();
  }
  async _write(operation,fields) {
    const generation=this._generation;
    const result=await this.getHass().callWS({type:`${this.prefix}${operation}`,...fields});
    if(generation===this._generation)await this.refresh();
    return result;
  }
  add(name) { return this._write("add",{name}); }
  adjust(item,delta) { return this._write("adjust",{item_id:item.id,delta}); }
  save(item,config) { return this._write("save",{item_id:item.id,revision:item.revision,config}); }
  remove(item) { return this._write("remove",{item_id:item.id,revision:item.revision}); }
}
