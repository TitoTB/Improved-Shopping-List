/** Five color suggestions and a button cycling through other results. */
const PREFIX = "improved_shopping_list/icons/";
const PAGE_SIZE = 5;
const LOCAL_PREFIX = "/improved_shopping_list_icons/";

function node(tag, text, className) {
  const result = document.createElement(tag);
  if (text !== undefined) result.textContent = text;
  if (className) result.className = className;
  return result;
}

function link(text, url) {
  const result = node("a", text);
  try { if (new URL(url).protocol !== "https:") return node("span", text); }
  catch { return node("span", text); }
  result.href = url;
  result.target = "_blank";
  result.rel = "noopener noreferrer";
  return result;
}

class ImprovedShoppingIconPicker extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._generation = 0;
    this._infoGeneration = 0;
    this._icons = [];
  }

  set hass(value) { this._hass = value; }
  set disabled(value) {
    this._disabled = value;
    if (value) { clearTimeout(this._timer); this._generation += 1; this._busy = false; }
    if (this._built) this._renderResults();
  }
  set value(value) {
    if (this._importing) {
      this._generation += 1;
      this._busy = this._importing = false;
      this.onBusyChange?.(false);
    }
    this._value = value ?? "";
    this._selectedId = undefined;
    this._showAttribution(null);
    if (this._built) this._renderResults();
    const generation = ++this._infoGeneration;
    if (!this._value.startsWith(LOCAL_PREFIX) || !this._hass) return;
    void this._hass.callWS({ type: `${PREFIX}info`, image_url: this._value }).then(info => {
      if (generation === this._infoGeneration && this.isConnected) this._showAttribution(info);
    }).catch(() => { /* A failed metadata read must not prevent product editing. */ });
  }

  connectedCallback() { if (!this._built) this._build(); }
  disconnectedCallback() { this.close(); this._infoGeneration += 1; }

  _build() {
    this.shadowRoot.innerHTML = `
      <style>
        :host{display:block;min-width:0}*{box-sizing:border-box}[hidden]{display:none!important}
        button,input{font:inherit;color:inherit}button{cursor:pointer;border:1px solid var(--divider-color,#dfe7e1);border-radius:10px;background:transparent;padding:10px 12px;min-height:44px}
        button:disabled{opacity:.5;cursor:default}button:focus-visible,input:focus-visible,a:focus-visible{outline:3px solid var(--primary-color,#267052);outline-offset:3px}
        ha-icon{--mdc-icon-size:20px}h3{margin:0 0 12px;font-size:15px}label{display:block;min-width:0;font-size:13px;font-weight:600}input{display:block;width:100%;margin-top:7px;min-height:46px;border:1px solid var(--divider-color,#dfe7e1);border-radius:10px;padding:10px 12px;background:var(--card-background-color,#fff)}
        .helper,.attribution{font-size:12px;line-height:1.5;color:var(--secondary-text-color,#63766b)}a{color:var(--primary-color,#267052)}
        .external-search{display:inline-flex;align-items:center;justify-content:center;gap:8px;min-height:44px;padding:10px 12px;border:1px solid var(--divider-color,#dfe7e1);border-radius:10px;text-decoration:none;color:inherit}.external-search[aria-disabled=true]{opacity:.5;pointer-events:none}.external-search ha-icon{display:flex;align-items:center;justify-content:center;width:20px;height:20px;flex:none;line-height:0}
        #results{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin:14px 0}.option{min-width:0;padding:8px 4px;display:flex;align-items:center;justify-content:center;aspect-ratio:1;overflow:hidden}.option img{width:min(64px,100%);height:auto;max-height:100%;aspect-ratio:1;object-fit:contain}.option[aria-pressed=true]{border:2px solid var(--primary-color,#267052)}.more{border:1px solid var(--divider-color,#dfe7e1);border-radius:10px;text-decoration:none;color:inherit}.more ha-icon{--mdc-icon-size:32px;width:32px;height:32px}.empty{border:1px dashed var(--divider-color,#dfe7e1);border-radius:10px;opacity:.3}.more[aria-disabled=true]{opacity:.4;pointer-events:none}
        #status{font-size:13px}#status.error{color:var(--error-color,#bd3636)}
        #selected{display:flex;align-items:center;gap:12px;margin-top:12px}#selected img{width:48px;height:48px;object-fit:contain;flex-shrink:0}
        @media(max-width:400px){#results{gap:4px}}
      </style>
      <section aria-label="Iconos sugeridos">
        <h3>Iconos sugeridos</h3>
        <p id="status" role="status" hidden></p><div id="results" aria-label="Iconos sugeridos"></div>
        <label>Buscar iconos<input id="query" type="search" minlength="2" maxlength="100" placeholder="Puedes escribir otro término"></label>
        <p class="helper">Las sugerencias se actualizan con el nombre del producto. Pulsa + para ver otras propuestas.</p>
        <div id="selected" hidden></div>
        <p class="helper">Iconos de <a href="https://iconify.design/" target="_blank" rel="noopener noreferrer">Iconify</a>. Se conservarán el autor y la licencia del icono elegido. También puedes consultar la web de <a href="https://www.flaticon.es/" target="_blank" rel="noopener noreferrer">Flaticon</a>.</p>
        <a id="flaticon-search" class="external-search" target="_blank" rel="noopener noreferrer"><ha-icon icon="mdi:open-in-new" aria-hidden="true"></ha-icon>Buscar en Flaticon</a>
      </section>`;
    this._built = true;
    const root = this.shadowRoot;
    root.querySelector("#query").addEventListener("keydown", event => {
      if (event.key === "Enter") { event.preventDefault(); void this._search(); }
    });
    root.querySelector("#query").addEventListener("input", () => {
      this._generation += 1;
      this._busy = false;
      this._icons = [];
      this._hasMore = false;
      this._searchOptions = {};
      this._status("");
      this._renderResults();
      clearTimeout(this._timer);
      this._timer = setTimeout(() => void this._search(), 500);
    });
    this._renderResults();
  }

  open(query) {
    if (this._disabled || !this._hass) return;
    clearTimeout(this._timer);
    this._active = true;
    this._generation += 1;
    this._busy = this._importing = false;
    this._icons = [];
    this._hasMore = false;
    this._searchOptions = this.getSearchOptions?.() ?? {};
    this.shadowRoot.querySelector("#query").value = query.slice(0, 100);
    this._status("");
    this._renderResults();
    this.onBusyChange?.(false);
    if (query.trim().length >= 2) void this._search();
    else this._status("Escribe el nombre del producto para ver sugerencias.");
  }

  suggest() {
    if (!this._active || this._disabled) return;
    clearTimeout(this._timer);
    this._generation += 1;
    this._busy = false;
    this._importing = false;
    this.onBusyChange?.(false);
    this._icons = [];
    this._hasMore = false;
    this._searchOptions = this.getSearchOptions?.() ?? {};
    const query = this.getQuery?.() ?? "";
    this.shadowRoot.querySelector("#query").value = query.slice(0, 100);
    this._status(query.trim().length >= 2 ? "Buscando iconos…" : "Escribe el nombre del producto para ver sugerencias.");
    this._renderResults();
    this._timer = setTimeout(() => void this._search(), 500);
  }

  close() {
    this._generation += 1;
    this._infoGeneration += 1;
    clearTimeout(this._timer);
    this._active = false;
    this._busy = this._importing = false;
    this.onBusyChange?.(false);
  }

  _status(message, error = false) {
    const status = this.shadowRoot.querySelector("#status");
    status.textContent = message;
    status.hidden = !message;
    status.classList.toggle("error", error);
  }

  async _search() {
    clearTimeout(this._timer);
    if (!this._active || this._disabled || this._importing || !this._hass) return;
    const query = this.shadowRoot.querySelector("#query").value.trim();
    const generation = ++this._generation;
    this._icons = [];
    this._pageStart = 0;
    this._hasMore = false;
    this._query = query;
    if (query.length < 2) {
      this._busy = false;
      this._status("Escribe el nombre del producto para ver sugerencias.");
      this._renderResults();
      return;
    }
    await this._load(query, 0, generation);
  }

  async _load(query, start, generation) {
    this._busy = true;
    this._status("Buscando iconos…");
    this._renderResults();
    try {
      const result = await this._hass.callWS({ type: `${PREFIX}search`, query, start, ...this._searchOptions });
      if (generation !== this._generation || !this.isConnected) return;
      const ids = new Set(this._icons.map(icon => icon.id));
      this._icons.push(...result.icons.filter(icon => !ids.has(icon.id) && ids.add(icon.id)));
      this._hasMore = Boolean(result.has_more);
      this._nextStart = result.next_start;
      this._query = result.query || query;
      if (result.query) this.shadowRoot.querySelector("#query").value = result.query;
      this._searchOptions = {};
      this._status(this._icons.length ? "" : "No se han encontrado iconos. Puedes escribir otro término o indicar una URL Imagen/Icono.");
      return true;
    } catch (error) {
      if (generation !== this._generation || !this.isConnected) return;
      this._status(error.message ?? "No se han podido buscar iconos. Inténtalo de nuevo.", true);
    } finally {
      if (generation === this._generation && this.isConnected) { this._busy = false; this._renderResults(); }
    }
  }

  async _more() {
    if (this._busy || this._disabled || !this._active) return;
    const generation = this._generation;
    const next = this._pageStart + PAGE_SIZE;
    if (next + PAGE_SIZE > this._icons.length && this._hasMore) {
      if (!await this._load(this._query, this._nextStart, generation) || generation !== this._generation) return;
    }
    if (generation !== this._generation || !this._active) return;
    if (next < this._icons.length) {
      this._pageStart = next;
      this._status("");
    } else if (!this._hasMore && this._icons.length > PAGE_SIZE) {
      this._pageStart = 0;
      this._status("");
    } else this._status("No hay otras propuestas disponibles. Puedes cambiar el término o indicar una URL Imagen/Icono.");
    this._renderResults();
  }

  _renderResults() {
    const root = this.shadowRoot;
    const productName = (this.getProductName?.() ?? "").trim();
    const externalSearch = root.querySelector("#flaticon-search");
    if (productName) externalSearch.href = `https://www.flaticon.es/buscar?word=${encodeURIComponent(productName)}`;
    else externalSearch.removeAttribute("href");
    externalSearch.setAttribute("aria-disabled", String(!productName));
    externalSearch.tabIndex = productName ? 0 : -1;
    const suggestions = Array.from({length:PAGE_SIZE}, (_, index) => {
      const position = (this._pageStart || 0) + index;
      const icon = this._icons[this._icons.length >= PAGE_SIZE ? position % this._icons.length : position];
      if (!icon) { const empty = node("span", undefined, "option empty"); empty.setAttribute("aria-hidden", "true"); return empty; }
      const button = node("button", undefined, "option");
      button.type = "button";
      button.title = `${icon.collection} · ${icon.author} · ${icon.license}`;
      button.setAttribute("aria-label", `Elegir ${icon.label} (${icon.collection})`);
      button.disabled = Boolean(this._busy || this._disabled);
      button.setAttribute("aria-pressed", String(this._selectedId === icon.id));
      const image = node("img");
      // Preview URLs are constructed by the backend, never inserted as markup.
      image.src = icon.preview_url;
      image.alt = "";
      image.referrerPolicy = "no-referrer";
      image.addEventListener("error", () => { image.hidden = true; }, { once:true });
      button.append(image);
      button.addEventListener("click", () => void this._select(icon));
      return button;
    });
    const query = root.querySelector("#query").value.trim();
    const more = node("button");
    more.type = "button";
    more.id = "more-icons";
    more.className = "option more";
    more.hidden = this._icons.length === 0;
    more.title = "Ver otros iconos";
    more.setAttribute("aria-label", more.title);
    const plus = node("ha-icon"); plus.setAttribute("icon", "mdi:plus-thick"); plus.setAttribute("aria-hidden", "true"); more.append(plus);
    more.disabled = query.length < 2 || Boolean(this._busy || this._disabled) || (this._icons.length <= PAGE_SIZE && !this._hasMore);
    more.addEventListener("click", () => void this._more());
    root.querySelector("#results").replaceChildren(...suggestions, more);
    root.querySelector("#query").disabled = Boolean(this._importing || this._disabled);
  }

  async _select(icon) {
    if (this._busy || this._disabled || !this._active) return;
    const generation = ++this._generation;
    this._busy = this._importing = true;
    this.onBusyChange?.(true);
    this._status("Guardando icono en Home Assistant…");
    this._renderResults();
    try {
      const asset = await this._hass.callWS({ type: `${PREFIX}import`, icon_id: icon.id });
      if (generation !== this._generation || !this.isConnected) return;
      this._value = asset.url;
      this._selectedId = icon.id;
      this._infoGeneration += 1;
      this._showAttribution(asset);
      this.onSelect?.(asset);
      this._status("");
    } catch (error) {
      if (generation === this._generation && this.isConnected) this._status(error.message ?? "No se ha podido guardar el icono.", true);
    } finally {
      if (generation === this._generation || !this._active) {
        this._busy = this._importing = false;
        this.onBusyChange?.(false);
        if (this.isConnected) this._renderResults();
      }
    }
  }

  _showAttribution(info) {
    const selected = this.shadowRoot.querySelector("#selected");
    if (!selected) return;
    selected.replaceChildren();
    selected.hidden = !info;
    if (!info) return;
    const image = node("img");
    image.src = info.url;
    image.alt = "Icono seleccionado";
    const text = node("div", undefined, "attribution");
    text.append(link(info.collection, info.source_url), node("span", " · "), link(info.author, info.author_url), node("span", " · "), link(info.license, info.license_url));
    selected.append(image, text);
  }
}

if (!customElements.get("isl-icon-picker")) customElements.define("isl-icon-picker", ImprovedShoppingIconPicker);
