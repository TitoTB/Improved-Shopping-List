import { installDialogCloseButtons } from "./dialog-controls.js?v=0.48.0";
import { installToggleStyles } from "./toggle-styles.js?v=0.48.0";

class ImprovedShoppingReaders extends HTMLElement {
  constructor() { super(); this.attachShadow({mode:"open"}); this._toggling = new Map(); }
  set data(value) { this._data = value; this._render(); }
  set active(value) {
    if(this._active===Boolean(value))return;
    this._active=Boolean(value);
    if(!this._active)this.shadowRoot.querySelectorAll('dialog').forEach(dialog=>dialog.close());
  }
  connectedCallback() {
    if (!this._built) this._build();
    this._render();
  }
  disconnectedCallback() { this.shadowRoot.querySelectorAll("dialog").forEach(dialog => dialog.close()); }

  _build() {
    this.shadowRoot.innerHTML = `
      <style>
        :host{display:block;color:var(--primary-text-color,#20352d)}:host([hidden]),[hidden]{display:none!important}*{box-sizing:border-box}
        .heading h2{font-size:20px;margin:0}h2{font-size:18px;margin:0;overflow-wrap:anywhere}
        p{font-size:13px;line-height:1.6;color:var(--secondary-text-color,#63766b)}button,input,select{font:inherit;color:inherit}
        button{cursor:pointer;padding:10px 14px;min-height:44px;border:1px solid var(--divider-color,#dfe7e1);border-radius:10px;background:transparent}
        button:disabled,input:disabled,select:disabled{opacity:.5;cursor:default}button:focus-visible,input:focus-visible,select:focus-visible{outline:3px solid var(--primary-color,#267052);outline-offset:3px}
        .primary{background:#267052;color:white;border:0}.heading{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap}
        .heading-tools{display:flex;align-items:center;gap:8px;margin-left:auto}.icon-button{display:grid;place-items:center;width:44px;height:44px;padding:0}.icon-button ha-icon{--mdc-icon-size:24px}
        .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:16px;margin-top:24px}article{position:relative;display:flex;flex-direction:column;align-items:center;text-align:center;padding:48px 22px 22px;border:1px solid var(--divider-color,#dfe7e1);border-radius:16px;background:var(--card-background-color,#fff);min-width:0}
        .reader-type{display:block;width:64px;height:64px;--mdc-icon-size:64px;margin-bottom:16px}.source,.last{overflow-wrap:anywhere;max-width:100%}.source{margin:8px 0}.last{margin:4px 0 0}.actions{display:flex;justify-content:center;gap:8px;margin-top:18px}.actions button{display:grid;place-items:center;width:40px;height:40px;min-height:40px;padding:8px}.actions ha-icon{--mdc-icon-size:20px}
        .notice{padding:12px 14px;font-size:13px;line-height:1.6;border-radius:10px;background:var(--secondary-background-color,#edf4ee);margin:14px 0}.error{border:1px solid var(--error-color,#bd3636);color:var(--error-color,#bd3636)}
        dialog{color:inherit;background:var(--card-background-color,#fff);width:min(560px,calc(100vw - 28px));max-height:calc(100dvh - 28px);border:1px solid var(--divider-color,#dfe7e1);border-radius:18px;padding:24px}dialog::backdrop{background:rgba(0,0,0,.4)}
        .fields{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin:22px 0}.wide{grid-column:1/-1}label{display:block;font-size:13px;font-weight:600}input:not([type=checkbox]),select{display:block;width:100%;min-height:46px;margin-top:7px;padding:10px 12px;border:1px solid var(--divider-color,#dfe7e1);border-radius:9px;background:var(--card-background-color,#fff)}input[type=checkbox]{width:20px;height:20px;vertical-align:middle;margin-right:8px;accent-color:#267052}.form-actions{display:flex;justify-content:flex-end;gap:10px;margin-top:22px}
        .reader-toggle[type=checkbox]{appearance:none;position:absolute;top:12px;right:12px;width:40px;height:24px;margin:0;padding:0;border:1px solid #b3261e;border-radius:20px;background:#b3261e;cursor:pointer}.reader-toggle::before{content:"";position:absolute;top:3px;left:3px;width:16px;height:16px;border-radius:50%;background:#fff;box-shadow:0 1px 3px rgba(0,0,0,.2);transition:transform .15s}.reader-toggle:checked{background:#267052;border-color:#267052}.reader-toggle:checked::before{transform:translateX(16px)}.reader-toggle:disabled{cursor:default}
        .actions .view{background:#1976d2;color:#fff;border:0}.actions .edit{background:#f9a825;border:0}.actions .danger,#confirm-remove-reader{background:#d32f2f;color:#fff;border:0}
        .live-reading{display:grid;grid-template-columns:auto minmax(0,1fr);gap:12px 18px;font-size:14px}.live-reading dt{font-weight:600}.live-reading dd{margin:0;white-space:pre-wrap;overflow-wrap:anywhere}
        @media(max-width:650px){.grid{grid-template-columns:1fr}.fields{grid-template-columns:1fr}dialog{padding:20px}}
      </style>
      <div class="heading"><h2>Lectores</h2><div class="heading-tools"><button id="new-reader" class="primary icon-button" type="button" aria-label="Añadir lector" title="Añadir lector"><ha-icon icon="mdi:plus-thick" aria-hidden="true"></ha-icon></button></div></div>
      <div id="readers-error" class="notice error" role="alert" hidden></div><div id="readers-status" class="notice" role="status" hidden></div>
      <p id="readers-admin" hidden>Solo los administradores pueden configurar lectores.</p>
      <div id="readers-grid" class="grid"></div><p id="readers-empty" hidden>Añade tu primer lector de códigos de barras, QR o NFC.</p>
      <dialog id="reader-dialog" aria-labelledby="reader-dialog-title"><form id="reader-form">
        <h2 id="reader-dialog-title">Añadir lector</h2><div id="reader-form-error" class="notice error" role="alert" hidden></div>
        <div class="fields">
          <label class="wide">Nombre del lector<input name="name" required maxlength="100"></label>
          <div><label for="reader-kind">Tipo de lector</label><select id="reader-kind" name="kind"><option value="barcode">Código de barras / QR</option><option value="nfc">NFC</option></select></div>
          <div><label for="reader-source">Fuente de lectura</label><select id="reader-source" name="source"><option value="entity">Entidad de Home Assistant</option><option value="tag">Evento NFC tag_scanned</option></select></div>
          <label class="wide" data-entity-field>Entidad del lector<input name="entity_id" list="reader-entities" placeholder="sensor.lector_cb_codigo_leido" maxlength="255"></label><datalist id="reader-entities"></datalist>
          <label class="wide" data-entity-field>Atributo del código (opcional)<input name="attribute" maxlength="100" placeholder="Vacío para utilizar el estado de la entidad"></label>
          <label class="wide" data-tag-field hidden>Device ID del lector NFC<input name="device_id" maxlength="100" placeholder="device_id incluido en el evento tag_scanned"></label>
          <div class="wide"><label for="reader-list">Lista de destino</label><select id="reader-list" name="list_entity"><option value="">Usar lista principal</option></select></div>
          <label>Antirrepetición (segundos)<input name="cooldown" type="number" min="1" max="3600" step="1" value="60" required></label>
          <div><label for="reader-default-action">Acción por defecto</label><select id="reader-default-action" name="default_action"><option value="none">Sin acción</option><option value="add_list">Añadir a la lista de la compra</option><option value="stock_remove">Quitar una unidad al stock</option><option value="stock_add">Añadir una unidad al stock</option></select></div>
        </div>
        <div class="form-actions"><button id="cancel-reader" type="button">Cancelar</button><button id="save-reader" class="primary" type="submit">Guardar lector</button></div>
      </form></dialog>
      <dialog id="remove-reader-dialog" aria-labelledby="remove-reader-title"><h2 id="remove-reader-title">Quitar lector</h2><p id="remove-reader-message"></p><div id="remove-reader-error" class="notice error" role="alert" hidden></div><div class="form-actions"><button id="cancel-remove-reader">Cancelar</button><button id="confirm-remove-reader">Quitar lector</button></div></dialog>
      <dialog id="reader-live-dialog" aria-labelledby="reader-live-title"><h2 id="reader-live-title">Lecturas en directo</h2><p id="reader-live-source"></p><div aria-live="polite" aria-atomic="true"><p id="reader-live-notice"></p><dl class="live-reading" id="reader-live-fields"><dt>Código</dt><dd id="reader-live-code"></dd><dt>Producto</dt><dd id="reader-live-product"></dd><dt>Resultado</dt><dd id="reader-live-result"></dd><dt>Última lectura</dt><dd id="reader-live-time"></dd></dl></div><div class="form-actions"><button id="close-reader-live" type="button">Cerrar</button></div></dialog>`;
    this._built = true;
    const root = this.shadowRoot;
    installDialogCloseButtons(root);
    installToggleStyles(root);
    root.querySelector("#new-reader").addEventListener("click", () => this._open());
    root.querySelector("#cancel-reader").addEventListener("click", () => root.querySelector("#reader-dialog").close());
    root.querySelector("#cancel-remove-reader").addEventListener("click", () => root.querySelector("#remove-reader-dialog").close());
    root.querySelector("#close-reader-live").addEventListener("click", () => root.querySelector("#reader-live-dialog").close());
    root.querySelector("#reader-live-dialog").addEventListener("close", () => { this._liveReaderId = null; });
    root.querySelector("#confirm-remove-reader").addEventListener("click", () => void this._remove());
    root.querySelector("#reader-form").addEventListener("submit", event => { event.preventDefault(); void this._save(); });
    root.querySelector("#reader-kind").addEventListener("change", () => this._sourceFields());
    root.querySelector("#reader-source").addEventListener("change", () => this._sourceFields());
    root.querySelectorAll("dialog").forEach(dialog => dialog.addEventListener("cancel", event => { if(this._busy)event.preventDefault(); }));
  }

  _render() {
    if (!this._built || !this._data) return;
    const {hass, readers, settings} = this._data;
    const root = this.shadowRoot;
    const admin = hass.user?.is_admin === true;
    root.querySelector("#new-reader").disabled = !admin || readers.loading;
    root.querySelector("#readers-admin").hidden = admin;
    const error = root.querySelector("#readers-error");error.textContent = this._toggleError || readers.error;error.hidden = !error.textContent;
    const status = root.querySelector("#readers-status");status.textContent = readers.loading ? "Cargando lectores…" : this._notice ?? "";status.hidden = !status.textContent;
    root.querySelector("#readers-empty").hidden = readers.readers.length > 0 || readers.loading;
    const select = root.querySelector("[name=list_entity]");const value=select.value;
    const options = settings.entities.map(id => new Option(hass.states[id]?.attributes.friendly_name ?? id,id));
    if(value&&!settings.entities.includes(value))options.push(new Option(`${value} · Lista quitada`,value));
    select.replaceChildren(new Option("Usar lista principal",""),...options);select.value=value;
    const entitySignature=JSON.stringify(Object.keys(hass.states).sort().map(id=>[id,hass.states[id].attributes.friendly_name]));
    if(entitySignature!==this._entitySignature){this._entitySignature=entitySignature;root.querySelector("#reader-entities").replaceChildren(...Object.keys(hass.states).sort().map(id => new Option(hass.states[id].attributes.friendly_name ?? id,id)));}
    root.querySelector("#readers-grid").replaceChildren(...readers.readers.map(reader => {
      const card=document.createElement("article");card.dataset.readerId=reader.id;
      const type=document.createElement("ha-icon");type.className="reader-type";type.setAttribute("icon",reader.kind==="nfc"?"mdi:nfc-variant":"mdi:barcode-scan");type.setAttribute("role","img");type.setAttribute("aria-label",reader.kind==="nfc"?"Lector NFC":"Lector de códigos de barras o QR");
      const toggle=document.createElement("input");toggle.type="checkbox";toggle.className="reader-toggle";toggle.setAttribute("role","switch");toggle.setAttribute("aria-label",`Activar lector ${reader.name}`);
      toggle.checked=this._toggling.get(reader.id)??reader.enabled;toggle.title=toggle.checked?"Desactivar lector":"Activar lector";toggle.disabled=!admin||readers.loading||this._busy||this._toggling.has(reader.id);
      toggle.addEventListener("change",()=>void this._toggleReader(reader,toggle.checked));
      const name=document.createElement("h2");name.textContent=reader.name;
      const last=document.createElement("p");last.className="last";last.dataset.lastUsed=reader.id;last.textContent=this._lastUsed(reader);
      const actions=document.createElement("div");actions.className="actions";
      for(const [text,mdi,style,fn] of [["Ver","mdi:eye-outline","view",()=>this._viewReader(reader)],["Editar","mdi:note-edit","edit",()=>this._open(reader)],["Quitar","mdi:delete","danger",()=>this._confirmRemove(reader)]]){const button=document.createElement("button");button.type="button";button.className=style;button.title=`${text} lector ${reader.name}`;button.setAttribute("aria-label",button.title);button.disabled=(text!=="Ver"&&!admin)||readers.loading||this._busy||this._toggling.has(reader.id);const icon=document.createElement("ha-icon");icon.setAttribute("icon",mdi);icon.setAttribute("aria-hidden","true");button.append(icon);button.addEventListener("click",fn);actions.append(button);}
      card.append(type,toggle,name,last,actions);return card;
    }));
    this._renderLiveReading();
  }

  _viewReader(reader) {
    if (reader.source !== "tag") {
      this.dispatchEvent(new CustomEvent("hass-more-info", {
        bubbles: true, composed: true, detail: { entityId: reader.entity_id },
      }));
      return;
    }
    this._liveReaderId = reader.id;
    this._renderLiveReading();
    this.shadowRoot.querySelector("#reader-live-dialog").showModal();
  }

  _renderLiveReading() {
    if (!this._liveReaderId) return;
    const root = this.shadowRoot;
    const reader = this._data.readers.readers.find(item => item.id === this._liveReaderId);
    root.querySelector("#reader-live-title").textContent = reader ? `Lecturas en directo: ${reader.name}` : "Lecturas en directo";
    root.querySelector("#reader-live-source").textContent = reader ? `NFC · ${reader.device_id}` : "";
    root.querySelector("#reader-live-notice").textContent = !reader ? "Este lector ya no está configurado." : reader.last ? "" : "Esperando una lectura…";
    root.querySelector("#reader-live-fields").hidden = !reader?.last;
    root.querySelector("#reader-live-code").textContent = reader?.last?.code ?? "";
    root.querySelector("#reader-live-product").textContent = reader?.last?.product ?? "Sin producto identificado";
    root.querySelector("#reader-live-result").textContent = reader?.last?.message ?? "";
    const timestamp = Date.parse(reader?.last?.time ?? "");
    root.querySelector("#reader-live-time").textContent = Number.isFinite(timestamp) ? new Date(timestamp).toLocaleString() : "";
  }

  _lastUsed(reader) {
    const timestamp=Date.parse(reader.last?.time??"");
    if(!Number.isFinite(timestamp))return "Último uso: —";
    const date=new Date(timestamp), pad=value=>String(value).padStart(2,"0");
    return `Último uso: ${pad(date.getDate())}/${pad(date.getMonth()+1)} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
  }

  async _toggleReader(reader,enabled) {
    if(this._busy||this._toggling.has(reader.id))return;
    this._toggleError="";this._toggling.set(reader.id,enabled);this._render();
    const config={...reader,enabled};delete config.last;
    try{await this._data.readers.save(config);}
    catch(error){this._toggleError=error.message??"No se ha podido cambiar el estado del lector.";}
    finally{this._toggling.delete(reader.id);if(this.isConnected)this._render();}
  }

  _sourceFields() {
    const form=this.shadowRoot.querySelector("form");const nfc=form.elements.kind.value==="nfc";
    form.elements.source.querySelector('[value="tag"]').disabled=!nfc;
    if(!nfc)form.elements.source.value="entity";
    const tag=form.elements.source.value==="tag";
    this.shadowRoot.querySelectorAll("[data-entity-field]").forEach(node=>{node.hidden=tag;node.querySelector("input").disabled=tag;});
    const device=this.shadowRoot.querySelector("[data-tag-field]");device.hidden=!tag;form.elements.device_id.disabled=!tag;
    form.elements.entity_id.required=!tag;form.elements.device_id.required=tag;
  }

  _open(reader) {
    if(this._busy)return;
    const root=this.shadowRoot,form=root.querySelector("form");form.reset();this._editing=reader?structuredClone(reader):null;
    root.querySelector("#reader-dialog-title").textContent=reader?"Editar lector":"Añadir lector";root.querySelector("#reader-form-error").hidden=true;
    if(reader){for(const key of ["name","kind","source","entity_id","attribute","device_id","list_entity","cooldown"])form.elements[key].value=reader[key];form.elements.default_action.value=reader.default_action??"none";}
    this._sourceFields();root.querySelector("#reader-dialog").showModal();form.elements.name.focus();
  }

  _busyState(value) {this._busy=value;this.shadowRoot.querySelectorAll("dialog button").forEach(button=>button.disabled=value);}

  async _save() {
    if(this._busy)return;const root=this.shadowRoot,form=root.querySelector("form");
    const reader={...Object.fromEntries(new FormData(form)),enabled:this._editing?.enabled??true,cooldown:Number(form.elements.cooldown.value)};
    if(this._editing)Object.assign(reader,{id:this._editing.id,revision:this._editing.revision});
    this._busyState(true);root.querySelector("#reader-form-error").hidden=true;
    try{await this._data.readers.save(reader);root.querySelector("#reader-dialog").close();this._notice="Lector guardado.";}
    catch(error){const notice=root.querySelector("#reader-form-error");notice.textContent=error.message??"No se ha podido guardar el lector.";notice.hidden=false;}
    finally{this._busyState(false);this._render();}
  }

  _confirmRemove(reader) {this._removing=structuredClone(reader);const root=this.shadowRoot;root.querySelector("#remove-reader-message").textContent=`Se quitará «${reader.name}» de esta integración. Su entidad y los productos se conservarán.`;root.querySelector("#remove-reader-error").hidden=true;root.querySelector("#remove-reader-dialog").showModal();}
  async _remove() {if(this._busy)return;this._busyState(true);try{await this._data.readers.remove(this._removing);this.shadowRoot.querySelector("#remove-reader-dialog").close();this._notice="Lector quitado.";}catch(error){const notice=this.shadowRoot.querySelector("#remove-reader-error");notice.textContent=error.message??"No se ha podido quitar el lector.";notice.hidden=false;}finally{this._busyState(false);this._render();}}
}

if(!customElements.get("isl-readers"))customElements.define("isl-readers",ImprovedShoppingReaders);
