import { CatalogSession } from "./catalog-client.js?v=0.4.1";
import "./category-panel.js?v=0.4.1";

export const normalizedName = value => String(value ?? "").normalize("NFKC").trim().replace(/\s+/g, " ").toLocaleLowerCase("es");

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

export function imageSource(value) {
  if (!value) return "";
  try {
    const url = new URL(value, location.origin);
    return ["http:", "https:"].includes(url.protocol) ? url.href : "";
  } catch { return ""; }
}

class ImprovedShoppingCatalog extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._catalog = new CatalogSession(() => this._hass, () => this._render());
    this._canAdd = false;
    this._notice = "";
    this._view = "products";
    this._pendingNames = new Set();
    this._listItems = [];
  }

  set hass(value) {
    const previous = this._hass?.connection;
    this._hass = value;
    if (previous && previous !== value.connection) this._started = false;
    this._start();
  }

  set canAdd(value) {
    if (this._canAdd === value) return;
    this._canAdd = value;
    this._renderProducts();
  }

  set listName(value) {
    this._listName = value;
    this._renderSuggestions();
  }

  set readerData(value) {
    this._readers = value;
    this._renderReaderActions();
    this._renderSuggestions();
  }

  showSuggestions() { this._switchView("suggestions"); }

  set listItems(value) {
    const signature = JSON.stringify((value ?? []).map(item => item.summary));
    if (signature === this._listSignature) return;
    this._listSignature = signature;
    this._listItems = value ?? [];
    this._renderSuggestions();
  }

  set pendingItems(value) {
    const names = new Set((value ?? []).map(item => normalizedName(item.summary)).filter(Boolean));
    const signature = JSON.stringify([...names].sort());
    if (signature === this._pendingSignature) return;
    this._pendingSignature = signature;
    this._pendingNames = names;
    this._renderProducts();
  }

  connectedCallback() {
    if (!this._built) this._build();
    this._start();
  }

  disconnectedCallback() {
    this._catalog.stop();
    this._started = false;
    this.shadowRoot.querySelector("dialog")?.close();
  }

  _start() {
    if (!this.isConnected || !this._built || !this._hass || this._started) return;
    this._started = true;
    void this._catalog.start();
  }

  _build() {
    this.shadowRoot.innerHTML = `
      <style>
        :host { display:block; color:var(--primary-text-color,#20352d); }
        :host([hidden]),[hidden] { display:none !important; }
        * { box-sizing:border-box; }
        button,input,select,textarea { font:inherit; }
        button { cursor:pointer; }
        button:disabled { opacity:.5; cursor:default; }
        button:focus-visible,input:focus-visible,select:focus-visible,textarea:focus-visible { outline:3px solid var(--primary-color,#267052); outline-offset:3px; }
        .heading { display:flex; align-items:center; justify-content:space-between; gap:16px; margin:28px 0 12px; }
        .heading-actions { display:flex; align-items:center; gap:8px; margin-left:auto; }
        .catalog-tabs { display:flex; flex-wrap:wrap; gap:8px; margin:18px 0; }
        .catalog-tabs button { display:inline-flex; align-items:center; gap:6px; }
        .catalog-tabs ha-icon { --mdc-icon-size:20px; }
        .suggestions { display:grid; gap:12px; }
        .suggestion { display:flex; align-items:center; gap:16px; padding:16px; border:1px solid var(--divider-color,#dfe7e1); border-radius:14px; background:var(--card-background-color,#fff); }
        .suggestion h2 { flex:1; font-size:17px; overflow-wrap:anywhere; min-width:0; }
        .suggestion .actions { margin:0; flex-shrink:0; }
        @media(max-width:650px) { .suggestion { flex-wrap:wrap; } .suggestion h2 { flex-basis:calc(100% - 48px); } .suggestion .actions { width:100%; } }
        .catalog-tabs button[aria-pressed=true] { background:var(--secondary-background-color,#edf4ee); font-weight:650; }
        h1 { font-size:32px; letter-spacing:-.03em; margin:0; }
        h2 { font-size:23px; margin:0; }
        .helper { color:var(--secondary-text-color,#63766b); font-size:13px; line-height:1.6; margin:8px 0 18px; }
        button { min-height:44px; padding:10px 14px; border:1px solid var(--divider-color,#dfe7e1); border-radius:10px; background:transparent; color:inherit; }
        .primary { background:#267052; color:#fff; border:0; font-weight:650; }
        .filters { display:grid; grid-template-columns:2fr 1fr; gap:12px; margin:24px 0 14px; align-items:end; }
        .category-controls { display:flex; align-items:end; gap:8px; min-width:0; }
        .category-controls label { flex:1; min-width:0; }
        #new-product { display:grid; place-items:center; flex:0 0 46px; width:46px; height:46px; padding:0; }
        #new-product ha-icon { --mdc-icon-size:24px; }
        .product-category-controls { display:flex; align-items:end; gap:8px; }
        .product-category-controls select { flex:1; min-width:0; }
        #add-product-category { display:grid; place-items:center; flex:0 0 46px; width:46px; height:46px; padding:0; }
        #add-product-category ha-icon { --mdc-icon-size:22px; }
        #catalog-refresh { width:44px; padding:10px; flex-shrink:0; }
        label { font-size:13px; font-weight:600; display:block; }
        input,select,textarea { display:block; min-height:46px; width:100%; margin-top:7px; padding:10px 12px; color:inherit; background:var(--card-background-color,#fff); border:1px solid var(--divider-color,#dfe7e1); border-radius:9px; min-width:0; }
        textarea { resize:vertical; min-height:76px; }
        .count { color:var(--secondary-text-color,#63766b); font-size:12px; margin:12px 0; }
        .grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(245px,1fr)); gap:16px; }
        .product { position:relative; display:flex; flex-direction:column; gap:12px; background:var(--card-background-color,#fff); border:1px solid var(--divider-color,#dfe7e1); border-radius:16px; padding:30px 18px 18px; min-width:0; text-align:center; }
        .product.in-list { background:linear-gradient(145deg,rgba(255,85,85,.32),rgba(220,38,38,.12)),var(--card-background-color,#fff); border-color:rgba(220,38,38,.45); }
        .product.in-list,.product.in-list .placeholder,.product.in-list .subtitle,.product.in-list button,.product.in-list ha-icon { color:#fff; }
        .product-top { display:flex; flex-direction:column; gap:14px; align-items:center; }
        .image { width:96px; height:96px; object-fit:contain; border-radius:10px; flex-shrink:0; }
        .placeholder { display:grid; place-items:center; color:var(--secondary-text-color,#63766b); }
        .placeholder ha-icon { --mdc-icon-size:64px; }
        .category-badge { position:absolute; top:12px; right:12px; display:grid; place-items:center; width:32px; height:32px; min-height:32px; padding:0; border:0; border-radius:50%; color:#fff; }
        .category-badge ha-icon { --mdc-icon-size:20px; }
        .title { font-size:17px; line-height:1.4; font-weight:650; margin:0; overflow-wrap:anywhere; text-align:center; }
        .subtitle { color:var(--secondary-text-color,#63766b); font-size:12px; margin:4px 0 0; overflow-wrap:anywhere; }
        .tags { display:flex; flex-wrap:wrap; justify-content:center; gap:5px; }
        .tag { padding:4px 8px; border-radius:20px; font-size:11px; background:var(--secondary-background-color,#edf4ee); }
        .actions { display:flex; gap:8px; margin-top:auto; }
        .actions button { display:inline-flex; align-items:center; justify-content:center; gap:7px; }
        .actions ha-icon { --mdc-icon-size:20px; }
        .actions .primary { flex:1; }
        .product .actions button { flex:1 1 0; min-width:0; min-height:32px; font-size:12px; padding:6px; gap:4px; border-radius:8px; }
        .product .actions ha-icon { --mdc-icon-size:16px; }
        .notice { font-size:13px; line-height:1.6; padding:12px 14px; background:var(--secondary-background-color,#edf4ee); border-radius:10px; margin:14px 0; }
        .error { color:var(--error-color,#bd3636); border:1px solid var(--error-color,#bd3636); }
        .empty { text-align:center; padding:38px 16px; color:var(--secondary-text-color,#63766b); line-height:1.7; border:1px dashed var(--divider-color,#dfe7e1); border-radius:16px; }
        dialog { color:inherit; background:var(--card-background-color,#fff); width:min(640px,calc(100vw - 28px)); max-height:calc(100dvh - 28px); border:1px solid var(--divider-color,#dfe7e1); border-radius:18px; padding:24px; }
        dialog::backdrop { background:rgba(0,0,0,.4); }
        .dialog-heading { display:flex; align-items:center; justify-content:space-between; gap:12px; }
        .fields { display:grid; grid-template-columns:1fr 1fr; gap:16px; margin:22px 0; }
        .wide { grid-column:1/-1; }
        .form-actions { display:flex; justify-content:flex-end; gap:10px; margin-top:22px; }
        @media(max-width:650px) { .filters { grid-template-columns:1fr; } .grid { grid-template-columns:1fr; } .heading { gap:10px; flex-wrap:wrap; } h1 { font-size:28px; } dialog { padding:20px; } }
        @media(max-width:390px) { .fields { grid-template-columns:1fr; } .heading { align-items:flex-start; } }
      </style>
      <div class="heading"><h1>Catálogo</h1><div class="heading-actions"><button id="catalog-refresh" aria-label="Actualizar catálogo" title="Actualizar catálogo"><ha-icon icon="mdi:refresh"></ha-icon></button></div></div>
      <p class="helper">Tus productos, categorías y etiquetas, disponibles para todas tus listas.</p>
      <nav class="catalog-tabs" aria-label="Vistas del catálogo"><button id="view-products" aria-pressed="true"><ha-icon icon="mdi:package-variant"></ha-icon>Productos</button><button id="view-categories" aria-pressed="false"><ha-icon icon="mdi:shape"></ha-icon>Categorías</button><button id="view-suggestions" aria-pressed="false"><ha-icon icon="mdi:creation"></ha-icon>Sugerencias</button></nav>
      <div id="catalog-error" class="notice error" role="alert" hidden></div>
      <div id="catalog-status" class="notice" role="status" hidden></div>
      <section id="products-view">
      <div class="filters">
        <label class="search">Buscar productos<input id="catalog-search" type="search" placeholder="Nombre, marca, código o etiqueta"></label>
        <div class="category-controls"><label>Categoría<select id="category-filter"><option value="">Todas</option></select></label><button id="new-product" class="primary" type="button" aria-label="Nuevo producto" title="Nuevo producto"><ha-icon icon="mdi:plus-thick"></ha-icon></button></div>
      </div>
      <p id="catalog-count" class="count" aria-live="polite"></p>
      <div id="catalog-grid" class="grid"></div>
      <p id="catalog-empty" class="empty" hidden></p>
      </section>
      <isl-categories id="catalog-categories" hidden></isl-categories>
      <section id="suggestions-view" hidden>
        <p id="suggestions-source" class="helper"></p>
        <div id="suggestions-error" class="notice error" role="alert" hidden></div>
        <div id="suggestions-list" class="suggestions"></div>
        <p id="suggestions-empty" class="empty" hidden>No hay sugerencias nuevas en esta lista.</p>
      </section>
      <dialog aria-labelledby="product-dialog-title">
        <form id="product-form">
          <div class="dialog-heading"><h2 id="product-dialog-title">Nuevo producto</h2></div>
          <p class="helper">Solo necesitas un nombre para empezar. Puedes completar el resto más adelante.</p>
          <div id="product-error" class="notice error" role="alert" hidden></div>
          <div class="fields">
            <label class="wide">Nombre del producto<input name="name" required maxlength="160" placeholder="Por ejemplo, Cacao"></label>
            <div><label for="product-category">Categoría</label><div class="product-category-controls"><select id="product-category" name="category"><option value="">Sin categoría</option></select><button id="add-product-category" type="button" aria-label="Nueva categoría" title="Nueva categoría"><ha-icon icon="mdi:plus-thick"></ha-icon></button></div></div>
            <label>Etiquetas<input name="tags" maxlength="850" placeholder="Desayuno, sin gluten"></label>
            <label>Marca<input name="brand" maxlength="100"></label>
            <label>Formato<input name="format" maxlength="100" placeholder="250 g, 1 l, 6 unidades…"></label>
            <label class="wide">Código de barras<input name="barcode" type="text" maxlength="1024"></label>
            <label class="wide">Otros códigos de barras o QR<textarea name="barcodes" maxlength="52000" placeholder="Un código por línea"></textarea></label>
            <label class="wide">Etiquetas NFC<textarea name="nfc_tags" maxlength="52000" placeholder="Un identificador por línea"></textarea></label>
            <div class="wide"><h3>Acciones de los lectores</h3><div id="product-reader-actions"></div><p class="helper">La acción se aplica solo al reconocer este producto. Las acciones de stock quedan guardadas para cuando esté disponible el inventario.</p></div>
            <label>Precio orientativo<input name="price" type="number" min="0" max="1000000" step="0.01" placeholder="Sin precio"></label>
            <label>Moneda<select name="currency"><option value="EUR">EUR · Euro</option><option value="USD">USD · Dólar</option><option value="GBP">GBP · Libra</option></select></label>
            <label class="wide">URL de la imagen<input name="image_url" maxlength="2048" placeholder="https://… o /local/producto.png"></label>
            <label class="wide">Icono del producto<input name="icon" maxlength="100" pattern="mdi:[a-z0-9]+(-[a-z0-9]+)*" placeholder="mdi:shopping"></label>
            <label class="wide">Notas<textarea name="notes" maxlength="1000"></textarea></label>
          </div>
          <div class="form-actions"><button id="cancel-product" type="button">Cancelar</button><button id="save-product" class="primary" type="submit">Guardar producto</button></div>
        </form>
        <isl-categories id="product-category-editor" editor-only></isl-categories>
      </dialog>`;
    this._built = true;
    const root = this.shadowRoot;
    root.querySelector("#new-product").addEventListener("click", () => this._openProduct());
    root.querySelector("#view-products").addEventListener("click", () => this._switchView("products"));
    root.querySelector("#view-categories").addEventListener("click", () => this._switchView("categories"));
    root.querySelector("#view-suggestions").addEventListener("click", () => this._switchView("suggestions"));
    root.querySelector("isl-categories").onSave = category => this._catalog.saveCategory(category);
    root.querySelector("isl-categories").onDelete = category => this._catalog.deleteCategory(category);
    const categoryEditor = root.querySelector("#product-category-editor");
    categoryEditor.onSave = async category => {
      const saved = await this._catalog.saveCategory(category);
      root.querySelector("#product-category").value = saved.name;
      return saved;
    };
    categoryEditor.onClose = () => root.querySelector("#add-product-category").focus();
    root.querySelector("#add-product-category").addEventListener("click", () => categoryEditor.create());
    root.querySelector("#catalog-refresh").addEventListener("click", () => void this._catalog.refresh());
    root.querySelector("#catalog-search").addEventListener("input", () => this._renderProducts());
    root.querySelector("#category-filter").addEventListener("change", () => this._renderProducts());
    root.querySelector("#cancel-product").addEventListener("click", () => root.querySelector("dialog").close());
    root.querySelector("dialog").addEventListener("cancel", (event) => { if (this._saving) event.preventDefault(); });
    root.querySelector("#product-form").addEventListener("submit", (event) => { event.preventDefault(); void this._saveProduct(); });
    this.listName = this._listName;
    this._render();
  }

  _switchView(view) {
    this._view = view;
    const root = this.shadowRoot;
    root.querySelector("#products-view").hidden = view !== "products";
    root.querySelector("#new-product").hidden = view !== "products";
    root.querySelector("isl-categories").hidden = view !== "categories";
    root.querySelector("#suggestions-view").hidden = view !== "suggestions";
    root.querySelector("#view-products").setAttribute("aria-pressed", String(view === "products"));
    root.querySelector("#view-categories").setAttribute("aria-pressed", String(view === "categories"));
    root.querySelector("#view-suggestions").setAttribute("aria-pressed", String(view === "suggestions"));
    this._notice = "";
    this._render();
  }

  _render() {
    if (!this._built) return;
    const root = this.shadowRoot;
    const error = root.querySelector("#catalog-error");
    error.hidden = !this._catalog.error;
    error.textContent = this._catalog.error;
    const status = root.querySelector("#catalog-status");
    status.hidden = !this._catalog.loading && !this._notice;
    status.textContent = this._catalog.loading ? "Cargando catálogo…" : this._notice;
    root.querySelector("#catalog-refresh").disabled = this._catalog.loading;
    const categories = this._catalog.categories.map(category => category.name).sort((a, b) => a.localeCompare(b, "es"));
    this._fillFilter(root.querySelector("#category-filter"), categories);
    const categorySelect = root.querySelector("[name=category]");
    const selectedCategory = categorySelect.value;
    const options = categories.map(category => new Option(category, category));
    if (selectedCategory && !categories.includes(selectedCategory)) options.push(new Option(`${selectedCategory} · No disponible`, selectedCategory));
    categorySelect.replaceChildren(new Option("Sin categoría", ""), ...options);
    categorySelect.value = selectedCategory;
    root.querySelector("isl-categories").categories = this._catalog.categories;
    this._renderProducts();
    this._renderSuggestions();
    this.dispatchEvent(new CustomEvent("catalog-change", {
      detail: { products: this._catalog.products, categories: this._catalog.categories },
    }));
  }

  _renderSuggestions() {
    if (!this._built) return;
    const root = this.shadowRoot;
    const selections = new Map([...root.querySelectorAll("[data-pending-id]")].map(row => [row.dataset.pendingId,row.querySelector("select").value]));
    const error = root.querySelector("#suggestions-error");
    error.hidden = !this._suggestionError;
    error.textContent = this._suggestionError ?? "";
    root.querySelector("#suggestions-source").textContent = this._listName
      ? `Productos de «${this._listName}» que todavía no están en tu catálogo y códigos desconocidos de tus lectores.`
      : "Aquí aparecerán los códigos desconocidos de tus lectores. Selecciona una lista para ver también sus productos sugeridos.";
    const excluded = new Set([
      ...this._catalog.products.map(product => normalizedName(product.name)),
      ...this._catalog.dismissedSuggestions.map(normalizedName),
    ]);
    const suggestions = [];
    for (const item of this._listItems) {
      const name = String(item.summary ?? "").trim();
      const key = normalizedName(name);
      if (!key || excluded.has(key)) continue;
      excluded.add(key);
      suggestions.push(name);
    }
    suggestions.sort((a, b) => a.localeCompare(b, "es"));
    const rows = suggestions.map(name => {
      const row = element("article", "suggestion");
      const icon = element("ha-icon");
      icon.setAttribute("icon", "mdi:shopping");
      row.append(icon, element("h2", "", name));
      const actions = element("div", "actions");
      for (const [label, mdi, action] of [["Añadir al catálogo", "mdi:plus", "add"], ["Descartar", "mdi:close", "dismiss"]]) {
        const button = element("button", action === "add" ? "primary" : "");
        button.setAttribute("aria-label", `${label}: ${name}`);
        button.disabled = Boolean(this._suggestionBusy) || this._catalog.loading || Boolean(this._catalog.error);
        const icon = element("ha-icon");
        icon.setAttribute("icon", mdi);
        button.append(icon, document.createTextNode(label));
        button.addEventListener("click", () => void this._actOnSuggestion(name, action));
        actions.append(button);
      }
      row.append(actions);
      return row;
    });
    const pending = (this._readers?.pending ?? []).filter(item => !this._catalog.products.some(product => {
      const values = item.kind === "nfc" ? product.nfc_tags ?? [] : [product.barcode, ...(product.barcodes ?? [])];
      return values.includes(item.code);
    }));
    root.querySelector("#suggestions-list").replaceChildren(...rows, ...pending.map(item => this._codeSuggestion(item,selections.get(item.id))));
    root.querySelector("#suggestions-empty").hidden = suggestions.length > 0 || pending.length > 0 || this._catalog.loading || Boolean(this._catalog.error);
  }

  _codeSuggestion(item, selectedProduct) {
    const row = element("article", "suggestion");
    row.dataset.pendingId=item.id;
    const info = element("div");
    info.style.cssText = "flex:1;min-width:0;overflow-wrap:anywhere";
    info.append(element("h2", "", item.kind === "nfc" ? "Etiqueta NFC sin identificar" : "Código sin identificar"), element("p", "subtitle", item.code), element("p", "subtitle", item.reader_name));
    const select = element("select");
    select.setAttribute("aria-label", `Producto para el código ${item.code}`);
    select.append(new Option("Crear un producto nuevo", ""), ...this._catalog.products.map(product => new Option([product.name,product.brand,product.format].filter(Boolean).join(" · "),product.id)));
    if(this._catalog.products.some(product=>product.id===selectedProduct))select.value=selectedProduct;
    info.append(select);
    const actions = element("div", "actions");
    const add = element("button", "primary", "Completar ficha");
    add.setAttribute("aria-label", `Completar ficha del código ${item.code}`);
    add.addEventListener("click", () => this._openProduct(this._catalog.products.find(product => product.id === select.value), "", item));
    const dismiss = element("button", "", "Descartar");
    dismiss.setAttribute("aria-label", `Descartar código ${item.code}`);
    dismiss.addEventListener("click", async () => {
      dismiss.disabled = true;
      try { await this._readers.dismiss(item.id); }
      catch(error) { this._suggestionError = error.message ?? "No se ha podido descartar el código."; }
      finally { this._renderSuggestions(); }
    });
    actions.append(add,dismiss);row.append(info,actions);return row;
  }

  _renderReaderActions() {
    if (!this._built) return;
    const container = this.shadowRoot.querySelector("#product-reader-actions");
    const signature = JSON.stringify((this._readers?.readers ?? []).map(reader => [reader.id, reader.name]));
    if (signature === this._readerSignature) return;
    this._readerSignature = signature;
    const previous = new Map([...container.querySelectorAll("select")].map(select => [select.dataset.readerAction,select.value]));
    const nodes = (this._readers?.readers ?? []).map(reader => {
      const wrap = element("div");wrap.style.marginTop="12px";
      const label = element("label", "", reader.name);
      const select = element("select");
      select.id = `action-${reader.id}`;label.htmlFor=select.id;select.dataset.readerAction=reader.id;
      for (const [value,text] of [["none","Sin acción"],["add_list","Añadir a la lista de la compra"],["stock_remove","Quitar una unidad al stock (próximamente)"],["stock_add","Añadir una unidad al stock (próximamente)"]]) select.append(new Option(text,value));
      select.value=previous.get(reader.id)??"none";wrap.append(label,select);return wrap;
    });
    container.replaceChildren(...(nodes.length ? nodes : [element("p","helper","Añade un lector en el apartado Lectores para configurar sus acciones.")]));
  }

  async _actOnSuggestion(name, action) {
    if (this._suggestionBusy) return;
    if (action === "add") {
      this._openProduct(undefined, name);
      return;
    }
    this._suggestionBusy = true;
    this._suggestionError = "";
    this._notice = "";
    this._render();
    try {
      await this._catalog.actOnSuggestion(name, action);
      this._notice = `Sugerencia descartada: ${name}.`;
    } catch (error) {
      this._suggestionError = error.message ?? "No se ha podido guardar el cambio.";
    } finally {
      this._suggestionBusy = false;
      this._render();
    }
  }

  _fillFilter(select, values) {
    const previous = select.value;
    select.replaceChildren(new Option("Todas", ""), ...values.map(value => new Option(value, value)));
    select.value = values.includes(previous) ? previous : "";
  }

  _renderProducts() {
    if (!this._built) return;
    const root = this.shadowRoot;
    const query = root.querySelector("#catalog-search").value.trim().toLocaleLowerCase("es");
    const category = root.querySelector("#category-filter").value;
    const products = this._catalog.products.filter(product =>
      (!category || normalizedName(product.category) === normalizedName(category)) &&
      [product.name, product.brand, product.barcode, ...(product.barcodes??[]), ...(product.nfc_tags??[]), product.category, ...product.tags].join(" ").toLocaleLowerCase("es").includes(query));
    root.querySelector("#catalog-count").textContent = `${products.length} de ${this._catalog.products.length} productos`;
    root.querySelector("#catalog-grid").replaceChildren(...products.map(product => this._productCard(product)));
    const empty = root.querySelector("#catalog-empty");
    empty.hidden = products.length > 0 || this._catalog.loading || Boolean(this._catalog.error);
    empty.textContent = this._catalog.products.length ? "No hay productos que coincidan con estos filtros." : "Tu catálogo empieza aquí. Añade el primer producto para tenerlo a mano en tu próxima compra.";
  }

  _productCard(product) {
    const card = element("article", "product");
    card.dataset.productId = product.id;
    const inList = this._pendingNames.has(normalizedName(product.name));
    card.classList.toggle("in-list", inList);
    card.dataset.inList = String(inList);
    if (inList) card.setAttribute("aria-description", "Pendiente en la lista seleccionada");
    const category = this._catalog.categories.find(category => normalizedName(category.name) === normalizedName(product.category));
    if (category) {
      const badge = element("button", "category-badge");
      badge.type = "button";
      badge.style.backgroundColor = category.color;
      badge.title = category.name;
      badge.setAttribute("aria-label", `Filtrar por categoría: ${category.name}`);
      badge.addEventListener("click", () => {
        const filter = this.shadowRoot.querySelector("#category-filter");
        filter.value = category.name;
        this._renderProducts();
        filter.focus();
      });
      const categoryIcon = element("ha-icon");
      categoryIcon.setAttribute("icon", category.icon);
      badge.append(categoryIcon);
      card.append(badge);
    }
    const top = element("div", "product-top");
    const placeholder = element("div", "image placeholder");
    const icon = element("ha-icon");
    icon.setAttribute("icon", product.icon || "mdi:shopping");
    placeholder.append(icon);
    const source = imageSource(product.image_url);
    if (source) {
      const image = element("img", "image");
      image.src = source;
      image.alt = "";
      image.loading = "lazy";
      image.referrerPolicy = "no-referrer";
      image.addEventListener("error", () => image.replaceWith(placeholder), { once: true });
      top.append(image);
    } else top.append(placeholder);
    const title = element("div");
    title.append(element("h2", "title", product.name));
    const subtitle = [product.brand, product.format].filter(Boolean).join(" · ");
    if (subtitle) title.append(element("p", "subtitle", subtitle));
    top.append(title);
    card.append(top);
    if (product.tags.length) {
      const tags = element("div", "tags");
      tags.append(...product.tags.map(tag => element("span", "tag", tag)));
      card.append(tags);
    }
    const actions = element("div", "actions");
    const add = element("button", "primary");
    const addIcon = element("ha-icon");
    addIcon.setAttribute("icon", "mdi:cart-plus");
    add.append(addIcon, document.createTextNode("Añadir"));
    add.setAttribute("aria-label", `Añadir ${product.name} a la lista`);
    add.title = this._canAdd ? `Añadir a «${this._listName}»` : "Selecciona una lista disponible en el apartado Lista para añadir productos.";
    add.disabled = !this._canAdd || Boolean(this._adding);
    add.addEventListener("click", () => void this._addToList(product));
    const edit = element("button");
    const editIcon = element("ha-icon");
    editIcon.setAttribute("icon", "mdi:note-edit");
    edit.append(editIcon, document.createTextNode("Editar"));
    edit.setAttribute("aria-label", `Editar ${product.name}`);
    edit.addEventListener("click", () => this._openProduct(product));
    actions.append(add, edit);
    card.append(actions);
    return card;
  }

  _openProduct(product, suggestedName = "", reading = null) {
    if (this._saving) return;
    const root = this.shadowRoot;
    const form = root.querySelector("form");
    form.reset();
    form.elements.name.value = suggestedName;
    this._renderReaderActions();
    this._editing = product ? structuredClone(product) : null;
    root.querySelector("#product-dialog-title").textContent = product ? "Editar producto" : "Nuevo producto";
    root.querySelector("#product-error").hidden = true;
    if (product) {
      for (const key of ["name", "category", "brand", "barcode", "format", "price", "image_url", "icon", "notes"]) form.elements[key].value = product[key] ?? "";
      if (![...form.elements.currency.options].some(option => option.value === product.currency)) form.elements.currency.add(new Option(product.currency, product.currency));
      form.elements.currency.value = product.currency;
      form.elements.tags.value = product.tags.join(", ");
      form.elements.barcodes.value = (product.barcodes ?? []).join("\n");
      form.elements.nfc_tags.value = (product.nfc_tags ?? []).join("\n");
    }
    for (const select of root.querySelectorAll("[data-reader-action]")) select.value = product?.reader_actions?.[select.dataset.readerAction] ?? "none";
    if (reading) {
      if (reading.kind === "barcode" && !form.elements.barcode.value) form.elements.barcode.value = reading.code;
      else {
        const field = reading.kind === "nfc" ? "nfc_tags" : "barcodes";
        const values = form.elements[field].value.split(/\r?\n/).filter(Boolean);
        if (!values.includes(reading.code) && !(reading.kind === "barcode" && form.elements.barcode.value === reading.code)) values.push(reading.code);
        form.elements[field].value = values.join("\n");
      }
    }
    root.querySelector("dialog").showModal();
    form.elements.name.focus();
  }

  async _saveProduct() {
    if (this._saving) return;
    const root = this.shadowRoot;
    const form = root.querySelector("form");
    const fields = Object.fromEntries(new FormData(form));
    const product = { ...fields, tags: fields.tags.split(",").map(tag => tag.trim()).filter(Boolean), price: fields.price || null };
    for (const key of ["barcodes","nfc_tags"]) product[key] = fields[key].split(/\r?\n/).map(value => value.trim()).filter(Boolean);
    product.reader_actions = Object.fromEntries([...root.querySelectorAll("[data-reader-action]")].map(select => [select.dataset.readerAction,select.value]));
    if (this._editing) Object.assign(product, { id: this._editing.id, revision: this._editing.revision });
    this._saving = true;
    root.querySelector("#save-product").disabled = true;
    root.querySelector("#cancel-product").disabled = true;
    root.querySelector("#product-error").hidden = true;
    try {
      await this._catalog.save(product);
      root.querySelector("dialog").close();
      this._notice = "Producto guardado en el catálogo.";
      this._render();
      root.querySelector(this._view === "suggestions" ? "#view-suggestions" : "#new-product").focus();
    } catch (error) {
      const notice = root.querySelector("#product-error");
      notice.textContent = error.message ?? "No se ha podido guardar el producto.";
      notice.hidden = false;
    } finally {
      this._saving = false;
      root.querySelector("#save-product").disabled = false;
      root.querySelector("#cancel-product").disabled = false;
    }
  }

  async _addToList(product) {
    if (!this._canAdd || this._adding || !this.onAdd) return;
    const listName = this._listName;
    this._adding = product.id;
    this._notice = "";
    this._render();
    try {
      if (await this.onAdd(product)) this._notice = `${product.name} añadido a «${listName}».`;
    } finally {
      this._adding = undefined;
      this._render();
    }
  }
}

if (!customElements.get("isl-catalog")) customElements.define("isl-catalog", ImprovedShoppingCatalog);
