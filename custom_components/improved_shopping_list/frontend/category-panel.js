/** Category management. Product membership stays in the shared catalog. */
import { installDialogCloseButtons } from "./dialog-controls.js?v=0.69.0";

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
  edit(category) { this._open(category); }
  set products(value) { this._products = value ?? []; }
  set recipes(value) { this._recipes = value ?? []; }

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
        :host([embedded]) .toolbar { display:none; }
        :host([editor-only]) .toolbar,:host([editor-only]) #category-grid,:host([editor-only]) #category-empty { display:none; }
        * { box-sizing:border-box; }
        button,input { font:inherit; }
        button { cursor:pointer; min-height:44px; padding:10px 14px; border:1px solid var(--divider-color,#dfe7e1); border-radius:10px; background:transparent; color:inherit; }
        button:disabled { opacity:.5; cursor:default; }
        button:focus-visible,input:focus-visible { outline:3px solid var(--primary-color,#267052); outline-offset:3px; }
        .primary { color:#fff; background:#267052; border:0; font-weight:650; }
        .danger { color:#fff; background:#d32f2f; border:0; }
        .toolbar { display:flex; justify-content:flex-end; margin:18px 0; }
        .grid { display:grid; grid-template-columns:repeat(min(var(--isl-columns,3),5),minmax(0,1fr)); gap:16px; }
        article { position:relative; align-self:start; width:100%; aspect-ratio:1 / 1; padding:0; border:1px solid var(--divider-color,#dfe7e1); border-radius:16px; background:var(--card-background-color,#fff); text-align:center; min-width:0; min-height:0; container-type:inline-size; overflow:hidden; overflow-wrap:anywhere; }
        .category-content { position:absolute; inset:0; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:clamp(2px,3cqi,10px); padding:clamp(6px,6cqi,22px); }
        .category-icon { display:grid; place-items:center; width:min(56px,80cqi); aspect-ratio:1; border-radius:50%; color:#fff; margin:0 auto 14px; }
        .category-icon ha-icon { --mdc-icon-size:clamp(12px,45cqi,30px); }
        article .category-icon { width:clamp(24px,24cqi,64px); height:clamp(24px,24cqi,64px); margin:0; flex:none; }
        article .category-icon ha-icon { --mdc-icon-size:clamp(16px,15cqi,36px); width:var(--mdc-icon-size); height:var(--mdc-icon-size); }
        h2 { font-size:clamp(9px,15cqi,18px); line-height:1.5; margin:0; overflow-wrap:anywhere; }
        p { color:var(--secondary-text-color,#63766b); line-height:1.6; font-size:13px; }
        article h2 { display:-webkit-box; -webkit-box-orient:vertical; -webkit-line-clamp:2; overflow:hidden; flex-shrink:0; max-width:100%; font-size:clamp(12px,9cqi,24px); line-height:1.2; }
        article p { font-size:clamp(10px,6cqi,14px); line-height:1.2; margin:0; flex-shrink:0; }
        .actions { position:absolute; z-index:2; top:clamp(3px,4cqi,12px); right:clamp(3px,4cqi,12px); display:flex; flex-wrap:nowrap; gap:clamp(2px,2cqi,6px); margin:0; }
        .actions button { --isl-category-action-size:clamp(18px,13cqi,32px); display:inline-flex; align-items:center; justify-content:center; appearance:none; -webkit-appearance:none; flex:none; width:var(--isl-category-action-size); min-width:var(--isl-category-action-size); max-width:var(--isl-category-action-size); height:var(--isl-category-action-size); min-height:var(--isl-category-action-size); max-height:var(--isl-category-action-size); aspect-ratio:1 / 1; margin:0; padding:0; border:0; border-radius:50%; line-height:0; color:#fff; box-shadow:0 2px 6px rgba(0,0,0,.22); }
        .actions .edit { background:#f9a825; }
        .actions button:focus-visible { outline-offset:1px; }
        .actions ha-icon { --mdc-icon-size:clamp(12px,8cqi,20px); display:flex; align-items:center; justify-content:center; width:var(--mdc-icon-size); height:var(--mdc-icon-size); flex:none; line-height:0; }
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
        .form-actions.category-form-actions { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); }
        .category-form-actions button { min-width:0; padding:10px 8px; }
        .category-form-actions #save-category { grid-column:2; }
        @media(max-width:650px) { .grid { grid-template-columns:repeat(min(var(--isl-mobile-columns,1),2),minmax(0,1fr)); } }
        .product-assignment { border:1px solid var(--divider-color,#dfe7e1); border-radius:10px; margin:20px 0 0; padding:12px; min-width:0; }
        #category-product-options { max-height:240px; overflow:auto; margin-top:12px; }
        #category-product-options label { display:flex; align-items:center; gap:10px; margin:0; padding:8px 0; overflow-wrap:anywhere; }
        #category-product-options input { width:18px; height:18px; min-height:18px; margin:0; padding:0; flex:none; }
      </style>
      <div class="toolbar"><button id="new-category" class="primary">Nueva categoría</button></div>
      <div id="category-grid" class="grid"></div>
      <p id="category-empty" class="empty">Crea categorías y elige un icono y un color para reconocer tus productos.</p>
      <dialog id="category-dialog" aria-labelledby="category-dialog-title">
        <form id="category-form">
          <h2 id="category-dialog-title">Nueva categoría</h2>
          <div id="category-error" class="notice error" role="alert" hidden></div>
          <label>Nombre de la categoría<input name="name" required maxlength="80"></label>
          <label>Icono MDI<input name="icon" required maxlength="100" pattern="mdi:[a-z0-9]+(-[a-z0-9]+)*" value="mdi:tag" placeholder="mdi:shopping"></label>
          <div class="preview"><label>Color<input name="color" type="color" value="#64748b"></label><span id="category-preview" class="category-icon"><ha-icon icon="mdi:tag"></ha-icon></span></div>
          <fieldset id="category-products" class="product-assignment" hidden><legend>Productos del catálogo</legend><input id="category-product-search" type="search" aria-label="Buscar productos para asociar" placeholder="Buscar productos"><div id="category-product-options"></div></fieldset>
          <div class="form-actions category-form-actions"><button id="delete-category" class="danger" type="button" hidden>Eliminar categoría</button><button id="save-category" class="primary" type="submit">Guardar categoría</button></div>
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
    installDialogCloseButtons(root);
    root.querySelector("#new-category").addEventListener("click", () => this._open());
    root.querySelector("#category-dialog").addEventListener("close", () => this.onClose?.());
    root.querySelector("#cancel-delete-category").addEventListener("click", () => root.querySelector("#delete-category-dialog").close());
    root.querySelector("#confirm-delete-category").addEventListener("click", () => void this._delete());
    root.querySelector("#delete-category").addEventListener("click", () => { if (this._editing) this._confirmDelete(this._editing); });
    root.querySelector("#category-form").addEventListener("submit", event => { event.preventDefault(); void this._save(); });
    root.querySelector("[name=icon]").addEventListener("input", () => this._preview());
    root.querySelector("[name=color]").addEventListener("input", () => this._preview());
    root.querySelector("#category-product-search").addEventListener("input", () => this._filterProducts());
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
      name.title = category.name;
      const count = document.createElement("p");
      const productCount = category.product_count ?? 0;
      count.textContent = `${productCount} ${productCount === 1 ? "producto" : "productos"}`;
      const actions = document.createElement("div");
      actions.className = "actions";
      for (const [label, mdi, action] of [
        ["Editar", "mdi:note-edit", () => this._open(category)],
      ]) {
        const button = document.createElement("button");
        button.className = label === "Editar" ? "edit" : "danger";
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
      const content = document.createElement("div");
      content.className = "category-content";
      content.append(badge, name, count);
      card.append(content, actions);
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
    root.querySelector("#delete-category").hidden = !this._editing;
    root.querySelector("#category-dialog-title").textContent = category ? "Editar categoría" : "Nueva categoría";
    root.querySelector("#category-error").hidden = true;
    if (category) for (const key of ["name", "icon", "color"]) form.elements[key].value = category[key];
    const assignment = this.hasAttribute("product-assignment");
    root.querySelector("#category-products").hidden = !assignment;
    if (assignment) {
      root.querySelector("#category-dialog-title").textContent = category ? "Editar categoría de sugerencias" : "Nueva categoría de sugerencias";
      const selected = new Set(category?.product_ids ?? []);
      const options = [...(this._products ?? [])].sort((a,b)=>a.name.localeCompare(b.name,"es",{sensitivity:"base"})).map(product=>{
        const label = document.createElement("label"), checkbox = document.createElement("input");
        checkbox.type="checkbox"; checkbox.value=product.id; checkbox.checked=selected.has(product.id);
        label.dataset.productName = product.name;
        label.append(checkbox,document.createTextNode(product.name)); return label;
      });
      const recipeOptions = [...(this._recipes ?? [])].map(recipe=>{
        const label=document.createElement("label"),checkbox=document.createElement("input");checkbox.type="checkbox";checkbox.value=recipe.id;checkbox.dataset.kind="recipe";
        checkbox.checked=(category?.recipe_ids??[]).includes(recipe.id);label.dataset.productName=recipe.name;
        label.append(checkbox,document.createTextNode("Receta · "+recipe.name));return label;
      });
      root.querySelector("#category-product-options").replaceChildren(...options,...recipeOptions);
      root.querySelector("#category-products legend").textContent="Productos y recetas del catálogo";
    }
    this._preview();
    root.querySelector("#category-dialog").showModal();
    form.elements.name.focus();
  }

  _filterProducts() {
    const normalize = value => value.normalize("NFKD").replace(/\p{M}/gu, "").toLocaleLowerCase("es").trim();
    const query = normalize(this.shadowRoot.querySelector("#category-product-search").value);
    for (const label of this.shadowRoot.querySelectorAll("#category-product-options label")) label.hidden = !normalize(label.dataset.productName).includes(query);
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
    root.querySelector("#delete-category-description").textContent = this.hasAttribute("product-assignment") ? `Se eliminará «${category.name}». Sus productos se conservarán en el catálogo.` : `Se eliminará «${category.name}». Sus productos se conservarán sin categoría.`;
    root.querySelector("#delete-category-error").hidden = true;
    root.querySelector("#delete-category-dialog").showModal();
  }

  _setBusy(value) {
    this._busy = value;
    this.shadowRoot.querySelectorAll("dialog button").forEach(button => { button.disabled = value; });
  }

  async _save() {
    if (this._busy) return;
    const root = this.shadowRoot;
    const category = Object.fromEntries(new FormData(root.querySelector("form")));
    if (this.hasAttribute("product-assignment")) {
      category.product_ids = [...root.querySelectorAll("#category-product-options input:checked:not([data-kind=recipe])")].map(input=>input.value);
      category.recipe_ids = [...root.querySelectorAll("#category-product-options input[data-kind=recipe]:checked")].map(input=>input.value);
    }
    if (this._editing) Object.assign(category, { id: this._editing.id, revision: this._editing.revision });
    this._setBusy(true);
    root.querySelector("#category-error").hidden = true;
    try {
      await this.onSave(category);
      root.querySelector("#category-dialog").close();
      if (!this.hasAttribute("editor-only") && !this.hasAttribute("embedded")) root.querySelector("#new-category").focus();
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
      if (this._editing?.id === this._deleting.id) {
        root.querySelector("#category-dialog").close();
        this._editing = null;
      }
    } catch (error) {
      const notice = root.querySelector("#delete-category-error");
      notice.textContent = error.message ?? "No se ha podido eliminar la categoría.";
      notice.hidden = false;
    } finally { this._setBusy(false); }
  }
}

if (!customElements.get("isl-categories")) customElements.define("isl-categories", ImprovedShoppingCategories);
