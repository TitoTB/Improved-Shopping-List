/** Category management. Product membership stays in the shared catalog. */
class ImprovedShoppingCategories extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._categories = [];
  }

  set categories(value) {
    this._categories = value ?? [];
    this._render();
  }

  create() { this._open(); }

  connectedCallback() {
    if (!this._built) this._build();
    this._render();
  }

  disconnectedCallback() {
    this.shadowRoot.querySelectorAll("dialog").forEach(dialog => dialog.close());
  }

  _build() {
    this.shadowRoot.innerHTML = `
      <style>
        :host { display:block; color:var(--primary-text-color,#20352d); }
        :host([hidden]),[hidden] { display:none !important; }
        :host([editor-only]) .toolbar,:host([editor-only]) #category-notice,:host([editor-only]) #category-grid,:host([editor-only]) #category-empty { display:none; }
        * { box-sizing:border-box; }
        button,input { font:inherit; }
        button { cursor:pointer; min-height:44px; padding:10px 14px; border:1px solid var(--divider-color,#dfe7e1); border-radius:10px; background:transparent; color:inherit; }
        button:disabled { opacity:.5; cursor:default; }
        button:focus-visible,input:focus-visible { outline:3px solid var(--primary-color,#267052); outline-offset:3px; }
        .primary { color:#fff; background:#267052; border:0; font-weight:650; }
        .danger { color:#fff; background:#b3261e; border:0; }
        .toolbar { display:flex; justify-content:flex-end; margin:18px 0; }
        .grid { display:grid; grid-template-columns:repeat(var(--isl-columns,3),minmax(0,1fr)); gap:16px; }
        article { padding:22px 18px 18px; border:1px solid var(--divider-color,#dfe7e1); border-radius:16px; background:var(--card-background-color,#fff); text-align:center; min-width:0; container-type:inline-size; overflow-wrap:anywhere; }
        .category-icon { display:grid; place-items:center; width:min(56px,80cqi); aspect-ratio:1; border-radius:50%; color:#fff; margin:0 auto 14px; }
        .category-icon ha-icon { --mdc-icon-size:clamp(12px,45cqi,30px); }
        h2 { font-size:clamp(9px,15cqi,18px); line-height:1.5; margin:0; overflow-wrap:anywhere; }
        p { color:var(--secondary-text-color,#63766b); line-height:1.6; font-size:13px; }
        article p { font-size:clamp(9px,12cqi,13px); }
        .actions { display:flex; flex-wrap:wrap; gap:8px; justify-content:center; margin-top:18px; }
        .actions button { display:inline-flex; align-items:center; justify-content:center; gap:4px; max-width:100%; padding:6px 4px; font-size:clamp(9px,12cqi,14px); }
        .actions ha-icon { --mdc-icon-size:clamp(10px,18cqi,20px); }
        @container(max-width:110px) { .actions { flex-direction:column; } }
        @container(max-width:65px) { .actions button { flex-direction:column; } }
        .notice { padding:12px 14px; border-radius:10px; background:var(--secondary-background-color,#edf4ee); font-size:13px; line-height:1.6; margin:14px 0; }
        .error { color:var(--error-color,#bd3636); border:1px solid var(--error-color,#bd3636); }
        .empty { text-align:center; border:1px dashed var(--divider-color,#dfe7e1); border-radius:16px; padding:32px 18px; }
        dialog { color:inherit; background:var(--card-background-color,#fff); border:1px solid var(--divider-color,#dfe7e1); border-radius:18px; padding:24px; width:min(460px,calc(100vw - 28px)); max-height:calc(100dvh - 28px); }
        dialog::backdrop { background:rgba(0,0,0,.4); }
        label { display:block; font-size:13px; font-weight:600; margin-top:16px; }
        input { display:block; margin-top:7px; width:100%; min-height:46px; border:1px solid var(--divider-color,#dfe7e1); border-radius:9px; padding:10px 12px; color:inherit; background:var(--card-background-color,#fff); }
        input[type=color] { padding:5px; cursor:pointer; }
        .preview { display:flex; align-items:center; gap:18px; margin-top:20px; }
        .preview label { flex:1; margin:0; }
        .preview .category-icon { margin:0; }
        .form-actions { display:flex; justify-content:flex-end; gap:10px; margin-top:24px; }
        @media(max-width:650px) { .grid { grid-template-columns:repeat(var(--isl-mobile-columns,1),minmax(0,1fr)); } article { padding:18px 6px 12px; } }
      </style>
      <div class="toolbar"><button id="new-category" class="primary">Nueva categoría</button></div>
      <div id="category-notice" class="notice" role="status" hidden></div>
      <div id="category-grid" class="grid"></div>
      <p id="category-empty" class="empty">Crea categorías y elige un icono y un color para reconocer tus productos.</p>
      <dialog id="category-dialog" aria-labelledby="category-dialog-title">
        <form id="category-form">
          <h2 id="category-dialog-title">Nueva categoría</h2>
          <div id="category-error" class="notice error" role="alert" hidden></div>
          <label>Nombre de la categoría<input name="name" required maxlength="80"></label>
          <label>Icono MDI<input name="icon" required maxlength="100" pattern="mdi:[a-z0-9]+(-[a-z0-9]+)*" value="mdi:tag" placeholder="mdi:shopping"></label>
          <div class="preview"><label>Color<input name="color" type="color" value="#64748b"></label><span id="category-preview" class="category-icon"><ha-icon icon="mdi:tag"></ha-icon></span></div>
          <div class="form-actions"><button id="cancel-category" type="button">Cancelar</button><button id="save-category" class="primary" type="submit">Guardar categoría</button></div>
        </form>
      </dialog>
      <dialog id="delete-category-dialog" aria-labelledby="delete-category-title">
        <h2 id="delete-category-title">Eliminar categoría</h2>
        <p id="delete-category-description"></p>
        <div id="delete-category-error" class="notice error" role="alert" hidden></div>
        <div class="form-actions"><button id="cancel-delete-category">Cancelar</button><button id="confirm-delete-category" class="danger">Eliminar categoría</button></div>
      </dialog>`;
    this._built = true;
    const root = this.shadowRoot;
    root.querySelector("#new-category").addEventListener("click", () => this._open());
    root.querySelector("#cancel-category").addEventListener("click", () => root.querySelector("#category-dialog").close());
    root.querySelector("#category-dialog").addEventListener("close", () => this.onClose?.());
    root.querySelector("#cancel-delete-category").addEventListener("click", () => root.querySelector("#delete-category-dialog").close());
    root.querySelector("#confirm-delete-category").addEventListener("click", () => void this._delete());
    root.querySelector("#category-form").addEventListener("submit", event => { event.preventDefault(); void this._save(); });
    root.querySelector("[name=icon]").addEventListener("input", () => this._preview());
    root.querySelector("[name=color]").addEventListener("input", () => this._preview());
    root.querySelectorAll("dialog").forEach(dialog => dialog.addEventListener("cancel", event => { if (this._busy) event.preventDefault(); }));
  }

  _render() {
    if (!this._built) return;
    const root = this.shadowRoot;
    root.querySelector("#category-empty").hidden = this._categories.length > 0;
    const cards = this._categories.map(category => {
      const card = document.createElement("article");
      card.dataset.categoryId = category.id;
      const badge = document.createElement("span");
      badge.className = "category-icon";
      badge.style.backgroundColor = category.color;
      const icon = document.createElement("ha-icon");
      icon.setAttribute("icon", category.icon);
      badge.append(icon);
      const name = document.createElement("h2");
      name.textContent = category.name;
      const count = document.createElement("p");
      const productCount = category.product_count ?? 0;
      count.textContent = `${productCount} ${productCount === 1 ? "producto" : "productos"}`;
      const actions = document.createElement("div");
      actions.className = "actions";
      for (const [label, mdi, action] of [
        ["Editar", "mdi:note-edit", () => this._open(category)],
        ["Eliminar", "mdi:delete", () => this._confirmDelete(category)],
      ]) {
        const button = document.createElement("button");
        button.type = "button";
        button.title = `${label} categoría ${category.name}`;
        button.setAttribute("aria-label", `${label} categoría ${category.name}`);
        const icon = document.createElement("ha-icon");
        icon.setAttribute("icon", mdi);
        icon.setAttribute("aria-hidden", "true");
        button.append(icon);
        button.addEventListener("click", action);
        actions.append(button);
      }
      card.append(badge, name, count, actions);
      return card;
    });
    root.querySelector("#category-grid").replaceChildren(...cards);
  }

  _open(category) {
    if (this._busy) return;
    const root = this.shadowRoot;
    const form = root.querySelector("form");
    form.reset();
    this._editing = category ? structuredClone(category) : null;
    root.querySelector("#category-dialog-title").textContent = category ? "Editar categoría" : "Nueva categoría";
    root.querySelector("#category-error").hidden = true;
    if (category) for (const key of ["name", "icon", "color"]) form.elements[key].value = category[key];
    this._preview();
    root.querySelector("#category-dialog").showModal();
    form.elements.name.focus();
  }

  _preview() {
    const root = this.shadowRoot;
    const form = root.querySelector("form");
    const badge = root.querySelector("#category-preview");
    badge.style.backgroundColor = form.elements.color.value;
    badge.querySelector("ha-icon").setAttribute("icon", /^mdi:[a-z0-9-]+$/.test(form.elements.icon.value) ? form.elements.icon.value : "mdi:tag");
  }

  _confirmDelete(category) {
    if (this._busy) return;
    this._deleting = structuredClone(category);
    const root = this.shadowRoot;
    root.querySelector("#delete-category-description").textContent = `Se eliminará «${category.name}». Sus productos se conservarán sin categoría.`;
    root.querySelector("#delete-category-error").hidden = true;
    root.querySelector("#delete-category-dialog").showModal();
  }

  _setBusy(value) {
    this._busy = value;
    this.shadowRoot.querySelectorAll("dialog button").forEach(button => { button.disabled = value; });
  }

  _notice(text) {
    const notice = this.shadowRoot.querySelector("#category-notice");
    notice.textContent = text;
    notice.hidden = false;
  }

  async _save() {
    if (this._busy) return;
    const root = this.shadowRoot;
    const category = Object.fromEntries(new FormData(root.querySelector("form")));
    if (this._editing) Object.assign(category, { id: this._editing.id, revision: this._editing.revision });
    this._setBusy(true);
    root.querySelector("#category-error").hidden = true;
    try {
      await this.onSave(category);
      root.querySelector("#category-dialog").close();
      this._notice("Categoría guardada.");
      if (!this.hasAttribute("editor-only")) root.querySelector("#new-category").focus();
    } catch (error) {
      const notice = root.querySelector("#category-error");
      notice.textContent = error.message ?? "No se ha podido guardar la categoría.";
      notice.hidden = false;
    } finally { this._setBusy(false); }
  }

  async _delete() {
    if (this._busy) return;
    const root = this.shadowRoot;
    this._setBusy(true);
    try {
      await this.onDelete(this._deleting);
      root.querySelector("#delete-category-dialog").close();
      this._notice("Categoría eliminada. Sus productos se han conservado.");
    } catch (error) {
      const notice = root.querySelector("#delete-category-error");
      notice.textContent = error.message ?? "No se ha podido eliminar la categoría.";
      notice.hidden = false;
    } finally { this._setBusy(false); }
  }
}

if (!customElements.get("isl-categories")) customElements.define("isl-categories", ImprovedShoppingCategories);
