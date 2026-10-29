/** Up to six automatic suggestions, with community results first. */
const PREFIX = "improved_shopping_list/icons/";
const SUGGESTION_LIMIT = 6;
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
        button{font:inherit;color:inherit}button{cursor:pointer;border:1px solid var(--divider-color,#dfe7e1);border-radius:10px;background:transparent;padding:10px 12px;min-height:44px}
        button:disabled{opacity:.5;cursor:default}button:focus-visible,a:focus-visible{outline:3px solid var(--primary-color,#267052);outline-offset:3px}
        h3{margin:0 0 12px;font-size:15px;font-weight:650;line-height:1.4}
        .helper,.attribution{font-size:12px;line-height:1.5;color:var(--secondary-text-color,#63766b)}a{color:var(--primary-color,#267052)}
        #results{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:8px;margin:14px 0;container-type:inline-size}.option{min-width:0;min-height:0;width:100%;padding:clamp(2px,1cqi,6px);display:flex;align-items:center;justify-content:center;aspect-ratio:1;overflow:hidden}.option img{width:min(56px,100%);height:auto;max-height:100%;aspect-ratio:1;object-fit:contain}.option[aria-pressed=true]{border:2px solid var(--primary-color,#267052)}
        #status{font-size:13px}#status.error{color:var(--error-color,#bd3636)}
        #selected{margin-top:12px}
        @media(max-width:400px){#results{gap:4px}}
      </style>
      <section aria-label="Iconos sugeridos">
        <h3>Iconos sugeridos</h3>
        <p id="status" role="status" hidden></p><div id="results" aria-label="Iconos sugeridos"></div>
        <div id="selected" hidden></div>
      </section>`;
    this._built = true;
    this._renderResults();
  }

  open(query) {
    if (this._disabled || !this._hass) return;
    clearTimeout(this._timer);
    this._active = true;
    this._generation += 1;
    this._busy = this._importing = false;
    this._icons = [];
    this._searchOptions = this.getSearchOptions?.() ?? {};
    this._query = query.slice(0, 100);
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
    this._searchOptions = this.getSearchOptions?.() ?? {};
    const query = this.getQuery?.() ?? "";
    this._query = query.slice(0, 100);
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
    const query = (this._query ?? "").trim();
    const generation = ++this._generation;
    this._icons = [];
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
      this._query = result.query || query;
      this._searchOptions = {};
      this._status(this._icons.length ? "" : "No se han encontrado iconos. Puedes indicar una URL Imagen/Icono.");
      return true;
    } catch (error) {
      if (generation !== this._generation || !this.isConnected) return;
      this._status(error.message ?? "No se han podido buscar iconos. Inténtalo de nuevo.", true);
    } finally {
      if (generation === this._generation && this.isConnected) { this._busy = false; this._renderResults(); }
    }
  }

  _renderResults() {
    const root = this.shadowRoot;
    const suggestions = this._icons.slice(0, SUGGESTION_LIMIT).map(icon => {
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
    const results = root.querySelector("#results");
    results.hidden = suggestions.length === 0;
    results.replaceChildren(...suggestions);
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
    const text = node("div", undefined, "attribution");
    text.append(document.createTextNode("Fuente: "), link(info.collection, info.source_url));
    selected.append(text);
  }
}

if (!customElements.get("isl-icon-picker")) customElements.define("isl-icon-picker", ImprovedShoppingIconPicker);
