import { ListSettingsSession } from "./list-settings-client.js?v=0.26.0";

export class ReadersSession extends ListSettingsSession {
  constructor(getHass, onChange) {
    super(getHass, onChange, "improved_shopping_list/readers/");
    this.readers = [];
    this.pending = [];
  }

  _receive(data) {
    this.readers = data.readers ?? [];
    this.pending = data.pending ?? [];
    this.loaded = true;
    this.loading = false;
    this.error = "";
    this.onChange();
  }

  async _write(operation, fields) {
    const generation = this._generation;
    const result = await this.getHass().callWS({type:`${this.prefix}${operation}`, ...fields});
    if (generation === this._generation) await this.refresh();
    return result;
  }

  save(reader) { return this._write("save", {reader}); }
  remove(reader) { return this._write("delete", {reader_id:reader.id, revision:reader.revision}); }
  dismiss(pendingId) { return this._write("dismiss", {pending_id:pendingId}); }
}
