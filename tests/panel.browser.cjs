/* Real-browser panel tests against a simulated Home Assistant WebSocket API. */
const assert = require("node:assert/strict");
const http = require("node:http");
const fs = require("node:fs/promises");
const path = require("node:path");
const { chromium } = require("playwright");

const root = path.resolve(__dirname, "../custom_components/improved_shopping_list/frontend");
const html = `<!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Panel test</title><style>html,body{margin:0;height:100%;font-family:system-ui}</style><body><script type="module">
import '/panel.js';
const data = {
  'todo.bring': [
    {uid:'cacao-1',summary:'Cacao',status:'needs_action'},
    {uid:'milk-1',summary:'Leche entera',description:'Para el desayuno',status:'needs_action'},
    {uid:'rice-1',summary:'Arroz',status:'completed'}
  ],
  'todo.local': [{uid:'other',summary:'Detergente',status:'needs_action'}],
  'todo.readonly': [{uid:'read',summary:'Lista compartida',status:'needs_action'}]
};
const listeners = new Map();
window.catalogProducts=JSON.parse(localStorage.getItem('catalog-fixture')??'[]');
window.catalogCategories=JSON.parse(localStorage.getItem('category-fixture')??'[]');
window.dismissedSuggestions=JSON.parse(localStorage.getItem('dismissed-fixture')??'[]');
const normalizeName=name=>name.normalize('NFKC').trim().replace(/\\s+/g,' ').toLowerCase();
const snapshot=()=>({products:structuredClone(window.catalogProducts),dismissed_suggestions:[...window.dismissedSuggestions],categories:window.catalogCategories.map(category=>({...category,product_count:window.catalogProducts.filter(product=>product.category===category.name).length}))});
const emitCatalog=()=>{
  localStorage.setItem('catalog-fixture',JSON.stringify(window.catalogProducts));
  localStorage.setItem('category-fixture',JSON.stringify(window.catalogCategories));
  localStorage.setItem('dismissed-fixture',JSON.stringify(window.dismissedSuggestions));
  for(const listener of listeners.keys())if(listener.catalog)listener.callback(snapshot());
};
window.calls=[];window.fail=false;window.failCatalog=false;
const panel=document.createElement('improved-shopping-list-panel');
const hass={
  states: {
    'todo.bring':{entity_id:'todo.bring',state:'2',attributes:{friendly_name:'Compra · Bring!',supported_features:5}},
    'todo.local':{entity_id:'todo.local',state:'1',attributes:{friendly_name:'Casa',supported_features:5}},
    'todo.readonly':{entity_id:'todo.readonly',state:'1',attributes:{friendly_name:'Solo lectura',supported_features:0}}
  },
  connection:{subscribeMessage:async(callback,msg)=>{
    if(msg.type==='improved_shopping_list/catalog/subscribe'){
      const listener={callback,catalog:true};listeners.set(listener,true);
      callback(snapshot());
      return ()=>listeners.delete(listener);
    }
    const listener={callback,entityId:msg.entity_id}; listeners.set(listener,true);
    callback({items:structuredClone(data[msg.entity_id]??[])});
    return ()=>listeners.delete(listener);
  }},
  callWS:async(msg)=>{
    if(msg.type==='improved_shopping_list/catalog/get')return snapshot();
    if(msg.type==='improved_shopping_list/catalog/suggestion'){
      if(window.failCatalog)throw new Error('No se ha podido guardar el cambio');
      if(msg.action==='dismiss'){
        window.dismissedSuggestions=[...new Set([...window.dismissedSuggestions,normalizeName(msg.name)])];emitCatalog();return {};
      }
      const existing=window.catalogProducts.find(product=>normalizeName(product.name)===normalizeName(msg.name));
      if(existing)return {product:existing};
      const product={name:msg.name,category:'',tags:[],brand:'',barcode:'',format:'',price:null,currency:'EUR',image_url:'',icon:'',notes:'',id:crypto.randomUUID(),revision:1};
      window.catalogProducts.push(product);emitCatalog();return {product};
    }
    if(msg.type==='improved_shopping_list/catalog/category/save'){
      const old=window.catalogCategories.find(category=>category.id===msg.category.id);
      const category={...msg.category,id:old?.id??crypto.randomUUID(),revision:(old?.revision??0)+1};
      if(old&&old.name!==category.name)window.catalogProducts=window.catalogProducts.map(product=>product.category===old.name?{...product,category:category.name,revision:product.revision+1}:product);
      window.catalogCategories=window.catalogCategories.filter(item=>item.id!==category.id);window.catalogCategories.push(category);
      emitCatalog();return {category};
    }
    if(msg.type==='improved_shopping_list/catalog/category/delete'){
      const category=window.catalogCategories.find(item=>item.id===msg.category_id);
      window.catalogProducts=window.catalogProducts.map(product=>product.category===category.name?{...product,category:'',revision:product.revision+1}:product);
      window.catalogCategories=window.catalogCategories.filter(item=>item.id!==category.id);emitCatalog();return {};
    }
    if(msg.type==='improved_shopping_list/catalog/save'){
      if(window.failCatalog)throw new Error('No se ha podido guardar el catálogo');
      const old=window.catalogProducts.find(product=>product.id===msg.product.id);
      const product={...msg.product,id:old?.id??crypto.randomUUID(),revision:(old?.revision??0)+1,price_updated_at:new Date().toISOString()};
      window.catalogProducts=window.catalogProducts.filter(item=>item.id!==product.id);window.catalogProducts.push(product);
      emitCatalog();
      return {product};
    }
    return {items:structuredClone(data[msg.entity_id]??[])};
  },
  callService:async(domain,service,args)=>{
    if(window.fail)throw new Error('Proveedor sin conexión');
    window.calls.push({domain,service,...args});
    if(service==='add_item')data[args.entity_id].push({uid:crypto.randomUUID(),summary:args.item,status:'needs_action'});
    if(service==='update_item')data[args.entity_id].find(item=>item.uid===args.item).status=args.status;
    window.emit(args.entity_id);
  }
};
window.emit=(entityId)=>{
  for(const listener of listeners.keys()) if(listener.entityId===entityId)listener.callback({items:structuredClone(data[entityId])});
};
window.listData=data;
window.rename=()=>{data['todo.bring'][0].summary='Cacao puro';window.emit('todo.bring');};
window.makeUnavailable=()=>{panel.hass={...hass,states:{...hass.states,'todo.bring':{...hass.states['todo.bring'],state:'unavailable'}}};};
window.listenerCount=()=>listeners.size;
panel.hass=hass;panel.panel={config:{default_entity:'todo.bring'}};panel.narrow=innerWidth<600;
document.body.append(panel);
window.testPanel=panel;
window.menuOpened=false;panel.addEventListener('hass-toggle-menu',()=>window.menuOpened=true);
</script></body></html>`;

async function main() {
  await fs.mkdir("test-results", { recursive: true });
  const server = http.createServer(async (req, res) => {
    const pathname = new URL(req.url, "http://localhost").pathname;
    if (pathname === "/") { res.setHeader("content-type", "text/html; charset=utf-8"); res.end(html); return; }
    if (!["/panel.js", "/todo-client.js", "/catalog-panel.js", "/catalog-client.js", "/category-panel.js", "/logo.png"].includes(pathname)) { res.writeHead(404).end(); return; }
    res.setHeader("content-type", pathname.endsWith(".png") ? "image/png" : "text/javascript; charset=utf-8");
    res.end(await fs.readFile(path.join(root, pathname.slice(1))));
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  let browser;
  try {
    browser = await chromium.launch({ headless: true, channel: process.env.PLAYWRIGHT_CHANNEL || undefined });
    const page = await browser.newPage({ viewport: { width: 1280, height: 960 } });
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    const url = `http://127.0.0.1:${server.address().port}`;
    await page.goto(url);
    await page.locator("#pending").getByText("Cacao", { exact: true }).waitFor();
    await page.locator(".brand-logo").evaluate(image => image.decode());
    assert.equal(await page.locator(".brand-logo").evaluate(image => image.naturalWidth > 0), true);
    const header = await page.locator("header").evaluate(node => {
      const title = node.querySelector(".brand").getBoundingClientRect();
      const version = node.querySelector(".version").getBoundingClientRect();
      const logo = node.querySelector(".brand-logo").getBoundingClientRect();
      return { background: getComputedStyle(node).backgroundColor, gap: version.left - title.right, logoFirst: logo.right <= title.left };
    });
    assert.equal(header.background, "rgba(0, 0, 0, 0)");
    assert.ok(header.gap >= 0 && header.gap < 20);
    assert.equal(header.logoFirst, true);
    assert.equal(await page.locator("#nav-catalog ha-icon").getAttribute("icon"), "mdi:view-grid");
    await page.screenshot({ path: "test-results/panel-desktop.png", fullPage: true });

    // Input is text, even if a provider supplies something resembling HTML.
    const dangerous = '<img src=x onerror="window.injected=true">';
    await page.getByLabel("Añadir producto", { exact: true }).fill(dangerous);
    await page.getByRole("button", { name: "Añadir", exact: true }).click();
    await page.locator("#pending").getByText(dangerous, { exact: true }).waitFor();
    assert.equal(await page.evaluate(() => window.injected), undefined);
    assert.equal(await page.getByLabel("Añadir producto", { exact: true }).inputValue(), "");

    await page.getByRole("checkbox", { name: "Marcar como comprado: Cacao", exact: true }).check();
    await page.getByText("Comprados (2)", { exact: true }).waitFor();
    assert.equal((await page.evaluate(() => window.calls)).at(-1).item, "cacao-1");
    await page.locator("#completed-summary").click();
    await page.getByRole("checkbox", { name: "Volver a poner por comprar: Cacao", exact: true }).uncheck();
    await page.getByRole("checkbox", { name: "Marcar como comprado: Cacao", exact: true }).waitFor();

    await page.evaluate(() => window.rename());
    await page.locator("#pending").getByText("Cacao puro", { exact: true }).waitFor();
    await page.getByLabel("Lista de la compra", { exact: true }).selectOption("todo.local");
    await page.locator("#pending").getByText("Detergente", { exact: true }).waitFor();
    assert.equal(await page.locator("#pending").getByText("Cacao puro", { exact: true }).count(), 0);
    assert.equal(await page.evaluate(() => window.listenerCount()), 2);

    await page.getByLabel("Lista de la compra", { exact: true }).selectOption("todo.readonly");
    await page.locator("#pending").getByText("Lista compartida", { exact: true }).waitFor();
    assert.equal(await page.getByRole("button", { name: "Añadir", exact: true }).isDisabled(), true);
    assert.equal(await page.getByRole("checkbox").isDisabled(), true);

    await page.getByLabel("Lista de la compra", { exact: true }).selectOption("todo.bring");
    await page.locator("#pending").getByText("Cacao puro", { exact: true }).waitFor();
    await page.evaluate(() => { window.fail = true; });
    await page.getByLabel("Añadir producto", { exact: true }).fill("Aceite");
    await page.getByRole("button", { name: "Añadir", exact: true }).click();
    await page.getByRole("alert").filter({ hasText: "Proveedor sin conexión" }).waitFor();
    assert.equal(await page.getByLabel("Añadir producto", { exact: true }).inputValue(), "Aceite");
    await page.evaluate(() => window.makeUnavailable());
    assert.equal(await page.getByRole("button", { name: "Añadir", exact: true }).isDisabled(), true);

    // Catalog form, persistence on reload, edit, filtering and native list add.
    await page.goto(url);
    await page.locator("#pending").getByText("Cacao", { exact: true }).waitFor();
    await page.getByRole("button", { name: "Catálogo", exact: true }).click();
    const catalog = page.locator("isl-catalog");
    const categories = catalog.locator("isl-categories");
    await catalog.getByRole("button", { name: "Categorías", exact: true }).click();
    await categories.getByRole("button", { name: "Nueva categoría", exact: true }).click();
    await categories.getByLabel("Nombre de la categoría", { exact: true }).fill("Lácteos");
    await categories.getByLabel("Icono MDI", { exact: true }).fill("mdi:shopping");
    await categories.getByLabel("Color", { exact: true }).evaluate(input => { input.value = "#9c27b0"; input.dispatchEvent(new Event("input", { bubbles: true })); });
    await categories.getByRole("button", { name: "Guardar categoría", exact: true }).click();
    await categories.getByRole("heading", { name: "Lácteos", exact: true }).waitFor();
    await catalog.getByRole("button", { name: "Productos", exact: true }).click();
    await catalog.getByRole("button", { name: "Nuevo producto", exact: true }).click();
    await catalog.getByLabel("Nombre del producto", { exact: true }).fill("Yogur natural");
    await catalog.getByLabel("Categoría", { exact: true }).last().selectOption("Lácteos");
    await catalog.getByLabel("Etiquetas", { exact: true }).fill("Desayuno, Fresco");
    await catalog.getByLabel("Marca", { exact: true }).fill("Marca de prueba");
    await catalog.getByLabel("Formato", { exact: true }).fill("4 × 125 g");
    await catalog.getByLabel("Código de barras", { exact: true }).fill("0012345678905");
    await catalog.getByLabel("Precio orientativo", { exact: true }).fill("2.59");
    await catalog.getByRole("button", { name: "Guardar producto", exact: true }).click();
    await catalog.getByRole("heading", { name: "Yogur natural", exact: true }).waitFor();
    assert.equal(await page.evaluate(() => window.catalogProducts[0].barcode), "0012345678905");
    const productCard = catalog.locator("#catalog-grid article").first();
    assert.equal(await productCard.locator(".placeholder ha-icon").getAttribute("icon"), "mdi:shopping");
    assert.equal(await productCard.getByText("Lácteos", { exact: true }).count(), 0);
    assert.equal((await productCard.textContent()).includes("2,59"), false);
    assert.equal(await productCard.locator(".category-badge").evaluate(node => getComputedStyle(node).color), "rgb(255, 255, 255)");
    assert.equal(await productCard.locator(".category-badge").evaluate(node => getComputedStyle(node).backgroundColor), "rgb(156, 39, 176)");
    assert.equal(await productCard.locator(".actions button").first().textContent(), "Añadir");
    assert.equal(await productCard.locator(".actions button").first().locator("ha-icon").getAttribute("icon"), "mdi:cart-plus");
    assert.equal(await productCard.locator(".actions button").last().locator("ha-icon").getAttribute("icon"), "mdi:note-edit");
    assert.ok(await productCard.evaluate(card => {
      const image = card.querySelector(".image").getBoundingClientRect();
      const title = card.querySelector(".title").getBoundingClientRect();
      const bounds = card.getBoundingClientRect();
      return Math.abs((image.left + image.right) / 2 - (bounds.left + bounds.right) / 2) < 2 && image.bottom <= title.top;
    }));
    await catalog.getByRole("button", { name: "Editar Yogur natural", exact: true }).click();
    await catalog.getByLabel("Nombre del producto", { exact: true }).fill("Yogur sin azúcar");
    await catalog.getByLabel("Icono del producto", { exact: true }).fill("mdi:view-grid");
    await catalog.getByRole("button", { name: "Guardar producto", exact: true }).click();
    await catalog.getByRole("heading", { name: "Yogur sin azúcar", exact: true }).waitFor();
    assert.equal(await page.evaluate(() => window.catalogProducts.length), 1);
    assert.equal(await productCard.locator(".placeholder ha-icon").getAttribute("icon"), "mdi:view-grid");
    await catalog.getByRole("button", { name: "Categorías", exact: true }).click();
    await categories.getByRole("button", { name: "Editar categoría Lácteos", exact: true }).click();
    await categories.getByLabel("Nombre de la categoría", { exact: true }).fill("Lácteos y frescos");
    await categories.getByRole("button", { name: "Guardar categoría", exact: true }).click();
    await categories.getByRole("heading", { name: "Lácteos y frescos", exact: true }).waitFor();
    await page.screenshot({ path: "test-results/categories-desktop.png", fullPage: true });
    await catalog.getByRole("button", { name: "Productos", exact: true }).click();
    assert.equal(await productCard.locator(".category-badge").getAttribute("title"), "Lácteos y frescos");
    await catalog.getByLabel("Buscar productos", { exact: true }).fill("inexistente");
    await catalog.getByText("No hay productos que coincidan con estos filtros.", { exact: true }).waitFor();
    await catalog.getByLabel("Buscar productos", { exact: true }).fill("");
    await catalog.locator("#category-filter").selectOption("Lácteos y frescos");
    await catalog.locator("#tag-filter").selectOption("Desayuno");
    await catalog.getByRole("button", { name: "Añadir Yogur sin azúcar a la lista", exact: true }).click();
    await catalog.getByRole("status").filter({ hasText: "Yogur sin azúcar añadido" }).waitFor();
    assert.equal((await page.evaluate(() => window.calls)).at(-1).entity_id, "todo.bring");
    assert.equal((await page.evaluate(() => window.calls)).at(-1).item, "Yogur sin azúcar");
    assert.equal(await productCard.getAttribute("data-in-list"), "true");
    assert.ok((await productCard.evaluate(node => getComputedStyle(node).backgroundImage)).includes("linear-gradient"));
    await page.screenshot({ path: "test-results/catalog-desktop.png", fullPage: true });
    await page.getByRole("button", { name: "Lista", exact: true }).click();
    await page.locator("#pending").getByText("Yogur sin azúcar", { exact: true }).waitFor();
    await page.getByRole("checkbox", { name: "Marcar como comprado: Yogur sin azúcar", exact: true }).check();
    await page.getByRole("button", { name: "Catálogo", exact: true }).click();
    assert.equal(await productCard.getAttribute("data-in-list"), "false");
    await page.getByRole("button", { name: "Lista", exact: true }).click();
    await page.locator("#completed-summary").click();
    await page.getByRole("checkbox", { name: "Volver a poner por comprar: Yogur sin azúcar", exact: true }).uncheck();
    await page.getByRole("button", { name: "Catálogo", exact: true }).click();
    assert.equal(await productCard.getAttribute("data-in-list"), "true");
    await page.getByRole("button", { name: "Lista", exact: true }).click();
    await page.getByLabel("Lista de la compra", { exact: true }).selectOption("todo.local");
    await page.locator("#pending").getByText("Detergente", { exact: true }).waitFor();
    await page.getByRole("button", { name: "Catálogo", exact: true }).click();
    assert.equal(await productCard.getAttribute("data-in-list"), "false");
    await catalog.locator("#category-filter").selectOption("");
    await catalog.getByRole("button", { name: "Categorías", exact: true }).click();
    await categories.getByRole("button", { name: "Nueva categoría", exact: true }).click();
    await categories.getByLabel("Nombre de la categoría", { exact: true }).fill("Temporal");
    await categories.getByRole("button", { name: "Guardar categoría", exact: true }).click();
    await categories.getByRole("heading", { name: "Temporal", exact: true }).waitFor();
    await catalog.getByRole("button", { name: "Productos", exact: true }).click();
    await catalog.getByRole("button", { name: "Editar Yogur sin azúcar", exact: true }).click();
    await catalog.getByLabel("Categoría", { exact: true }).last().selectOption("Temporal");
    await catalog.getByRole("button", { name: "Guardar producto", exact: true }).click();
    await catalog.getByRole("button", { name: "Categorías", exact: true }).click();
    await categories.getByRole("button", { name: "Eliminar categoría Temporal", exact: true }).click();
    await categories.getByRole("button", { name: "Eliminar categoría", exact: true }).click();
    await categories.getByRole("status").filter({ hasText: "Categoría eliminada" }).waitFor();
    assert.equal(await page.evaluate(() => window.catalogProducts.length), 1);
    assert.equal(await page.evaluate(() => window.catalogProducts[0].category), "");
    await catalog.getByRole("button", { name: "Productos", exact: true }).click();
    assert.equal(await productCard.locator(".category-badge").count(), 0);
    await catalog.getByRole("button", { name: "Editar Yogur sin azúcar", exact: true }).click();
    await catalog.getByLabel("Categoría", { exact: true }).last().selectOption("Lácteos y frescos");
    await catalog.getByLabel("URL de la imagen", { exact: true }).fill("/logo.png");
    await catalog.getByRole("button", { name: "Guardar producto", exact: true }).click();
    await productCard.locator("img").evaluate(image => image.decode());
    assert.equal(await productCard.locator(".placeholder").count(), 0);
    await page.goto(url);
    await page.getByRole("button", { name: "Catálogo", exact: true }).click();
    await catalog.getByRole("heading", { name: "Yogur sin azúcar", exact: true }).waitFor();
    await catalog.getByRole("button", { name: "Editar Yogur sin azúcar", exact: true }).click();
    await catalog.getByLabel("Nombre del producto", { exact: true }).fill("Conservar formulario");
    await page.evaluate(() => { window.failCatalog = true; });
    await catalog.getByRole("button", { name: "Guardar producto", exact: true }).click();
    await catalog.locator("#product-error").filter({ hasText: "No se ha podido guardar" }).waitFor();
    assert.equal(await catalog.getByLabel("Nombre del producto", { exact: true }).inputValue(), "Conservar formulario");
    await catalog.getByRole("button", { name: "Cancelar", exact: true }).click();

    // Actual narrow layout, sidebar access and horizontal overflow.
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(url);
    await page.locator("#pending").getByText("Cacao", { exact: true }).waitFor();
    await page.getByRole("button", { name: "Abrir menú de Home Assistant" }).click();
    assert.equal(await page.evaluate(() => window.menuOpened), true);
    assert.equal(await page.evaluate(() => {
      const root = window.testPanel.shadowRoot;
      return root.querySelector("main").scrollWidth > window.innerWidth;
    }), false);
    await page.screenshot({ path: "test-results/panel-mobile.png", fullPage: true });
    assert.equal(await page.locator(".version").isVisible(), true);
    await page.getByRole("button", { name: "Catálogo", exact: true }).click();
    await catalog.getByRole("heading", { name: "Yogur sin azúcar", exact: true }).waitFor();
    await page.screenshot({ path: "test-results/catalog-mobile.png", fullPage: true });
    assert.equal(await catalog.evaluate(node => node.shadowRoot.querySelector("#catalog-grid").scrollWidth > innerWidth), false);
    await catalog.getByRole("button", { name: "Categorías", exact: true }).click();
    await categories.getByRole("heading", { name: "Lácteos y frescos", exact: true }).waitFor();
    await page.screenshot({ path: "test-results/categories-mobile.png", fullPage: true });
    // Suggestions are derived from the current native list; dismissals live in shared catalog storage.
    const suggestionContext = await browser.newContext({ viewport: { width: 1280, height: 960 } });
    const suggestionPage = await suggestionContext.newPage();
    suggestionPage.on("pageerror", error => errors.push(error.message));
    await suggestionPage.goto(url);
    await suggestionPage.locator("#pending").getByText("Cacao", { exact: true }).waitFor();
    await suggestionPage.getByRole("button", { name: "Catálogo", exact: true }).click();
    const suggestionCatalog = suggestionPage.locator("isl-catalog");
    await suggestionCatalog.getByRole("button", { name: "Sugerencias", exact: true }).click();
    assert.equal(await suggestionCatalog.locator("#view-suggestions ha-icon").getAttribute("icon"), "mdi:creation");
    const suggestions = suggestionCatalog.locator("#suggestions-list");
    assert.deepEqual(await suggestions.locator("h2").allTextContents(), ["Arroz", "Cacao", "Leche entera"]);
    await suggestionPage.evaluate(() => {
      window.listData['todo.bring'].push({uid:'duplicate',summary:'  CACAO  ',status:'needs_action'});
      window.emit('todo.bring');
    });
    assert.equal(await suggestions.locator("article").count(), 3);
    await suggestionPage.evaluate(() => { window.failCatalog = true; });
    await suggestions.getByRole("button", { name: "Descartar: Leche entera", exact: true }).click();
    await suggestionCatalog.locator("#suggestions-error").filter({ hasText: "No se ha podido guardar" }).waitFor();
    assert.equal(await suggestions.locator("article").count(), 3);
    await suggestionPage.evaluate(() => { window.failCatalog = false; });
    await suggestions.getByRole("button", { name: "Descartar: Leche entera", exact: true }).click();
    await suggestionCatalog.getByRole("status").filter({ hasText: "Sugerencia descartada" }).waitFor();
    await suggestions.getByRole("button", { name: "Añadir al catálogo: Cacao", exact: true }).click();
    await suggestionCatalog.getByRole("status").filter({ hasText: "Cacao añadido al catálogo" }).waitFor();
    assert.deepEqual(await suggestions.locator("h2").allTextContents(), ["Arroz"]);
    assert.equal(await suggestionPage.evaluate(() => window.calls.length), 0);
    assert.equal(await suggestionPage.evaluate(() => window.catalogProducts.length), 1);
    await suggestionCatalog.getByRole("button", { name: "Productos", exact: true }).click();
    await suggestionCatalog.getByRole("heading", { name: "Cacao", exact: true }).waitFor();
    assert.equal(await suggestionCatalog.locator("#catalog-grid article").getAttribute("data-in-list"), "true");
    await suggestionPage.reload();
    await suggestionPage.getByRole("button", { name: "Catálogo", exact: true }).click();
    await suggestionCatalog.getByRole("button", { name: "Sugerencias", exact: true }).click();
    assert.deepEqual(await suggestions.locator("h2").allTextContents(), ["Arroz"]);
    await suggestions.getByRole("button", { name: "Añadir al catálogo: Arroz", exact: true }).click();
    await suggestionCatalog.locator("#suggestions-empty").waitFor();
    await suggestionPage.getByRole("button", { name: "Lista", exact: true }).click();
    await suggestionPage.getByLabel("Lista de la compra", { exact: true }).selectOption("todo.local");
    await suggestionPage.getByRole("button", { name: "Catálogo", exact: true }).click();
    await suggestions.getByRole("heading", { name: "Detergente", exact: true }).waitFor();
    await suggestionPage.evaluate(() => {
      window.listData['todo.local'].push({uid:'dismissed',summary:' LECHE   entera ',status:'needs_action'});
      window.emit('todo.local');
    });
    assert.deepEqual(await suggestions.locator("h2").allTextContents(), ["Detergente"]);
    await suggestionPage.screenshot({ path: "test-results/suggestions-desktop.png", fullPage: true });
    await suggestionPage.setViewportSize({ width: 390, height: 844 });
    await suggestionPage.screenshot({ path: "test-results/suggestions-mobile.png", fullPage: true });
    assert.equal(await suggestionCatalog.evaluate(node => node.shadowRoot.querySelector("#suggestions-list").scrollWidth > innerWidth), false);
    await suggestionContext.close();
    await page.evaluate(() => window.testPanel.remove());
    assert.equal(await page.evaluate(() => window.listenerCount()), 0);
    assert.deepEqual(errors, []);
    console.log("Browser checks passed: native list operations, UID, subscriptions, errors, permissions, HTML text, mobile layout and cleanup.");
  } finally {
    await browser?.close();
    await new Promise((resolve) => server.close(resolve));
  }
}
main().catch((error) => { console.error(error); process.exitCode = 1; });
