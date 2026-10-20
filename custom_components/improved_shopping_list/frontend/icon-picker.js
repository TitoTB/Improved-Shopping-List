/** Three color suggestions and a fourth tile opening the full Iconify search. */
const PREFIX = "improved_shopping_list/icons/";
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
    if (this._built) this.shadowRoot.querySelector("#open-picker").disabled = Boolean(value);
  }
  set value(value) {
    this._value = value ?? "";
    this._showAttribution(null);
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
        #open-picker{display:inline-flex;align-items:center;gap:8px}ha-icon{--mdc-icon-size:20px}
        dialog{color:var(--primary-text-color,#20352d);background:var(--card-background-color,#fff);width:min(620px,calc(100vw - 28px));max-height:calc(100dvh - 28px);border:1px solid var(--divider-color,#dfe7e1);border-radius:18px;padding:24px}dialog::backdrop{background:rgba(0,0,0,.4)}
        h2{margin:0 0 18px;font-size:22px}.search{display:flex;align-items:end;gap:8px}label{flex:1;min-width:0;font-size:13px;font-weight:600}input{display:block;width:100%;margin-top:7px;min-height:46px;border:1px solid var(--divider-color,#dfe7e1);border-radius:10px;padding:10px 12px;background:var(--card-background-color,#fff)}
        .helper,.attribution{font-size:12px;line-height:1.5;color:var(--secondary-text-color,#63766b)}a{color:var(--primary-color,#267052)}
        #results{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin:18px 0}.option{min-width:0;padding:8px 4px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:8px;aspect-ratio:1;overflow:hidden}.option img{width:64px;height:64px;max-width:100%;object-fit:contain}.option span{font-size:11px;overflow-wrap:anywhere;max-width:100%}.more{border:1px solid var(--divider-color,#dfe7e1);border-radius:10px;text-decoration:none;color:inherit}.more ha-icon{--mdc-icon-size:32px;width:32px;height:32px}.empty{border:1px dashed var(--divider-color,#dfe7e1);border-radius:10px;opacity:.3}.more[aria-disabled=true]{opacity:.4;pointer-events:none}
        .footer{display:flex;flex-wrap:wrap;justify-content:flex-end;gap:8px;margin-top:18px}#status{font-size:13px}#status.error{color:var(--error-color,#bd3636)}
        #selected{display:flex;align-items:center;gap:12px;margin-top:12px}#selected img{width:48px;height:48px;object-fit:contain;flex-shrink:0}
        @media(max-width:400px){dialog{padding:18px}.option img{width:44px;height:44px}#results{gap:4px}.option span{font-size:10px}.search button{padding:10px}}
      </style>
      <button id="open-picker" type="button"><ha-icon icon="mdi:image-search" aria-hidden="true"></ha-icon>Buscar icono</button>
      <div id="selected" hidden></div>
      <dialog aria-labelledby="picker-title">
        <h2 id="picker-title">Buscar icono</h2>
        <div class="search"><label>Buscar iconos<input id="query" type="search" minlength="2" maxlength="100" placeholder="Por ejemplo, milk o bread"></label><button id="search" type="button">Buscar</button></div>
        <p class="helper">Traducimos el nombre al inglés para buscar iconos. Puedes cambiar el término. El botón + abre todas las opciones en Iconify.</p>
        <p id="status" role="status" hidden></p><div id="results" aria-label="Iconos sugeridos"></div>
        <p class="helper">Iconos de <a href="https://iconify.design/" target="_blank" rel="noopener noreferrer">Iconify</a>. Se conservarán el autor y la licencia del icono elegido.</p>
        <div class="footer"><button id="close" type="button">Cerrar</button></div>
      </dialog>`;
    this._built = true;
    const root = this.shadowRoot;
    root.querySelector("#open-picker").disabled = Boolean(this._disabled);
    root.querySelector("#open-picker").addEventListener("click", () => this.open(this.getQuery?.() ?? ""));
    root.querySelector("#search").addEventListener("click", () => void this._search());
    root.querySelector("#query").addEventListener("keydown", event => {
      if (event.key === "Enter") { event.preventDefault(); void this._search(); }
    });
    root.querySelector("#query").addEventListener("input", () => {
      this._generation += 1;
      this._busy = false;
      this._icons = [];
      this._searchOptions = {};
      this._status("");
      this._renderResults();
    });
    root.querySelector("#close").addEventListener("click", () => this.close());
    root.querySelector("dialog").addEventListener("close", () => {
      if (root.querySelector("dialog").open) return;
      this._generation += 1;
      this._busy = this._importing = false;
      root.querySelector("#open-picker").focus();
    });
  }

  open(query) {
    if (this._disabled || !this._hass) return;
    this._generation += 1;
    this._busy = this._importing = false;
    this._icons = [];
    this._searchOptions = this.getSearchOptions?.() ?? {};
    this.shadowRoot.querySelector("#query").value = query.slice(0, 100);
    this._status("");
    this._renderResults();
    this.shadowRoot.querySelector("dialog").showModal();
    this.shadowRoot.querySelector("#query").focus();
    if (query.trim().length >= 2) void this._search();
  }

  close() {
    this._generation += 1;
    this._busy = this._importing = false;
    this.shadowRoot.querySelector("dialog")?.close();
  }

  _status(message, error = false) {
    const status = this.shadowRoot.querySelector("#status");
    status.textContent = message;
    status.hidden = !message;
    status.classList.toggle("error", error);
  }

  async _search() {
    const query = this.shadowRoot.querySelector("#query").value.trim();
    const generation = ++this._generation;
    this._icons = [];
    this._query = query;
    if (query.length < 2) {
      this._busy = false;
      this._status("Escribe al menos dos caracteres.", true);
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
      this._icons = result.icons.slice(0, 3);
      if (result.query) this.shadowRoot.querySelector("#query").value = result.query;
      this._searchOptions = {};
      this._status(this._icons.length ? "" : "No se han encontrado iconos a color. Prueba con otro término o abre la búsqueda completa con +.");
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
    const suggestions = Array.from({length:3}, (_, index) => {
      const icon = this._icons[index];
      if (!icon) { const empty = node("span", undefined, "option empty"); empty.setAttribute("aria-hidden", "true"); return empty; }
      const button = node("button", undefined, "option");
      button.type = "button";
      button.title = `${icon.collection} · ${icon.author} · ${icon.license}`;
      button.setAttribute("aria-label", `Elegir ${icon.label} (${icon.collection})`);
      button.disabled = Boolean(this._busy);
      const image = node("img");
      // Preview URLs are constructed by the backend, never inserted as markup.
      image.src = icon.preview_url;
      image.alt = "";
      image.referrerPolicy = "no-referrer";
      image.addEventListener("error", () => { image.hidden = true; }, { once:true });
      button.append(image, node("span", icon.label));
      button.addEventListener("click", () => void this._select(icon));
      return button;
    });
    const query = root.querySelector("#query").value.trim();
    const more = link("", `https://icon-sets.iconify.design/?query=${encodeURIComponent(query)}`);
    more.id = "all-icons";
    more.className = "option more";
    more.title = "Ver todos los iconos en Iconify";
    more.setAttribute("aria-label", more.title);
    const plus = node("ha-icon"); plus.setAttribute("icon", "mdi:plus-thick"); plus.setAttribute("aria-hidden", "true"); more.append(plus);
    if (query.length < 2) { more.removeAttribute("href"); more.setAttribute("aria-disabled", "true"); more.tabIndex = -1; }
    root.querySelector("#results").replaceChildren(...suggestions, more);
    root.querySelector("#search").disabled = Boolean(this._importing);
    root.querySelector("#query").disabled = Boolean(this._importing);
  }

  async _select(icon) {
    if (this._busy) return;
    const generation = ++this._generation;
    this._busy = this._importing = true;
    this._status("Guardando icono en Home Assistant…");
    this._renderResults();
    try {
      const asset = await this._hass.callWS({ type: `${PREFIX}import`, icon_id: icon.id });
      if (generation !== this._generation || !this.isConnected) return;
      this._value = asset.url;
      this._infoGeneration += 1;
      this._showAttribution(asset);
      this.onSelect?.(asset);
      this.close();
    } catch (error) {
      if (generation === this._generation && this.isConnected) this._status(error.message ?? "No se ha podido guardar el icono.", true);
    } finally {
      if (generation === this._generation || !this.shadowRoot.querySelector("dialog").open) {
        this._busy = this._importing = false;
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
