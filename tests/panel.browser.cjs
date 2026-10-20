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
window.calls=[];window.fail=false;
const panel=document.createElement('improved-shopping-list-panel');
const hass={
  states: {
    'todo.bring':{entity_id:'todo.bring',state:'2',attributes:{friendly_name:'Compra · Bring!',supported_features:5}},
    'todo.local':{entity_id:'todo.local',state:'1',attributes:{friendly_name:'Casa',supported_features:5}},
    'todo.readonly':{entity_id:'todo.readonly',state:'1',attributes:{friendly_name:'Solo lectura',supported_features:0}}
  },
  connection:{subscribeMessage:async(callback,msg)=>{
    const listener={callback,entityId:msg.entity_id}; listeners.set(listener,true);
    callback({items:structuredClone(data[msg.entity_id]??[])});
    return ()=>listeners.delete(listener);
  }},
  callWS:async(msg)=>({items:structuredClone(data[msg.entity_id]??[])}),
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
    if (!["/panel.js", "/todo-client.js"].includes(pathname)) { res.writeHead(404).end(); return; }
    res.setHeader("content-type", "text/javascript; charset=utf-8");
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
    await page.getByText("Cacao", { exact: true }).waitFor();
    await page.screenshot({ path: "test-results/panel-desktop.png", fullPage: true });

    // Input is text, even if a provider supplies something resembling HTML.
    const dangerous = '<img src=x onerror="window.injected=true">';
    await page.getByLabel("Añadir producto", { exact: true }).fill(dangerous);
    await page.getByRole("button", { name: "Añadir", exact: true }).click();
    await page.getByText(dangerous, { exact: true }).waitFor();
    assert.equal(await page.evaluate(() => window.injected), undefined);
    assert.equal(await page.getByLabel("Añadir producto", { exact: true }).inputValue(), "");

    await page.getByRole("checkbox", { name: "Marcar como comprado: Cacao", exact: true }).check();
    await page.getByText("Comprados (2)", { exact: true }).waitFor();
    assert.equal((await page.evaluate(() => window.calls)).at(-1).item, "cacao-1");
    await page.locator("#completed-summary").click();
    await page.getByRole("checkbox", { name: "Volver a poner por comprar: Cacao", exact: true }).uncheck();
    await page.getByRole("checkbox", { name: "Marcar como comprado: Cacao", exact: true }).waitFor();

    await page.evaluate(() => window.rename());
    await page.getByText("Cacao puro", { exact: true }).waitFor();
    await page.getByLabel("Lista de la compra", { exact: true }).selectOption("todo.local");
    await page.getByText("Detergente", { exact: true }).waitFor();
    assert.equal(await page.getByText("Cacao puro", { exact: true }).count(), 0);
    assert.equal(await page.evaluate(() => window.listenerCount()), 1);

    await page.getByLabel("Lista de la compra", { exact: true }).selectOption("todo.readonly");
    await page.getByText("Lista compartida", { exact: true }).waitFor();
    assert.equal(await page.getByRole("button", { name: "Añadir", exact: true }).isDisabled(), true);
    assert.equal(await page.getByRole("checkbox").isDisabled(), true);

    await page.getByLabel("Lista de la compra", { exact: true }).selectOption("todo.bring");
    await page.getByText("Cacao puro", { exact: true }).waitFor();
    await page.evaluate(() => { window.fail = true; });
    await page.getByLabel("Añadir producto", { exact: true }).fill("Aceite");
    await page.getByRole("button", { name: "Añadir", exact: true }).click();
    await page.getByRole("alert").filter({ hasText: "Proveedor sin conexión" }).waitFor();
    assert.equal(await page.getByLabel("Añadir producto", { exact: true }).inputValue(), "Aceite");
    await page.evaluate(() => window.makeUnavailable());
    assert.equal(await page.getByRole("button", { name: "Añadir", exact: true }).isDisabled(), true);

    // Actual narrow layout, sidebar access and horizontal overflow.
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(url);
    await page.getByText("Cacao", { exact: true }).waitFor();
    await page.getByRole("button", { name: "Abrir menú de Home Assistant" }).click();
    assert.equal(await page.evaluate(() => window.menuOpened), true);
    assert.equal(await page.evaluate(() => {
      const root = window.testPanel.shadowRoot;
      return root.querySelector("main").scrollWidth > window.innerWidth;
    }), false);
    await page.screenshot({ path: "test-results/panel-mobile.png", fullPage: true });
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
