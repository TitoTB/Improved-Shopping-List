import { ListSettingsSession } from "./list-settings-client.js?v=0.59.0";

const SOURCES = {manual:"Usuario / API",automatic:"Automático · Home Assistant",reader:"Lector",integration:"Integración",external:"Proveedor externo · origen desconocido",home_assistant:"Home Assistant · origen desconocido"};
const GROUPS = {notification:"Notificaciones",stock:"Stock",list:"Listas",gateway:"Listas pasarela",catalog:"Catálogo y categorías",reader:"Lectores",settings:"Ajustes",recurrence:"Recurrencias",stores:"Tiendas"};
const FIELDS = {commercial_references:"alternativas de compra",ingredients:"ingredientes",recipe_ids:"recetas asociadas",product_ids:"productos asociados",season_months:"meses de temporada",name:"nombre",category:"categoría",icon:"icono",color:"color",image_url:"imagen",price:"precio",currency:"moneda",tags:"etiquetas",notes:"notas",barcode:"código",barcodes:"códigos de barras",nfc_tags:"etiquetas NFC",reader_actions:"acciones de lectores",recurrence:"recurrencia",price_updated_at:"fecha del precio"};
const REFERENCE_FIELDS={store:"tienda",name:"nombre comercial",ean:"EAN",reference_id:"referencia de la tienda",ticket_reference_id:"referencia del ticket",url:"URL",brand:"marca",image_url:"imagen",content_quantity:"contenido por envase",content_unit:"unidades",pack_count:"unidades por pack",last_price:"precio",measure_price:"precio por unidad de medida",nutriscore:"Nutri-Score",active:"disponibilidad de la alternativa"};
const STORES={alcampo:"Alcampo",elcorteingles:"El Corte Inglés",carrefour:"Carrefour",lidl:"Lidl",mercadona:"Mercadona",dia:"DIA",consum:"Consum",eroski:"Eroski",lasirena:"La Sirena"};
const referenceDetail=change=>{
  const identity=change.ean?`EAN ${change.ean}`:change.name||change.reference_id||'Referencia';
  const label=[STORES[change.store]??change.store,identity].filter(Boolean).join(' · ');
  const fields=[['added_fields','Añadidos'],['updated_fields','Actualizados'],['removed_fields','Eliminados']].flatMap(([key,title])=>change[key]?.length?[`${title}: ${change[key].map(field=>REFERENCE_FIELDS[field]??field).join(', ')}`]:[]);
  return [change.action==='added'&&change.store?`Nueva alternativa: ${label}`:change.action==='removed'&&change.store?`Alternativa retirada: ${label}`:label,...fields].join(' · ');
};
const node = (tag, text, className) => { const value=document.createElement(tag); if(text!==undefined)value.textContent=text; if(className)value.className=className;return value; };

class LogsSession extends ListSettingsSession {
  constructor(getHass,onChange) {
    super(getHass,onChange,"improved_shopping_list/logs/");
    this.entries=[];
    this.limit=1000;
  }
  _receive(data) {
    this.entries=data.entries??[];
    this.limit=data.limit??1000;
    this.loaded=true;
    this.loading=false;
    this.error="";
    this.onChange();
  }
}

class ImprovedShoppingLogs extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({mode:"open"});
    this._visible=100;
    this._session=new LogsSession(()=>this._hass,()=>this._render());
  }
  set hass(value) {
    const changed=this._hass?.connection!==value?.connection;
    this._hass=value;
    if(changed&&this._active)void this._session.start();
  }
  set active(value) {
    if(this._active===value)return;
    this._active=value;
    if(value&&this._hass)void this._session.start();
    else this._session.stop();
  }
  connectedCallback() { if(!this._built)this._build(); }
  disconnectedCallback() { this._session.stop();this._active=false; }

  _build() {
    this.shadowRoot.innerHTML=`
      <style>
        :host{display:block;color:var(--primary-text-color,#20352d)}:host([hidden]),[hidden]{display:none!important}*{box-sizing:border-box}
        .heading{display:flex;align-items:center;justify-content:space-between;gap:12px;margin:0 0 18px}h2{font-size:20px;margin:0}
        button,input,select{font:inherit;color:inherit}button{cursor:pointer;border:1px solid var(--divider-color,#dfe7e1);border-radius:10px;background:transparent;min-height:44px;padding:10px 14px}button:disabled{opacity:.5;cursor:default}button:focus-visible,input:focus-visible,select:focus-visible{outline:3px solid var(--primary-color,#267052);outline-offset:3px}
        #refresh{width:44px;padding:0;display:grid;place-items:center}ha-icon{--mdc-icon-size:20px;width:20px;height:20px;display:block}
        .filters{display:grid;grid-template-columns:2fr 1fr 1fr;gap:12px;margin-bottom:16px}label{font-size:13px;font-weight:600;min-width:0}input,select{display:block;width:100%;min-width:0;min-height:44px;margin-top:7px;padding:10px 12px;border:1px solid var(--divider-color,#dfe7e1);border-radius:10px;background:var(--card-background-color,#fff)}
        .helper,#status,#empty{font-size:13px;color:var(--secondary-text-color,#63766b);line-height:1.6}.error{color:var(--error-color,#bd3636)!important}
        ol{list-style:none;padding:0;margin:16px 0;display:grid;gap:10px}li{display:grid;grid-template-columns:32px minmax(0,1fr);gap:12px;border:1px solid var(--divider-color,#dfe7e1);border-radius:12px;padding:16px;background:var(--card-background-color,#fff)}.event-icon{display:grid;place-items:center;align-self:start;border-radius:50%;width:32px;height:32px;background:var(--secondary-background-color,#edf4ee);color:var(--primary-color,#267052)}
        .message{margin:0;font-size:15px;line-height:1.5;font-weight:600;overflow-wrap:anywhere}.meta{display:flex;flex-wrap:wrap;gap:4px 12px;margin-top:6px;font-size:12px;line-height:1.5;color:var(--secondary-text-color,#63766b)}.detail{margin:6px 0 0;font-size:12px;line-height:1.5;overflow-wrap:anywhere;color:var(--secondary-text-color,#63766b)}.footer{text-align:center}
        @media(max-width:650px){.filters{grid-template-columns:1fr 1fr}.search{grid-column:1/-1}li{padding:12px;gap:8px}}
        .technical{margin-top:10px;font-size:12px;min-width:0}.technical summary{cursor:pointer}.technical pre{white-space:pre-wrap;overflow-wrap:anywhere;word-break:break-word;padding:10px;border-radius:8px;background:var(--secondary-background-color,#edf4ee);line-height:1.5}
      </style>
      <div class="heading"><h2>Logs</h2><button id="refresh" type="button" aria-label="Actualizar logs" title="Actualizar logs"><ha-icon icon="mdi:refresh"></ha-icon></button></div>
      <div class="filters"><label class="search">Buscar en el historial<input id="search" type="search" placeholder="Producto, categoría, lector o lista"></label><label>Actividad<select id="kind" aria-label="Actividad"><option value="">Toda la actividad</option>${Object.entries(GROUPS).map(([key,label])=>`<option value="${key}">${label}</option>`).join("")}</select></label><label>Origen<select id="source" aria-label="Origen"><option value="">Todos los orígenes</option>${Object.entries(SOURCES).map(([key,label])=>`<option value="${key}">${label}</option>`).join("")}</select></label></div>
      <p class="helper">Últimas <span id="limit">1000</span> entradas, de más reciente a más antigua. El registro comienza al instalar esta función.</p>
      <p id="status" role="status" hidden></p><p id="empty" hidden></p><ol id="entries" aria-label="Historial de actividad"></ol><div class="footer"><button id="more" type="button" hidden>Ver más</button></div>`;
    this._built=true;
    const root=this.shadowRoot;
    for(const selector of ["#search","#kind","#source"])root.querySelector(selector).addEventListener("input",()=>{this._visible=100;this._render();});
    root.querySelector("#refresh").addEventListener("click",()=>void this._session.refresh());
    root.querySelector("#more").addEventListener("click",()=>{this._visible+=100;this._render();});
    this._render();
  }

  _render() {
    if(!this._built)return;
    const root=this.shadowRoot,session=this._session;
    const status=root.querySelector("#status");
    status.textContent=session.error||(session.loading?"Cargando logs…":"");
    status.hidden=!status.textContent;
    status.classList.toggle("error",Boolean(session.error));
    root.querySelector("#refresh").disabled=session.loading;
    root.querySelector("#limit").textContent=String(session.limit);
    const key=value=>String(value??"").normalize("NFD").replace(/\p{M}/gu,"").toLocaleLowerCase("es");
    const search=key(root.querySelector("#search").value.trim());
    const kind=root.querySelector("#kind").value,source=root.querySelector("#source").value;
    const entries=session.entries.filter(entry=>(!kind||entry.kind.startsWith(kind+"."))&&(!source||entry.source===source)&&(!search||key([entry.message,entry.product,entry.category,entry.reader,entry.list_name,entry.list_entity,entry.code,entry.previous_name,...(entry.reference_changes??[]).map(referenceDetail),JSON.stringify(entry.diagnostics??{})].join(" ")).includes(search)));
    const content=entries.slice(0,this._visible).map(entry=>{
      const row=node("li");row.dataset.entryId=entry.id;
      const badge=node("span",undefined,"event-icon"),icon=node("ha-icon");
      icon.setAttribute("icon",entry.kind.startsWith("stock.")?"mdi:package-variant":entry.kind.startsWith("stores.")?"mdi:store":entry.kind.startsWith("reader.")?"mdi:barcode-scan":entry.kind.includes("categories")?"mdi:label":entry.kind.startsWith("catalog.")?"mdi:view-grid":entry.kind==="list.removed"?"mdi:cart-minus":entry.kind==="list.completed"?"mdi:check":entry.kind.startsWith("settings.")?"mdi:cog":"mdi:cart-plus");
      icon.setAttribute("aria-hidden","true");badge.append(icon);
      const body=node("div");body.append(node("p",entry.message,"message"));
      const meta=node("div",undefined,"meta"),date=new Date(entry.time),time=node("time",Number.isNaN(date.getTime())?entry.time:date.toLocaleString());time.dateTime=entry.time;
      meta.append(time,node("span",SOURCES[entry.source]??"Origen desconocido"));
      if(entry.list_name||entry.list_entity)meta.append(node("span",entry.list_name||entry.list_entity));
      if(entry.reader)meta.append(node("span",`Lector: ${entry.reader}`));
      body.append(meta);
      if(entry.previous_name)body.append(node("p",`Nombre anterior: ${entry.previous_name}`,"detail"));
      const fields=(entry.changed_fields??[]).filter(field=>field!=='commercial_references'||!entry.reference_changes?.length);
      if(fields.length)body.append(node("p",`Campos: ${fields.map(field=>FIELDS[field]??field).join(", ")}`,"detail"));
      for(const change of entry.reference_changes??[])body.append(node("p",referenceDetail(change),"detail reference-change"));
      if(entry.code)body.append(node("p",`Código: ${entry.code}`,"detail"));
      if(entry.diagnostics && typeof entry.diagnostics === "object") {
        const details=node("details",undefined,"technical");
        details.append(node("summary","Información técnica"),node("pre",JSON.stringify(entry.diagnostics,null,2)));
        body.append(details);
      }
      row.append(badge,body);return row;
    });
    root.querySelector("#entries").replaceChildren(...content);
    const empty=root.querySelector("#empty");empty.hidden=entries.length>0||session.loading||Boolean(session.error);empty.textContent=session.entries.length?"No hay entradas que coincidan con estos filtros.":"Todavía no hay actividad registrada.";
    root.querySelector("#more").hidden=entries.length<=this._visible;
  }
}

if(!customElements.get("isl-logs"))customElements.define("isl-logs",ImprovedShoppingLogs);
