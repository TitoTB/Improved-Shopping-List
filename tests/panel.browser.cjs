/* Real-browser panel tests against a simulated Home Assistant WebSocket API. */
const assert = require("node:assert/strict");
const http = require("node:http");
const fs = require("node:fs/promises");
const path = require("node:path");
const { chromium } = require("playwright");

const root = path.resolve(__dirname, "../custom_components/improved_shopping_list/frontend");
const html = `<!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Panel test</title><style>html,body{margin:0;height:100%;font-family:system-ui}</style><body><script src="/scoped-custom-element-registry.js"></script><script type="module">
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
window.readerFixture=JSON.parse(localStorage.getItem('reader-fixture')??'{"readers":[],"pending":[]}');
window.failReaders=false;
window.emitReaders=()=>{
  localStorage.setItem('reader-fixture',JSON.stringify(window.readerFixture));
  for(const listener of listeners.keys())if(listener.readers)listener.callback(structuredClone(window.readerFixture));
};
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
    if(msg.type==='improved_shopping_list/readers/subscribe'){
      const listener={callback,readers:true};listeners.set(listener,true);callback(structuredClone(window.readerFixture));return()=>listeners.delete(listener);
    }
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
    if(msg.type==='improved_shopping_list/readers/get')return structuredClone(window.readerFixture);
    if(msg.type==='improved_shopping_list/readers/save'){
      if(window.failReaders)throw new Error('No se ha podido guardar el lector');
      const old=window.readerFixture.readers.find(reader=>reader.id===msg.reader.id);
      const reader={entity_id:'',attribute:'',device_id:'',list_entity:'',...msg.reader,id:old?.id??crypto.randomUUID(),revision:(old?.revision??0)+1};
      window.readerFixture.readers=window.readerFixture.readers.filter(item=>item.id!==reader.id);window.readerFixture.readers.push(reader);window.emitReaders();return reader;
    }
    if(msg.type==='improved_shopping_list/readers/delete'){window.readerFixture.readers=window.readerFixture.readers.filter(reader=>reader.id!==msg.reader_id);window.emitReaders();return null;}
    if(msg.type==='improved_shopping_list/readers/dismiss'){window.readerFixture.pending=window.readerFixture.pending.filter(item=>item.id!==msg.pending_id);window.emitReaders();return null;}
    if(msg.type==='improved_shopping_list/settings/get')return structuredClone(window.listSettings);
    if(msg.type==='improved_shopping_list/settings/personalization'){
      if(window.failSettings)throw new Error('No se ha podido guardar la personalización');
      window.listSettings.appearance=structuredClone(msg.appearance);window.emitSettings();return structuredClone(window.listSettings);
    }
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
      if(window.failCategory)throw new Error('No se ha podido guardar la categoría');
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
    if (pathname === "/scoped-custom-element-registry.js") {
      res.setHeader("content-type", "text/javascript; charset=utf-8");
      res.end(await fs.readFile(require.resolve("@webcomponents/scoped-custom-element-registry")));
      return;
    }
    if (pathname === "/") { res.setHeader("content-type", "text/html; charset=utf-8"); res.end(html); return; }
    if (!["/panel.js", "/todo-client.js", "/catalog-panel.js", "/catalog-client.js", "/category-panel.js", "/list-settings-client.js", "/settings-panel.js", "/readers-client.js", "/readers-panel.js", "/logo.png"].includes(pathname)) { res.writeHead(404).end(); return; }
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

    assert.equal(await page.locator("#items-card .purchase-control,#items-card input[type=checkbox]").count(), 0);
    assert.equal(await listCards.first().locator("button.item").evaluate(node => getComputedStyle(node).backgroundImage), "linear-gradient(rgb(238, 82, 79), rgb(181, 42, 39))");
    await page.getByRole("button", { name: "Marcar como comprado: Cacao", exact: true }).click();
    await page.getByText("Comprados (2)", { exact: true }).waitFor();
    assert.equal((await page.evaluate(() => window.calls)).at(-1).item, "cacao-1");
    await page.locator("#completed-summary").click();
    const completedCard = page.getByRole("button", { name: "Volver a poner por comprar: Cacao", exact: true });
    assert.equal(await completedCard.evaluate(node => getComputedStyle(node).backgroundImage), "linear-gradient(rgb(79, 171, 162), rgb(38, 133, 124))");
    assert.equal(await completedCard.getAttribute("aria-pressed"), "true");
    assert.equal(await completedCard.getByText("Por comprar", { exact:true }).count(), 0);
    await page.getByRole("button", { name: "Volver a poner por comprar: Cacao", exact: true }).press("Enter");
    await page.getByRole("button", { name: "Marcar como comprado: Cacao", exact: true }).waitFor();
    assert.equal((await page.evaluate(() => window.calls)).at(-1).service, "update_item");
    assert.equal((await page.evaluate(() => window.calls)).at(-1).status, "needs_action");

    await page.evaluate(() => window.rename());
    await page.locator("#pending").getByText("Cacao puro", { exact: true }).waitFor();
    await selectList(page, "todo.local");
    await page.locator("#pending").getByText("Detergente", { exact: true }).waitFor();
    assert.equal(await page.locator("#pending").getByText("Cacao puro", { exact: true }).count(), 0);
    assert.equal(await page.evaluate(() => window.listenerCount()), 4);

    await selectList(page, "todo.readonly");
    await page.locator("#pending").getByText("Lista compartida", { exact: true }).waitFor();
    assert.equal(await page.getByRole("button", { name: "Añadir", exact: true }).isDisabled(), true);
    assert.equal(await page.getByRole("button", { name: "Marcar como comprado: Lista compartida", exact: true }).isDisabled(), true);

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
    const categories = catalog.locator("#catalog-categories");
    assert.equal(await catalog.locator(".heading #new-product").count(), 0);
    assert.equal(await catalog.locator(".category-controls #new-product ha-icon").getAttribute("icon"), "mdi:plus-thick");
    assert.equal(await catalog.locator("#new-product").textContent(), "");
    await catalog.getByRole("button", { name: "Nuevo producto", exact: true }).click();
    await catalog.getByLabel("Nombre del producto", { exact: true }).fill("Yogur natural");
    const categoryEditor = catalog.locator("#product-category-editor");
    await catalog.getByRole("button", { name:"Nueva categoría", exact:true }).click();
    await categoryEditor.getByLabel("Nombre de la categoría", { exact:true }).fill("Cancelar categoría");
    await categoryEditor.getByRole("button", { name:"Cancelar", exact:true }).click();
    assert.equal(await catalog.getByLabel("Nombre del producto", { exact:true }).inputValue(), "Yogur natural");
    assert.equal(await catalog.locator("#product-category").inputValue(), "");
    assert.equal(await page.evaluate(() => window.catalogCategories.length), 0);
    await catalog.getByRole("button", { name:"Nueva categoría", exact:true }).click();
    await categoryEditor.getByLabel("Nombre de la categoría", { exact:true }).fill("Lácteos");
    await categoryEditor.getByLabel("Icono MDI", { exact:true }).fill("mdi:shopping");
    await categoryEditor.getByLabel("Color", { exact:true }).evaluate(input => { input.value="#9c27b0";input.dispatchEvent(new Event("input", {bubbles:true})); });
    await page.evaluate(() => { window.failCategory=true; });
    await categoryEditor.getByRole("button", { name:"Guardar categoría", exact:true }).click();
    await categoryEditor.getByRole("alert").filter({hasText:"No se ha podido guardar la categoría"}).waitFor();
    assert.equal(await categoryEditor.getByLabel("Nombre de la categoría", { exact:true }).inputValue(), "Lácteos");
    await page.evaluate(() => { window.failCategory=false; });
    await categoryEditor.getByRole("button", { name:"Guardar categoría", exact:true }).click();
    await categoryEditor.getByRole("dialog", { name:"Nueva categoría", exact:true }).waitFor({state:"hidden"});
    assert.equal(await catalog.locator("#product-category").inputValue(), "Lácteos");
    assert.equal(await catalog.getByLabel("Nombre del producto", { exact:true }).inputValue(), "Yogur natural");
    assert.equal(await page.evaluate(() => window.catalogProducts.length), 0);
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
    assert.equal(await productCard.locator(".actions button").first().textContent(), "");
    assert.equal(await productCard.locator(".actions button").last().textContent(), "");
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
    await productCard.getByRole("button", { name: "Filtrar por categoría: Lácteos y frescos", exact: true }).click();
    assert.equal(await catalog.locator("#category-filter").inputValue(), "Lácteos y frescos");
    await catalog.locator("#category-filter").selectOption("");
    await productCard.getByRole("button", { name: "Filtrar por categoría: Lácteos y frescos", exact: true }).focus();
    await page.keyboard.press("Enter");
    assert.equal(await catalog.locator("#category-filter").inputValue(), "Lácteos y frescos");
    assert.equal(await catalog.locator("#tag-filter").count(), 0);
    assert.equal(await catalog.locator("#view-products ha-icon").getAttribute("icon"), "mdi:package-variant");
    assert.equal(await catalog.locator("#view-categories ha-icon").getAttribute("icon"), "mdi:shape");
    await catalog.getByRole("button", { name: "Añadir Yogur sin azúcar a la lista", exact: true }).click();
    await catalog.getByRole("status").filter({ hasText: "Yogur sin azúcar añadido" }).waitFor();
    assert.equal((await page.evaluate(() => window.calls)).at(-1).entity_id, "todo.bring");
    assert.equal((await page.evaluate(() => window.calls)).at(-1).item, "Yogur sin azúcar");
    assert.equal(await productCard.getAttribute("data-in-list"), "true");
    assert.equal(await productCard.evaluate(node => getComputedStyle(node).backgroundImage), "linear-gradient(rgb(238, 82, 79), rgb(181, 42, 39))");
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
    await page.getByRole("button", { name: "Marcar como comprado: Yogur sin azúcar", exact: true }).click();
    await page.getByRole("button", { name: "Catálogo", exact: true }).click();
    assert.equal(await productCard.getAttribute("data-in-list"), "false");
    await page.getByRole("button", { name: "Lista", exact: true }).click();
    await page.locator("#completed-summary").click();
    await page.getByRole("button", { name: "Volver a poner por comprar: Yogur sin azúcar", exact: true }).click();
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
    await suggestionCatalog.getByRole("button", { name:"Categorías", exact:true }).click();
    const suggestionCategories = suggestionCatalog.locator("#catalog-categories");
    await suggestionCategories.getByRole("button", { name:"Nueva categoría", exact:true }).click();
    await suggestionCategories.getByLabel("Nombre de la categoría", { exact:true }).fill("Despensa");
    await suggestionCategories.getByRole("button", { name:"Guardar categoría", exact:true }).click();
    await suggestionCategories.getByRole("heading", { name:"Despensa", exact:true }).waitFor();
    await suggestionCatalog.getByRole("button", { name: "Sugerencias", exact: true }).click();
    assert.equal(await suggestionCatalog.locator("#view-suggestions ha-icon").getAttribute("icon"), "mdi:creation");
    const suggestions = suggestionCatalog.locator("#suggestions-list");
    assert.equal(await suggestionCatalog.locator("#list-suggestions-group").evaluate(node => node.open), false);
    assert.equal(await suggestionCatalog.locator("#scan-suggestions-group").evaluate(node => node.open), false);
    assert.equal(await suggestionCatalog.locator("#list-suggestions-count").textContent(), "3");
    assert.equal(await suggestionCatalog.locator("#scan-suggestions-count").textContent(), "0");
    assert.equal(await suggestions.getByRole("button", {name:"Añadir al catálogo: Cacao",exact:true}).isVisible(), false);
    await suggestionCatalog.locator("#list-suggestions-summary").click();
    assert.equal(await suggestionCatalog.locator("#list-suggestions article > ha-icon").count(), 0);
    assert.deepEqual(await suggestionCatalog.locator("#list-suggestions article").first().locator(".actions ha-icon").evaluateAll(icons => icons.map(icon => icon.getAttribute("icon"))), ["mdi:plus-thick","mdi:delete"]);
    assert.deepEqual(await suggestionCatalog.locator("#list-suggestions article").first().locator(".actions button").allTextContents(), ["", ""]);
    await suggestionCatalog.locator("#scan-suggestions-summary").focus();
    await suggestionPage.keyboard.press("Enter");
    await suggestionCatalog.locator("#scan-suggestions-empty").waitFor();
    await suggestionPage.keyboard.press("Enter");
    assert.deepEqual(await suggestions.locator("h2").allTextContents(), ["Arroz", "Cacao", "Leche entera"]);
    await suggestionPage.evaluate(() => {
      window.listData['todo.bring'].push({uid:'duplicate',summary:'  CACAO  ',status:'needs_action'});
      window.emit('todo.bring');
    });
    assert.equal(await suggestions.locator("article").count(), 3);
    assert.equal(await suggestionCatalog.locator("#list-suggestions-group").evaluate(node => node.open), true);
    await suggestionPage.evaluate(() => { window.failCatalog = true; });
    await suggestions.getByRole("button", { name: "Descartar: Leche entera", exact: true }).click();
    await suggestionCatalog.locator("#suggestions-error").filter({ hasText: "No se ha podido guardar" }).waitFor();
    assert.equal(await suggestions.locator("article").count(), 3);
    await suggestionPage.evaluate(() => { window.failCatalog = false; });
    await suggestions.getByRole("button", { name: "Descartar: Leche entera", exact: true }).click();
    await suggestionCatalog.getByRole("status").filter({ hasText: "Sugerencia descartada" }).waitFor();
    await suggestions.getByRole("button", { name: "Añadir al catálogo: Cacao", exact: true }).click();
    const suggestionDialog = suggestionCatalog.getByRole("dialog", { name:"Nuevo producto", exact:true });
    await suggestionDialog.waitFor();
    assert.equal(await suggestionDialog.getByLabel("Nombre del producto", { exact:true }).inputValue(), "Cacao");
    assert.equal(await suggestionPage.evaluate(() => window.catalogProducts.length), 0);
    await suggestionDialog.getByRole("button", { name:"Cancelar", exact:true }).click();
    assert.deepEqual(await suggestions.locator("h2").allTextContents(), ["Arroz", "Cacao"]);
    await suggestions.getByRole("button", { name:"Añadir al catálogo: Cacao", exact:true }).click();
    await suggestionDialog.getByLabel("Categoría", { exact:true }).selectOption("Despensa");
    await suggestionDialog.getByLabel("Marca", { exact:true }).fill("Marca de cacao");
    await suggestionDialog.getByLabel("Etiquetas", { exact:true }).fill("Desayuno");
    await suggestionPage.evaluate(() => { window.failCatalog=true; });
    await suggestionDialog.getByRole("button", { name:"Guardar producto", exact:true }).click();
    await suggestionDialog.getByRole("alert").filter({ hasText:"No se ha podido guardar" }).waitFor();
    assert.equal(await suggestionDialog.getByLabel("Categoría", { exact:true }).inputValue(), "Despensa");
    assert.equal(await suggestionPage.evaluate(() => window.catalogProducts.length), 0);
    await suggestionPage.evaluate(() => { window.failCatalog=false; });
    await suggestionDialog.getByRole("button", { name:"Guardar producto", exact:true }).click();
    await suggestionCatalog.getByRole("status").filter({ hasText:"Producto guardado en el catálogo" }).waitFor();
    assert.equal(await suggestionPage.evaluate(() => window.catalogProducts[0].category), "Despensa");
    assert.equal(await suggestionPage.evaluate(() => window.catalogProducts[0].brand), "Marca de cacao");
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
    assert.equal(await suggestionCatalog.locator("#list-suggestions-group").evaluate(node => node.open), false);
    await suggestionCatalog.locator("#list-suggestions-summary").click();
    await suggestions.getByRole("button", { name: "Añadir al catálogo: Arroz", exact: true }).click();
    assert.equal(await suggestionDialog.getByLabel("Nombre del producto", { exact:true }).inputValue(), "Arroz");
    assert.equal(await suggestionDialog.getByLabel("Marca", { exact:true }).inputValue(), "");
    await suggestionDialog.getByRole("button", { name:"Guardar producto", exact:true }).click();
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
    await settingsView.getByRole("button", { name: "Personalización", exact: true }).click();
    assert.equal(await settingsView.getByLabel("Color inicial del degradado", { exact: true }).inputValue(), "#ee524f");
    assert.equal(await settingsView.getByLabel("Color final del degradado", { exact: true }).inputValue(), "#b52a27");
    assert.equal(await settingsView.getByLabel("Color inicial de Comprados", { exact:true }).inputValue(), "#4faba2");
    assert.equal(await settingsView.getByLabel("Color final de Comprados", { exact:true }).inputValue(), "#26857c");
    await settingsView.getByLabel("Color inicial del degradado", { exact: true }).evaluate(input => { input.value="#ffe082";input.dispatchEvent(new Event("input",{bubbles:true})); });
    await settingsView.getByLabel("Color final del degradado", { exact: true }).evaluate(input => { input.value="#ffb300";input.dispatchEvent(new Event("input",{bubbles:true})); });
    await settingsView.getByLabel("Color inicial de Comprados", { exact:true }).evaluate(input => { input.value="#80cbc4";input.dispatchEvent(new Event("input",{bubbles:true})); });
    await settingsView.getByLabel("Color final de Comprados", { exact:true }).evaluate(input => { input.value="#26a69a";input.dispatchEvent(new Event("input",{bubbles:true})); });
    await settingsView.getByLabel("Productos por fila (ordenador)", { exact: true }).selectOption("4");
    await settingsView.getByLabel("Productos por fila (móvil)", { exact: true }).selectOption("2");
    assert.equal(await settingsView.locator("#appearance-preview").evaluate(node => getComputedStyle(node).color), "rgb(0, 0, 0)");
    assert.equal(await settingsView.locator("#completed-appearance-preview").evaluate(node => getComputedStyle(node).backgroundImage), "linear-gradient(rgb(128, 203, 196), rgb(38, 166, 154))");
    await settingsPage.evaluate(() => { window.failSettings=true; });
    await settingsView.getByRole("button", { name: "Guardar personalización", exact: true }).click();
    await settingsView.getByRole("alert").filter({ hasText:"No se ha podido guardar la personalización" }).waitFor();
    assert.equal(await settingsView.getByLabel("Productos por fila (ordenador)", { exact: true }).inputValue(), "4");
    assert.equal(await settingsView.getByLabel("Color inicial del degradado", { exact: true }).inputValue(), "#ffe082");
    await settingsPage.evaluate(() => { window.failSettings=false; });
    await settingsView.getByRole("button", { name: "Guardar personalización", exact: true }).click();
    await settingsView.getByRole("status").filter({ hasText: "Personalización guardada" }).waitFor();
    await settingsPage.screenshot({ path: "test-results/personalization-mobile.png", fullPage: true });
    await settingsPage.getByRole("button", { name: "Lista", exact: true }).click();
    assert.equal(await settingsPage.locator("#pending").evaluate(node => getComputedStyle(node).gridTemplateColumns.split(" ").length), 2);
    const customizedCard = settingsPage.locator("#pending .item").first();
    assert.equal(await customizedCard.evaluate(node => getComputedStyle(node).backgroundImage), "linear-gradient(rgb(255, 224, 130), rgb(255, 179, 0))");
    assert.equal(await customizedCard.evaluate(node => getComputedStyle(node).color), "rgb(0, 0, 0)");
    assert.equal(await settingsPage.locator("main").evaluate(node => node.scrollWidth > innerWidth), false);
    await settingsPage.screenshot({ path: "test-results/personalized-list-mobile.png", fullPage: true });
    await settingsPage.locator("#completed-summary").click();
    const customizedCompleted = settingsPage.getByRole("button", { name:"Volver a poner por comprar: Arroz", exact:true });
    assert.equal(await customizedCompleted.evaluate(node => getComputedStyle(node).backgroundImage), "linear-gradient(rgb(128, 203, 196), rgb(38, 166, 154))");
    assert.equal(await customizedCompleted.getByText("Por comprar", { exact:true }).count(), 0);
    await settingsPage.screenshot({ path:"test-results/completed-personalized-mobile.png",fullPage:true });
    await customizedCompleted.press("Space");
    await settingsPage.locator("#pending").getByText("Arroz", { exact:true }).waitFor();
    assert.equal((await settingsPage.evaluate(() => window.calls)).at(-1).item, "rice-1");
    assert.equal((await settingsPage.evaluate(() => window.calls)).at(-1).service, "update_item");
    await settingsPage.setViewportSize({ width:320,height:844 });
    await settingsPage.evaluate(async () => {
      window.listSettings.appearance.mobile_columns=4;window.emitSettings();
      await window.testPanel._hass.callWS({type:'improved_shopping_list/catalog/save',product:{name:'Cacao',category:'',tags:['a'.repeat(40)],brand:'Marca larga',format:'250 g',barcode:'',image_url:'/logo.png',icon:'',notes:'',price:null,currency:'EUR'}});
    });
    assert.equal(await settingsPage.locator("#pending").evaluate(node => getComputedStyle(node).gridTemplateColumns.split(" ").length), 4);
    assert.equal(await settingsPage.locator("#items-card").evaluate(node => node.scrollWidth > innerWidth), false);
    await settingsPage.setViewportSize({ width:1280,height:960 });
    assert.equal(await settingsPage.locator("#pending").evaluate(node => getComputedStyle(node).gridTemplateColumns.split(" ").length), 4);
    const listGradient = await settingsPage.locator("#pending .item").first().evaluate(node => getComputedStyle(node).backgroundImage);
    await settingsPage.getByRole("button", { name:"Catálogo", exact:true }).click();
    assert.equal(await settingsPage.locator("isl-catalog #catalog-grid .product.in-list").first().evaluate(node => getComputedStyle(node).backgroundImage), listGradient);
    await settingsPage.getByRole("button", { name:"Lista", exact:true }).click();
    await settingsPage.reload();
    await settingsPage.locator("#pending").getByText("Cacao", { exact:true }).waitFor();
    assert.equal(await settingsPage.locator("#pending").evaluate(node => getComputedStyle(node).gridTemplateColumns.split(" ").length), 4);
    await settingsPage.getByRole("button", { name:"Ajustes", exact:true }).click();
    await settingsView.getByRole("button", { name:"Personalización", exact:true }).click();
    assert.equal(await settingsView.getByLabel("Color inicial del degradado", { exact:true }).inputValue(), "#ffe082");
    assert.equal(await settingsView.getByLabel("Color inicial de Comprados", { exact:true }).inputValue(), "#80cbc4");
    assert.equal(await settingsView.getByLabel("Color final de Comprados", { exact:true }).inputValue(), "#26a69a");
    await settingsView.getByRole("button", { name:"Restablecer valores", exact:true }).click();
    assert.equal(await settingsView.getByLabel("Productos por fila (ordenador)", { exact:true }).inputValue(), "3");
    assert.equal(await settingsView.getByLabel("Color inicial de Comprados", { exact:true }).inputValue(), "#4faba2");
    assert.equal(await settingsView.getByLabel("Color final de Comprados", { exact:true }).inputValue(), "#26857c");
    await settingsView.getByRole("button", { name:"Guardar personalización", exact:true }).click();
    await settingsView.getByRole("status").filter({ hasText:"Personalización guardada" }).waitFor();
    await settingsPage.evaluate(() => { window.testPanel.hass={...window.testPanel._hass,user:{is_admin:false}}; });
    assert.equal(await settingsView.getByRole("button", { name:"Guardar personalización", exact:true }).isDisabled(), true);
    await settingsView.getByRole("button", { name:"Listas", exact:true }).click();
    assert.equal(await settingsView.getByRole("button", { name: "Añadir lista", exact: true }).isDisabled(), true);
    assert.equal(await settingsView.getByRole("button", { name: "Quitar: Compra · Bring!", exact: true }).isDisabled(), true);
    await settingsPage.getByRole("button", { name:"Lista", exact:true }).click();
    await settingsPage.evaluate(() => {
      window.listData['todo.bring'].push({uid:'square-long',summary:'Producto con un nombre muy largo '.repeat(6),description:'Una descripción extensa '.repeat(20),status:'needs_action'});
      window.listData['todo.bring'].push({uid:'square-completed',summary:'Producto comprado de nombre largo',status:'completed'});
      window.emit('todo.bring');
    });
    await settingsPage.locator("#completed-summary").click();
    for (const width of [1280,390,320]) {
      await settingsPage.setViewportSize({width,height:960});
      const sizes=[];
      for (let columns=1;columns<=(width>650?6:4);columns++) {
        await settingsPage.evaluate(({width,columns}) => {
          window.listSettings.appearance[width>650?'columns':'mobile_columns']=columns;window.emitSettings();
        },{width,columns});
        const metrics=await settingsPage.locator("#items-card .item").evaluateAll(cards => cards.map(card => {
          const bounds=card.getBoundingClientRect(),media=card.querySelector('.product-media').getBoundingClientRect(),name=card.querySelector('.summary').getBoundingClientRect();
          return {width:bounds.width,height:bounds.height,font:parseFloat(getComputedStyle(card.querySelector('.summary')).fontSize),mediaWidth:media.width,
            fits:media.top>=bounds.top&&media.bottom<=name.top+1&&name.bottom<=bounds.bottom&&name.left>=bounds.left&&name.right<=bounds.right};
        }));
        for (const card of metrics) {
          assert.ok(Math.abs(card.width-card.height)<1,`Square card at ${width}px / ${columns} columns: ${JSON.stringify(card)}`);
          assert.ok(card.fits,`Content fits at ${width}px / ${columns} columns: ${JSON.stringify(card)}`);
        }
        sizes.push(metrics[0]);
      }
      assert.ok(sizes[0].font>sizes.at(-1).font);
      assert.ok(sizes[0].mediaWidth>sizes.at(-1).mediaWidth);
      await settingsPage.screenshot({path:`test-results/list-square-${width}.png`,fullPage:true});
    }
    await settingsContext.close();
    // Reader configuration and unknown-code association use the same product form.
    const readerContext=await browser.newContext({viewport:{width:1280,height:960}});
    const readerPage=await readerContext.newPage();readerPage.on("pageerror",error=>errors.push(error.message));
    await readerPage.goto(url);
    await readerPage.evaluate(()=>{const panel=window.testPanel;panel.hass={...panel._hass,states:{...panel._hass.states,'sensor.lector_cb_codigo_leido':{entity_id:'sensor.lector_cb_codigo_leido',state:'',attributes:{friendly_name:'Código leído'}}}};});
    await readerPage.getByRole("button",{name:"Lectores",exact:true}).click();
    assert.equal(await readerPage.locator("#nav-readers ha-icon").getAttribute("icon"),"mdi:barcode-scan");
    const readersView=readerPage.locator("isl-readers");
    await readersView.getByRole("button",{name:"Añadir lector",exact:true}).click();
    const readerDialog=readersView.getByRole("dialog",{name:"Añadir lector",exact:true});
    await readerDialog.getByLabel("Nombre del lector",{exact:true}).fill("Cocina");
    await readerDialog.getByLabel("Entidad del lector",{exact:true}).fill("sensor.lector_cb_codigo_leido");
    await readerDialog.getByLabel("Lista de destino",{exact:true}).selectOption("todo.local");
    assert.equal(await readerDialog.getByLabel("Antirrepetición (segundos)",{exact:true}).inputValue(),"60");
    await readerPage.evaluate(()=>{window.failReaders=true;});
    await readerDialog.getByRole("button",{name:"Guardar lector",exact:true}).click();
    await readerDialog.getByRole("alert").filter({hasText:"No se ha podido guardar el lector"}).waitFor();
    assert.equal(await readerDialog.getByLabel("Nombre del lector",{exact:true}).inputValue(),"Cocina");
    await readerPage.evaluate(()=>{window.failReaders=false;});
    await readerDialog.getByRole("button",{name:"Guardar lector",exact:true}).click();
    await readersView.getByRole("heading",{name:"Cocina",exact:true}).waitFor();
    await readersView.getByRole("button",{name:"Añadir lector",exact:true}).click();
    await readerDialog.getByLabel("Nombre del lector",{exact:true}).fill("NFC despensa");
    await readerDialog.getByLabel("Tipo de lector",{exact:true}).selectOption("nfc");
    await readerDialog.getByLabel("Fuente de lectura",{exact:true}).selectOption("tag");
    await readerDialog.getByLabel("Device ID del lector NFC",{exact:true}).fill("nfc-device");
    await readerDialog.getByRole("button",{name:"Guardar lector",exact:true}).click();
    await readersView.getByRole("heading",{name:"NFC despensa",exact:true}).waitFor();
    await readerPage.evaluate(()=>{const reader=window.readerFixture.readers[0];window.readerFixture.pending=[{id:'scan-1',kind:'barcode',code:'0012345678905',reader_id:reader.id,reader_name:reader.name,time:new Date().toISOString()}];window.emitReaders();});
    await readerPage.screenshot({path:"test-results/readers-desktop.png",fullPage:true});
    await readersView.getByRole("button",{name:"Ver códigos desconocidos en Sugerencias",exact:true}).click();
    const readerCatalog=readerPage.locator("isl-catalog");
    assert.equal(await readerCatalog.locator("#list-suggestions-group").evaluate(node => node.open),false);
    assert.equal(await readerCatalog.locator("#scan-suggestions-group").evaluate(node => node.open),false);
    assert.equal(await readerCatalog.locator("#scan-suggestions [data-pending-id]").count(),1);
    assert.equal(await readerCatalog.locator("#list-suggestions [data-pending-id]").count(),0);
    assert.equal(await readerCatalog.locator("#scan-suggestions-count").textContent(),"1");
    await readerCatalog.locator("#scan-suggestions-summary").click();
    const scanCard = readerCatalog.locator('#scan-suggestions [data-pending-id="scan-1"]');
    assert.deepEqual(await scanCard.locator(".actions ha-icon").evaluateAll(icons => icons.map(icon => icon.getAttribute("icon"))), ["mdi:plus-thick","mdi:view-grid","mdi:delete"]);
    assert.deepEqual(await scanCard.locator(".actions button").allTextContents(), ["", "", ""]);
    assert.equal(await scanCard.getByRole("button",{name:"Asignar código 0012345678905 a un producto del catálogo",exact:true}).isDisabled(),true);
    await readerCatalog.getByRole("button",{name:"Crear producto con el código 0012345678905",exact:true}).click();
    const codeDialog=readerCatalog.getByRole("dialog",{name:"Nuevo producto",exact:true});
    assert.equal(await codeDialog.getByLabel("Código de barras",{exact:true}).inputValue(),"0012345678905");
    assert.equal(await codeDialog.getByLabel("Nombre del producto",{exact:true}).inputValue(),"");
    await codeDialog.getByLabel("Nombre del producto",{exact:true}).fill("Cacao lector");
    await codeDialog.getByLabel("Otros códigos de barras o QR",{exact:true}).fill("https://example.test/cacao\n0012345678906");
    await codeDialog.getByLabel("Etiquetas NFC",{exact:true}).fill("AA:BB:CC:DD\ntag-despensa");
    await codeDialog.getByLabel("Cocina",{exact:true}).selectOption("add_list");
    await codeDialog.getByLabel("NFC despensa",{exact:true}).selectOption("stock_remove");
    await codeDialog.getByRole("button",{name:"Guardar producto",exact:true}).click();
    await readerCatalog.getByRole("status").filter({hasText:"Producto guardado"}).waitFor();
    assert.equal(await readerCatalog.getByRole("button",{name:"Crear producto con el código 0012345678905",exact:true}).count(),0);
    assert.deepEqual(await readerPage.evaluate(()=>window.catalogProducts[0].barcodes),["https://example.test/cacao","0012345678906"]);
    assert.equal(await readerPage.evaluate(()=>Object.values(window.catalogProducts[0].reader_actions).includes("stock_remove")),true);
    await readerPage.evaluate(()=>{const reader=window.readerFixture.readers[1];window.readerFixture.pending=[{id:'scan-2',kind:'nfc',code:'11223344',reader_id:reader.id,reader_name:reader.name,time:new Date().toISOString()}];window.emitReaders();});
    const productId=await readerPage.evaluate(()=>window.catalogProducts[0].id);
    assert.equal(await readerCatalog.getByLabel("Producto para el código 11223344",{exact:true}).isVisible(),false);
    await readerCatalog.getByRole("button",{name:"Asignar código 11223344 a un producto del catálogo",exact:true}).click();
    await readerCatalog.getByLabel("Producto para el código 11223344",{exact:true}).selectOption(productId);
    const linkDialog=readerCatalog.getByRole("dialog",{name:"Editar producto",exact:true});
    await linkDialog.getByRole("button",{name:"Cancelar",exact:true}).click();
    await readerPage.evaluate(()=>window.emitReaders());
    assert.equal(await readerCatalog.locator("#scan-suggestions-group").evaluate(node => node.open),true);
    assert.equal(await readerCatalog.getByLabel("Producto para el código 11223344",{exact:true}).inputValue(),productId);
    await readerCatalog.getByRole("button",{name:"Asignar código 11223344 a un producto del catálogo",exact:true}).click();
    assert.ok((await linkDialog.getByLabel("Etiquetas NFC",{exact:true}).inputValue()).includes("11223344"));
    assert.equal(await linkDialog.getByLabel("Cocina",{exact:true}).inputValue(),"add_list");
    await linkDialog.getByRole("button",{name:"Guardar producto",exact:true}).click();
    await readerCatalog.getByRole("status").filter({hasText:"Producto guardado"}).waitFor();
    assert.equal(await readerPage.evaluate(()=>window.catalogProducts.length),1);
    await readerPage.evaluate(()=>{window.readerFixture.pending=[{id:'scan-discard',kind:'barcode',code:'999999',reader_name:'Cocina',time:new Date().toISOString()}];window.emitReaders();});
    await readerCatalog.getByRole("button",{name:"Descartar código 999999",exact:true}).click();
    assert.equal(await readerCatalog.locator('#scan-suggestions [data-pending-id="scan-discard"]').count(),0);
    await readerPage.getByRole("button",{name:"Lectores",exact:true}).click();
    await readersView.getByRole("button",{name:"Editar lector Cocina",exact:true}).click();
    const editReader=readersView.getByRole("dialog",{name:"Editar lector",exact:true});
    await editReader.getByLabel("Antirrepetición (segundos)",{exact:true}).fill("90");
    await editReader.getByRole("button",{name:"Guardar lector",exact:true}).click();
    await readersView.getByRole("status").filter({hasText:"Lector guardado"}).waitFor();
    assert.equal(await readerPage.evaluate(()=>window.readerFixture.readers.find(reader=>reader.name==='Cocina').cooldown),90);
    await readerPage.setViewportSize({width:390,height:844});
    await readerPage.screenshot({path:"test-results/readers-mobile.png",fullPage:true});
    assert.equal(await readerPage.locator("main").evaluate(node=>node.scrollWidth>innerWidth),false);
    await readerPage.reload();
    await readerPage.getByRole("button",{name:"Lectores",exact:true}).click();
    await readersView.getByRole("heading",{name:"NFC despensa",exact:true}).waitFor();
    await readersView.getByRole("button",{name:"Quitar lector NFC despensa",exact:true}).click();
    await readersView.getByRole("dialog",{name:"Quitar lector",exact:true}).getByRole("button",{name:"Quitar lector",exact:true}).click();
    await readersView.getByRole("status").filter({hasText:"Lector quitado"}).waitFor();
    assert.equal(await readerPage.evaluate(()=>window.readerFixture.readers.length),1);
    await readerContext.close();
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
