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
window.listSettings=JSON.parse(localStorage.getItem('settings-fixture')??'{"entities":["todo.bring","todo.local","todo.readonly"],"primary_entity":"todo.bring"}');
window.failSettings=false;
window.emitSettings=()=>{
  localStorage.setItem('settings-fixture',JSON.stringify(window.listSettings));
  for(const listener of listeners.keys())if(listener.settings)listener.callback(structuredClone(window.listSettings));
};
const panel=document.createElement('improved-shopping-list-panel');
const hass={
  user:{is_admin:true},
  states: {
    'todo.bring':{entity_id:'todo.bring',state:'2',attributes:{friendly_name:'Compra · Bring!',supported_features:5}},
    'todo.local':{entity_id:'todo.local',state:'1',attributes:{friendly_name:'Casa',supported_features:5}},
    'todo.readonly':{entity_id:'todo.readonly',state:'1',attributes:{friendly_name:'Solo lectura',supported_features:0}}
  },
  connection:{subscribeMessage:async(callback,msg)=>{
    if(msg.type==='improved_shopping_list/settings/subscribe'){
      const listener={callback,settings:true};listeners.set(listener,true);
      callback(structuredClone(window.listSettings));return ()=>listeners.delete(listener);
    }
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
    if(msg.type==='improved_shopping_list/settings/get')return structuredClone(window.listSettings);
    if(msg.type==='improved_shopping_list/settings/update'){
      if(window.failSettings)throw new Error('No se han podido guardar los ajustes');
      if(msg.action==='add'&&!window.listSettings.entities.includes(msg.entity_id))window.listSettings.entities.push(msg.entity_id);
      if(msg.action==='remove')window.listSettings.entities=window.listSettings.entities.filter(entity=>entity!==msg.entity_id);
      if(msg.action==='primary')window.listSettings.primary_entity=msg.entity_id;
      if(!window.listSettings.entities.includes(window.listSettings.primary_entity))window.listSettings.primary_entity=window.listSettings.entities[0]??'';
      window.emitSettings();return structuredClone(window.listSettings);
    }
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

async function selectList(page, entityId) {
  await page.getByRole("button", { name: "Seleccionar lista", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Seleccionar lista", exact: true });
  await dialog.locator(`[data-entity-id="${entityId}"]`).click();
  await dialog.waitFor({ state: "hidden" });
}

async function main() {
  await fs.mkdir("test-results", { recursive: true });
  const server = http.createServer(async (req, res) => {
    const pathname = new URL(req.url, "http://localhost").pathname;
    if (pathname === "/") { res.setHeader("content-type", "text/html; charset=utf-8"); res.end(html); return; }
    if (!["/panel.js", "/todo-client.js", "/catalog-panel.js", "/catalog-client.js", "/category-panel.js", "/list-settings-client.js", "/settings-panel.js", "/logo.png"].includes(pathname)) { res.writeHead(404).end(); return; }
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
    assert.equal(await page.locator("footer").count(), 0);
    assert.equal(await page.locator("#list-select").count(), 0);
    assert.equal(await page.locator("#add-button").textContent(), "");
    assert.equal(await page.locator("#add-button ha-icon").getAttribute("icon"), "mdi:plus-thick");
    assert.equal(await page.locator("#choose-list ha-icon").getAttribute("icon"), "mdi:format-list-checks");
    const assertCompactBar = async currentPage => {
      assert.ok(await currentPage.locator("#add-form").evaluate(form => {
        const controls = ["#product-input", "#add-button", "#choose-list"].map(selector => form.querySelector(selector).getBoundingClientRect());
        return controls.every(bounds => Math.abs(bounds.top - controls[0].top) < 2) &&
          controls[0].right <= controls[1].left && controls[1].right <= controls[2].left && controls[2].right <= innerWidth;
      }));
    };
    await assertCompactBar(page);
    await page.getByRole("button", { name: "Seleccionar lista", exact: true }).click();
    const listDialog = page.getByRole("dialog", { name: "Seleccionar lista", exact: true });
    assert.equal(await listDialog.getByRole("button", { name: "Compra · Bring!", exact: true }).getAttribute("aria-pressed"), "true");
    assert.equal(await listDialog.locator(".list-option").count(), 3);
    await page.screenshot({ path: "test-results/list-selector-desktop.png", fullPage: true });
    await listDialog.getByRole("button", { name: "Cerrar", exact: true }).click();
    await page.getByRole("button", { name: "Seleccionar lista", exact: true }).press("Enter");
    await listDialog.waitFor();
    await page.keyboard.press("Escape");
    await listDialog.waitFor({ state: "hidden" });
    assert.equal(await page.locator("#pending").evaluate(node => getComputedStyle(node).display), "grid");
    const listCards = page.locator("#pending > li");
    assert.equal(await listCards.first().locator(".placeholder ha-icon").getAttribute("icon"), "mdi:shopping");
    assert.ok(await listCards.first().evaluate(node => {
      const image = node.querySelector(".image").getBoundingClientRect();
      const title = node.querySelector(".summary").getBoundingClientRect();
      return image.bottom <= title.top && Math.abs((image.left + image.right) / 2 - (title.left + title.right) / 2) < 2;
    }));
    assert.ok(await listCards.evaluateAll(nodes => Math.abs(nodes[0].getBoundingClientRect().top - nodes[1].getBoundingClientRect().top) < 2));
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
    await selectList(page, "todo.local");
    await page.locator("#pending").getByText("Detergente", { exact: true }).waitFor();
    assert.equal(await page.locator("#pending").getByText("Cacao puro", { exact: true }).count(), 0);
    assert.equal(await page.evaluate(() => window.listenerCount()), 3);

    await selectList(page, "todo.readonly");
    await page.locator("#pending").getByText("Lista compartida", { exact: true }).waitFor();
    assert.equal(await page.getByRole("button", { name: "Añadir", exact: true }).isDisabled(), true);
    assert.equal(await page.getByRole("checkbox").isDisabled(), true);

    await selectList(page, "todo.bring");
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
    const yogurtListCard = page.locator("#pending > li").filter({ hasText: "Yogur sin azúcar" });
    assert.equal(await yogurtListCard.locator(".placeholder ha-icon").getAttribute("icon"), "mdi:view-grid");
    assert.equal(await yogurtListCard.locator(".category-badge").getAttribute("title"), "Lácteos y frescos");
    assert.equal(await yogurtListCard.locator(".category-badge").evaluate(node => getComputedStyle(node).color), "rgb(255, 255, 255)");
    assert.equal(await yogurtListCard.locator(".subtitle").textContent(), "Marca de prueba · 4 × 125 g");
    assert.equal((await yogurtListCard.textContent()).includes("2,59"), false);
    await page.screenshot({ path: "test-results/list-grid-desktop.png", fullPage: true });
    await page.getByRole("checkbox", { name: "Marcar como comprado: Yogur sin azúcar", exact: true }).check();
    await page.getByRole("button", { name: "Catálogo", exact: true }).click();
    assert.equal(await productCard.getAttribute("data-in-list"), "false");
    await page.getByRole("button", { name: "Lista", exact: true }).click();
    await page.locator("#completed-summary").click();
    await page.getByRole("checkbox", { name: "Volver a poner por comprar: Yogur sin azúcar", exact: true }).uncheck();
    await page.getByRole("button", { name: "Catálogo", exact: true }).click();
    assert.equal(await productCard.getAttribute("data-in-list"), "true");
    await page.getByRole("button", { name: "Lista", exact: true }).click();
    await selectList(page, "todo.local");
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
    await page.getByRole("button", { name: "Lista", exact: true }).click();
    await selectList(page, "todo.bring");
    await yogurtListCard.locator("img").evaluate(image => image.decode());
    assert.equal(await yogurtListCard.locator(".placeholder").count(), 0);
    assert.equal(await yogurtListCard.locator(".category-badge").getAttribute("title"), "Lácteos y frescos");
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
    await assertCompactBar(page);
    await page.getByRole("button", { name: "Seleccionar lista", exact: true }).click();
    await page.screenshot({ path: "test-results/list-selector-mobile.png", fullPage: true });
    await listDialog.getByRole("button", { name: "Cerrar", exact: true }).click();
    assert.equal(await page.locator(".version").isVisible(), true);
    assert.equal(await page.locator("#pending").evaluate(node => getComputedStyle(node).gridTemplateColumns.split(" ").length), 1);
    await page.locator("#completed-summary").click();
    assert.equal(await page.locator("#completed .item.completed").count(), 1);
    assert.equal(await page.locator("#completed").evaluate(node => getComputedStyle(node).display), "grid");
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
    await selectList(suggestionPage, "todo.local");
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
    // Predictive catalog search: canonical names, keyboard/touch, free text and provider failures.
    const predictiveContext = await browser.newContext({ viewport: { width: 1280, height: 960 } });
    const predictivePage = await predictiveContext.newPage();
    predictivePage.on("pageerror", error => errors.push(error.message));
    await predictivePage.goto(url);
    await predictivePage.evaluate(() => {
      const products = ["Café molido", "Cacao puro", "Leche sin lactosa"].map((name, index) => ({
        id: `predictive-${index}`, revision: 1, name, category: "", tags: index === 2 ? ["Desayuno"] : [],
        brand: index === 2 ? "Marca especial" : "", format: "250 g", barcode: `001234${index}`,
        image_url: index === 0 ? "/logo.png" : "", icon: "mdi:shopping", price: null, currency: "EUR", notes: "",
      }));
      localStorage.setItem("catalog-fixture", JSON.stringify(products));
    });
    await predictivePage.reload();
    const predictiveInput = predictivePage.getByRole("combobox", { name: "Añadir producto", exact: true });
    const predictions = predictivePage.getByRole("listbox", { name: "Productos del catálogo", exact: true });
    await predictiveInput.fill("CAFE");
    await predictions.getByRole("option", { name: "Café molido 250 g", exact: true }).waitFor();
    assert.equal(await predictiveInput.getAttribute("aria-expanded"), "true");
    await predictions.locator("img").evaluate(image => image.decode());
    await predictivePage.screenshot({ path: "test-results/predictive-desktop.png", fullPage: true });
    await predictiveInput.press("ArrowDown");
    assert.equal(await predictions.getByRole("option").getAttribute("aria-selected"), "true");
    assert.ok(await predictiveInput.getAttribute("aria-activedescendant"));
    await predictiveInput.press("Enter");
    await predictivePage.locator("#pending").getByText("Café molido", { exact: true }).waitFor();
    assert.equal((await predictivePage.evaluate(() => window.calls)).at(-1).item, "Café molido");
    assert.equal(await predictiveInput.inputValue(), "");
    await predictiveInput.fill("marca especial");
    await predictions.getByRole("option").filter({ hasText: "Leche sin lactosa" }).waitFor();
    await predictiveInput.press("Escape");
    assert.equal(await predictiveInput.getAttribute("aria-expanded"), "false");
    await predictiveInput.fill("0012342");
    await predictions.getByRole("option").filter({ hasText: "Leche sin lactosa" }).waitFor();
    await predictiveInput.fill("desayuno");
    assert.equal(await predictions.getByRole("option").count(), 1);
    await predictivePage.setViewportSize({ width: 390, height: 844 });
    await predictivePage.screenshot({ path: "test-results/predictive-mobile.png", fullPage: true });
    assert.ok(await predictions.evaluate(node => node.getBoundingClientRect().right <= innerWidth));
    await predictions.getByRole("option").click();
    await predictivePage.locator("#pending").getByText("Leche sin lactosa", { exact: true }).waitFor();
    assert.equal((await predictivePage.evaluate(() => window.calls)).at(-1).item, "Leche sin lactosa");
    await predictiveInput.fill("Producto nuevo");
    assert.equal(await predictiveInput.getAttribute("aria-expanded"), "false");
    await predictiveInput.press("Enter");
    await predictivePage.locator("#pending").getByText("Producto nuevo", { exact: true }).waitFor();
    await predictivePage.evaluate(() => { window.fail = true; });
    await predictiveInput.fill("cacao");
    await predictiveInput.press("ArrowUp");
    await predictiveInput.press("Enter");
    await predictivePage.getByRole("alert").filter({ hasText: "Proveedor sin conexión" }).waitFor();
    assert.equal(await predictiveInput.inputValue(), "Cacao puro");
    await predictivePage.evaluate(() => { window.fail = false; });
    await predictiveInput.press("Escape");
    await predictivePage.getByRole("button", { name: "Añadir", exact: true }).click();
    await predictivePage.locator("#pending").getByText("Cacao puro", { exact: true }).waitFor();
    assert.equal(await predictivePage.evaluate(() => window.calls.length), 4);
    await selectList(predictivePage, "todo.readonly");
    assert.equal(await predictiveInput.isDisabled(), true);
    assert.equal(await predictiveInput.getAttribute("aria-expanded"), "false");
    await predictiveContext.close();
    const settingsContext = await browser.newContext({ viewport: { width: 1280, height: 960 } });
    const settingsPage = await settingsContext.newPage();
    settingsPage.on("pageerror", error => errors.push(error.message));
    await settingsPage.goto(url);
    await settingsPage.locator("#pending").getByText("Cacao", { exact: true }).waitFor();
    assert.equal(await settingsPage.locator("#nav-settings ha-icon").getAttribute("icon"), "mdi:cog");
    const settingsView = settingsPage.locator("isl-settings");
    await settingsPage.getByRole("button", { name: "Ajustes", exact: true }).click();
    const configured = settingsView.locator("#configured-lists article");
    assert.equal(await configured.count(), 3);
    assert.equal(await configured.filter({ hasText: "todo.bring" }).locator(".badge").textContent(), "Principal");
    await settingsView.getByRole("button", { name: "Quitar: Casa", exact: true }).click();
    await settingsView.getByRole("status").filter({ hasText: "Ajustes guardados" }).waitFor();
    assert.equal(await configured.count(), 2);
    assert.equal(await settingsPage.evaluate(() => window.listData['todo.local'].length), 1);
    await settingsPage.getByRole("button", { name: "Lista", exact: true }).click();
    await settingsPage.getByRole("button", { name: "Seleccionar lista", exact: true }).click();
    const configuredDialog = settingsPage.getByRole("dialog", { name: "Seleccionar lista", exact: true });
    assert.equal(await configuredDialog.locator(".list-option").count(), 2);
    assert.equal(await configuredDialog.getByRole("button", { name: "Casa", exact: true }).count(), 0);
    await configuredDialog.getByRole("button", { name: "Cerrar", exact: true }).click();
    await settingsPage.getByRole("button", { name: "Ajustes", exact: true }).click();
    await settingsView.getByLabel("Entidad todo", { exact: true }).selectOption("todo.local");
    await settingsView.getByRole("button", { name: "Añadir lista", exact: true }).click();
    await configured.filter({ hasText: "todo.local" }).waitFor();
    await settingsView.getByRole("button", { name: "Hacer principal: Casa", exact: true }).click();
    await configured.filter({ hasText: "todo.local" }).locator(".badge").waitFor();
    await settingsPage.screenshot({ path: "test-results/settings-desktop.png", fullPage: true });
    await settingsPage.getByRole("button", { name: "Lista", exact: true }).click();
    await settingsPage.locator("#pending").getByText("Detergente", { exact: true }).waitFor();
    await settingsPage.reload();
    await settingsPage.locator("#pending").getByText("Detergente", { exact: true }).waitFor();
    await settingsPage.getByRole("button", { name: "Ajustes", exact: true }).click();
    await settingsPage.evaluate(() => { window.failSettings = true; });
    await settingsView.getByRole("button", { name: "Quitar: Casa", exact: true }).click();
    await settingsView.getByRole("alert").filter({ hasText: "No se han podido guardar" }).waitFor();
    assert.equal(await configured.count(), 3);
    await settingsPage.evaluate(() => { window.failSettings = false; });
    await settingsView.getByRole("button", { name: "Quitar: Casa", exact: true }).click();
    await configured.filter({ hasText: "todo.bring" }).locator(".badge").waitFor();
    await settingsView.getByRole("button", { name: "Quitar: Compra · Bring!", exact: true }).click();
    await settingsView.getByRole("button", { name: "Quitar: Solo lectura", exact: true }).click();
    await settingsView.getByText("No hay listas añadidas. Añade una entidad todo para empezar.", { exact: true }).waitFor();
    await settingsPage.reload();
    assert.equal(await settingsPage.locator("#product-input").isDisabled(), true);
    await settingsPage.getByRole("button", { name: "Ajustes", exact: true }).click();
    assert.equal(await configured.count(), 0);
    await settingsPage.evaluate(() => {
      const panel = window.testPanel;
      panel.hass = {...panel._hass, states:{...panel._hass.states, 'todo.custom_provider':{entity_id:'todo.custom_provider',state:'0',attributes:{friendly_name:'Otra integración',supported_features:5}}}};
      window.listData['todo.custom_provider']=[];
    });
    await settingsView.getByLabel("Entidad todo", { exact: true }).selectOption("todo.custom_provider");
    await settingsView.getByRole("button", { name: "Añadir lista", exact: true }).click();
    await configured.filter({ hasText: "todo.custom_provider" }).locator(".badge").waitFor();
    // A settings snapshot from another session updates the selected provider immediately.
    await settingsPage.evaluate(() => { window.listSettings={entities:['todo.bring','todo.custom_provider'],primary_entity:'todo.bring'};window.emitSettings(); });
    await configured.filter({ hasText: "todo.bring" }).locator(".badge").waitFor();
    await settingsPage.setViewportSize({ width: 390, height: 844 });
    await settingsPage.screenshot({ path: "test-results/settings-mobile.png", fullPage: true });
    assert.equal(await settingsPage.locator("main").evaluate(node => node.scrollWidth > innerWidth), false);
    await settingsPage.evaluate(() => { window.testPanel.hass={...window.testPanel._hass,user:{is_admin:false}}; });
    assert.equal(await settingsView.getByRole("button", { name: "Añadir lista", exact: true }).isDisabled(), true);
    assert.equal(await settingsView.getByRole("button", { name: "Quitar: Compra · Bring!", exact: true }).isDisabled(), true);
    await settingsContext.close();
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
