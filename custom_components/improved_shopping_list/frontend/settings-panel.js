import { todoEntities, isAvailable } from "./todo-client.js?v=0.6.0";
import { DEFAULT_APPEARANCE, gradientTextColor } from "./list-settings-client.js?v=0.6.0";

class ImprovedShoppingSettings extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
  }

  set data(value) { this._data = value; this._render(); }

  connectedCallback() {
    if (!this._built) this._build();
    this._render();
  }

  _build() {
    this.shadowRoot.innerHTML = `
      <style>
        :host { display:block; color:var(--primary-text-color,#20352d); }
        :host([hidden]),[hidden] { display:none !important; }
        * { box-sizing:border-box; }
        h1 { font-size:32px; letter-spacing:-.03em; margin:28px 0 12px; }
        h2 { font-size:20px; margin:0 0 16px; }
        p { color:var(--secondary-text-color,#63766b); line-height:1.6; font-size:13px; }
        .card { padding:22px; border:1px solid var(--divider-color,#dfe7e1); border-radius:16px; background:var(--card-background-color,#fff); margin-top:20px; }
        button,select,input { font:inherit; min-height:46px; border:1px solid var(--divider-color,#dfe7e1); border-radius:10px; color:inherit; background:transparent; padding:10px 14px; }
        button { cursor:pointer; }
        button:disabled,select:disabled,input:disabled { opacity:.5; cursor:default; }
        button:focus-visible,select:focus-visible,input:focus-visible { outline:3px solid var(--primary-color,#267052); outline-offset:3px; }
        .settings-tabs { display:flex; flex-wrap:wrap; gap:8px; margin:18px 0; }
        .settings-tabs [aria-pressed=true] { background:var(--secondary-background-color,#edf4ee); font-weight:650; }
        .appearance-fields { display:grid; grid-template-columns:1fr 1fr; gap:18px; }
        input[type=color] { display:block; width:100%; padding:5px; cursor:pointer; }
        .appearance-actions { display:flex; justify-content:flex-end; flex-wrap:wrap; gap:10px; margin-top:24px; }
        .preview { display:grid; place-items:center; min-height:120px; border-radius:16px; margin-top:24px; padding:20px; font-weight:650; }
        @media(max-width:540px) { .appearance-fields { grid-template-columns:1fr; } }
        .primary { color:#fff; background:#267052; border:0; }
        .add-row { display:flex; align-items:end; gap:10px; }
        .select-wrap { flex:1; min-width:0; }
        label { display:block; font-size:13px; font-weight:600; margin-bottom:8px; }
        select { width:100%; background:var(--card-background-color,#fff); }
        .lists { display:grid; gap:12px; margin-top:24px; }
        article { display:flex; flex-wrap:wrap; gap:14px; align-items:center; padding:18px; border:1px solid var(--divider-color,#dfe7e1); border-radius:12px; }
        .list-info { flex:1; min-width:150px; overflow-wrap:anywhere; }
        h3 { margin:0; font-size:16px; }
        .entity { margin:5px 0 0; font-size:12px; }
        .badge { display:inline-flex; gap:5px; align-items:center; color:var(--primary-color,#267052); font-size:12px; margin-top:8px; }
        .badge ha-icon { --mdc-icon-size:18px; }
        .actions { display:flex; gap:8px; flex-wrap:wrap; }
        .notice { padding:12px 14px; border-radius:10px; background:var(--secondary-background-color,#edf4ee); font-size:13px; line-height:1.6; margin:14px 0; }
        .error { color:var(--error-color,#bd3636); border:1px solid var(--error-color,#bd3636); }
        @media(max-width:540px) { .card { padding:18px 14px; } .add-row { flex-wrap:wrap; } .select-wrap { flex-basis:100%; } .actions { width:100%; } }
      </style>
      <h1>Ajustes</h1>
      <nav class="settings-tabs" aria-label="Vistas de ajustes"><button id="settings-view-lists" aria-pressed="true">Listas</button><button id="settings-view-appearance" aria-pressed="false">Personalización</button></nav>
      <div id="settings-error" class="notice error" role="alert" hidden></div>
      <div id="settings-status" class="notice" role="status" hidden></div>
      <p id="admin-help" hidden>Necesitas una cuenta administradora de Home Assistant para modificar estos ajustes.</p>
      <section id="settings-lists" class="card" aria-labelledby="settings-lists-title">
        <h2 id="settings-lists-title">Listas de la compra</h2>
        <p>Elige las listas que quieres utilizar y marca una como principal. Quitar una lista de aquí conserva su entidad y sus productos en Home Assistant.</p>
        <div class="add-row"><div class="select-wrap"><label for="todo-entity">Entidad todo</label><select id="todo-entity"></select></div><button id="add-list" class="primary">Añadir lista</button></div>
        <div id="configured-lists" class="lists"></div>
        <p id="settings-empty" hidden>No hay listas añadidas. Añade una entidad todo para empezar.</p>
      </section>
      <section id="settings-appearance" class="card" aria-labelledby="settings-appearance-title" hidden>
        <h2 id="settings-appearance-title">Personalización</h2>
        <p>Personaliza las tarjetas del apartado Lista. Pulsa una tarjeta para marcar o desmarcar su compra.</p>
        <form id="appearance-form">
          <div class="appearance-fields">
            <div><label for="gradient-start">Color inicial del degradado</label><input id="gradient-start" name="gradient_start" type="color" value="#ee524f"></div>
            <div><label for="gradient-end">Color final del degradado</label><input id="gradient-end" name="gradient_end" type="color" value="#b52a27"></div>
            <div><label for="completed-gradient-start">Color inicial de Comprados</label><input id="completed-gradient-start" name="completed_gradient_start" type="color" value="#4faba2"></div>
            <div><label for="completed-gradient-end">Color final de Comprados</label><input id="completed-gradient-end" name="completed_gradient_end" type="color" value="#26857c"></div>
            <div><label for="desktop-columns">Productos por fila (ordenador)</label><select id="desktop-columns" name="columns">${[1,2,3,4,5,6].map(value => `<option value="${value}">${value}</option>`).join("")}</select></div>
            <div><label for="mobile-columns">Productos por fila (móvil)</label><select id="mobile-columns" name="mobile_columns">${[1,2,3,4].map(value => `<option value="${value}">${value}</option>`).join("")}</select></div>
          </div>
          <div id="appearance-preview" class="preview">Vista previa de producto pendiente</div>
          <div id="completed-appearance-preview" class="preview">Vista previa de producto comprado</div>
          <div class="appearance-actions"><button id="reset-appearance" type="button">Restablecer valores</button><button id="save-appearance" class="primary" type="submit">Guardar personalización</button></div>
        </form>
      </section>`;
    this._built = true;
    this.shadowRoot.querySelector("#add-list").addEventListener("click", () => {
      const entity = this.shadowRoot.querySelector("#todo-entity").value;
      if (entity) void this._act("add", entity);
    });
    const root = this.shadowRoot;
    for (const [id, view] of [["settings-view-lists", "lists"], ["settings-view-appearance", "appearance"]]) {
      root.querySelector(`#${id}`).addEventListener("click", () => {
        root.querySelector("#settings-lists").hidden = view !== "lists";
        root.querySelector("#settings-appearance").hidden = view !== "appearance";
        root.querySelector("#settings-view-lists").setAttribute("aria-pressed", String(view === "lists"));
        root.querySelector("#settings-view-appearance").setAttribute("aria-pressed", String(view === "appearance"));
        this._notice = "";
        this._error = "";
        this._render();
      });
    }
    root.querySelector("#appearance-form").addEventListener("input", () => { this._appearanceDirty = true; this._preview(); });
    root.querySelector("#appearance-form").addEventListener("change", () => { this._appearanceDirty = true; this._preview(); });
    root.querySelector("#appearance-form").addEventListener("submit", event => { event.preventDefault(); void this._saveAppearance(); });
    root.querySelector("#reset-appearance").addEventListener("click", () => {
      this._fillAppearance(DEFAULT_APPEARANCE);
      this._appearanceDirty = true;
    });
  }

  _render() {
    if (!this._built || !this._data) return;
    const { hass, settings } = this._data;
    const root = this.shadowRoot;
    const admin = hass?.user?.is_admin === true;
    const locked = !admin || !settings.loaded || settings.loading || this._busy;
    const error = root.querySelector("#settings-error");
    error.textContent = this._error || settings.error;
    error.hidden = !error.textContent;
    const status = root.querySelector("#settings-status");
    status.textContent = settings.loading ? "Cargando ajustes…" : this._notice ?? "";
    status.hidden = !status.textContent;
    root.querySelector("#admin-help").hidden = admin;
    const select = root.querySelector("#todo-entity");
    const previous = select.value;
    const candidates = todoEntities(hass).filter(state => !settings.entities.includes(state.entity_id));
    select.replaceChildren(...(candidates.length ? candidates.map(state => new Option(
      `${state.attributes.friendly_name ?? state.entity_id} · ${state.entity_id}${isAvailable(state) ? "" : " · No disponible"}`, state.entity_id,
    )) : [new Option("No hay más entidades todo disponibles", "")]));
    if (candidates.some(state => state.entity_id === previous)) select.value = previous;
    select.disabled = locked || !candidates.length;
    root.querySelector("#add-list").disabled = locked || !candidates.length;
    const rows = settings.entities.map(entity => {
      const state = hass?.states[entity];
      const name = state?.attributes.friendly_name ?? entity;
      const row = document.createElement("article");
      row.dataset.entityId = entity;
      const info = document.createElement("div");
      info.className = "list-info";
      const title = document.createElement("h3");
      title.textContent = name;
      const id = document.createElement("p");
      id.className = "entity";
      id.textContent = entity + (isAvailable(state) ? "" : " · No disponible");
      info.append(title, id);
      if (entity === settings.primary) {
        const badge = document.createElement("span");
        badge.className = "badge";
        const icon = document.createElement("ha-icon");
        icon.setAttribute("icon", "mdi:star");
        badge.append(icon, document.createTextNode("Principal"));
        info.append(badge);
      }
      const actions = document.createElement("div");
      actions.className = "actions";
      for (const [label, action] of [["Hacer principal", "primary"], ["Quitar", "remove"]]) {
        if (action === "primary" && entity === settings.primary) continue;
        const button = document.createElement("button");
        button.textContent = label;
        button.setAttribute("aria-label", `${label}: ${name}`);
        button.disabled = locked;
        button.addEventListener("click", () => void this._act(action, entity));
        actions.append(button);
      }
      row.append(info, actions);
      return row;
    });
    root.querySelector("#configured-lists").replaceChildren(...rows);
    root.querySelector("#settings-empty").hidden = settings.entities.length > 0 || settings.loading;
    const form = root.querySelector("#appearance-form");
    if (!this._appearanceDirty && !this._busy) this._fillAppearance(settings.appearance);
    // Home Assistant's scoped registry does not implement form.elements iteration.
    for (const control of form.querySelectorAll("input, select, textarea, button")) control.disabled = locked;
  }

  _fillAppearance(appearance) {
    const form = this.shadowRoot.querySelector("#appearance-form");
    for (const [key, value] of Object.entries(appearance)) form.elements[key].value = value;
    this._preview();
  }

  _readAppearance() {
    const form = this.shadowRoot.querySelector("#appearance-form");
    return {
      gradient_start: form.elements.gradient_start.value,
      gradient_end: form.elements.gradient_end.value,
      completed_gradient_start: form.elements.completed_gradient_start.value,
      completed_gradient_end: form.elements.completed_gradient_end.value,
      columns: Number(form.elements.columns.value),
      mobile_columns: Number(form.elements.mobile_columns.value),
    };
  }

  _preview() {
    const appearance = this._readAppearance();
    const preview = this.shadowRoot.querySelector("#appearance-preview");
    preview.style.background = `linear-gradient(${appearance.gradient_start},${appearance.gradient_end})`;
    preview.style.color = gradientTextColor(appearance.gradient_start, appearance.gradient_end);
    const completed = this.shadowRoot.querySelector("#completed-appearance-preview");
    completed.style.background = `linear-gradient(${appearance.completed_gradient_start},${appearance.completed_gradient_end})`;
    completed.style.color = gradientTextColor(appearance.completed_gradient_start, appearance.completed_gradient_end);
  }

  async _saveAppearance() {
    if (this._busy) return;
    const appearance = this._readAppearance();
    this._busy = true;
    this._error = "";
    this._notice = "";
    this._render();
    try {
      await this.onAppearance(appearance);
      this._appearanceDirty = false;
      this._notice = "Personalización guardada.";
    } catch (error) {
      this._error = error.message ?? "No se ha podido guardar la personalización.";
    } finally { this._busy = false; this._render(); }
  }

  async _act(action, entity) {
    if (this._busy) return;
    this._busy = true;
    this._error = "";
    this._notice = "";
    this._render();
    try {
      await this.onAction(action, entity);
      this._notice = "Ajustes guardados.";
    } catch (error) {
      this._error = error.message ?? "No se han podido guardar los ajustes.";
    } finally { this._busy = false; this._render(); }
  }
}

if (!customElements.get("isl-settings")) customElements.define("isl-settings", ImprovedShoppingSettings);
