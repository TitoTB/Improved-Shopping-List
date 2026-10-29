import { CarrefourAccountPanel } from "./carrefour-account.js?v=0.49.1";
class DiaAccountPanel extends CarrefourAccountPanel {
  get providerId(){return "dia";}
  get providerName(){return "DIA";}
  async _action(action,fields){await super._action(action,fields);if(action==="login"&&this._status.connected)this.shadowRoot.querySelector("#login-dialog").close();}
}
if(!customElements.get("isl-dia-account"))customElements.define("isl-dia-account",DiaAccountPanel);
