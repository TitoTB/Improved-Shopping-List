import { FEATURES, TodoSession, errorMessage, isAvailable, supports, todoEntities } from "./todo-client.js?v=0.2.0";
import "./catalog-panel.js?v=0.2.0";

const LOGO_URL = new URL("logo.png", import.meta.url).href;

class ImprovedShoppingListPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._session = new TodoSession(() => this._hass, () => this._renderData());
    this._busy = false;
    this._rows = new Map();
    this._view = "shopping";
    this._onVisibility = () => {
      if (document.visibilityState === "visible") void this._session.refresh();
    };
  }

  set hass(value) {
    const previousConnection = this._hass?.connection;
    const previousState = this._hass?.states[this._session.entityId];
    this._hass = value;
    if (!this.isConnected) return;
    if (this._built) this.shadowRoot.querySelector("isl-catalog").hass = value;
    this._ensureStarted();
    this._renderOptions();
    if (previousConnection && previousConnection !== value.connection && this._session.entityId) {
      void this._session.select(this._session.entityId);
    } else if (previousState !== value.states[this._session.entityId]) {
      this._renderData();
    }
  }

  set panel(value) {
    const previousDefault = this._panel?.config?.default_entity;
    this._panel = value;
    this._ensureStarted();
    const nextDefault = value?.config?.default_entity;
    if (this.isConnected && this._hass && previousDefault && previousDefault !== nextDefault) {
      void this._session.select(nextDefault);
    }
  }

  set narrow(value) {
    this.toggleAttribute("narrow", Boolean(value));
  }

  connectedCallback() {
    if (!this._built) this._build();
    document.addEventListener("visibilitychange", this._onVisibility);
    this._started = false;
    this._ensureStarted();
  }

  disconnectedCallback() {
    document.removeEventListener("visibilitychange", this._onVisibility);
    this._session.dispose();
    this._started = false;
  }

  _ensureStarted() {
    if (!this.isConnected || !this._built || !this._hass || !this._panel || this._started) return;
    this._started = true;
    this._renderOptions();
    const initial = this._panel.config?.default_entity ?? todoEntities(this._hass)[0]?.entity_id ?? "";
    void this._session.select(initial);
  }

  _build() {
    // All dynamic product names and provider messages are inserted as text.
    this.shadowRoot.innerHTML = `
      <style>
        :host { display:block; height:100%; overflow:auto; color:var(--primary-text-color,#20352d); background:var(--primary-background-color,#f5f7f5); font-family:var(--paper-font-body1_-_font-family,system-ui,sans-serif); --isl-green:#267052; }
        * { box-sizing:border-box; }
        button,input,select { font:inherit; }
        button { cursor:pointer; }
        button:disabled { cursor:default; opacity:.5; }
        button:focus-visible,input:focus-visible,select:focus-visible,summary:focus-visible { outline:3px solid var(--primary-color,#267052); outline-offset:3px; }
        header { display:flex; align-items:center; gap:12px; padding:16px 24px; border-bottom:1px solid var(--divider-color,#dfe7e1); background:transparent; }
        .menu { border:0; background:transparent; color:inherit; padding:8px; width:44px; height:44px; display:none; }
        :host([narrow]) .menu { display:inline-flex; align-items:center; justify-content:center; }
        .branding { display:flex; align-items:center; gap:10px; min-width:0; }
        .brand-copy { min-width:0; }
        .brand { font-size:16px; font-weight:650; }
        .brand-logo { width:44px; height:44px; object-fit:contain; flex-shrink:0; }
        .version { color:var(--secondary-text-color,#63766b); font-size:12px; margin-left:8px; white-space:nowrap; }
        .section-nav { display:flex; gap:8px; margin-left:auto; }
        .section-nav button { display:inline-flex; align-items:center; gap:8px; padding:10px 12px; min-height:44px; border:0; border-radius:10px; color:var(--secondary-text-color,#63766b); background:transparent; }
        .section-nav button[aria-pressed=true] { background:var(--secondary-background-color,#edf4ee); color:var(--primary-text-color,#20352d); font-weight:650; }
        .section-nav ha-icon { --mdc-icon-size:20px; }
        main { max-width:900px; margin:auto; padding:36px 24px 64px; }
        .eyebrow { text-transform:uppercase; letter-spacing:.13em; font-size:11px; color:var(--secondary-text-color,#63766b); font-weight:700; margin:0 0 10px; }
        h1 { font-size:clamp(30px,5vw,42px); line-height:1.15; letter-spacing:-.04em; margin:0 0 12px; font-weight:650; }
        .intro { color:var(--secondary-text-color,#63766b); margin:0 0 28px; line-height:1.6; }
        .card { background:var(--card-background-color,#fff); border:1px solid var(--divider-color,#dfe7e1); border-radius:18px; padding:22px; margin-bottom:18px; }
        .label { display:block; font-size:13px; font-weight:650; margin:0 0 10px; }
        .selector-row { display:flex; gap:10px; }
        select,input { color:inherit; background:var(--secondary-background-color,#f6f8f6); border:1px solid var(--divider-color,#dfe7e1); border-radius:10px; min-height:48px; padding:10px 12px; min-width:0; }
        select { width:100%; }
        .refresh { flex-shrink:0; min-width:48px; border:1px solid var(--divider-color,#dfe7e1); border-radius:10px; background:transparent; color:inherit; }
        .helper { font-size:12px; color:var(--secondary-text-color,#63766b); line-height:1.6; margin:10px 0 0; }
        form { display:flex; gap:10px; margin-top:22px; }
        .input-wrap { flex:1; min-width:0; }
        input[type=text] { width:100%; }
        .primary { min-height:48px; padding:10px 20px; border:0; border-radius:10px; color:white; background:var(--isl-green); font-weight:650; align-self:end; }
        .list-header { display:flex; justify-content:space-between; align-items:center; gap:12px; margin-bottom:14px; }
        h2 { margin:0; font-size:18px; font-weight:650; }
        .count { padding:5px 10px; border-radius:20px; background:var(--secondary-background-color,#edf4ee); font-size:13px; }
        ul { list-style:none; margin:0; padding:0; }
        li+li { border-top:1px solid var(--divider-color,#e6ece7); }
        .item { display:flex; align-items:center; min-height:62px; gap:14px; padding:10px 0; }
        input[type=checkbox] { appearance:auto; accent-color:var(--isl-green); width:23px; height:23px; min-height:23px; flex-shrink:0; margin:10px; cursor:pointer; }
        input[type=checkbox]:disabled { cursor:default; }
        .item-text { flex:1; min-width:0; overflow-wrap:anywhere; line-height:1.45; }
        .description { display:block; color:var(--secondary-text-color,#63766b); font-size:12px; white-space:pre-wrap; }
        .completed .summary { text-decoration:line-through; color:var(--secondary-text-color,#63766b); }
        .empty { padding:28px 8px; text-align:center; color:var(--secondary-text-color,#63766b); line-height:1.6; }
        .empty strong { display:block; font-size:18px; color:var(--primary-text-color,#20352d); margin-bottom:5px; }
        details { margin-top:24px; }
        summary { cursor:pointer; color:var(--secondary-text-color,#63766b); font-size:14px; padding:10px 0; }
        .notice { line-height:1.6; padding:12px 16px; border-radius:12px; background:var(--secondary-background-color,#edf4ee); margin:0 0 18px; font-size:14px; }
        .error { border:1px solid var(--error-color,#bd3636); color:var(--error-color,#bd3636); }
        [hidden] { display:none !important; }
        .sr-only { position:absolute; width:1px; height:1px; padding:0; overflow:hidden; clip:rect(0,0,0,0); white-space:nowrap; border:0; }
        footer { text-align:center; color:var(--secondary-text-color,#63766b); font-size:12px; line-height:1.7; margin-top:24px; }
        @media(max-width:650px) { header { flex-wrap:wrap; padding:10px 12px; } .branding { flex:1; } .brand-logo { width:36px; height:36px; } .brand { font-size:14px; } .version { font-size:11px; margin-left:6px; } .section-nav { width:100%; justify-content:flex-end; } }
        @media(max-width:540px) { main { padding:26px 14px 40px; } .card { padding:18px 16px; border-radius:14px; } .primary { padding:10px 14px; } }
      </style>
      <header>
        <button class="menu" aria-label="Abrir menú de Home Assistant"><ha-icon icon="mdi:menu"></ha-icon></button>
        <div class="branding"><img class="brand-logo" src="${LOGO_URL}" alt="" width="44" height="44"><div class="brand-copy"><span class="brand">Improved Shopping List</span><span class="version">0.2.0</span></div></div>
        <nav class="section-nav" aria-label="Apartados">
          <button id="nav-shopping" aria-pressed="true"><ha-icon icon="mdi:shopping"></ha-icon>Lista</button>
          <button id="nav-catalog" aria-pressed="false"><ha-icon icon="mdi:view-grid"></ha-icon>Catálogo</button>
        </nav>
      </header>
      <main>
        <div id="shopping-intro"><p class="eyebrow">Tu lista, conectada</p>
        <h1>Vamos a por la compra.</h1>
        <p class="intro">Todo lo que necesitas, en la lista que ya utilizas.</p></div>
        <div id="error" class="notice error" role="alert" hidden></div>
        <div id="status" class="notice" role="status" hidden></div>
        <section class="card" aria-label="Seleccionar lista y añadir productos">
          <label class="label" for="list-select">Lista de la compra</label>
          <div class="selector-row"><select id="list-select"></select><button id="refresh" class="refresh" aria-label="Actualizar lista" title="Actualizar lista"><ha-icon icon="mdi:refresh"></ha-icon></button></div>
          <p id="list-help" class="helper"></p>
          <form id="add-form">
            <div class="input-wrap"><label class="label" for="product-input">Añadir producto</label><input id="product-input" type="text" maxlength="255" placeholder="Por ejemplo, cacao" autocomplete="off" required></div>
            <button id="add-button" class="primary" type="submit">Añadir</button>
          </form>
          <p id="capability-help" class="helper" hidden></p>
        </section>
        <section class="card" aria-labelledby="pending-title" id="items-card">
          <div class="list-header"><h2 id="pending-title">Por comprar</h2><span id="pending-count" class="count">0 productos</span></div>
          <ul id="pending"></ul>
          <div id="empty" class="empty" hidden></div>
          <details id="completed-details"><summary id="completed-summary">Comprados</summary><ul id="completed"></ul></details>
        </section>
        <isl-catalog hidden></isl-catalog>
        <footer>Los cambios se guardan en tu lista de Home Assistant.<br>También los verás en la aplicación de tu proveedor.</footer>
        <div id="announcement" class="sr-only" role="status" aria-live="polite"></div>
      </main>`;
    this._built = true;
    const root = this.shadowRoot;
    root.querySelector("#nav-shopping").addEventListener("click", () => this._switchView("shopping"));
    root.querySelector("#nav-catalog").addEventListener("click", () => this._switchView("catalog"));
    root.querySelector("isl-catalog").onAdd = (product) => this._runAction(
      () => this._session.add(product.name), `${product.name} añadido a la lista.`,
    );
    root.querySelector(".menu").addEventListener("click", () => {
      this.dispatchEvent(new CustomEvent("hass-toggle-menu", { bubbles: true, composed: true }));
    });
    root.querySelector("#list-select").addEventListener("change", (event) => {
      this._actionError = "";
      void this._session.select(event.target.value);
    });
    root.querySelector("#refresh").addEventListener("click", () => {
      this._actionError = "";
      void this._session.refresh();
    });
    root.querySelector("#add-form").addEventListener("submit", (event) => {
      event.preventDefault();
      void this._addItem();
    });
  }

  _switchView(view) {
    this._view = view;
    this._actionError = "";
    const root = this.shadowRoot;
    root.querySelector("#shopping-intro").hidden = view !== "shopping";
    root.querySelector("#items-card").hidden = view !== "shopping";
    root.querySelector("#add-form").hidden = view !== "shopping";
    root.querySelector("isl-catalog").hidden = view !== "catalog";
    root.querySelector("#nav-shopping").setAttribute("aria-pressed", String(view === "shopping"));
    root.querySelector("#nav-catalog").setAttribute("aria-pressed", String(view === "catalog"));
    root.querySelector("footer").textContent = view === "catalog"
      ? "Tu catálogo se guarda en Home Assistant y se comparte entre tus dispositivos."
      : "Los cambios se guardan en tu lista de Home Assistant. También los verás en la aplicación de tu proveedor.";
    this._renderData();
  }

  _renderOptions() {
    if (!this._built || !this._hass) return;
    const select = this.shadowRoot.querySelector("#list-select");
    const entities = todoEntities(this._hass);
    const signature = JSON.stringify(entities.map((state) => [state.entity_id, state.attributes.friendly_name, state.state === "unavailable"]));
    const selected = this._session.entityId || this._panel?.config?.default_entity || "";
    if (signature !== this._optionsSignature || selected !== select.value) {
      this._optionsSignature = signature;
      const options = entities.map((state) => new Option(
        (state.attributes.friendly_name ?? state.entity_id) + (isAvailable(state) ? "" : " · No disponible"), state.entity_id,
      ));
      if (selected && !entities.some((state) => state.entity_id === selected)) {
        options.unshift(new Option(`${selected} · No disponible`, selected));
      }
      if (!options.length) options.push(new Option("No hay listas disponibles", ""));
      select.replaceChildren(...options);
      select.value = selected;
    }
  }

  _renderData() {
    if (!this._built || !this._hass) return;
    this._renderOptions();
    const root = this.shadowRoot;
    const session = this._session;
    const state = this._hass.states[session.entityId];
    const available = isAvailable(state);
    const canCreate = available && supports(state, FEATURES.CREATE);
    const canUpdate = available && supports(state, FEATURES.UPDATE);
    const catalog = root.querySelector("isl-catalog");
    catalog.hass = this._hass;
    catalog.canAdd = canCreate && !this._busy && !session.loading;
    catalog.listName = state?.attributes.friendly_name ?? session.entityId;
    const locked = this._busy || session.loading || !available;
    root.querySelector("#product-input").disabled = locked || !canCreate;
    root.querySelector("#add-button").disabled = locked || !canCreate;
    root.querySelector("#add-button").textContent = this._busy ? "Guardando…" : "Añadir";
    root.querySelector("#refresh").disabled = session.loading || !session.entityId;
    root.querySelector("#list-help").textContent = session.entityId
      ? "Puedes cambiar entre las listas integradas en Home Assistant."
      : "Configura primero una integración de listas, como Shopping List o Bring!.";
    const capabilityHelp = root.querySelector("#capability-help");
    capabilityHelp.hidden = this._view === "catalog" || !available || (canCreate && canUpdate);
    capabilityHelp.textContent = !canCreate
      ? "Esta lista no permite añadir productos desde Home Assistant."
      : "Esta lista permite añadir productos, pero no marcarlos como comprados.";
    const status = root.querySelector("#status");
    status.hidden = available && !session.loading;
    status.textContent = session.loading ? "Cargando tu lista…"
      : session.entityId ? "La lista seleccionada no está disponible. Comprueba su integración o selecciona otra lista."
        : "Todavía no hay una lista seleccionada.";
    const error = root.querySelector("#error");
    const message = this._actionError || session.error;
    error.hidden = !message;
    error.textContent = message;
    const pending = session.items.filter((item) => item.status !== "completed");
    const completed = session.items.filter((item) => item.status === "completed");
    if (this._rowsEntity !== session.entityId) {
      this._rows.clear();
      this._rowsEntity = session.entityId;
    }
    this._usedRows = new Set();
    root.querySelector("#pending-count").textContent = `${pending.length} ${pending.length === 1 ? "producto" : "productos"}`;
    root.querySelector("#items-card").setAttribute("aria-busy", String(session.loading));
    this._renderItems(root.querySelector("#pending"), pending, locked || !canUpdate);
    this._renderItems(root.querySelector("#completed"), completed, locked || !canUpdate);
    for (const key of this._rows.keys()) {
      if (!this._usedRows.has(key)) this._rows.delete(key);
    }
    const details = root.querySelector("#completed-details");
    details.hidden = !completed.length;
    root.querySelector("#completed-summary").textContent = `Comprados (${completed.length})`;
    const empty = root.querySelector("#empty");
    empty.hidden = pending.length > 0 || session.loading || !available || Boolean(session.error);
    if (!empty.hidden) {
      const title = document.createElement("strong");
      title.textContent = "Todo listo por aquí";
      empty.replaceChildren(title, document.createTextNode("Añade lo que necesites para tu próxima compra."));
    }
  }

  _renderItems(container, items, disabled) {
    const focusedUid = this.shadowRoot.activeElement?.dataset.uid;
    const nodes = items.map((item, index) => {
      const key = item.uid ?? `missing:${item.status}:${index}`;
      this._usedRows.add(key);
      let row = this._rows.get(key);
      if (!row) {
        row = document.createElement("li");
        const label = document.createElement("label");
        const checkbox = document.createElement("input");
        checkbox.type = "checkbox";
        checkbox.addEventListener("change", () => {
          const completed = checkbox.checked;
          void this._runAction(() => this._session.setCompleted(row._item, completed), "Lista actualizada.");
        });
        const text = document.createElement("span");
        text.className = "item-text";
        const summary = document.createElement("span");
        summary.className = "summary";
        const description = document.createElement("span");
        description.className = "description";
        text.append(summary, description);
        label.append(checkbox, text);
        row.append(label);
        this._rows.set(key, row);
      }
      row._item = item;
      const label = row.querySelector("label");
      const checkbox = row.querySelector("input");
      label.className = `item${item.status === "completed" ? " completed" : ""}`;
      checkbox.checked = item.status === "completed";
      checkbox.disabled = disabled || !item.uid;
      checkbox.dataset.uid = item.uid ?? "";
      checkbox.setAttribute("aria-label", `${checkbox.checked ? "Volver a poner por comprar" : "Marcar como comprado"}: ${item.summary ?? "Producto"}`);
      const summary = row.querySelector(".summary");
      summary.textContent = item.summary ?? "Producto sin nombre";
      const description = row.querySelector(".description");
      description.textContent = item.description ?? "";
      description.hidden = !item.description;
      return row;
    });
    container.replaceChildren(...nodes);
    if (focusedUid) {
      const checkbox = [...container.querySelectorAll("input")].find((input) => input.dataset.uid === focusedUid);
      checkbox?.focus({ preventScroll: true });
    }
  }

  async _addItem() {
    const input = this.shadowRoot.querySelector("#product-input");
    const summary = input.value.trim();
    if (!summary || this._busy) return;
    const entityId = this._session.entityId;
    const succeeded = await this._runAction(() => this._session.add(summary), "Producto añadido.");
    if (succeeded && entityId === this._session.entityId && input.value.trim() === summary) input.value = "";
    if (this.isConnected && !input.disabled) input.focus();
  }

  async _runAction(action, announcement) {
    if (this._busy) return false;
    this._busy = true;
    this._actionError = "";
    const entityId = this._session.entityId;
    this._renderData();
    try {
      await action();
      if (entityId === this._session.entityId) this.shadowRoot.querySelector("#announcement").textContent = announcement;
      return true;
    } catch (error) {
      if (entityId === this._session.entityId) this._actionError = errorMessage(error);
      return false;
    } finally {
      this._busy = false;
      if (this.isConnected) this._renderData();
    }
  }
}

if (!customElements.get("improved-shopping-list-panel")) {
  customElements.define("improved-shopping-list-panel", ImprovedShoppingListPanel);
}
