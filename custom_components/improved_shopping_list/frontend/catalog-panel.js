import { CatalogSession } from "./catalog-client.js?v=0.2.0";

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function imageSource(value) {
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
    if (this._built) this.shadowRoot.querySelector("#catalog-list-help").textContent = value
      ? `Añade productos a «${value}» desde sus fichas.` : "Selecciona una lista para añadir productos.";
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
        h1 { font-size:32px; letter-spacing:-.03em; margin:0; }
        h2 { font-size:23px; margin:0; }
        .helper { color:var(--secondary-text-color,#63766b); font-size:13px; line-height:1.6; margin:8px 0 18px; }
        button { min-height:44px; padding:10px 14px; border:1px solid var(--divider-color,#dfe7e1); border-radius:10px; background:transparent; color:inherit; }
        .primary { background:#267052; color:#fff; border:0; font-weight:650; }
        .filters { display:grid; grid-template-columns:2fr 1fr 1fr; gap:12px; margin:24px 0 14px; align-items:end; }
        #catalog-refresh { width:44px; padding:10px; flex-shrink:0; }
        label { font-size:13px; font-weight:600; display:block; }
        input,select,textarea { display:block; min-height:46px; width:100%; margin-top:7px; padding:10px 12px; color:inherit; background:var(--card-background-color,#fff); border:1px solid var(--divider-color,#dfe7e1); border-radius:9px; min-width:0; }
        textarea { resize:vertical; min-height:76px; }
        .count { color:var(--secondary-text-color,#63766b); font-size:12px; margin:12px 0; }
        .grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(245px,1fr)); gap:16px; }
        .product { display:flex; flex-direction:column; gap:12px; background:var(--card-background-color,#fff); border:1px solid var(--divider-color,#dfe7e1); border-radius:16px; padding:18px; min-width:0; }
        .product-top { display:flex; gap:14px; align-items:center; }
        .image { width:64px; height:64px; object-fit:contain; border-radius:10px; flex-shrink:0; }
        .placeholder { display:grid; place-items:center; background:var(--secondary-background-color,#edf4ee); color:var(--secondary-text-color,#63766b); }
        .title { font-size:17px; line-height:1.4; font-weight:650; margin:0; overflow-wrap:anywhere; }
        .subtitle { color:var(--secondary-text-color,#63766b); font-size:12px; margin:4px 0 0; overflow-wrap:anywhere; }
        .category { color:var(--secondary-text-color,#63766b); font-size:12px; margin:0; }
        .tags { display:flex; flex-wrap:wrap; gap:5px; }
        .tag { padding:4px 8px; border-radius:20px; font-size:11px; background:var(--secondary-background-color,#edf4ee); }
        .price { margin:0; font-weight:650; }
        .price small { font-size:11px; font-weight:400; color:var(--secondary-text-color,#63766b); margin-left:6px; }
        .actions { display:flex; gap:8px; margin-top:auto; }
        .actions .primary { flex:1; }
        .notice { font-size:13px; line-height:1.6; padding:12px 14px; background:var(--secondary-background-color,#edf4ee); border-radius:10px; margin:14px 0; }
        .error { color:var(--error-color,#bd3636); border:1px solid var(--error-color,#bd3636); }
        .empty { text-align:center; padding:38px 16px; color:var(--secondary-text-color,#63766b); line-height:1.7; border:1px dashed var(--divider-color,#dfe7e1); border-radius:16px; }
        dialog { color:inherit; background:var(--card-background-color,#fff); width:min(640px,calc(100vw - 28px)); max-height:calc(100dvh - 28px); border:1px solid var(--divider-color,#dfe7e1); border-radius:18px; padding:24px; }
        dialog::backdrop { background:rgba(0,0,0,.4); }
        .dialog-heading { display:flex; align-items:center; justify-content:space-between; gap:12px; }
        .fields { display:grid; grid-template-columns:1fr 1fr; gap:16px; margin:22px 0; }
        .wide { grid-column:1/-1; }
        .form-actions { display:flex; justify-content:flex-end; gap:10px; margin-top:22px; }
        @media(max-width:650px) { .filters { grid-template-columns:1fr 1fr; } .search { grid-column:1/-1; } .grid { grid-template-columns:1fr; } .heading { gap:10px; flex-wrap:wrap; } h1 { font-size:28px; } dialog { padding:20px; } }
        @media(max-width:390px) { .fields { grid-template-columns:1fr; } .heading { align-items:flex-start; } }
      </style>
      <div class="heading"><h1>Catálogo</h1><div class="heading-actions"><button id="new-product" class="primary">Nuevo producto</button><button id="catalog-refresh" aria-label="Actualizar catálogo" title="Actualizar catálogo"><ha-icon icon="mdi:refresh"></ha-icon></button></div></div>
      <p id="catalog-list-help" class="helper"></p>
      <div id="catalog-error" class="notice error" role="alert" hidden></div>
      <div id="catalog-status" class="notice" role="status" hidden></div>
      <div class="filters">
        <label class="search">Buscar productos<input id="catalog-search" type="search" placeholder="Nombre, marca, código o etiqueta"></label>
        <label>Categoría<select id="category-filter"><option value="">Todas</option></select></label>
        <label>Etiqueta<select id="tag-filter"><option value="">Todas</option></select></label>
      </div>
      <p id="catalog-count" class="count" aria-live="polite"></p>
      <div id="catalog-grid" class="grid"></div>
      <p id="catalog-empty" class="empty" hidden></p>
      <dialog aria-labelledby="product-dialog-title">
        <form id="product-form">
          <div class="dialog-heading"><h2 id="product-dialog-title">Nuevo producto</h2></div>
          <p class="helper">Solo necesitas un nombre para empezar. Puedes completar el resto más adelante.</p>
          <div id="product-error" class="notice error" role="alert" hidden></div>
          <div class="fields">
            <label class="wide">Nombre del producto<input name="name" required maxlength="160" placeholder="Por ejemplo, Cacao"></label>
            <label>Categoría<input name="category" list="category-suggestions" maxlength="80" placeholder="Despensa"></label>
            <label>Etiquetas<input name="tags" maxlength="850" placeholder="Desayuno, sin gluten"></label>
            <label>Marca<input name="brand" maxlength="100"></label>
            <label>Formato<input name="format" maxlength="100" placeholder="250 g, 1 l, 6 unidades…"></label>
            <label class="wide">Código de barras<input name="barcode" type="text" inputmode="numeric" maxlength="64"></label>
            <label>Precio orientativo<input name="price" type="number" min="0" max="1000000" step="0.01" placeholder="Sin precio"></label>
            <label>Moneda<select name="currency"><option value="EUR">EUR · Euro</option><option value="USD">USD · Dólar</option><option value="GBP">GBP · Libra</option></select></label>
            <label class="wide">URL de la imagen<input name="image_url" maxlength="2048" placeholder="https://… o /local/producto.png"></label>
            <label class="wide">Notas<textarea name="notes" maxlength="1000"></textarea></label>
          </div>
          <datalist id="category-suggestions"></datalist>
          <p class="helper">Separa las etiquetas con comas. El precio es manual y corresponde al formato indicado; todavía no es una oferta de supermercado.</p>
          <div class="form-actions"><button id="cancel-product" type="button">Cancelar</button><button id="save-product" class="primary" type="submit">Guardar producto</button></div>
        </form>
      </dialog>`;
    this._built = true;
    const root = this.shadowRoot;
    root.querySelector("#new-product").addEventListener("click", () => this._openProduct());
    root.querySelector("#catalog-refresh").addEventListener("click", () => void this._catalog.refresh());
    root.querySelector("#catalog-search").addEventListener("input", () => this._renderProducts());
    root.querySelector("#category-filter").addEventListener("change", () => this._renderProducts());
    root.querySelector("#tag-filter").addEventListener("change", () => this._renderProducts());
    root.querySelector("#cancel-product").addEventListener("click", () => root.querySelector("dialog").close());
    root.querySelector("dialog").addEventListener("cancel", (event) => { if (this._saving) event.preventDefault(); });
    root.querySelector("#product-form").addEventListener("submit", (event) => { event.preventDefault(); void this._saveProduct(); });
    this.listName = this._listName;
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
    const categories = [...new Set(this._catalog.products.map(product => product.category).filter(Boolean))].sort((a, b) => a.localeCompare(b, "es"));
    const tags = [...new Set(this._catalog.products.flatMap(product => product.tags))].sort((a, b) => a.localeCompare(b, "es"));
    this._fillFilter(root.querySelector("#category-filter"), categories);
    this._fillFilter(root.querySelector("#tag-filter"), tags);
    root.querySelector("#category-suggestions").replaceChildren(...categories.map(category => new Option(category, category)));
    this._renderProducts();
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
    const tag = root.querySelector("#tag-filter").value;
    const products = this._catalog.products.filter(product =>
      (!category || product.category === category) && (!tag || product.tags.includes(tag)) &&
      [product.name, product.brand, product.barcode, product.category, ...product.tags].join(" ").toLocaleLowerCase("es").includes(query));
    root.querySelector("#catalog-count").textContent = `${products.length} de ${this._catalog.products.length} productos`;
    root.querySelector("#catalog-grid").replaceChildren(...products.map(product => this._productCard(product)));
    const empty = root.querySelector("#catalog-empty");
    empty.hidden = products.length > 0 || this._catalog.loading || Boolean(this._catalog.error);
    empty.textContent = this._catalog.products.length ? "No hay productos que coincidan con estos filtros." : "Tu catálogo empieza aquí. Añade el primer producto para tenerlo a mano en tu próxima compra.";
  }

  _productCard(product) {
    const card = element("article", "product");
    card.dataset.productId = product.id;
    const top = element("div", "product-top");
    const placeholder = element("div", "image placeholder");
    const icon = element("ha-icon");
    icon.setAttribute("icon", "mdi:package-variant-closed");
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
    card.append(top, element("p", "category", product.category || "Sin categoría"));
    if (product.tags.length) {
      const tags = element("div", "tags");
      tags.append(...product.tags.map(tag => element("span", "tag", tag)));
      card.append(tags);
    }
    const price = element("p", "price");
    if (product.price !== null) {
      let formatted;
      try { formatted = new Intl.NumberFormat("es-ES", { style: "currency", currency: product.currency }).format(Number(product.price)); }
      catch { formatted = `${product.price} ${product.currency}`; }
      price.append(document.createTextNode(formatted), element("small", "", "orientativo"));
      if (product.price_updated_at) price.title = `Actualizado el ${new Date(product.price_updated_at).toLocaleDateString("es-ES")}`;
    } else price.append(element("small", "", "Sin precio"));
    const actions = element("div", "actions");
    const add = element("button", "primary", this._adding === product.id ? "Añadiendo…" : "Añadir a lista");
    add.setAttribute("aria-label", `Añadir ${product.name} a la lista`);
    add.disabled = !this._canAdd || Boolean(this._adding);
    add.addEventListener("click", () => void this._addToList(product));
    const edit = element("button", "", "Editar");
    edit.setAttribute("aria-label", `Editar ${product.name}`);
    edit.addEventListener("click", () => this._openProduct(product));
    actions.append(add, edit);
    card.append(price, actions);
    return card;
  }

  _openProduct(product) {
    if (this._saving) return;
    const root = this.shadowRoot;
    const form = root.querySelector("form");
    form.reset();
    this._editing = product ? structuredClone(product) : null;
    root.querySelector("#product-dialog-title").textContent = product ? "Editar producto" : "Nuevo producto";
    root.querySelector("#product-error").hidden = true;
    if (product) {
      for (const key of ["name", "category", "brand", "barcode", "format", "price", "image_url", "notes"]) form.elements[key].value = product[key] ?? "";
      if (![...form.elements.currency.options].some(option => option.value === product.currency)) form.elements.currency.add(new Option(product.currency, product.currency));
      form.elements.currency.value = product.currency;
      form.elements.tags.value = product.tags.join(", ");
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
      root.querySelector("#new-product").focus();
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
