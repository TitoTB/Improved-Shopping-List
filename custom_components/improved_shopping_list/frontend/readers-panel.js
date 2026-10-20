class ImprovedShoppingReaders extends HTMLElement {
  constructor() { super(); this.attachShadow({mode:"open"}); }
  set data(value) { this._data = value; this._render(); }
  connectedCallback() { if (!this._built) this._build(); this._render(); }
  disconnectedCallback() { this.shadowRoot.querySelectorAll("dialog").forEach(dialog => dialog.close()); }

  _build() {
    this.shadowRoot.innerHTML = `
      <style>
        :host{display:block;color:var(--primary-text-color,#20352d)}:host([hidden]),[hidden]{display:none!important}*{box-sizing:border-box}
        h1{font-size:32px;margin:28px 0 12px;letter-spacing:-.03em}h2{font-size:18px;margin:0;overflow-wrap:anywhere}
        p{font-size:13px;line-height:1.6;color:var(--secondary-text-color,#63766b)}button,input,select{font:inherit;color:inherit}
        button{cursor:pointer;padding:10px 14px;min-height:44px;border:1px solid var(--divider-color,#dfe7e1);border-radius:10px;background:transparent}
        button:disabled,input:disabled,select:disabled{opacity:.5;cursor:default}button:focus-visible,input:focus-visible,select:focus-visible{outline:3px solid var(--primary-color,#267052);outline-offset:3px}
        .primary{background:#267052;color:white;border:0}.heading{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap}
        .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:16px;margin-top:24px}article{padding:22px;border:1px solid var(--divider-color,#dfe7e1);border-radius:16px;background:var(--card-background-color,#fff);min-width:0}
        .source,.last{overflow-wrap:anywhere}.badge{display:inline-block;font-size:12px;background:var(--secondary-background-color,#edf4ee);padding:4px 8px;border-radius:20px;margin-top:10px}.actions{display:flex;gap:8px;margin-top:18px}
        .notice{padding:12px 14px;font-size:13px;line-height:1.6;border-radius:10px;background:var(--secondary-background-color,#edf4ee);margin:14px 0}.error{border:1px solid var(--error-color,#bd3636);color:var(--error-color,#bd3636)}
        dialog{color:inherit;background:var(--card-background-color,#fff);width:min(560px,calc(100vw - 28px));max-height:calc(100dvh - 28px);border:1px solid var(--divider-color,#dfe7e1);border-radius:18px;padding:24px}dialog::backdrop{background:rgba(0,0,0,.4)}
        .fields{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin:22px 0}.wide{grid-column:1/-1}label{display:block;font-size:13px;font-weight:600}input:not([type=checkbox]),select{display:block;width:100%;min-height:46px;margin-top:7px;padding:10px 12px;border:1px solid var(--divider-color,#dfe7e1);border-radius:9px;background:var(--card-background-color,#fff)}input[type=checkbox]{width:20px;height:20px;vertical-align:middle;margin-right:8px;accent-color:#267052}.form-actions{display:flex;justify-content:flex-end;gap:10px;margin-top:22px}
        @media(max-width:650px){.grid{grid-template-columns:1fr}.fields{grid-template-columns:1fr}dialog{padding:20px}}
      </style>
      <div class="heading"><h1>Lectores</h1><button id="new-reader" class="primary">Añadir lector</button></div>
      <p>Los lectores funcionan aunque esta interfaz esté cerrada. Configura los códigos y la acción de cada lector en la ficha del producto.</p>
      <div id="readers-error" class="notice error" role="alert" hidden></div><div id="readers-status" class="notice" role="status" hidden></div>
      <p id="readers-admin" hidden>Solo los administradores pueden configurar lectores.</p>
      <button id="reader-suggestions" hidden>Ver códigos desconocidos en Sugerencias</button>
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
          <label><input name="enabled" type="checkbox" checked>Lector activo</label>
        </div>
        <div class="form-actions"><button id="cancel-reader" type="button">Cancelar</button><button id="save-reader" class="primary" type="submit">Guardar lector</button></div>
      </form></dialog>
      <dialog id="remove-reader-dialog" aria-labelledby="remove-reader-title"><h2 id="remove-reader-title">Quitar lector</h2><p id="remove-reader-message"></p><div id="remove-reader-error" class="notice error" role="alert" hidden></div><div class="form-actions"><button id="cancel-remove-reader">Cancelar</button><button id="confirm-remove-reader">Quitar lector</button></div></dialog>`;
    this._built = true;
    const root = this.shadowRoot;
    root.querySelector("#new-reader").addEventListener("click", () => this._open());
    root.querySelector("#cancel-reader").addEventListener("click", () => root.querySelector("#reader-dialog").close());
    root.querySelector("#cancel-remove-reader").addEventListener("click", () => root.querySelector("#remove-reader-dialog").close());
    root.querySelector("#confirm-remove-reader").addEventListener("click", () => void this._remove());
    root.querySelector("#reader-form").addEventListener("submit", event => { event.preventDefault(); void this._save(); });
    root.querySelector("#reader-kind").addEventListener("change", () => this._sourceFields());
    root.querySelector("#reader-source").addEventListener("change", () => this._sourceFields());
    root.querySelector("#reader-suggestions").addEventListener("click", () => this.onSuggestions?.());
    root.querySelectorAll("dialog").forEach(dialog => dialog.addEventListener("cancel", event => { if(this._busy)event.preventDefault(); }));
  }

  _render() {
    if (!this._built || !this._data) return;
    const {hass, readers, settings} = this._data;
    const root = this.shadowRoot;
    const admin = hass.user?.is_admin === true;
    root.querySelector("#new-reader").disabled = !admin || readers.loading;
    root.querySelector("#readers-admin").hidden = admin;
    const error = root.querySelector("#readers-error");error.textContent = readers.error;error.hidden = !readers.error;
    const status = root.querySelector("#readers-status");status.textContent = readers.loading ? "Cargando lectores…" : this._notice ?? "";status.hidden = !status.textContent;
    root.querySelector("#readers-empty").hidden = readers.readers.length > 0 || readers.loading;
    root.querySelector("#reader-suggestions").hidden = !readers.pending.length;
    const select = root.querySelector("[name=list_entity]");const value=select.value;
    const options = settings.entities.map(id => new Option(hass.states[id]?.attributes.friendly_name ?? id,id));
    if(value&&!settings.entities.includes(value))options.push(new Option(`${value} · Lista quitada`,value));
    select.replaceChildren(new Option("Usar lista principal",""),...options);select.value=value;
    const entitySignature=JSON.stringify(Object.keys(hass.states).sort().map(id=>[id,hass.states[id].attributes.friendly_name]));
    if(entitySignature!==this._entitySignature){this._entitySignature=entitySignature;root.querySelector("#reader-entities").replaceChildren(...Object.keys(hass.states).sort().map(id => new Option(hass.states[id].attributes.friendly_name ?? id,id)));}
    root.querySelector("#readers-grid").replaceChildren(...readers.readers.map(reader => {
      const card=document.createElement("article");card.dataset.readerId=reader.id;
      const name=document.createElement("h2");name.textContent=reader.name;
      const source=document.createElement("p");source.className="source";source.textContent=reader.source==="tag"?`NFC · tag_scanned · ${reader.device_id}`:`${reader.kind==="nfc"?"NFC":"Barras / QR"} · ${reader.entity_id}${reader.attribute?` · ${reader.attribute}`:""}`;
      const unavailable=reader.source==="entity"&&(!hass.states[reader.entity_id]||["unknown","unavailable"].includes(hass.states[reader.entity_id].state));
      const badge=document.createElement("span");badge.className="badge";badge.textContent=`${reader.enabled?"Activo":"Desactivado"} · ${reader.cooldown} s${unavailable?" · Entidad no disponible":""}`;
      const target=document.createElement("p");target.textContent=reader.list_entity?`Lista: ${hass.states[reader.list_entity]?.attributes.friendly_name??reader.list_entity}`:"Lista: principal";
      const last=document.createElement("p");last.className="last";last.textContent=reader.last?`${new Date(reader.last.time).toLocaleTimeString("es")} · ${reader.last.product??reader.last.code} · ${reader.last.message}`:"Sin lecturas desde el inicio de Home Assistant.";
      const actions=document.createElement("div");actions.className="actions";
      for(const [text,fn] of [["Editar",()=>this._open(reader)],["Quitar",()=>this._confirmRemove(reader)]]){const button=document.createElement("button");button.textContent=text;button.setAttribute("aria-label",`${text} lector ${reader.name}`);button.disabled=!admin||this._busy;button.addEventListener("click",fn);actions.append(button);}
      card.append(name,source,badge,target,last,actions);return card;
    }));
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
    if(reader){for(const key of ["name","kind","source","entity_id","attribute","device_id","list_entity","cooldown"])form.elements[key].value=reader[key];form.elements.enabled.checked=reader.enabled;}
    this._sourceFields();root.querySelector("#reader-dialog").showModal();form.elements.name.focus();
  }

  _busyState(value) {this._busy=value;this.shadowRoot.querySelectorAll("dialog button").forEach(button=>button.disabled=value);}

  async _save() {
    if(this._busy)return;const root=this.shadowRoot,form=root.querySelector("form");
    const reader={...Object.fromEntries(new FormData(form)),enabled:form.elements.enabled.checked,cooldown:Number(form.elements.cooldown.value)};
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
