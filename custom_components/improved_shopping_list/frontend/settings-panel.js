import { todoEntities, isAvailable } from "./todo-client.js?v=0.11.0";
import { DEFAULT_APPEARANCE, gradientTextColor } from "./list-settings-client.js?v=0.11.0";

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

  disconnectedCallback() { clearTimeout(this._storeRetryTimer); clearInterval(this._storeProgressTimer); this._stopStoreProgress?.(); this._stopStoreProgress = null; this._productsLoading = false; this._productsGeneration = (this._productsGeneration || 0) + 1; this.shadowRoot.querySelector("#store-dialog")?.close(); }

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
        .settings-tabs button { display:inline-flex; align-items:center; justify-content:center; gap:8px; }
        .settings-tabs ha-icon { --mdc-icon-size:20px; display:flex; align-items:center; justify-content:center; width:20px; height:20px; flex:none; line-height:0; }
        .settings-tabs [aria-pressed=true] { background:var(--secondary-background-color,#edf4ee); font-weight:650; }
        .appearance-fields { display:grid; grid-template-columns:1fr 1fr; gap:18px; }
        input[type=checkbox] { min-height:20px; width:20px; vertical-align:middle; accent-color:#267052; }
        input[type=color] { display:block; width:100%; padding:5px; cursor:pointer; }
        .appearance-actions { display:flex; justify-content:flex-end; flex-wrap:wrap; gap:10px; margin-top:24px; }
        .preview { display:grid; place-items:center; min-height:120px; border-radius:16px; margin-top:24px; padding:20px; font-weight:650; }
        @media(max-width:540px) { .appearance-fields { grid-template-columns:1fr; } }
        .store-row { flex-wrap:nowrap; gap:12px; }
        .store-logo { width:56px; height:56px; padding:8px; flex:none; object-fit:contain; border-radius:10px; background:#fff; }
        .store-name { flex:1; min-width:0; }
        .store-controls { display:flex; align-items:center; gap:12px; margin-left:auto; flex:none; }
        .store-toggle[type=checkbox] { appearance:none; position:relative; width:40px; height:24px; min-height:24px; margin:0; padding:0; border:0; border-radius:20px; background:#b3261e; cursor:pointer; }
        .store-toggle::before { content:""; position:absolute; top:4px; left:4px; width:16px; height:16px; border-radius:50%; background:white; }
        .store-toggle:checked { background:#267052; }.store-toggle:checked::before { transform:translateX(16px); }
        .store-cog { display:flex; align-items:center; justify-content:center; padding:0; width:44px; height:44px; min-height:44px; border:0; background:transparent; box-shadow:none; }
        .store-cog ha-icon { display:flex; align-items:center; justify-content:center; width:24px; height:24px; --mdc-icon-size:24px; }
        dialog { color:inherit; background:var(--card-background-color,#fff); width:min(680px,calc(100vw - 28px)); max-height:calc(100dvh - 28px); border:1px solid var(--divider-color,#dfe7e1); border-radius:18px; padding:24px; }
        dialog::backdrop { background:rgba(0,0,0,.4); }
        .store-products { display:grid; gap:12px; margin-top:16px; }.store-product { display:flex; justify-content:space-between; align-items:center; gap:12px; border:1px solid var(--divider-color,#dfe7e1); border-radius:10px; padding:14px; }
        .store-progress progress { display:block; width:100%; height:14px; accent-color:var(--primary-color,#267052); }.store-progress p { margin:6px 0; }
        .store-product-info { min-width:0; overflow-wrap:anywhere; }.store-product-info p { margin:4px 0 0; }.store-price { flex:none; max-width:50%; text-align:right; }.store-price p { margin:4px 0; font-size:12px; }
        @media(max-width:540px) { dialog { padding:18px; }.store-row { padding:12px; gap:8px; }.store-logo { width:40px; height:40px; padding:6px; }.store-controls { gap:8px; } }
        .primary { color:#fff; background:#267052; border:0; }
        .add-row { display:flex; align-items:end; gap:10px; }
        .select-wrap { flex:1; min-width:0; }
        .community-export { display:flex; align-items:center; gap:24px; }
        .community-export p { flex:1; min-width:0; }
        .community-export button { flex:none; max-width:42%; }
        #settings-community a { color:var(--primary-color,#267052); }
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
      <nav class="settings-tabs" aria-label="Vistas de ajustes"><button id="settings-view-lists" aria-pressed="true"><ha-icon icon="mdi:format-list-checks" aria-hidden="true"></ha-icon>Listas</button><button id="settings-view-appearance" aria-pressed="false"><ha-icon icon="mdi:palette" aria-hidden="true"></ha-icon>Personalización</button><button id="settings-view-stores" aria-pressed="false"><ha-icon icon="mdi:store" aria-hidden="true"></ha-icon>Tiendas</button><button id="settings-view-community" aria-pressed="false"><ha-icon icon="mdi:account-group" aria-hidden="true"></ha-icon>Comunidad</button></nav>
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
      </section>
      <section id="settings-stores" class="card" aria-labelledby="settings-stores-title" hidden>
        <h2 id="settings-stores-title">Tiendas</h2>
        <article class="store-row" id="mercadona-row">
          <img class="store-logo" src="https://i.pinimg.com/736x/66/bc/4e/66bc4e8d1482e6ec4525987c1691c83e.jpg" alt="Logo de Mercadona" referrerpolicy="no-referrer" loading="lazy" width="56" height="56">
          <div class="store-name"><h3>Mercadona</h3><span id="store-favorite" class="badge"></span></div>
          <div class="store-controls"><input id="mercadona-enabled" class="store-toggle" type="checkbox" role="switch" aria-label="Habilitar Mercadona"><button id="configure-mercadona" class="store-cog" type="button" aria-label="Ajustes de Mercadona" title="Ajustes de Mercadona"><ha-icon icon="mdi:cog" aria-hidden="true"></ha-icon></button></div>
        </article>
      </section>
      <dialog id="store-dialog" aria-labelledby="store-dialog-title">
        <h2 id="store-dialog-title">Mercadona</h2>
        <nav class="settings-tabs" aria-label="Vistas de Mercadona"><button id="store-view-products" aria-pressed="true" type="button"><ha-icon icon="mdi:view-grid" aria-hidden="true"></ha-icon>Productos</button><button id="store-view-configuration" aria-pressed="false" type="button"><ha-icon icon="mdi:cog" aria-hidden="true"></ha-icon>Configuración</button></nav>
        <div id="store-dialog-error" class="notice error" role="alert" hidden></div>
        <section id="store-products-view">
          <div class="appearance-actions"><button id="refresh-store-products" type="button"><ha-icon icon="mdi:refresh" aria-hidden="true"></ha-icon> Forzar actualización</button></div>
          <p id="store-products-status" role="status"></p><div id="store-products-error" class="notice error" role="alert" hidden></div>
          <div id="store-progress" class="store-progress" hidden><progress aria-label="Progreso de actualización de precios"></progress><p id="store-progress-count" role="status"></p><p id="store-progress-time"></p><p>Se revisan hasta 20 códigos por lote, durante unos 35 segundos. La estimación puede variar según la respuesta de la tienda.</p></div>
          <div id="store-products" class="store-products"></div>
        </section>
        <section id="store-configuration-view" hidden>
          <form id="store-form">
            <p>Introduce tu código postal para obtener el almacén asignado por Mercadona. No necesitas una cuenta.</p>
            <label for="mercadona-postal">Código postal</label>
            <input id="mercadona-postal" type="text" inputmode="numeric" autocomplete="postal-code" maxlength="5" pattern="(?:0[1-9]|[1-4][0-9]|5[0-2])[0-9]{3}" placeholder="28001" required>
            <p id="mercadona-warehouse" role="status"></p>
            <div class="appearance-actions"><button id="save-store" class="primary" type="submit">Comprobar y guardar</button></div>
          </form>
        </section>
        <div class="appearance-actions"><button id="close-store-dialog" type="button">Cerrar</button></div>
      </dialog>
      <section id="settings-community" class="card" aria-labelledby="settings-community-title" hidden>
        <h2 id="settings-community-title">Comunidad</h2>
        <div class="community-export"><p>Exporta un diccionario con los nombres de tus productos, sus traducciones disponibles y las imágenes locales asignadas. Puedes enviarlo al mantenedor para incorporar las imágenes revisadas al catálogo comunitario, creando un Issue en el <a href="https://github.com/TitoTB/Improved-Shopping-List" target="_blank" rel="noopener noreferrer">repositorio de Github</a>.</p><button id="export-community" class="primary" type="button">Exportar mis iconos</button></div>
        <p>No se envía nada automáticamente. El ZIP no incluye listas, códigos, notas ni datos de tu cuenta. Las imágenes externas se indican como referencias y las licencias desconocidas quedan pendientes de revisión.</p>
        <p>Este proyecto ha sido desarrollado por la <a href="https://t.me/aguacatec_es/3" target="_blank" rel="noopener noreferrer">comunidad de Aguacatec</a>. Si tienes cualquier duda o sugerencia puedes unirte a través de Telegram o apoyarnos <a href="https://www.patreon.com/c/aguacatec/membership" target="_blank" rel="noopener noreferrer">haciéndote Patreon</a>.</p>
      </section>`;
    this._built = true;
    this.shadowRoot.querySelector("#add-list").addEventListener("click", () => {
      const entity = this.shadowRoot.querySelector("#todo-entity").value;
      if (entity) void this._act("add", entity);
    });
    const root = this.shadowRoot;
    for (const [id, view] of [["settings-view-lists", "lists"], ["settings-view-appearance", "appearance"], ["settings-view-community", "community"], ["settings-view-stores", "stores"]]) {
      root.querySelector(`#${id}`).addEventListener("click", () => {
        for (const section of ["lists", "appearance", "community", "stores"]) {
          root.querySelector(`#settings-${section}`).hidden = view !== section;
          root.querySelector(`#settings-view-${section}`).setAttribute("aria-pressed", String(view === section));
        }
        this._notice = "";
        this._error = "";
        this._render();
      });
    }
    root.querySelector("#store-form").addEventListener("submit", event => { event.preventDefault(); void this._saveStore(this._storeEnableDraft ?? Boolean(this._data.settings.stores?.mercadona?.enabled), true); });
    root.querySelector("#mercadona-enabled").addEventListener("change", () => {
      const enabled = root.querySelector("#mercadona-enabled").checked;
      const store = this._data.settings.stores?.mercadona ?? {};
      if (enabled && !store.postal_code) { this._storeEnableDraft = true; this._openStore("configuration"); }
      else void this._saveStore(enabled, false);
    });
    root.querySelector("#configure-mercadona").addEventListener("click", () => this._openStore("products"));
    root.querySelector("#close-store-dialog").addEventListener("click", () => root.querySelector("#store-dialog").close());
    root.querySelector("#store-dialog").addEventListener("cancel", event => { if (this._busy) event.preventDefault(); });
    root.querySelector("#store-dialog").addEventListener("close", () => {
      if (root.querySelector("#store-dialog").open) return;
      clearTimeout(this._storeRetryTimer);
      this._storeEnableDraft = undefined; this._storeDirty = false;
      this._productsGeneration = (this._productsGeneration || 0) + 1; this._productsLoading = false;
      this._error = ""; this._render();
    });
    for (const view of ["products", "configuration"]) root.querySelector(`#store-view-${view}`).addEventListener("click", () => this._switchStoreView(view));
    root.querySelector("#refresh-store-products").addEventListener("click", () => void this._loadStoreProducts(true));
    root.querySelector("#store-form").addEventListener("input", () => { this._storeDirty = true; this._renderStore(); });
    root.querySelector("#export-community").addEventListener("click", () => void this._exportCommunity());
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
    root.querySelector("#export-community").disabled = locked;
    const error = root.querySelector("#settings-error");
    error.textContent = this._error || settings.error;
    error.hidden = !error.textContent || root.querySelector("#store-dialog").open;
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
    this._renderStore();
    const form = root.querySelector("#appearance-form");
    if (!this._appearanceDirty && !this._busy) this._fillAppearance(settings.appearance);
    // Home Assistant's scoped registry does not implement form.elements iteration.
    for (const control of form.querySelectorAll("input, select, textarea, button")) control.disabled = locked;
  }

  _renderStore() {
    const { settings, hass } = this._data;
    const root = this.shadowRoot;
    const store = settings.stores?.mercadona ?? {};
    const enabled = root.querySelector("#mercadona-enabled");
    const postal = root.querySelector("#mercadona-postal");
    if (!this._storeDirty && !this._busy) {
      enabled.checked = this._storeEnableDraft ?? (store.enabled === true);
      postal.value = store.postal_code ?? "";
    }
    const locked = hass?.user?.is_admin !== true || !settings.loaded || settings.loading || this._busy;
    enabled.disabled = locked;
    postal.disabled = locked;
    root.querySelector("#configure-mercadona").disabled = !settings.loaded || settings.loading || this._busy;
    root.querySelector("#close-store-dialog").disabled = Boolean(this._busy);
    root.querySelector("#store-dialog-error").textContent = this._error || "";
    root.querySelector("#store-dialog-error").hidden = !this._error;
    const save = root.querySelector("#save-store");
    save.disabled = locked;
    save.textContent = this._busy ? "Guardando…" : "Comprobar y guardar";
    root.querySelector("#mercadona-warehouse").textContent = store.warehouse
      ? `Configuración guardada: ${store.postal_code} · Almacén: ${store.warehouse}${store.enabled ? "" : " · Deshabilitada"}`
      : "Todavía no se ha configurado un almacén.";
    root.querySelector("#store-favorite").textContent = store.enabled && settings.favoriteStore === "mercadona"
      ? "Favorita" : "";
    this._renderStoreProducts();
  }

  async _saveStore(enabled, verify) {
    if (this._busy || this._data?.hass?.user?.is_admin !== true) return;
    const root = this.shadowRoot;
    const postal = verify ? root.querySelector("#mercadona-postal").value.trim() : this._data.settings.stores?.mercadona?.postal_code ?? "";
    this._busy = true;
    this._error = this._notice = "";
    this._render();
    try {
      await this._data.settings.saveStore(enabled, postal, verify);
      this._storeEnableDraft = undefined;
      this._storeDirty = false;
      this._notice = verify ? "Configuración de Mercadona guardada." : enabled ? "Mercadona activada." : "Mercadona deshabilitada.";
    } catch (error) { this._error = error.message ?? "No se ha podido configurar Mercadona."; }
    finally { this._busy = false; this._render(); }
  }

  _openStore(view) {
    const root = this.shadowRoot;
    this._error = ""; this._storeDirty = false;
    this._renderStore();
    root.querySelector("#store-dialog").showModal();
    this._switchStoreView(view);
  }

  _switchStoreView(view) {
    const root = this.shadowRoot;
    for (const section of ["products", "configuration"]) {
      root.querySelector(`#store-${section}-view`).hidden = view !== section;
      root.querySelector(`#store-view-${section}`).setAttribute("aria-pressed", String(view === section));
    }
    if (view === "products") void this._loadStoreProducts(false);
  }

  _renderStoreProducts() {
    const root = this.shadowRoot;
    const store = this._data.settings.stores?.mercadona ?? {};
    this._renderStoreProgress();
    const data = this._storeProducts?.warehouse === store.warehouse && store.enabled ? this._storeProducts : null;
    const retryAt = Number.isFinite(data?.retry_at) ? data.retry_at : 0;
    const paused = retryAt > Date.now()/1000;
    clearTimeout(this._storeRetryTimer);
    if (paused && root.querySelector("#store-dialog").open) {
      this._storeRetryTimer = setTimeout(() => this._renderStoreProducts(), (retryAt-Date.now()/1000)*1000+100);
    }
    const refresh = root.querySelector("#refresh-store-products");
    refresh.disabled = !store.enabled || !store.warehouse || paused || this._productsLoading || this._busy || this._data.hass?.user?.is_admin !== true;
    refresh.title = paused ? "Espera al final de la pausa indicada antes de volver a consultar." : "Consultar de nuevo los precios de la tienda";
    const error = root.querySelector("#store-products-error");
    error.textContent = store.enabled ? data?.error || this._productsError || "" : "";
    error.hidden = !error.textContent || this._productsLoading;
    const progress = Number.isFinite(data?.total) && data.total > 0 ? ` ${data.processed ?? 0} de ${data.total} códigos revisados.` : "";
    root.querySelector("#store-products-status").textContent = this._productsLoading ? "Consultando productos y precios…"
      : !store.enabled ? "Habilita la tienda para consultar sus productos."
      : paused ? `Actualización pausada hasta las ${new Date(retryAt*1000).toLocaleTimeString("es-ES")}.${progress} Consulta el diagnóstico en Logs → Tiendas.`
      : error.textContent ? `La última actualización no se pudo completar.${progress} Consulta el diagnóstico en Logs → Tiendas.`
      : data?.remaining ? `Quedan ${data.remaining} códigos por revisar. Puedes continuar con Forzar actualización.`
      : !data?.products?.length ? "No hay productos encontrados. Se buscan los EAN válidos de tu catálogo."
      : `${data.products.length} productos encontrados · Almacén: ${store.warehouse}`;
    const money = value => new Intl.NumberFormat("es-ES",{style:"currency",currency:"EUR"}).format(value);
    root.querySelector("#store-products").replaceChildren(...(data?.products ?? []).map(product => {
      const row = document.createElement("div"); row.className = "store-product";
      const info = document.createElement("div"); info.className = "store-product-info";
      const name = document.createElement("strong"); name.textContent = product.name;
      const code = document.createElement("p"); code.textContent = `EAN: ${product.ean}`;
      const source = document.createElement("a"); source.textContent = product.store_name || "Ver en Mercadona";
      source.href = `https://tienda.mercadona.es/product/${encodeURIComponent(product.store_product_id)}`; source.target = "_blank"; source.rel = "noopener noreferrer";
      info.append(name,code,source);
      const prices = document.createElement("div"); prices.className = "store-price";
      const price = document.createElement("strong"); price.textContent = `${product.approximate ? "≈ " : ""}${money(product.price)}`;
      const checked = document.createElement("p"); checked.textContent = `Consultado: ${new Date(product.checked_at*1000).toLocaleString("es-ES")}`;
      prices.append(price);
      if (Number.isFinite(product.reference_price) && product.reference_unit) {
        const reference = document.createElement("p"); reference.textContent = `${money(product.reference_price)}/${product.reference_unit}`; prices.append(reference);
      }
      if (product.available === false) { const unavailable = document.createElement("p"); unavailable.textContent = "No disponible"; prices.append(unavailable); }
      prices.append(checked); row.append(info,prices); return row;
    }));
  }

  _renderStoreProgress() {
    const root = this.shadowRoot;
    const state = this._storeProgress;
    const store = this._data.settings.stores?.mercadona ?? {};
    const visible = this._productsLoading && this._productsForced && store.enabled && store.warehouse === this._productsWarehouse;
    root.querySelector("#store-progress").hidden = !visible;
    if (!visible) return;
    const bar = root.querySelector("#store-progress progress");
    const total = Math.max(0, Number(state?.total) || 0);
    const processed = Math.min(total, Math.max(0, Number(state?.processed) || 0));
    bar.max = total || 1;
    if (total) bar.value = processed; else bar.removeAttribute("value");
    const phase = {starting:"Preparando consultas", waiting:"Esperando entre consultas", ean:"Buscando por EAN", name:"Buscando por nombre", processed:"Código revisado"}[state?.phase] ?? "Preparando actualización";
    root.querySelector("#store-progress-count").textContent = total ? `${processed} de ${total} códigos revisados · ${phase}` : "Preparando actualización…";
    const seconds = Math.max(0, Math.ceil((state?.estimated_seconds ?? 0) - (Date.now() - (this._storeProgressReceived ?? Date.now())) / 1000));
    root.querySelector("#store-progress-time").textContent = state?.running
      ? seconds > 0 ? `Tiempo estimado restante de este lote: ${seconds} s` : "Finalizando lote…"
      : "Esperando respuesta…";
  }

  async _loadStoreProducts(force) {
    if (this._productsLoading) return;
    const store = this._data.settings.stores?.mercadona ?? {};
    if (!store.enabled || !store.warehouse) { this._renderStoreProducts(); return; }
    const generation = this._productsGeneration = (this._productsGeneration || 0) + 1;
    const warehouse = store.warehouse;
    this._productsLoading = true; this._productsForced = force; this._productsWarehouse = warehouse; this._storeProgress = null; this._productsError = ""; this._renderStoreProducts();
    let unsubscribe;
    try {
      if (force) {
        const stop = await this._data.hass.connection.subscribeMessage(state => {
          if (generation !== this._productsGeneration || state.warehouse !== warehouse || this._data.settings.stores?.mercadona?.warehouse !== warehouse) return;
          this._storeProgress = state; this._storeProgressReceived = Date.now(); this._renderStoreProgress();
        }, {type:"improved_shopping_list/settings/store_progress"});
        let stopped = false;
        unsubscribe = () => { if (!stopped) { stopped = true; stop(); } };
        if (generation !== this._productsGeneration) return;
        this._stopStoreProgress = unsubscribe;
        this._storeProgressTimer = setInterval(() => this._renderStoreProgress(), 1000);
      }
      const data = await this._data.hass.callWS({type:"improved_shopping_list/settings/store_products",force});
      if (generation === this._productsGeneration && this._data.settings.stores?.mercadona?.warehouse === warehouse) this._storeProducts = data;
    } catch (error) { if (generation === this._productsGeneration) this._productsError = error.message ?? "No se han podido consultar los precios."; }
    finally {
      unsubscribe?.();
      if (generation === this._productsGeneration) {
        clearInterval(this._storeProgressTimer); this._stopStoreProgress = null;
        this._productsLoading = false; this._renderStoreProducts();
      }
    }
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

  async _exportCommunity() {
    if (this._busy || !this._data?.hass?.user?.is_admin) return;
    this._busy = true;
    this._error = this._notice = "";
    this._render();
    let downloadUrl;
    try {
      const result = await this._data.hass.callWS({type:"improved_shopping_list/community/export"});
      const bytes = Uint8Array.from(atob(result.data), character => character.charCodeAt(0));
      downloadUrl = URL.createObjectURL(new Blob([bytes], {type:"application/zip"}));
      const anchor = document.createElement("a");
      anchor.href = downloadUrl;
      anchor.download = "improved-shopping-list-icons.zip";
      this.shadowRoot.append(anchor);
      anchor.click();
      anchor.remove();
      this._notice = `Exportados ${result.entries} registros y ${result.images} imágenes.${result.skipped ? ` No se pudieron incluir ${result.skipped} referencias locales.` : ""}`;
    } catch (error) { this._error = error.message ?? "No se ha podido exportar el diccionario."; }
    finally {
      if (downloadUrl) setTimeout(() => URL.revokeObjectURL(downloadUrl), 60000);
      this._busy = false;
      this._render();
    }
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
