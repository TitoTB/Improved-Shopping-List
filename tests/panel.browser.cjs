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
window.recommendationCategories=JSON.parse(localStorage.getItem('recommendation-fixture')??'[]');
window.catalogRecipes=JSON.parse(localStorage.getItem('recipe-fixture')??'[]');
window.dismissedSuggestions=JSON.parse(localStorage.getItem('dismissed-fixture')??'[]');
const normalizeName=name=>name.normalize('NFKC').trim().replace(/\\s+/g,' ').toLowerCase();
const snapshot=()=>({recipes:structuredClone(window.catalogRecipes),recommendation_categories:structuredClone(window.recommendationCategories),products:structuredClone(window.catalogProducts),dismissed_suggestions:[...window.dismissedSuggestions],categories:window.catalogCategories.map(category=>({...category,product_count:window.catalogProducts.filter(product=>product.category===category.name).length}))});
const emitCatalog=window.emitCatalog=()=>{
  localStorage.setItem('catalog-fixture',JSON.stringify(window.catalogProducts));
  localStorage.setItem('category-fixture',JSON.stringify(window.catalogCategories));
  localStorage.setItem('recommendation-fixture',JSON.stringify(window.recommendationCategories));
  localStorage.setItem('recipe-fixture',JSON.stringify(window.catalogRecipes));
  localStorage.setItem('dismissed-fixture',JSON.stringify(window.dismissedSuggestions));
  for(const listener of listeners.keys())if(listener.catalog)listener.callback(snapshot());
};
window.stockItems=JSON.parse(localStorage.getItem('stock-fixture')??'[]');
window.quantityEntries=JSON.parse(localStorage.getItem('quantity-fixture')??'{}');
window.emitQuantities=()=>{localStorage.setItem('quantity-fixture',JSON.stringify(window.quantityEntries));for(const listener of listeners.keys())if(listener.quantities)listener.callback({entries:structuredClone(window.quantityEntries)});};
window.receiptHistory=JSON.parse(localStorage.getItem('receipt-fixture')??'[]');
window.receiptLinks=[];
const receiptOptions=()=>({products:[...new Map([{id:'cacao',name:'Seitán',unit:'g',price:3.80,image_url:'/local/receipt-seitan.svg',icon:'mdi:food',stock_id:'s1',revision:1},...window.catalogProducts.filter(p=>p.id!=='cacao').map(p=>({id:p.id,name:p.name,image_url:p.image_url??'',icon:p.icon??'',unit:'uds',stock_id:'',revision:0}))].map(p=>[p.id,p])).values()],purchases:[]});
window.emitStock=()=>{localStorage.setItem('stock-fixture',JSON.stringify(window.stockItems));for(const listener of listeners.keys())if(listener.stock)listener.callback({items:structuredClone(window.stockItems)});};
window.calls=[];window.fail=false;window.failCatalog=false;
window.logFixture={entries:[],limit:1000};window.failLogs=false;
window.emitLogs=()=>{for(const listener of listeners.keys())if(listener.logs)listener.callback(structuredClone(window.logFixture));};
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
  services:{notify:{mobile_app_one:{name:"Móvil uno"},mobile_app_two:{name:"Móvil dos"},send_message:{name:"Enviar mensaje"},notify:{name:"Genérico"}}},
  states: {
    'notify.kitchen':{entity_id:'notify.kitchen',state:'unknown',attributes:{friendly_name:'Pantalla cocina'}},
    'todo.bring':{entity_id:'todo.bring',state:'2',attributes:{friendly_name:'Compra · Bring!',supported_features:5}},
    'todo.local':{entity_id:'todo.local',state:'1',attributes:{friendly_name:'Casa',supported_features:5}},
    'todo.readonly':{entity_id:'todo.readonly',state:'1',attributes:{friendly_name:'Solo lectura',supported_features:0}}
  },
  connection:{subscribeMessage:async(callback,msg)=>{
    if(msg.type==='improved_shopping_list/quantities/subscribe'){
      const listener={callback,quantities:true};listeners.set(listener,true);callback({entries:structuredClone(window.quantityEntries)});return()=>listeners.delete(listener);
    }
    if(msg.type==='improved_shopping_list/receipts/subscribe'){
      const listener={callback,receipts:true};listeners.set(listener,true);callback({receipts:structuredClone(window.receiptHistory)});return()=>listeners.delete(listener);
    }
    if(msg.type==='improved_shopping_list/stock/subscribe'){
      const listener={callback,stock:true};listeners.set(listener,true);callback({items:structuredClone(window.stockItems)});return()=>listeners.delete(listener);
    }
    if(msg.type==='improved_shopping_list/settings/store_progress'){
      (window.storeProgressListeners??=new Set()).add(callback);callback(JSON.parse(localStorage.getItem('price-progress-fixture')??'null')??{running:false,last_updated:window.lastPriceUpdateFixture??0});
      return()=>window.storeProgressListeners.delete(callback);
    }
    if(msg.type==='improved_shopping_list/logs/subscribe'){
      if(window.failLogs)throw new Error('Error al cargar logs');
      const listener={callback,logs:true};listeners.set(listener,true);callback(structuredClone(window.logFixture));return()=>listeners.delete(listener);
    }
    if(msg.type==='improved_shopping_list/readers/capture'){
      if(window.failCapture)throw new Error('Lector ocupado');
      const captures=window.captureListeners??=new Map();
      captures.set(msg.reader_id,callback);return()=>captures.delete(msg.reader_id);
    }
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
    if(msg.type==='improved_shopping_list/quantities/get')return {entries:structuredClone(window.quantityEntries)};
    if(msg.type==='improved_shopping_list/quantities/adjust'){
      if(window.failQuantities)throw new Error('No se pudo cambiar la cantidad');
      const item=data[msg.entity_id].find(item=>item.uid===msg.uid);
      const product=window.catalogProducts.find(product=>normalizeName(product.name)===normalizeName(item.summary));
      const record=window.quantityEntries[msg.entity_id]?.[msg.uid],unit=product?.purchase_unit??record?.unit??'uds';
      const current=record&&(!product||record.unit===unit)?record.quantity:product?.unit_quantity??1;
      const step=product?.quantity_step??record?.step??1,quantity=Math.round((current+msg.direction*step)*1000)/1000;
      if(quantity<=0)throw new Error('La cantidad debe ser positiva');
      (window.quantityEntries[msg.entity_id]??={})[msg.uid]={quantity,unit,step};window.emitQuantities();return {entries:structuredClone(window.quantityEntries)};
    }
    if(msg.type==='improved_shopping_list/logs/get'){if(window.failLogs)throw new Error('Error al cargar logs');return structuredClone(window.logFixture);}
    if(msg.type==='improved_shopping_list/icons/search'){
      (window.iconCalls??=[]).push(msg);
      if(window.failIconSearch)throw new Error('Iconify sin conexión');
      if(msg.query==='slow')await new Promise(resolve=>{window.releaseIconSearch=resolve;});
      const query=msg.translate?({Leche:'Milk',Pan:'Bread',Arroz:'Rice'}[msg.query]??msg.query):msg.query;
      if(msg.translate&&msg.product_id){const product=window.catalogProducts.find(product=>product.id===msg.product_id);if(product){product.name_en=query;emitCatalog();}}
      const count=query==='few'?3:query==='paged'?(msg.start?3:32):12;
      const icons=Array.from({length:count},(_,i)=>({id:'fluent-emoji-flat:milk-'+((msg.start??0)+i),label:query+' '+((msg.start??0)+i+1),collection:'Fluent Emoji Flat',author:'Microsoft',license:'MIT',preview_url:'/improved_shopping_list_icons/fixture.svg'}));
      return {icons:['zzzz','Arroz','Leche'].includes(query)?[]:icons,next_start:(msg.start??0)+32,has_more:query==='paged'&&!msg.start,query};
    }
    if(msg.type==='improved_shopping_list/icons/import'){
      (window.iconImports??=[]).push(msg);
      if(window.failIconImport)throw new Error('No se ha podido guardar el icono');
      if(window.delayIconImport)await new Promise(resolve=>{window.releaseIconImport=resolve;});
      const asset={id:msg.icon_id,url:'/improved_shopping_list_icons/fixture.svg',collection:'Tabler Icons',author:'Paweł Kuna',author_url:'https://github.com/tabler/tabler-icons',license:'MIT',license_url:'https://github.com/tabler/tabler-icons/blob/master/LICENSE',source_url:'https://icon-sets.iconify.design/tabler/milk/'};
      localStorage.setItem('icon-asset-fixture',JSON.stringify(asset));return asset;
    }
    if(msg.type==='improved_shopping_list/catalog/nutrition_distribution'){
      if(window.failNutritionDistribution)throw new Error('Disconnected');
      const counts={a:0,b:0,c:0,d:0,e:0},product_ids={a:[],b:[],c:[],d:[],e:[]};
      for(const product of window.catalogProducts){
        const grade=[product.barcode,...(product.barcodes??[])].map(code=>window.nutriFixture?.[String(code).replace(/^0+/,'')]).find(value=>counts[value?.grade]!=null)?.grade;
        if(grade){counts[grade]++;product_ids[grade].push(product.id);}
      }
      return {counts,total:Object.values(counts).reduce((sum,count)=>sum+count,0),product_ids};
    }
    if(msg.type==='improved_shopping_list/catalog/nutriscore'){
      (window.nutriCalls??=[]).push(msg.code);
      if(window.delayNutriCode===msg.code)await new Promise(resolve=>{window.releaseNutri=resolve;});
      if(window.failNutri||window.failNutriCode===msg.code)throw new Error('OFF sin conexión');
      return {code:msg.code,product_name:'Producto '+msg.code,nutriscore:window.nutriFixture?.[msg.code]??null};
    }
    if(msg.type==='improved_shopping_list/community/status')return structuredClone(window.communityFixture??{sharing:false,connected:false,account:'',authorization:null});
    if(msg.type==='improved_shopping_list/community/sharing'){
      window.communityFixture={sharing:msg.enabled,connected:false,account:'',authorization:msg.enabled?{user_code:'ABCD-EFGH',verification_uri:'https://github.com/login/device'}:null};
      return structuredClone(window.communityFixture);
    }
    if(msg.type==='improved_shopping_list/community/export'){
      if(window.failCommunityExport)throw new Error('No se ha podido exportar el diccionario');
      return {data:'UEsFBgAAAAAAAAAAAAAAAAAAAAAAAA==',entries:2,images:1,skipped:0};
    }
    if(msg.type==='improved_shopping_list/icons/info')return JSON.parse(localStorage.getItem('icon-asset-fixture')??'null');
    if(msg.type==='improved_shopping_list/readers/get')return structuredClone(window.readerFixture);
    if(msg.type==='improved_shopping_list/readers/save'){
      if(window.failReaders)throw new Error('No se ha podido guardar el lector');
      if('last' in msg.reader)throw new Error('Runtime state must not be sent as reader configuration');
      const old=window.readerFixture.readers.find(reader=>reader.id===msg.reader.id);
      const reader={entity_id:'',attribute:'',device_id:'',list_entity:'',...msg.reader,id:old?.id??crypto.randomUUID(),revision:(old?.revision??0)+1};
      if(old?.last)reader.last=old.last;
      window.readerFixture.readers=window.readerFixture.readers.filter(item=>item.id!==reader.id);window.readerFixture.readers.push(reader);window.emitReaders();return reader;
    }
    if(msg.type==='improved_shopping_list/readers/delete'){window.readerFixture.readers=window.readerFixture.readers.filter(reader=>reader.id!==msg.reader_id);window.emitReaders();return null;}
    if(msg.type==='improved_shopping_list/readers/dismiss'){window.readerFixture.pending=window.readerFixture.pending.filter(item=>item.id!==msg.pending_id);window.emitReaders();return null;}
    if(msg.type==='improved_shopping_list/stock/get')return {items:structuredClone(window.stockItems)};
    if(msg.type==='improved_shopping_list/receipts/get')return {receipts:structuredClone(window.receiptHistory)};
    if(msg.type==='improved_shopping_list/receipts/discard')return null;
    if(msg.type==='improved_shopping_list/receipts/options')return receiptOptions();
    if(msg.type==='improved_shopping_list/receipts/link'){
      const ids=msg.lines.map(line=>line.product_id).filter(Boolean);if(new Set(ids).size!==ids.length)throw new Error('Dos líneas no pueden vincularse al mismo producto.');
      window.receiptLinks=structuredClone(msg.lines);return receiptOptions();
    }
    if(msg.type.startsWith('improved_shopping_list/carrefour_account/')){
      window.calls.push({type:msg.type,receipt_id:msg.receipt_id});
      window.cfStatus??={connected:false,verification_required:false,destinations:[],verification_sent:false};
      const action=msg.type.split('/').at(-1);
      if(action==='status')return structuredClone(window.cfStatus);
      if(action==='preview_saved'&&window.failCarrefourAccount)throw new Error('Carrefour ha rechazado el acceso (HTTP 403).');
      if(action==='login'){window.cfStatus={connected:false,verification_required:true,destinations:[{id:'0',label:'a***@example.test'}],verification_sent:false};return structuredClone(window.cfStatus);}
      if(action==='send_code'){window.cfStatus.verification_sent=true;return structuredClone(window.cfStatus);}
      if(action==='verify'){window.cfStatus={connected:true,email:'test@example.test',options:{history_enabled:false,auto_ticket:false,public_prices:false},verification_required:false,destinations:[],verification_sent:false};return structuredClone(window.cfStatus);}
      if(action==='disconnect'){window.cfStatus={connected:false,verification_required:false,destinations:[],verification_sent:false};return structuredClone(window.cfStatus);}
      if(action==='options'){window.cfStatus.options=structuredClone(msg.options);if(msg.options.history_enabled){for(const [id,total] of [['summary-ticket',5.22],['summary-order',10]])if(!window.receiptHistory.some(r=>r.id===id))window.receiptHistory.push({id,store:'carrefour',store_name:'Carrefour',purchased_at:'2026-10-16T19:59:30',total,article_count:null,lines:[],summary_only:true,account_key:id,ticket_available:id==='summary-ticket'});localStorage.setItem('receipt-fixture',JSON.stringify(window.receiptHistory));}return structuredClone(window.cfStatus);}
      if(action==='sync_history'){if(window.failCarrefourAccount)throw new Error('Carrefour ha rechazado el acceso (HTTP 403).');for(const [id,total] of [['summary-ticket',5.22],['summary-order',10]])if(!window.receiptHistory.some(r=>r.id===id))window.receiptHistory.push({id,store:'carrefour',store_name:'Carrefour',purchased_at:'2026-10-16T19:59:30',total,article_count:null,lines:[],summary_only:true,account_key:id,ticket_available:id==='summary-ticket'});localStorage.setItem('receipt-fixture',JSON.stringify(window.receiptHistory));return {added:2,available:2,complete:true};}
      if(action==='purchases'){if(window.failCarrefourAccount)throw new Error('Carrefour ha rechazado el acceso (HTTP 403).');return {purchases:[{id:'private-purchase-key',purchased_at:'2026-10-16T19:59:30',amount:5.22,store:'Carrefour de prueba',reviewable:true,kind:'Ticket'},...(msg.cursor?[]:[{id:'online-key',purchased_at:'2026-10-16T19:59:30',amount:10,store:'Carrefour online',reviewable:false,kind:'Pedido online · factura pendiente de soporte'}])],next_cursor:msg.cursor?null:{ticketOffset:10}};}
    }
    if(msg.type==='improved_shopping_list/receipts/preview'||msg.type==='improved_shopping_list/carrefour_account/preview'||msg.type==='improved_shopping_list/carrefour_account/preview_saved'){
      if(window.receiptHistory.some(receipt=>!receipt.summary_only))throw new Error('Este ticket ya se ha importado.');
      const draft={token:'preview',receipt:{id:'ticket1',store:'carrefour',store_name:'Carrefour',purchased_at:'2026-10-16T19:59:30',total:5.22,subtotal:6.22,discount:1,article_count:4,
        lines:[{id:'0',description:'SEITAN 250 G',count:1,unit_price:2.65,amount:2.65,pack_quantity:250,pack_unit:'g',product_id:'cacao',matched:!window.receiptSuggestionOnly,quantity:250,replenish:false},
          {id:'1',description:'FLAUTIN CEREALES',count:2,unit_price:.44,amount:.88,pack_quantity:null,pack_unit:'',product_id:'',quantity:null,replenish:false},
          {id:'2',description:'ANACARDO CRUDO 200',count:1,unit_price:2.69,amount:2.69,pack_quantity:null,pack_unit:'',product_id:'',quantity:null,replenish:false}]},
        ...receiptOptions()};
      if(window.receiptInvoice){Object.assign(draft.receipt,{id:'invoice1',document_type:'invoice',shipping:3.99,discount:0,total:10.21});Object.assign(draft.receipt.lines[0],{ean:'1234567890128',count:2,gross_amount:5.30,line_discount:2.65,quantity:500});}
      for(const line of draft.receipt.lines){const learned=window.receiptLinks.find(link=>link.id===line.id);if(learned)line.product_id=learned.product_id;}
      window.receiptDraft=structuredClone(draft.receipt);return draft;
    }
    if(msg.type==='improved_shopping_list/receipts/confirm'){
      if(window.failReceipt)throw new Error('No se ha podido guardar el ticket.');
      window.lastReceiptConfirmation=structuredClone(msg);
      const receipt=structuredClone(window.receiptDraft);
      for(const [index,line] of receipt.lines.entries()){
        const edit=msg.lines[index],product=receiptOptions().products.find(p=>p.id===edit.product_id);
        Object.assign(line,{product_name:product?.name??'',replenished:edit.replenish,quantity:edit.quantity,unit:edit.unit,price_saved:edit.save_price});
        if(edit.replenish){let stock=window.stockItems.find(item=>item.catalog_product_id===edit.product_id);if(!stock){stock={id:crypto.randomUUID(),catalog_product_id:edit.product_id,name:product.name,quantity:0,unit:edit.unit,revision:0};window.stockItems.push(stock);}stock.quantity+=edit.quantity;stock.revision++;}
      }
      window.emitStock();
      window.receiptHistory.push(receipt);localStorage.setItem('receipt-fixture',JSON.stringify(window.receiptHistory));return receipt;
    }
    if(msg.type.startsWith('improved_shopping_list/stock/')){
      if(window.failStock)throw new Error('No se ha podido guardar el stock');
      if(msg.type.endsWith('/save')){
        const item=window.stockItems.find(item=>item.id===msg.item_id);
        if(item?.revision!==msg.revision)throw new Error('El stock ha cambiado. Cierra y vuelve a abrir la ficha para actualizarla.');
        Object.assign(item,structuredClone(msg.config),{configured:true,config_revision:(item.config_revision??0)+1,revision:item.revision+1});
        window.emitStock();return structuredClone(item);
      }
      if(msg.type.endsWith('/remove')){
        const item=window.stockItems.find(item=>item.id===msg.item_id);
        if(item?.revision!==msg.revision)throw new Error('El stock del producto ha cambiado');
        window.stockItems=window.stockItems.filter(item=>item.id!==msg.item_id);window.emitStock();return null;
      }
      let item=msg.item_id?window.stockItems.find(item=>item.id===msg.item_id):window.stockItems.find(item=>normalizeName(item.name)===normalizeName(msg.name));
      if(!item){const product=window.catalogProducts.find(product=>normalizeName(product.name)===normalizeName(msg.name));item={id:crypto.randomUUID(),name:product?.name??msg.name,catalog_product_id:product?.id??'',quantity:0,revision:0};window.stockItems.push(item);}
      item.quantity=Math.max(0,item.quantity+(msg.delta??1));item.revision++;window.emitStock();return structuredClone(item);
    }
    if(msg.type==='improved_shopping_list/settings/get')return structuredClone(window.listSettings);
    if(msg.type==='improved_shopping_list/settings/notifications'){
      if(window.failSettings)throw new Error('No se han podido guardar las notificaciones');
      for(const rule of Object.values(msg.notifications))if(rule.enabled&&!rule.targets.length)throw new Error('Selecciona al menos un dispositivo');
      window.listSettings.notifications=structuredClone(msg.notifications);window.emitSettings();return structuredClone(window.listSettings);
    }
    if(msg.type==='improved_shopping_list/settings/personalization'){
      if(window.failSettings)throw new Error('No se ha podido guardar la personalización');
      window.listSettings.appearance=structuredClone(msg.appearance);window.emitSettings();return structuredClone(window.listSettings);
    }
    if(msg.type==='improved_shopping_list/settings/store_products'){
      (window.storeProductCalls??=[]).push(msg);
      if(!msg.force&&window.holdAutomaticStoreRefresh)await new Promise(resolve=>window.finishAutomaticStoreRefresh=resolve);
      if(msg.force&&window.holdStoreRefresh)await new Promise(resolve=>window.finishStoreRefresh=resolve);
      return {warehouse:'mad3',enabled:true,products:[{name:'Tomate',ean:'8430543025611',store_name:'Tomate rallado',store_product_id:'69938',price:msg.force?1.55:1.45,reference_price:5,reference_unit:'kg',checked_at:1800000000}],error:window.failStoreProducts?'Mercadona ha rechazado la consulta (HTTP 403)':'',automatic_refresh_blocked:!!window.failStoreProducts,remaining:window.failStoreProducts?20:0,processed:0,total:20,retry_at:window.failStoreProducts?Date.now()/1000+900:0};
    }
    if(msg.type==='improved_shopping_list/settings/store_enabled'){
      if(window.failSettings)throw new Error('No se ha podido guardar la tienda');
      (window.storePostalCalls??=[]).push(structuredClone(msg));
      const defaults={mercadona:{postal_code:'28024',warehouse:'mad1'},carrefour:{postal_code:'28024',sale_point:'005704'},alcampo:{postal_code:'28024',region_id:'deb03a69-3104-4451-9ffa-3a55dc156d9f'},consum:{postal_code:'46409',area_id:'301D',zone:'301'},lasirena:{postal_code:'28024',area_id:'lasirena259'},eroski:{postal_code:'48001',area_id:'f7e80707-fd7a-437c-b451-698301f2cf77',zone:'244'},dia:{postal_code:'28024',area_id:'28024',zone:'28024'}};
      window.listSettings.stores={...window.listSettings.stores,[msg.store]:{enabled:msg.enabled,...defaults[msg.store]}};
      if(!window.listSettings.stores?.[window.listSettings.favorite_store]?.enabled)window.listSettings.favorite_store=Object.keys(window.listSettings.stores).find(key=>window.listSettings.stores[key].enabled)||'';
      window.listSettingsPush?.(structuredClone(window.listSettings));
      return structuredClone(window.listSettings);
    }
    if(msg.type==='improved_shopping_list/settings/resolve_store'){
      if(msg.postal_code==='28024'&&msg.store==='consum')throw new Error('Consum no ofrece entrega para este código postal.');
      return {postal_code:msg.postal_code,areas:msg.store==='dia'?[{id:msg.postal_code,zone:msg.postal_code,name:'Código postal '+msg.postal_code}]:msg.store==='eroski'?[{id:'f7e80707-fd7a-437c-b451-698301f2cf77',zone:'244',name:'BIZKAIA - Eroski Deusto'}]:msg.store==='consum'?[{id:'301D',name:'Centro 301 · Cullera',zone:'301'}]:[{id:'lasirena102',name:'Centro 102'},{id:'lasirena259',name:'Centro 259'}]};
    }
    if(msg.type==='improved_shopping_list/settings/store'){
      if(window.failSettings)throw new Error('Mercadona no está disponible');
      if(['consum','lasirena','eroski','dia'].includes(msg.store)){
        const previous=window.listSettings.stores?.[msg.store]??{};
        window.listSettings.stores={...window.listSettings.stores,[msg.store]:{...previous,enabled:msg.enabled,...(msg.verify?{postal_code:msg.postal_code,area_id:msg.area_id,area_name:msg.area_id,zone:msg.store==='dia'?msg.postal_code:msg.store==='consum'?'301':msg.store==='eroski'?'244':'',checked_at:12345}:{})}};
        const active=Object.keys(window.listSettings.stores).filter(key=>window.listSettings.stores[key].enabled);
        if(!active.includes(window.listSettings.favorite_store))window.listSettings.favorite_store=active[0]??'';
        window.emitSettings();return structuredClone(window.listSettings);
      }
      if(msg.store==='carrefour'||msg.store==='alcampo'){
        if(msg.store==='carrefour'&&msg.sale_point!==undefined&&!/^[0-9]{6}$/.test(msg.sale_point))throw new Error('El centro de Carrefour debe contener seis dígitos.');
        window.listSettings.stores={...window.listSettings.stores,[msg.store]:{...window.listSettings.stores?.[msg.store],enabled:msg.enabled,...(msg.store!=='carrefour'?{region_id:msg.region_id}: {sale_point:msg.sale_point??window.listSettings.stores?.carrefour?.sale_point??'005290'})}};
        const active=Object.keys(window.listSettings.stores).filter(key=>window.listSettings.stores[key].enabled);
        if(!active.includes(window.listSettings.favorite_store))window.listSettings.favorite_store=active[0]??'';
        window.emitSettings();return structuredClone(window.listSettings);
      }
      const previous=window.listSettings.stores?.mercadona??{};
      window.listSettings.stores={...window.listSettings.stores,mercadona:msg.enabled||msg.verify?{enabled:msg.enabled,postal_code:msg.postal_code||'28001',warehouse:'mad3',checked_at:12345}:{...previous,enabled:false}};
      window.listSettings.favorite_store=msg.enabled?'mercadona':'';
      window.emitSettings();return structuredClone(window.listSettings);
    }
    if(msg.type==='improved_shopping_list/settings/favorite_store'){
      window.listSettings.favorite_store=msg.store;window.emitSettings();return structuredClone(window.listSettings);
    }
    if(msg.type==='improved_shopping_list/settings/price_schedule'){
      window.listSettings.price_update_time=msg.time;window.listSettings.price_updates_enabled=msg.enabled;window.listSettings.price_update_days=msg.days;window.emitSettings();return structuredClone(window.listSettings);
    }
    if(msg.type==='improved_shopping_list/settings/refresh_all_prices'){
      window.calls.push(structuredClone(msg));
      if(window.delayManualRefresh)await new Promise(resolve=>{window.releaseManualRefresh=resolve;});
      if(window.failManualPriceRefresh)throw new Error('La tienda ha indicado una pausa.');
      if(window.manualResumeProgress)return {resumed:true,queued:5,errors:[],progress:structuredClone(window.manualResumeProgress)};
      return {queued:4,errors:window.manualPriceErrors??[]};
    }
    if(msg.type==='improved_shopping_list/catalog/store_prices'){
      const products=window.storePriceFixture??((msg.codes??[]).includes('8431876279146')?[{store:'carrefour',store_name:'Alcaparras Carrefour',ean:'8431876279146',price:'1.35',currency:'EUR',url:'https://www.awin1.com/pclick.php?p=123&a=1535625&m=25399',checked_at:1792490400}]:[]);
      return {nightly:true,products:msg.store?products.filter(p=>p.store===msg.store):products,enabled:!!window.listSettings.stores?.[msg.store]?.enabled,warehouse:msg.store==='mercadona'?(window.listSettings.stores?.mercadona?.warehouse??''):'',update_time:window.listSettings.price_update_time??'01:00'};
    }
    if(msg.type==='improved_shopping_list/settings/carrefour_products')return {
      enabled:!!window.listSettings.stores?.carrefour?.enabled,version:'published',generated_at:'2026-10-20T12:00:00+00:00',error:'',stale:false,
      products:[{ean:'8431876279146',name:'Alcaparras Carrefour',price:'1.35',currency:'EUR',affiliate_url:'https://www.awin1.com/pclick.php?p=123&a=1535625&m=25399'}]
    };
    if(msg.type==='improved_shopping_list/settings/gateway_save'){
      if(window.failSettings)throw new Error('No se pudo guardar la pasarela');
      window.listSettings.gateway_lists=(window.listSettings.gateway_lists??[]).filter(item=>item.entity_id!==msg.entity_id);
      window.listSettings.gateway_lists.push({entity_id:msg.entity_id,target_entity:msg.target_entity,remove_after_transfer:msg.remove_after_transfer});
      window.listSettings.entities=window.listSettings.entities.filter(entity=>entity!==msg.entity_id);
      window.emitSettings();return structuredClone(window.listSettings);
    }
    if(msg.type==='improved_shopping_list/settings/gateway_remove'){
      window.listSettings.gateway_lists=(window.listSettings.gateway_lists??[]).filter(item=>item.entity_id!==msg.entity_id);
      window.emitSettings();return structuredClone(window.listSettings);
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
    if(msg.type==='improved_shopping_list/catalog/delete'){
      if(window.failDeleteProduct)throw new Error('No se ha podido eliminar el producto');
      const product=window.catalogProducts.find(item=>item.id===msg.product_id);
      if(!product||product.revision!==msg.revision)throw new Error('El producto ha cambiado');
      window.catalogProducts=window.catalogProducts.filter(item=>item.id!==msg.product_id);emitCatalog();return null;
    }
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
    if(msg.type==='improved_shopping_list/catalog/recipe/save'){
      if(window.failCatalog)throw new Error('No se ha podido guardar la receta');
      const previous=window.catalogRecipes.find(recipe=>recipe.id===msg.recipe.id);
      const recipe={...msg.recipe,id:previous?.id??crypto.randomUUID(),revision:(previous?.revision??0)+1,season_months:previous?.season_months??[]};
      window.catalogRecipes=window.catalogRecipes.filter(item=>item.id!==recipe.id);window.catalogRecipes.push(recipe);emitCatalog();return {recipe};
    }
    if(msg.type==='improved_shopping_list/catalog/recipe/delete'){
      window.catalogRecipes=window.catalogRecipes.filter(recipe=>recipe.id!==msg.recipe_id);
      for(const group of window.recommendationCategories)group.recipe_ids=(group.recipe_ids??[]).filter(id=>id!==msg.recipe_id);
      emitCatalog();return {};
    }
    if(msg.type==='improved_shopping_list/catalog/recipe/season_months'){
      const recipe=window.catalogRecipes.find(recipe=>recipe.id===msg.recipe_id),months=new Set(recipe.season_months??[]);
      for(const month of msg.months)msg.enabled?months.add(month):months.delete(month);
      recipe.season_months=[...months];recipe.revision++;emitCatalog();return {recipe};
    }
    if(msg.type==='improved_shopping_list/catalog/recipe/add'){
      const recipe=window.catalogRecipes.find(recipe=>recipe.id===msg.recipe_id);const applied=[];
      for(const ingredient of recipe.ingredients){
        const product=window.catalogProducts.find(product=>product.id===ingredient.product_id);
        let item=data[msg.entity_id].find(item=>item.summary===product.name&&item.status==='needs_action');
        const current=item?window.quantityEntries[msg.entity_id]?.[item.uid]?.quantity??product.unit_quantity??1:0;
        if(!item){await hass.callService('todo','add_item',{entity_id:msg.entity_id,item:product.name});item=data[msg.entity_id].find(item=>item.summary===product.name&&item.status==='needs_action');}
        (window.quantityEntries[msg.entity_id]??={})[item.uid]={quantity:current+ingredient.quantity,unit:ingredient.unit,step:product.quantity_step??1};applied.push({product_id:product.id});
      }
      window.emitQuantities();return {applied,error:''};
    }
    if(msg.type==='improved_shopping_list/catalog/recommendation_category/save'){
      if(window.failCatalog)throw new Error('No se ha podido guardar la categoría');
      const previous=window.recommendationCategories.find(group=>group.id===msg.category.id);
      const category={...msg.category,id:previous?.id??crypto.randomUUID(),revision:(previous?.revision??0)+1};
      window.recommendationCategories=window.recommendationCategories.filter(group=>group.id!==category.id);window.recommendationCategories.push(category);
      emitCatalog();return {category};
    }
    if(msg.type==='improved_shopping_list/catalog/recommendation_category/delete'){
      window.recommendationCategories=window.recommendationCategories.filter(group=>group.id!==msg.category_id);emitCatalog();return {};
    }
    if(msg.type==='improved_shopping_list/catalog/season_months'){
      if(window.failCatalog)throw new Error('No se ha podido guardar la temporada');
      const product=window.catalogProducts.find(product=>product.id===msg.product_id);
      if(!product)throw new Error('El producto ya no existe');
      const months=new Set(product.season_months??[]);
      for(const month of msg.months)msg.enabled?months.add(month):months.delete(month);
      product.season_months=[...months].sort((a,b)=>a-b);product.revision++;
      emitCatalog();return {product:structuredClone(product)};
    }
    if(msg.type==='improved_shopping_list/catalog/save'){
      if(window.failCatalog)throw new Error('No se ha podido guardar el catálogo');
      const old=window.catalogProducts.find(product=>product.id===msg.product.id);
      const product={...msg.product,season_months:old?.season_months??[],id:old?.id??crypto.randomUUID(),revision:(old?.revision??0)+1,price_updated_at:new Date().toISOString()};
      product.name_en=product.name==='Leche'?'Milk':'';
      delete product.brand;delete product.format;
      window.catalogProducts=window.catalogProducts.filter(item=>item.id!==product.id);window.catalogProducts.push(product);
      emitCatalog();
      return {product};
    }
    return {items:structuredClone(data[msg.entity_id]??[])};
  },
  callService:async(domain,service,args)=>{
    if(window.fail)throw new Error('Proveedor sin conexión');
    window.calls.push({domain,service,...args});
    if(service==='remove_completed_items'){if(window.delayClear)await new Promise(resolve=>{window.releaseClear=resolve;});data[args.entity_id]=data[args.entity_id].filter(item=>item.status!=='completed');}
    if(service==='add_item')data[args.entity_id].push({uid:crypto.randomUUID(),summary:args.item,status:'needs_action'});
    if(service==='update_item'){const item=data[args.entity_id].find(item=>item.uid===args.item);if(!item)throw new Error('Item missing');if('status' in args)item.status=args.status;if('rename' in args)item.summary=args.rename;}
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
window.logListenerCount=()=>[...listeners.keys()].filter(listener=>listener.logs).length;
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

async function editCatalogProduct(catalog, name) {
  if (!await catalog.locator("#catalog-grid").evaluate(node=>node.classList.contains("rows"))) {
    await catalog.getByRole("button",{name:"Cambiar a vista de filas",exact:true}).click();
  }
  await catalog.getByRole("button",{name,exact:true}).click();
}

async function captureProductCode(page, form, kind, code, expected = code) {
  await page.evaluate(kind=>{
    if(!window.readerFixture.readers.some(reader=>reader.kind===kind&&reader.enabled)){
      window.readerFixture.readers.push({id:'capture-'+kind,name:'Captura '+kind,kind,enabled:true,default_action:'none'});
      window.emitReaders();
    }
  },kind);
  await form.getByRole('button',{name:'Automatización',exact:true}).click();
  const group=form.locator('#product-'+kind+'-codes');
  await group.getByRole('button',{name:'Escanear',exact:true}).click();
  await page.waitForFunction(()=>window.captureListeners?.size>0);
  await page.evaluate(({kind,code})=>{
    for(const [readerId,callback] of window.captureListeners){
      const reader=window.readerFixture.readers.find(reader=>reader.id===readerId);
      if(reader.kind===kind)callback({status:'scanned',kind,reader_id:readerId,code});
    }
  },{kind,code});
  await group.getByText(expected,{exact:true}).waitFor();
  await group.getByRole('button',{name:'Detener',exact:true}).click();
}

async function main() {
  await fs.mkdir("test-results", { recursive: true });
  const server = http.createServer(async (req, res) => {
    const pathname = new URL(req.url, "http://localhost").pathname;
    if (pathname === "/improved_shopping_list_icons/fixture.svg") {
      res.setHeader("content-type", "image/svg+xml");
      res.end('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path fill="#267052" d="M4 4h16v16H4z"/></svg>');
      return;
    }
    if (pathname === "/scoped-custom-element-registry.js") {
      res.setHeader("content-type", "text/javascript; charset=utf-8");
      res.end(await fs.readFile(require.resolve("@webcomponents/scoped-custom-element-registry")));
      return;
    }
    if (pathname === "/") { res.setHeader("content-type", "text/html; charset=utf-8"); res.end(html); return; }
    if (!["/carrefour-account.js", "/notification-settings.js", "/recipe-editor.js", "/quantity-client.js", "/panel.js", "/purchases-panel.js", "/stock-client.js", "/dialog-controls.js", "/todo-client.js", "/catalog-panel.js", "/catalog-client.js", "/category-panel.js", "/icon-picker.js", "/list-settings-client.js", "/settings-panel.js", "/readers-client.js", "/readers-panel.js", "/product-matching.js", "/product-names.js", "/logs-panel.js", "/logo.png", "/mercadona.png", "/consum.jpg", "/lasirena.jpg", "/eroski.svg", "/dia.png"].includes(pathname)) { res.writeHead(404).end(); return; }
    res.setHeader("content-type", pathname.endsWith(".svg") ? "image/svg+xml" : pathname.endsWith(".png") ? "image/png" : pathname.endsWith(".jpg") ? "image/jpeg" : "text/javascript; charset=utf-8");
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
    assert.deepEqual(await page.locator("#completed .item.completed").first().evaluate(card =>
      [card,card.querySelector(".summary"),card.querySelector(".placeholder ha-icon")].map(node => getComputedStyle(node).color)
    ), ["rgb(255, 255, 255)","rgb(255, 255, 255)","rgb(255, 255, 255)"]);
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
    assert.equal(await page.evaluate(() => {
      const dialogs = [];
      const visit = root => {
        dialogs.push(...root.querySelectorAll("dialog"));
        root.querySelectorAll("*").forEach(element => { if (element.shadowRoot) visit(element.shadowRoot); });
      };
      visit(document);
      return dialogs.filter(dialog => dialog.querySelectorAll(".isl-dialog-close[aria-label='Cerrar ventana']").length === 1).length;
    }), 34);
    await page.getByRole("button", { name: "Seleccionar lista", exact: true }).click();
    const listDialog = page.getByRole("dialog", { name: "Seleccionar lista", exact: true });
    assert.equal(await listDialog.getByRole("button", { name: "Compra · Bring!", exact: true }).getAttribute("aria-pressed"), "true");
    assert.equal(await listDialog.locator(".list-option").count(), 3);
    await page.screenshot({ path: "test-results/list-selector-desktop.png", fullPage: true });
    const closeWindow = listDialog.getByRole("button", { name: "Cerrar ventana", exact: true });
    assert.ok(await closeWindow.evaluate(button => {
      const bounds = button.getBoundingClientRect(), popup = button.closest("dialog").getBoundingClientRect();
      return bounds.top >= popup.top && bounds.top < popup.top + 16 && bounds.right <= popup.right && bounds.right > popup.right - 16;
    }));
    await closeWindow.click();
    await listDialog.waitFor({ state: "hidden" });
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
    await page.getByText("Compras recientes (2)", { exact: true }).waitFor();
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
    assert.equal(await page.evaluate(() => window.listenerCount()), 6);

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
    assert.equal(await catalog.locator(".catalog-product-controls #new-product ha-icon").getAttribute("icon"), "mdi:plus-thick");
    assert.equal(await catalog.getByRole("button",{name:"Actualizar catálogo",exact:true}).count(),0);
    assert.equal(await catalog.locator("#new-product").textContent(), "");
    await catalog.getByRole("button", { name: "Nuevo producto", exact: true }).click();
    await catalog.getByLabel("Nombre del producto", { exact: true }).fill("Yogur natural");
    const categoryEditor = catalog.locator("#product-category-editor");
    await catalog.getByRole("button", { name:"Nueva categoría", exact:true }).click();
    await categoryEditor.getByLabel("Nombre de la categoría", { exact:true }).fill("Cancelar categoría");
    await categoryEditor.getByRole("button", { name:"Cerrar ventana", exact:true }).click();
    assert.equal(await catalog.getByLabel("Nombre del producto", { exact:true }).inputValue(), "Yogur natural");
    assert.equal(await catalog.locator("#product-category").inputValue(), "");
    assert.equal(await page.evaluate(() => window.catalogCategories.length), 0);
    await catalog.getByRole("button", { name:"Nueva categoría", exact:true }).click();
    await categoryEditor.getByLabel("Nombre de la categoría", { exact:true }).fill("Lácteos");
    await categoryEditor.getByLabel("Icono MDI", { exact:true }).fill("mdi:food");
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
    assert.equal(await catalog.getByLabel("Etiquetas", { exact:true }).count(),1);
    assert.equal(await catalog.getByLabel("Icono del producto", { exact:true }).count(),0);
    assert.equal(await catalog.getByLabel("Notas", { exact:true }).count(),0);
    await catalog.getByRole("button",{name:"Automatización",exact:true}).click();
    assert.equal(await catalog.getByLabel("Marca", { exact: true }).count(), 0);
    assert.equal(await catalog.getByLabel("Formato", { exact: true }).count(), 0);
    await captureProductCode(page,catalog,"barcode","0012345678905");
    await catalog.getByRole("button",{name:"Información adicional",exact:true}).click();
    assert.equal(await catalog.getByLabel("Precio orientativo", { exact: true }).count(),0);
    assert.equal(await catalog.getByLabel("Moneda", { exact: true }).count(),0);
    await catalog.getByRole("button",{name:"Características",exact:true}).click();
    assert.equal(await catalog.getByLabel("Nombre del producto",{exact:true}).inputValue(),"Yogur natural");
    assert.equal(await catalog.locator("#product-automation").isVisible(),false);
    await catalog.getByRole("button", { name: "Guardar producto", exact: true }).click();
    await catalog.getByRole("heading", { name: "Yogur natural", exact: true }).waitFor();
    assert.equal(await page.evaluate(() => window.catalogProducts[0].barcode), "0012345678905");
    // Existing manual prices remain readable after removing their edit controls.
    await page.evaluate(async()=>{
      const product=structuredClone(window.catalogProducts[0]);
      await window.testPanel._hass.callWS({type:'improved_shopping_list/catalog/save',product:{...product,price:2.59,currency:'EUR'}});
    });
    const productCard = catalog.locator("#catalog-grid article").first();
    const callsBeforeProductControls = await page.evaluate(()=>window.calls.length);
    assert.equal(await productCard.locator(".placeholder ha-icon").getAttribute("icon"), "mdi:food");
    assert.equal(await page.evaluate(() => window.catalogProducts[0].icon), "");
    assert.equal(await productCard.getByText("Lácteos", { exact: true }).count(), 0);
    assert.equal((await productCard.textContent()).includes("2,59"), false);
    assert.equal(await productCard.locator(".edit-product").evaluate(node => getComputedStyle(node).color), "rgb(255, 255, 255)");
    assert.equal(await productCard.locator(".edit-product").evaluate(node => getComputedStyle(node).backgroundColor), "rgb(249, 168, 37)");
    const assertCatalogBadge = async () => {
      if (!await catalog.locator("#catalog-grid").evaluate(node=>node.classList.contains("rows"))) {
        assert.equal(await productCard.locator(".edit-product").isVisible(),false);
        return;
      }
      assert.ok(await productCard.locator(".edit-product").evaluate(badge => {
        const bounds = badge.getBoundingClientRect();
        const icon = badge.querySelector("ha-icon").getBoundingClientRect();
        const style = getComputedStyle(badge);
        return bounds.width > 0 && Math.abs(bounds.width - bounds.height) < .1 &&
          icon.width > 0 && Math.abs(icon.width - icon.height) < .1 &&
          Math.abs((icon.left + icon.right) / 2 - (bounds.left + bounds.right) / 2) < .5 &&
          Math.abs((icon.top + icon.bottom) / 2 - (bounds.top + bounds.bottom) / 2) < .5 &&
          [style.borderTopWidth, style.borderRightWidth, style.borderBottomWidth, style.borderLeftWidth].every(width => width === "0px") &&
          style.borderRadius === "50%" && style.boxShadow !== "none" && style.appearance === "none";
      }));
    };
    for (const width of [1280, 390, 320]) {
      await page.setViewportSize({width,height:960});
      const sizes = [];
      for (const columns of width > 650 ? [1,3,6] : [1,2,4]) {
        await catalog.evaluate((node,columns) => {
          node.style.setProperty("--isl-columns", columns);
          node.style.setProperty("--isl-mobile-columns", columns);
        }, columns);
        await assertCatalogBadge();
        assert.ok(await productCard.evaluate(card => {
          const bounds=card.getBoundingClientRect(),name=card.querySelector(".title").getBoundingClientRect();
          return Math.abs(bounds.width-bounds.height)<1 && name.left>=bounds.left && name.right<=bounds.right && name.top>=bounds.top && name.bottom<=bounds.bottom &&
            [...card.querySelectorAll(".product-controls button")].filter(button=>button.getClientRects().length).every(button=>{const rect=button.getBoundingClientRect();return Math.abs(rect.width-rect.height)<.1&&rect.left>=bounds.left&&rect.right<=bounds.right&&rect.bottom<=bounds.bottom;});
        }),`Square catalog card with content inside at ${width}px / ${columns} columns`);
        sizes.push(await productCard.evaluate(card => ({
          font:parseFloat(getComputedStyle(card.querySelector(".title")).fontSize),
          icon:card.querySelector(".placeholder ha-icon").getBoundingClientRect().width,
          image:card.querySelector(".image").getBoundingClientRect().width,
        })));
      }
      assert.ok(sizes[0].font > sizes.at(-1).font);
      assert.ok(sizes[0].icon > sizes.at(-1).icon);
      assert.ok(sizes[0].image > sizes.at(-1).image);
    }
    await catalog.evaluate(node => { node.style.removeProperty("--isl-columns"); node.style.removeProperty("--isl-mobile-columns"); });
    await page.setViewportSize({width:1280,height:960});
    assert.equal(await productCard.locator(".product-controls button").first().textContent(), "");
    assert.equal(await productCard.locator(".product-controls button").count(), 1);
    assert.equal(await productCard.locator(".product-controls button").first().locator("ha-icon").getAttribute("icon"), "mdi:note-edit");
    const assertEditButton = async () => {
      assert.equal(await productCard.locator(".edit-product").evaluate(button => getComputedStyle(button).backgroundColor), "rgb(249, 168, 37)");
      assert.equal(await productCard.locator(".edit-product").evaluate(button => getComputedStyle(button).borderWidth), "0px");
    };
    await assertEditButton();
    assert.equal(await productCard.locator(".delete-product").count(),0);
    assert.equal(await productCard.locator('ha-icon[icon="mdi:cart-plus"]').count(),0);
    assert.ok(await productCard.evaluate(card => {
      const image = card.querySelector(".image").getBoundingClientRect();
      const title = card.querySelector(".title").getBoundingClientRect();
      const bounds = card.getBoundingClientRect();
      return Math.abs((image.left + image.right) / 2 - (bounds.left + bounds.right) / 2) < 2 && image.bottom <= title.top;
    }));
    // Existing tags load in the editor; edited tags support catalog and list searches.
    await page.evaluate(async()=>{
      const product=window.catalogProducts[0];
      await window.testPanel._hass.callWS({type:'improved_shopping_list/catalog/save',product:{...product,icon:'mdi:view-grid',tags:['Legacy'],notes:'Existing note'}});
    });
    await editCatalogProduct(catalog,"Editar Yogur natural");
    assert.equal(await catalog.locator("#product-main").isVisible(),true);
    assert.equal(await catalog.getByLabel("Etiquetas",{exact:true}).inputValue(),"Legacy");
    await catalog.getByLabel("Etiquetas",{exact:true}).fill("Danóne, Carrefour, Desayuno");
    await catalog.getByLabel("Nombre del producto", { exact: true }).fill("Yogur sin azúcar");
    assert.equal(await catalog.getByLabel("Icono del producto",{exact:true}).count(),0);
    await catalog.getByRole("button", { name: "Guardar producto", exact: true }).click();
    await catalog.getByRole("heading", { name: "Yogur sin azúcar", exact: true }).waitFor();
    await catalog.getByRole("button",{name:"Cambiar a vista de cuadrícula",exact:true}).click();
    assert.equal(await page.evaluate(() => window.catalogProducts.length), 1);
    assert.equal(await productCard.locator(".placeholder ha-icon").getAttribute("icon"), "mdi:view-grid");
    assert.deepEqual(await page.evaluate(()=>window.catalogProducts[0].tags),['Danóne','Carrefour','Desayuno']);
    assert.equal(await page.evaluate(()=>window.catalogProducts[0].notes),'Existing note');
    await catalog.getByLabel('Buscar productos',{exact:true}).fill('DANONE');
    assert.equal(await catalog.locator('#catalog-grid .product').count(),1);
    await catalog.getByLabel('Buscar productos',{exact:true}).fill('carrefour');
    assert.equal(await catalog.locator('#catalog-grid .product').count(),1);
    await catalog.getByLabel('Buscar productos',{exact:true}).fill('');
    await page.getByRole('button',{name:'Lista',exact:true}).click();
    await page.getByRole('combobox',{name:'Añadir producto',exact:true}).fill('danone');
    await page.getByRole('listbox',{name:'Productos del catálogo',exact:true}).getByRole('option').filter({hasText:'Yogur sin azúcar'}).waitFor();
    await page.getByRole('combobox',{name:'Añadir producto',exact:true}).fill('');
    await page.getByRole('button',{name:'Catálogo',exact:true}).click();
    await editCatalogProduct(catalog,'Editar Yogur sin azúcar');
    assert.equal(await catalog.getByLabel('Etiquetas',{exact:true}).inputValue(),'Danóne, Carrefour, Desayuno');
    await catalog.getByRole('dialog',{name:'Editar producto',exact:true}).getByRole('button',{name:'Cerrar ventana',exact:true}).click();
    await catalog.getByRole('button',{name:'Cambiar a vista de cuadrícula',exact:true}).click();
    await catalog.getByRole("button", { name: "Categorías", exact: true }).click();
    await categories.getByRole("button", { name: "Editar categoría Lácteos", exact: true }).click();
    await categories.getByLabel("Nombre de la categoría", { exact: true }).fill("Lácteos y frescos");
    await categories.getByRole("button", { name: "Guardar categoría", exact: true }).click();
    await categories.getByRole("heading", { name: "Lácteos y frescos", exact: true }).waitFor();
    await categories.evaluate(node=>{
      node._testOriginalCategories=structuredClone(node._categories);
      node.categories=Array.from({length:8},(_,index)=>({...node._categories[0],id:`layout-${index}`,name:index?`Categoría con un nombre largo para comprobar el espacio ${index}`:node._categories[0].name}));
    });
    for (const width of [1280,390,320]) {
      await page.setViewportSize({width,height:960});
      for (const columns of width > 650 ? [1,3,6] : [1,2,4]) {
        await categories.evaluate((node,columns) => {
          node.style.setProperty("--isl-columns",columns);
          node.style.setProperty("--isl-mobile-columns",columns);
        },columns);
        assert.equal(await categories.locator("#category-grid").evaluate(grid=>getComputedStyle(grid).gridTemplateColumns.split(" ").length),Math.min(columns,width>650?5:2));
        assert.ok(await categories.locator("#category-grid article").evaluateAll(cards=>cards.every(card=>{
          const bounds=card.getBoundingClientRect();
          return Math.abs(bounds.width-bounds.height)<1 && [...card.querySelectorAll(".category-icon,h2,p,.actions")].every(child=>{
            const rect=child.getBoundingClientRect();
            return rect.left>=bounds.left&&rect.right<=bounds.right&&rect.top>=bounds.top&&rect.bottom<=bounds.bottom;
          }) && [...card.querySelectorAll(".actions button")].every(button=>{const rect=button.getBoundingClientRect();return Math.abs(rect.width-rect.height)<.1;});
        })),`Square category cards/buttons with content inside at ${width}px / ${columns} requested columns`);
        assert.ok(await categories.locator("#category-grid article").first().evaluate(card => {
          const buttons = [...card.querySelectorAll(".actions button")];
          const [edit] = buttons.map(button => button.getBoundingClientRect());
          const bounds = card.getBoundingClientRect();
          return buttons.every(button => getComputedStyle(button).borderWidth === "0px" && button.textContent === "") &&
            getComputedStyle(buttons[0]).backgroundColor === "rgb(249, 168, 37)" &&
            buttons.length === 1 &&
            buttons.every(button => getComputedStyle(button).borderRadius === "50%" && getComputedStyle(button).color === "rgb(255, 255, 255)") &&
            edit.left >= bounds.left && edit.right <= bounds.right &&
            edit.top-bounds.top <= 14 && bounds.right-edit.right <= 14 && edit.width > 0;
        }), `Category actions fit in one row at ${width}px / ${columns} columns`);
      }
      await page.screenshot({path:`test-results/categories-square-${width}.png`,fullPage:true});
    }
    await categories.evaluate(node => { node.categories=node._testOriginalCategories;delete node._testOriginalCategories;node.style.removeProperty("--isl-columns"); node.style.removeProperty("--isl-mobile-columns"); });
    await page.setViewportSize({width:1280,height:960});
    await page.screenshot({ path: "test-results/categories-desktop.png", fullPage: true });
    await catalog.getByRole("button", { name: "Productos", exact: true }).click();
    assert.equal(await productCard.locator(".category-badge").count(), 0);
    await catalog.getByLabel("Buscar productos", { exact: true }).fill("inexistente");
    await catalog.getByText("No hay productos que coincidan con estos filtros.", { exact: true }).waitFor();
    await catalog.getByLabel("Buscar productos", { exact: true }).fill("");
    assert.equal(await catalog.locator("#category-filter").count(),0);
    assert.equal(await catalog.locator("#toggle-catalog-order ha-icon").getAttribute("icon"),"mdi:label");
    await catalog.getByRole("button",{name:"Agrupar por categorías",exact:true}).click();
    assert.deepEqual(await catalog.locator(".category-group-title").allTextContents(),["Lácteos y frescos"]);
    assert.equal(await catalog.locator("#toggle-catalog-order ha-icon").getAttribute("icon"),"mdi:sort-alphabetical-ascending");
    await catalog.getByRole("button",{name:"Ordenar alfabéticamente",exact:true}).click();
    assert.equal(await catalog.locator("#tag-filter").count(), 0);
    assert.equal(await catalog.locator("#view-products ha-icon").getAttribute("icon"), "mdi:view-grid");
    assert.equal(await catalog.locator("#view-categories ha-icon").getAttribute("icon"), "mdi:label");
    assert.equal(await page.evaluate(()=>window.calls.length),callsBeforeProductControls);
    await catalog.getByRole("button", { name: "Añadir Yogur sin azúcar a la lista", exact: true }).focus();
    await page.keyboard.press("Enter");
    await page.waitForFunction(()=>window.listData['todo.bring'].some(item=>item.summary==='Yogur sin azúcar'&&item.status==='needs_action'));
    assert.equal((await page.evaluate(() => window.calls)).at(-1).entity_id, "todo.bring");
    assert.equal((await page.evaluate(() => window.calls)).at(-1).item, "Yogur sin azúcar");
    assert.equal(await productCard.getAttribute("data-in-list"), "true");
    assert.equal(await productCard.locator(".add-product").isDisabled(),true);
    const callsAfterCatalogAdd=await page.evaluate(()=>window.calls.length);
    await productCard.locator(".add-product").evaluate(button=>button.click());
    assert.equal(await page.evaluate(()=>window.calls.length),callsAfterCatalogAdd);
    assert.equal(await catalog.getByRole("status").filter({hasText:"añadido"}).count(),0);
    await assertCatalogBadge();
    await assertEditButton();
    assert.equal(await productCard.evaluate(node => getComputedStyle(node).backgroundImage), "linear-gradient(rgb(238, 82, 79), rgb(181, 42, 39))");
    assert.ok((await productCard.evaluate(node => getComputedStyle(node).backgroundImage)).includes("linear-gradient"));
    await page.screenshot({ path: "test-results/catalog-desktop.png", fullPage: true });
    assert.equal(await productCard.locator(".edit-product").isVisible(),false);
    assert.equal(await catalog.locator("#toggle-catalog-layout").evaluate(node=>getComputedStyle(node).backgroundColor),
      await page.locator("#toggle-list-layout").evaluate(node=>getComputedStyle(node).backgroundColor));
    await catalog.getByRole("button",{name:"Cambiar a vista de filas",exact:true}).click();
    assert.equal(await catalog.locator("#toggle-catalog-layout ha-icon").getAttribute("icon"),"mdi:view-comfy");
    assert.equal(await productCard.locator(".edit-product").isVisible(),true);
    await assertCatalogBadge();
    assert.equal(await catalog.locator("#catalog-grid").evaluate(node=>getComputedStyle(node).gridTemplateColumns.split(" ").length),1);
    assert.equal(await productCard.locator(".row-category").count(),0);
    assert.match(await productCard.locator(".row-price").textContent(),/2,59/);
    for(const width of [1280,390]){
      await page.setViewportSize({width,height:844});
      assert.ok(await catalog.locator(".catalog-product-controls").evaluate(node=>{
        const add=node.querySelector("#new-product").getBoundingClientRect(),order=node.querySelector("#toggle-catalog-order").getBoundingClientRect(),
          toggle=node.querySelector("#toggle-catalog-layout").getBoundingClientRect();
        return add.right<=order.left&&order.right<=toggle.left&&Math.abs(add.top-order.top)<1&&Math.abs(order.top-toggle.top)<1&&order.height===add.height;
      }));
      assert.ok(await productCard.evaluate(node=>node.getBoundingClientRect().width>node.getBoundingClientRect().height&&node.scrollWidth<=node.clientWidth));
      assert.equal(await productCard.locator(".title").evaluate(node=>getComputedStyle(node).textAlign),"left");
      assert.ok(await productCard.evaluate(node=>{
        const media=node.querySelector(".product-media").getBoundingClientRect(),title=node.querySelector(".title").getBoundingClientRect();
        return title.left>media.right&&title.left-media.right<=13;
      }));
      assert.equal(await productCard.locator(".row-category").count(),0);
      await page.screenshot({path:`test-results/catalog-rows-${width}.png`,fullPage:true});
    }
    const rowEditCalls=await page.evaluate(()=>window.calls.length);
    await productCard.getByRole("button",{name:"Editar Yogur sin azúcar",exact:true}).click();
    await catalog.getByRole("dialog",{name:"Editar producto",exact:true}).waitFor();
    assert.equal(await page.evaluate(()=>window.calls.length),rowEditCalls);
    await catalog.locator("#product-form").locator("..").getByRole("button",{name:"Cerrar ventana",exact:true}).click();
    await catalog.getByRole("button",{name:"Cambiar a vista de cuadrícula",exact:true}).click();
    assert.equal(await catalog.locator("#toggle-catalog-layout ha-icon").getAttribute("icon"),"mdi:view-sequential");
    assert.equal(await productCard.locator(".edit-product").isVisible(),false);
    await page.setViewportSize({width:1280,height:844});
    await page.getByRole("button", { name: "Lista", exact: true }).click();
    await page.locator("#pending").getByText("Yogur sin azúcar", { exact: true }).waitFor();
    const yogurtListCard = page.locator("#pending > li").filter({ hasText: "Yogur sin azúcar" });
    assert.equal(await yogurtListCard.locator(".placeholder ha-icon").getAttribute("icon"), "mdi:view-grid");
    assert.equal(await yogurtListCard.locator(".category-badge").getAttribute("title"), "Lácteos y frescos");
    assert.equal(await yogurtListCard.locator(".category-badge").evaluate(node => getComputedStyle(node).color), "rgb(255, 255, 255)");
    assert.equal(await yogurtListCard.locator(".subtitle").count(), 0);
    assert.equal((await yogurtListCard.textContent()).includes("2,59"), false);
    assert.match(await page.locator("#pending-total").textContent(),/≈ 2,59/);
    await page.screenshot({ path: "test-results/list-grid-desktop.png", fullPage: true });
    assert.equal(await page.locator("#toggle-list-layout ha-icon").getAttribute("icon"),"mdi:view-sequential");
    await page.route("https://almeria.online/**",route=>route.fulfill({contentType:"image/svg+xml",body:'<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32"><rect width="32" height="32" fill="red"/></svg>'}));
    await page.evaluate(()=>{window.nutriFixture={"0012345678905":{grade:"b"}};});
    await page.getByRole("button",{name:"Cambiar a vista de filas",exact:true}).click();
    await yogurtListCard.locator(".row-nutriscore").filter({hasText:"B"}).waitFor();
    assert.equal(await yogurtListCard.locator(".row-nutriscore").getAttribute("aria-label"),"Nutri-Score B");
    assert.equal(await yogurtListCard.locator(".row-nutriscore").evaluate(node=>getComputedStyle(node).backgroundColor),"rgb(133, 187, 47)");
    for(const width of [1280,390,320]){
      await page.setViewportSize({width,height:960});
      const badges=await yogurtListCard.evaluate(node=>[...node.closest('li').querySelectorAll('.row-category,.row-price,.row-nutriscore,.row-quantity')].map(badge=>({kind:badge.className,height:badge.getBoundingClientRect().height,radius:getComputedStyle(badge).borderRadius,background:getComputedStyle(badge).backgroundColor})));
      assert.ok(badges.length>=3);
      assert.equal(new Set(badges.map(badge=>badge.height)).size,1);
      assert.equal(new Set(badges.map(badge=>badge.radius)).size,1);

    }
    await page.setViewportSize({width:1280,height:960});

    assert.equal(await page.locator("#pending > li").filter({hasText:"Cacao"}).locator(".row-nutriscore").count(),0);
    assert.equal(await page.locator("#toggle-list-layout ha-icon").getAttribute("icon"),"mdi:view-comfy");
    assert.equal(await page.locator("#pending").evaluate(node=>getComputedStyle(node).gridTemplateColumns.split(" ").length),1);
    assert.equal(await yogurtListCard.locator(".row-category").textContent(),"Lácteos y frescos");
    assert.match(await yogurtListCard.locator(".row-price").textContent(),/2,59/);
    await page.evaluate(()=>{
      window.listSettings.favorite_store="alcampo";window.emitSettings();
      window.storePriceFixture=[
        {catalog_product_id:window.catalogProducts[0].id,store:"alcampo",price:"2.15",currency:"EUR",checked_at:1},
        {catalog_product_id:window.catalogProducts[0].id,store:"carrefour",price:"2.25",currency:"EUR",checked_at:2}];
      for(const callback of window.storeProgressListeners)callback({running:false});
    });
    await yogurtListCard.locator(".row-price").filter({hasText:"2,15"}).waitFor();
    assert.equal(await yogurtListCard.locator(".row-price img").getAttribute("alt"),"Alcampo");
    assert.equal(await yogurtListCard.locator(".row-price ha-icon").count(),0);
    assert.ok(await yogurtListCard.locator(".row-price img").evaluate(node=>{
      const style=getComputedStyle(node);return style.backgroundColor==="rgb(255, 255, 255)"&&style.borderRadius==="50%"&&style.width===style.height;
    }));
    const nutritionCallsAfterLoad=await page.evaluate(()=>window.nutriCalls.length);
    assert.match(await page.locator("#pending-total").textContent(),/≈ 2,15/);
    for(const width of [1280,390]){
      await page.setViewportSize({width,height:844});
      const bounds=await yogurtListCard.locator("button.item").evaluate(node=>{
        const card=node.getBoundingClientRect(),media=node.querySelector(".product-media").getBoundingClientRect(),
          text=node.querySelector(".item-text").getBoundingClientRect(),meta=node.querySelector(".row-meta").getBoundingClientRect();
        return {wide:card.width>card.height,ordered:media.right<=text.left&&text.right<=meta.left,overflow:node.scrollWidth>node.clientWidth};
      });
      assert.deepEqual(bounds,{wide:true,ordered:true,overflow:false});
      assert.equal(await yogurtListCard.locator(".item-text").evaluate(node=>getComputedStyle(node).textAlign),"left");
      assert.ok(await page.locator("#pending .item-text").evaluateAll(nodes=>{
        const left=nodes[0].getBoundingClientRect().left;return nodes.every(node=>Math.abs(node.getBoundingClientRect().left-left)<1);
      }));
      assert.equal(await yogurtListCard.locator(".row-category span").isVisible(),width>540);
      assert.equal(await yogurtListCard.locator(".row-category").getAttribute("aria-label"),"Categoría: Lácteos y frescos");
    assert.ok(await page.locator("#items-card .list-totals").evaluate(node=>{
        const count=node.querySelector("#pending-count").getBoundingClientRect(),total=node.querySelector("#pending-total").getBoundingClientRect();
        return count.right<=total.left&&Math.abs(count.top-total.top)<1&&node.scrollWidth<=node.clientWidth;
      }));
      await page.screenshot({path:`test-results/list-rows-${width}.png`,fullPage:true});
    }
    await page.getByRole("button",{name:"Marcar como comprado: Yogur sin azúcar",exact:true}).click();
    await page.locator("#completed-summary").click();
    await page.locator("#completed .row-price").filter({hasText:"2,15"}).waitFor();
    assert.equal(await page.locator("#completed .row-nutriscore").textContent(),"B");
    assert.equal(await page.evaluate(()=>window.nutriCalls.length),nutritionCallsAfterLoad);
    assert.match(await page.locator("#pending-total").textContent(),/≈ 0,00/);
    await page.getByRole("button",{name:"Volver a poner por comprar: Yogur sin azúcar",exact:true}).click();
    await page.getByRole("button",{name:"Cambiar a vista de cuadrícula",exact:true}).click();
    await page.locator("#completed-details").evaluate(node=>{node.open=false;});
    assert.equal(await page.locator("#pending").evaluate(node=>node.classList.contains("rows")),false);
    assert.match(await page.locator("#pending-total").textContent(),/≈ 2,15/);
    await page.evaluate(()=>{window.storePriceFixture=undefined;window.listSettings.favorite_store="";window.emitSettings();});
    await page.setViewportSize({width:1280,height:844});
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
    await catalog.getByRole("button", { name: "Categorías", exact: true }).click();
    await catalog.getByRole("button", { name: "Nueva categoría", exact: true }).click();
    assert.equal(await categories.locator('#delete-category').isVisible(),false);
    await categories.getByLabel("Nombre de la categoría", { exact: true }).fill("Temporal");
    await categories.getByRole("button", { name: "Guardar categoría", exact: true }).click();
    await categories.getByRole("heading", { name: "Temporal", exact: true }).waitFor();
    await catalog.getByRole("button", { name: "Productos", exact: true }).click();
    await editCatalogProduct(catalog,"Editar Yogur sin azúcar");
    await catalog.getByLabel("Categoría", { exact: true }).last().selectOption("Temporal");
    await catalog.getByRole("button", { name: "Guardar producto", exact: true }).click();
    await catalog.getByRole("button", { name: "Categorías", exact: true }).click();
    assert.equal(await categories.getByRole("button", { name: "Eliminar categoría Temporal", exact: true }).count(),0);
    await categories.getByRole("button", { name: "Editar categoría Temporal", exact: true }).click();
    const categoryDeleteEditor = categories.locator('#category-dialog');
    assert.equal(await categoryDeleteEditor.getByRole("button",{name:"Cancelar",exact:true}).count(),0);
    assert.ok(await categoryDeleteEditor.locator(".category-form-actions").evaluate(node=>{
      const remove=node.querySelector("#delete-category").getBoundingClientRect(),save=node.querySelector("#save-category").getBoundingClientRect();
      return remove.right<=save.left&&Math.abs(remove.top-save.top)<1;
    }));
    await categoryDeleteEditor.getByRole("button", { name: "Eliminar categoría", exact: true }).click();
    await categories.locator('#delete-category-dialog').getByRole('button',{name:'Cancelar',exact:true}).click();
    assert.equal(await categoryDeleteEditor.isVisible(),true);
    await categoryDeleteEditor.getByRole("button", { name: "Eliminar categoría", exact: true }).click();
    await categories.locator('#delete-category-dialog').getByRole("button", { name: "Eliminar categoría", exact: true }).click();
    await categoryDeleteEditor.waitFor({state:'hidden'});
    assert.equal(await categories.locator("#category-notice").count(),0);
    assert.equal(await page.evaluate(() => window.catalogProducts.length), 1);
    assert.equal(await page.evaluate(() => window.catalogProducts[0].category), "");
    await catalog.getByRole("button", { name: "Productos", exact: true }).click();
    assert.equal(await productCard.locator(".edit-product").evaluate(button => getComputedStyle(button).backgroundColor), "rgb(249, 168, 37)");
    await editCatalogProduct(catalog,"Editar Yogur sin azúcar");
    await catalog.getByLabel("Categoría", { exact: true }).last().selectOption("Lácteos y frescos");
    await catalog.getByLabel("URL Imagen/Icono", { exact: true }).fill("/logo.png");
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
    await editCatalogProduct(catalog,"Editar Yogur sin azúcar");
    await catalog.getByLabel("Nombre del producto", { exact: true }).fill("Conservar formulario");
    await page.evaluate(() => { window.failCatalog = true; });
    await catalog.getByRole("button", { name: "Guardar producto", exact: true }).click();
    await catalog.locator("#product-error").filter({ hasText: "No se ha podido guardar" }).waitFor();
    assert.equal(await catalog.getByLabel("Nombre del producto", { exact: true }).inputValue(), "Conservar formulario");
    await catalog.locator("#product-form").locator("..").getByRole("button", { name: "Cerrar ventana", exact: true }).click();

    // Actual narrow layout, sidebar access and horizontal overflow.
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(url);
    await page.locator("#pending").getByText("Cacao", { exact: true }).waitFor();
    for (const width of [320, 390, 650]) {
      await page.setViewportSize({ width, height:844 });
      assert.equal(await page.locator(".brand-copy").isVisible(), false);
      assert.equal(await page.locator(".brand-logo").isVisible(), true);
      for (const view of ["catalog", "stock", "settings", "shopping"]) {
        await page.locator(`#nav-${view}`).click();
        assert.equal(await page.locator(".section-nav .nav-label:visible").count(), 1);
        assert.equal(await page.locator(`#nav-${view} .nav-label`).isVisible(), true);
        if (view === "catalog") {
          for (const tab of ["products","categories","recipes","recommendations","suggestions"]) {
            await catalog.locator(`#view-${tab}`).click();
            assert.equal(await catalog.locator(".catalog-tabs .tab-label:visible").count(),1);
            assert.equal(await catalog.locator(`#view-${tab} .tab-label`).isVisible(),true);
            assert.equal(await catalog.locator(".catalog-tabs ha-icon:visible").count(),5);
            const tabLayout = await catalog.locator(".catalog-toolbar").evaluate(toolbar=>{
              const tabs=toolbar.querySelector(".catalog-tabs");
              const bounds=toolbar.getBoundingClientRect();
              return {scroll:tabs.scrollWidth,client:tabs.clientWidth,left:bounds.left,right:bounds.right,buttons:[...toolbar.querySelectorAll("button")].filter(button=>button.getClientRects().length).map(button=>{const rect=button.getBoundingClientRect();return {id:button.id,left:rect.left,right:rect.right};})};
            });
            assert.ok(tabLayout.scroll<=tabLayout.client+1 && tabLayout.buttons.every(button=>button.left>=tabLayout.left-1 && button.right<=tabLayout.right+1),`Compact catalog tabs fit at ${width}px with ${tab} active: ${JSON.stringify(tabLayout)}`);
          }
          await catalog.locator("#view-products").click();
        }
        assert.equal(await page.locator("header").evaluate(header => {
          const buttons = [...header.querySelectorAll(".section-nav button")];
          const logo = header.querySelector(".brand-logo").getBoundingClientRect();
          return buttons.every(button => {
            const rect = button.getBoundingClientRect();
            return rect.right <= innerWidth && rect.top < logo.bottom && rect.bottom > logo.top;
          }) && header.scrollWidth <= header.clientWidth;
        }), true);
      }
    }
    await page.setViewportSize({ width:1280, height:960 });
    assert.equal(await page.locator(".brand-copy").isVisible(), true);
    assert.equal(await page.locator(".section-nav .nav-label:visible").count(), 4);
    await page.getByRole("button",{name:"Catálogo",exact:true}).click();
    assert.equal(await catalog.locator(".catalog-tabs .tab-label:visible").count(),5);
    await page.getByRole("button",{name:"Lista",exact:true}).click();
    await page.setViewportSize({ width:390, height:844 });
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
    assert.equal(await page.locator(".version").isVisible(), false);
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
    await suggestionCatalog.getByRole("button", { name:"Nueva categoría", exact:true }).click();
    await suggestionCategories.getByLabel("Nombre de la categoría", { exact:true }).fill("Despensa");
    await suggestionCategories.getByRole("button", { name:"Guardar categoría", exact:true }).click();
    await suggestionCategories.getByRole("heading", { name:"Despensa", exact:true }).waitFor();
    await suggestionCatalog.getByRole("button", { name: "Nuevos", exact: true }).click();
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
    await suggestions.getByRole("button",{name:"Descartar: Leche entera",exact:true}).waitFor({state:"hidden"});
    assert.equal(await suggestionCatalog.locator("#catalog-status").isVisible(),false);
    await suggestions.getByRole("button", { name: "Añadir al catálogo: Cacao", exact: true }).click();
    const suggestionDialog = suggestionCatalog.getByRole("dialog", { name:"Nuevo producto", exact:true });
    await suggestionDialog.waitFor();
    assert.equal(await suggestionDialog.getByLabel("Nombre del producto", { exact:true }).inputValue(), "Cacao");
    assert.equal(await suggestionPage.evaluate(() => window.catalogProducts.length), 0);
    await suggestionDialog.getByRole("button", { name:"Cerrar ventana", exact:true }).click();
    assert.deepEqual(await suggestions.locator("h2").allTextContents(), ["Arroz", "Cacao"]);
    await suggestions.getByRole("button", { name:"Añadir al catálogo: Cacao", exact:true }).click();
    await suggestionDialog.getByLabel("Categoría", { exact:true }).selectOption("Despensa");
    assert.equal(await suggestionDialog.getByLabel("Etiquetas", { exact:true }).count(),1);
    await suggestionPage.evaluate(() => { window.failCatalog=true; });
    await suggestionDialog.getByRole("button", { name:"Guardar producto", exact:true }).click();
    await suggestionDialog.getByRole("alert").filter({ hasText:"No se ha podido guardar" }).waitFor();
    assert.equal(await suggestionDialog.getByLabel("Categoría", { exact:true }).inputValue(), "Despensa");
    assert.equal(await suggestionPage.evaluate(() => window.catalogProducts.length), 0);
    await suggestionPage.evaluate(() => { window.failCatalog=false; });
    await suggestionDialog.getByRole("button", { name:"Guardar producto", exact:true }).click();
    await suggestionDialog.waitFor({state:"hidden"});
    assert.equal(await suggestionCatalog.locator("#catalog-status").isVisible(),false);
    assert.equal(await suggestionPage.evaluate(() => window.catalogProducts[0].category), "Despensa");
    assert.equal(await suggestionPage.evaluate(() => 'brand' in window.catalogProducts[0] || 'format' in window.catalogProducts[0]), false);
    assert.deepEqual(await suggestions.locator("h2").allTextContents(), ["Arroz"]);
    assert.equal(await suggestionPage.evaluate(() => window.calls.length), 0);
    assert.equal(await suggestionPage.evaluate(() => window.catalogProducts.length), 1);
    await suggestionCatalog.getByRole("button", { name: "Productos", exact: true }).click();
    await suggestionCatalog.getByRole("heading", { name: "Cacao", exact: true }).waitFor();
    assert.equal(await suggestionCatalog.locator("#catalog-grid article").getAttribute("data-in-list"), "true");
    await suggestionPage.reload();
    await suggestionPage.getByRole("button", { name: "Catálogo", exact: true }).click();
    await suggestionCatalog.getByRole("button", { name: "Nuevos", exact: true }).click();
    assert.deepEqual(await suggestions.locator("h2").allTextContents(), ["Arroz"]);
    assert.equal(await suggestionCatalog.locator("#list-suggestions-group").evaluate(node => node.open), false);
    await suggestionCatalog.locator("#list-suggestions-summary").click();
    await suggestions.getByRole("button", { name: "Añadir al catálogo: Arroz", exact: true }).click();
    assert.equal(await suggestionDialog.getByLabel("Nombre del producto", { exact:true }).inputValue(), "Arroz");
    assert.equal(await suggestionDialog.getByLabel("Marca", { exact:true }).count(), 0);
    await suggestionDialog.getByRole("button", { name:"Guardar producto", exact:true }).click();
    await suggestions.locator("h2").waitFor({state:"detached"});
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
    await predictions.getByRole("option", { name: "Café molido", exact: true }).waitFor();
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
    assert.equal(await predictions.getByRole("option").count(), 0);
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
    const totalContext = await browser.newContext({viewport:{width:390,height:844}});
    await totalContext.addInitScript(()=>{
      localStorage.setItem("catalog-fixture",JSON.stringify([
        {id:"total-cacao",name:"Cacao",price:"0.10"},
        {id:"total-milk",name:"Leche entera",price:"0.20"},
        {id:"total-rice",name:"Arroz",price:"99.99"}
      ].map(product=>({...product,currency:"EUR",category:"",tags:[],barcode:"",barcodes:[],nfc_tags:[],image_url:"",icon:"",revision:1}))));
    });
    const totalPage=await totalContext.newPage();
    totalPage.on("pageerror",error=>errors.push(error.message));
    await totalPage.goto(url);
    await totalPage.locator("#pending-total").filter({hasText:"0,30"}).waitFor();
    await totalPage.locator("#pending-total").click();
    assert.match(await totalPage.locator("#receipt .receipt-total").textContent(),/0,30/);
    assert.equal(await totalPage.locator("#pending").isVisible(),false);
    await totalPage.locator("#pending-count").click();
    await totalPage.getByRole("button",{name:"Marcar como comprado: Cacao",exact:true}).click();
    await totalPage.locator("#pending-total").filter({hasText:"0,20"}).waitFor();
    await selectList(totalPage,"todo.local");
    await totalPage.locator("#pending-total").filter({hasText:"0,00"}).waitFor();
    assert.equal(await totalPage.evaluate(()=>window.calls.some(call=>/refresh_prices|settings\/store_products/.test(call.type??""))),false);
    await totalContext.close();
    const receiptContext=await browser.newContext({viewport:{width:390,height:844}});
    for (const domain of ['https://images.seeklogo.com/**','https://almeria.online/**']) await receiptContext.route(domain,route=>route.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32"><circle cx="16" cy="16" r="14" fill="green"/></svg>'}));
    await receiptContext.addInitScript(()=>{
      localStorage.setItem('settings-fixture',JSON.stringify({entities:['todo.bring','todo.local'],primary_entity:'todo.bring',favorite_store:'carrefour',stores:{alcampo:{enabled:true},carrefour:{enabled:true},mercadona:{enabled:false},dia:{enabled:true}}}));
      localStorage.setItem('catalog-fixture',JSON.stringify([
        {id:'ticket-cacao',name:'Cacao',price:99},{id:'ticket-milk',name:'Leche entera',price:99},{id:'ticket-rice',name:'Arroz',price:99}
      ].map(product=>({...product,revision:1,currency:'EUR',category:'',tags:[],barcode:'',barcodes:[],nfc_tags:[],image_url:'',icon:''}))));
      window.storePriceFixture=[
        {catalog_product_id:'ticket-cacao',store:'alcampo',price:'2.10',currency:'EUR',checked_at:1},
        {catalog_product_id:'ticket-cacao',store:'alcampo',price:'1.10',currency:'EUR',checked_at:2},
        {catalog_product_id:'ticket-milk',store:'alcampo',price:'0.20',currency:'EUR',checked_at:2},
        {catalog_product_id:'ticket-cacao',store:'carrefour',price:'0.50',currency:'EUR',checked_at:2},
        {catalog_product_id:'ticket-milk',store:'mercadona',price:'0.01',currency:'EUR',checked_at:2},
        {catalog_product_id:'ticket-rice',store:'dia',price:'0.01',currency:'EUR',checked_at:2}
      ];
    });
    const receiptPage=await receiptContext.newPage();
    receiptPage.on('pageerror',error=>errors.push(error.message));
    await receiptPage.goto(url);
    await receiptPage.locator('#pending-total').filter({hasText:'1,30'}).waitFor();
    assert.deepEqual(await receiptPage.locator('#pending-total').evaluate(node=>[getComputedStyle(node).backgroundColor,getComputedStyle(node).color]),['rgb(255, 255, 255)','rgb(0, 0, 0)']);
    assert.equal(await receiptPage.locator('#pending-total img').getAttribute('alt'),'Alcampo');
    await receiptPage.locator('#pending-total').press('Enter');
    const receipt=receiptPage.locator('#receipt');
    await receipt.waitFor();
    assert.equal(await receiptPage.locator('#pending-count').evaluate(node=>getComputedStyle(node).backgroundColor),'rgb(238, 82, 79)');
    assert.deepEqual(await receipt.locator('.receipt-stores button').evaluateAll(nodes=>nodes.map(node=>node.dataset.receiptStore)),['alcampo','carrefour']);
    assert.match(await receipt.locator('[data-receipt-store="alcampo"]').textContent(),/1,30\s*€ \(2\/2\)/);
    assert.equal(await receipt.locator('.receipt-hint').count(),0);
    assert.deepEqual(await receipt.locator('.receipt-known .receipt-name').allTextContents(),['Cacao','Leche entera']);
    assert.match(await receipt.locator('.receipt-total').textContent(),/1,30/);
    assert.equal(await receiptPage.locator('#completed-details').isVisible(),false);
    await receipt.locator('[data-receipt-store="carrefour"]').click();
    assert.match(await receipt.locator('.receipt-total').textContent(),/0,50/);
    assert.deepEqual(await receipt.locator('.receipt-missing .receipt-name').allTextContents(),['Leche entera']);
    assert.equal(await receipt.locator('.receipt-missing').isVisible(),false);
    await receipt.locator('.receipt-unknown summary').click();
    assert.equal(await receipt.locator('.receipt-missing').isVisible(),true);
    await receiptPage.evaluate(()=>window.testPanel._renderData());
    assert.equal(await receipt.locator('.receipt-missing').isVisible(),true);
    assert.equal(await receiptPage.locator('#pending-total img').getAttribute('alt'),'Carrefour');
    for(const width of [1280,390,320]){
      await receiptPage.setViewportSize({width,height:844});
      assert.ok(await receipt.evaluate(node=>node.scrollWidth<=node.clientWidth));
      assert.ok(await receipt.locator('.receipt-row').evaluateAll(nodes=>nodes.every(node=>node.querySelector('.receipt-name').getBoundingClientRect().right<=node.querySelector('.receipt-price').getBoundingClientRect().left)));
      await receiptPage.screenshot({path:`test-results/list-receipt-${width}.png`,fullPage:true});
    }
    await receiptPage.locator('#pending-count').click();
    assert.equal(await receipt.isVisible(),false);
    await receiptPage.getByRole('button',{name:'Marcar como comprado: Cacao',exact:true}).click();
    await receiptPage.locator('#pending-total').filter({hasText:'0,20'}).waitFor();
    assert.equal(await receiptPage.locator('#pending-total img').getAttribute('alt'),'Alcampo');
    await receiptPage.locator('#pending-total').click();
    assert.deepEqual(await receipt.locator('.receipt-known .receipt-name').allTextContents(),['Leche entera']);
    await receiptPage.evaluate(()=>{window.listSettings.stores.alcampo.enabled=false;window.emitSettings();});
    await receipt.locator('.receipt-stores button').waitFor({state:'detached'});
    await selectList(receiptPage,'todo.local');
    await receipt.locator('.receipt-unknown summary').click();
    await receipt.locator('.receipt-missing').getByText('Detergente',{exact:true}).waitFor();
    assert.match(await receipt.locator('.receipt-total').textContent(),/0,00/);
    // Five eligible shops: coverage wins over a lower subtotal, and only four fit the selector.
    await receiptPage.evaluate(()=>{
      const panel=window.testPanel;
      const stores=['carrefour','alcampo','consum','eroski','lasirena'];
      panel._settings.stores=Object.fromEntries(stores.map(store=>[store,{enabled:true}]));
      panel._rowPrices=stores.flatMap((store,index)=>[
        {catalog_product_id:'ticket-cacao',store,price:10-index,currency:'EUR',checked_at:2},
        ...(index===0?[{catalog_product_id:'ticket-milk',store,price:20,currency:'EUR',checked_at:2}]:[])
      ]);
      const items=[{summary:'Leche entera'},{summary:'Cacao'}];
      const receipts=panel._storeReceipts(items);
      panel._renderReceipt(items,receipts,receipts[0]);
    });
    assert.deepEqual(await receipt.locator('.receipt-stores button').evaluateAll(nodes=>nodes.map(node=>node.dataset.receiptStore)),['carrefour','lasirena','eroski','consum']);
    for(const width of [1280,390,320]){
      await receiptPage.setViewportSize({width,height:844});
      assert.ok(await receipt.evaluate(node=>node.scrollWidth<=node.clientWidth));
      assert.equal(await receipt.locator('.receipt-stores button').evaluateAll(nodes=>new Set(nodes.map(node=>node.getBoundingClientRect().top)).size),1);
      assert.ok(await receipt.locator('.receipt-stores button').evaluateAll(nodes=>nodes.every(node=>node.scrollWidth<=node.clientWidth)));
      await receiptPage.screenshot({path:`test-results/list-receipt-four-stores-${width}.png`,fullPage:true});
    }
    assert.equal(await receiptPage.evaluate(()=>window.calls.some(call=>/refresh_prices|refresh_all_prices|settings\/store_products/.test(call.type??''))),false);
    await receiptContext.close();
    const resumeContext=await browser.newContext({viewport:{width:390,height:844}});
    await resumeContext.addInitScript(()=>{
      localStorage.setItem('settings-fixture',JSON.stringify({entities:['todo.bring'],primary_entity:'todo.bring',stores:{mercadona:{enabled:true,warehouse:'mad3'}}}));
      localStorage.setItem('price-progress-fixture',JSON.stringify({running:true,total:6,processed:1,batch_id:'background-batch',finished_at:null,errors:{},estimated_seconds:1500}));
    });
    const resumePage=await resumeContext.newPage();
    resumePage.on('pageerror',error=>errors.push(error.message));
    await resumePage.goto(url);
    const resumeSettings=resumePage.locator('isl-settings');
    const resumeDialog=resumeSettings.getByRole('dialog',{name:'Actualización de precios',exact:true});
    for(let reload=0;reload<2;reload++){
      if(reload)await resumePage.reload();
      await resumePage.getByRole('button',{name:'Ajustes',exact:true}).click();
      await resumeSettings.getByRole('button',{name:'Tiendas',exact:true}).click();
      await resumeSettings.locator('#refresh-all-prices').click();
      await resumeDialog.waitFor();
      assert.equal(await resumeDialog.locator('#prices-progress-percentage').textContent(),'17 %');
      assert.match(await resumeDialog.locator('#prices-progress-status').textContent(),/1 de 6 referencias/);
      assert.equal(await resumePage.evaluate(()=>window.calls.filter(call=>call.type==='improved_shopping_list/settings/refresh_all_prices').length),0);
      await resumeDialog.getByRole('button',{name:'Cerrar',exact:true}).click();
    }
    // A reconnect can leave the local cache empty before the initial subscription arrives.
    await resumePage.evaluate(()=>{
      window.testPanel.shadowRoot.querySelector('isl-settings')._latestPriceProgress=null;
      window.manualResumeProgress=JSON.parse(localStorage.getItem('price-progress-fixture'));
    });
    await resumeSettings.locator('#refresh-all-prices').click();
    await resumeDialog.locator('#prices-progress-percentage').filter({hasText:'17 %'}).waitFor();
    assert.equal(await resumePage.evaluate(()=>window.testPanel.shadowRoot.querySelector('isl-settings')._latestPriceProgress.batch_id),'background-batch');
    await resumeDialog.getByRole('button',{name:'Cerrar',exact:true}).click();
    await resumePage.evaluate(()=>{window.delayManualRefresh=true;window.testPanel.shadowRoot.querySelector('isl-settings')._latestPriceProgress=null;});
    await resumeSettings.locator('#refresh-all-prices').click();
    await resumePage.waitForFunction(()=>typeof window.releaseManualRefresh==='function');
    await resumeDialog.getByRole('button',{name:'Cerrar',exact:true}).click();
    await resumeSettings.locator('#refresh-all-prices').click();
    assert.equal(await resumeDialog.isVisible(),true);
    assert.equal(await resumePage.evaluate(()=>window.calls.filter(call=>call.type==='improved_shopping_list/settings/refresh_all_prices').length),2);
    await resumePage.evaluate(()=>{window.delayManualRefresh=false;window.releaseManualRefresh();});
    await resumeDialog.locator('#prices-progress-percentage').filter({hasText:'17 %'}).waitFor();
    await resumeContext.close();
    const settingsContext = await browser.newContext({ viewport: { width: 1280, height: 960 } });
    await settingsContext.route("https://logos-world.net/**",route=>route.fulfill({contentType:"image/svg+xml",body:'<svg xmlns="http://www.w3.org/2000/svg" width="56" height="56"><rect width="56" height="56" fill="green"/></svg>'}));
    await settingsContext.route("https://images.seeklogo.com/**",route=>route.fulfill({contentType:"image/svg+xml",body:'<svg xmlns="http://www.w3.org/2000/svg" width="56" height="56"><rect width="56" height="56" fill="blue"/></svg>'}));
    const settingsPage = await settingsContext.newPage();
    settingsPage.on("pageerror", error => errors.push(error.message));
    await settingsPage.goto(url);
    await settingsPage.locator("#pending").getByText("Cacao", { exact: true }).waitFor();
    assert.equal(await settingsPage.locator("#nav-settings ha-icon").getAttribute("icon"), "mdi:cog");
    const settingsView = settingsPage.locator("isl-settings");
    await settingsPage.getByRole("button", { name: "Ajustes", exact: true }).click();
    await settingsView.getByRole("button",{name:"Tiendas",exact:true}).click();
    assert.equal(await settingsView.locator("#settings-view-stores ha-icon").getAttribute("icon"), "mdi:store");
    assert.deepEqual(await settingsView.locator(".stores-grid .store-name h3").allTextContents(),["Alcampo","Carrefour","Consum","DIA","Eroski","La Sirena","Mercadona"]);
    // Store settings open without cached-product listings or count badges.
    for (const store of ['Mercadona','Carrefour','Alcampo','Consum','La Sirena','Eroski','DIA']) {
      const gear=settingsView.getByRole('button',{name:`Ajustes de ${store}`,exact:true});
      assert.equal(await gear.locator('ha-icon').getAttribute('icon'),'mdi:cog');
      assert.equal(await gear.locator('.store-associated-count').count(),0);
      await gear.click();const dialog=settingsView.getByRole('dialog',{name:store,exact:true});
      assert.equal(await dialog.locator('.store-products:visible,.store-cache-footer:visible').count(),0);
      await dialog.getByRole('button',{name:'Cerrar ventana',exact:true}).click();
    }
    assert.equal(await settingsView.getByRole('button',{name:'Código postal de las tiendas',exact:true}).count(),0);
    for(const [store,name] of [['consum','Consum'],['lasirena','La Sirena'],['eroski','Eroski'],['dia','DIA']]){
      await settingsView.getByLabel(`Habilitar ${name}`,{exact:true}).check();
      await settingsPage.waitForFunction(store=>window.listSettings.stores?.[store]?.enabled,store);
      assert.equal(await settingsPage.evaluate(store=>window.listSettings.stores[store].postal_code,store),{consum:'46409',lasirena:'28024',eroski:'48001',dia:'28024'}[store]);
      await settingsView.getByLabel(`Habilitar ${name}`,{exact:true}).uncheck();
    }
    await settingsView.getByLabel('Habilitar Mercadona').check();
    await settingsPage.waitForFunction(()=>window.listSettings.stores.mercadona.enabled);
    const storeRow=settingsView.locator('#mercadona-row');
    assert.equal(await storeRow.evaluate(node=>getComputedStyle(node).opacity),'1');
    assert.match(await storeRow.locator('img').getAttribute('src'),/\/mercadona\.png$/);
    assert.equal(await settingsView.locator('.stores-grid').evaluate(node=>getComputedStyle(node).gridTemplateColumns.split(' ').length),2);
    await settingsView.getByLabel('Habilitar Carrefour',{exact:true}).check();
    await settingsView.getByRole('button',{name:'Marcar Carrefour como favorita',exact:true}).click();
    await settingsView.locator('#favorite-carrefour[aria-pressed="true"]').waitFor();
    assert.equal(await settingsView.locator('#favorite-mercadona').getAttribute('aria-pressed'),'false');
    assert.equal(await settingsView.locator('.store-favorite[aria-pressed="true"]').count(),1);
    await settingsPage.setViewportSize({width:390,height:844});
    const updateAll = settingsView.getByRole('button',{name:'Actualizar ahora',exact:true});
    assert.equal(await updateAll.count(),1);
    assert.equal(await updateAll.textContent(),'');
    assert.equal(await updateAll.locator('ha-icon').getAttribute('icon'),'mdi:refresh');
    assert.equal(await settingsView.locator('#stores-last-updated').textContent(),'—');
    await settingsPage.evaluate(()=>{
      document.querySelector('improved-shopping-list-panel').shadowRoot.querySelector('isl-settings')._data.hass.config={time_zone:'Europe/Madrid'};
      window.lastPriceUpdateFixture=Date.parse('2026-10-20T18:35:00Z')/1000;
      for(const callback of window.storeProgressListeners)callback({running:false,last_updated:window.lastPriceUpdateFixture});
    });
    assert.equal(await settingsView.locator('#stores-last-updated').textContent(),'20/10 20:35');
    await updateAll.click();
    const allPricesDialog=settingsView.getByRole('dialog',{name:'Actualización de precios',exact:true});
    await allPricesDialog.waitFor();
    await settingsView.locator('#refresh-all-prices:not([disabled])').waitFor();
    assert.equal(await settingsPage.evaluate(()=>window.calls.filter(call=>call.type==='improved_shopping_list/settings/refresh_all_prices').length),1);
    assert.equal(await settingsView.locator('#stores-refresh-error').isVisible(),false);
    await settingsPage.evaluate(()=>{for(const callback of window.storeProgressListeners)callback({running:true,total:4,processed:1,estimated_seconds:900,errors:{},last_updated:window.lastPriceUpdateFixture});});
    assert.equal(await allPricesDialog.locator('#prices-progress-bar').evaluate(node=>node.value),1);
    assert.equal(await allPricesDialog.locator('#prices-progress-percentage').textContent(),'25 %');
    await allPricesDialog.getByRole('button',{name:'Cerrar',exact:true}).click();
    await updateAll.click();
    assert.equal(await settingsPage.evaluate(()=>window.calls.filter(call=>call.type==='improved_shopping_list/settings/refresh_all_prices').length),1);
    assert.equal(await allPricesDialog.locator('#prices-progress-percentage').textContent(),'25 %');
    await settingsPage.screenshot({path:'test-results/all-prices-progress-mobile.png',fullPage:true});
    await settingsPage.evaluate(()=>{for(const callback of window.storeProgressListeners)callback({running:false,total:4,processed:4,estimated_seconds:0,errors:{},last_updated:window.lastPriceUpdateFixture});});
    assert.equal(await allPricesDialog.locator('#prices-progress-percentage').textContent(),'100 %');
    await settingsPage.evaluate(()=>{
      const view=window.testPanel.shadowRoot.querySelector('isl-settings');
      view._manualQueued=null;view._refreshStartErrors=[];
      for(const callback of window.storeProgressListeners)callback({running:false,total:4,processed:4,batch_id:'finished-batch',finished_at:1792520000,log_pending:true,errors:{},last_updated:window.lastPriceUpdateFixture});
    });
    assert.equal(await allPricesDialog.locator('#prices-progress-percentage').textContent(),'100 %');
    assert.match(await allPricesDialog.locator('#prices-progress-status').textContent(),/Revisión finalizada/);
    assert.match(await allPricesDialog.locator('#prices-progress-time').textContent(),/pendiente de guardar/);
    await settingsPage.evaluate(()=>{for(const callback of window.storeProgressListeners)callback({running:false,total:4,processed:4,batch_id:'finished-batch',finished_at:1792520000,log_pending:false,errors:{},last_updated:window.lastPriceUpdateFixture});});
    assert.match(await allPricesDialog.locator('#prices-progress-time').textContent(),/Resumen disponible/);
    await allPricesDialog.getByRole('button',{name:'Cerrar',exact:true}).click();
    assert.equal(await settingsView.locator('#stores-last-updated').textContent(),'20/10 20:35'); // Queueing alone must not change a price's timestamp.
    assert.doesNotMatch(await settingsView.locator('#settings-stores').textContent(),/referencias pendientes en cola/);
    await settingsPage.evaluate(()=>{window.failManualPriceRefresh=true;});
    await updateAll.click();
    await settingsView.locator('#stores-refresh-error').filter({hasText:'pausa'}).waitFor();
    await allPricesDialog.getByRole('button',{name:'Cerrar',exact:true}).click();
    await settingsPage.evaluate(()=>{window.failManualPriceRefresh=false;document.querySelector('improved-shopping-list-panel').shadowRoot.querySelector('isl-catalog').dispatchEvent(new CustomEvent('catalog-change',{detail:{products:window.catalogProducts,categories:window.catalogCategories}}));});
    await settingsPage.evaluate(()=>{window.manualPriceErrors=[{store:'consum',error:'Consum: Consum: Consum no ofrece entrega para el código postal 28024.'}];});
    await updateAll.click();
    assert.equal(await settingsView.locator('#stores-refresh-error').textContent(),'Consum: no ofrece entrega para el código postal 28024.');
    await allPricesDialog.getByRole('button',{name:'Cerrar',exact:true}).click();
    await settingsPage.evaluate(()=>{window.manualPriceErrors=[];});
    for(const row of await settingsView.locator('.store-row').all()){
      const geometry=await row.evaluate(node=>{const name=node.querySelector('.store-name').getBoundingClientRect(),logo=node.querySelector('.store-logo').getBoundingClientRect();return {difference:Math.abs(name.y+name.height/2-logo.y-logo.height/2),overflow:node.scrollWidth-node.clientWidth};});
      assert.ok(geometry.difference<2,'Store name and logo are vertically centered');
      assert.ok(geometry.overflow<=1,'Store controls fit the mobile card');
    }
    assert.match(await settingsView.locator('img[alt="Logo de Alcampo"]').getAttribute('src'),/almeria.online/);
    assert.equal(await settingsView.locator('.stores-grid').evaluate(node=>getComputedStyle(node).gridTemplateColumns.split(' ').length),1);
    assert.match(await settingsView.locator('.stores-footer').textContent(),/Última actualización: 20\/10 20:35/);
    assert.equal(await settingsView.locator('.stores-footer').evaluate(node=>getComputedStyle(node).textAlign),'right');
    assert.equal(await settingsView.locator('#settings-stores #price-update-time').count(),0);
    await settingsView.getByRole("switch",{name:"Habilitar Mercadona",exact:true}).uncheck();
    assert.equal(await settingsView.getByRole("switch",{name:"Habilitar Mercadona",exact:true}).isChecked(),false);
    assert.equal(await settingsPage.evaluate(()=>window.listSettings.stores.mercadona.postal_code),"28024");
    await settingsPage.screenshot({path:"test-results/stores-mobile.png",fullPage:true});
    await settingsView.getByRole("button",{name:"Comunidad",exact:true}).click();
    await settingsView.getByRole("heading",{name:"Comunidad",exact:true}).waitFor();
    assert.equal(await settingsView.locator("#settings-lists").isVisible(),false);
    assert.match(await settingsView.locator("#settings-community").textContent(),/sugerencia para mejorar la integración puedes unirte a través de Telegram/);
    assert.match(await settingsView.locator("#settings-community").textContent(),/conseguir contenido exclusivo, participar en sorteos y otras ventajas/);
    const patreon = settingsView.getByRole("link",{name:"Hacerme Patreon",exact:true});
    assert.equal(await patreon.getAttribute("href"),"https://www.patreon.com/c/aguacatec/membership");
    assert.equal(await patreon.getAttribute("target"),"_blank");
    assert.equal(await patreon.evaluate(node=>getComputedStyle(node).backgroundColor),"rgb(0, 0, 0)");
    for (const width of [1280,390]) {
      await settingsPage.setViewportSize({width,height:844});
      const actions = await settingsView.locator(".community-action").evaluateAll(nodes=>nodes.map(node=>{
        const rect=node.getBoundingClientRect(),icon=node.querySelector("svg, input").getBoundingClientRect();
        return {width:rect.width,iconWidth:icon.width,iconHeight:icon.height};
      }));
      assert.equal(actions.length,3);
      assert.ok(actions.every(action=>action.width===actions[0].width && action.iconWidth===16 && action.iconHeight===16));
      await settingsPage.screenshot({path:`test-results/community-${width}.png`,fullPage:true});
    }
    const sharing=settingsView.getByLabel('Compartir mis datos de productos',{exact:true});
    assert.equal(await sharing.isChecked(),false);
    await settingsPage.context().route('https://github.com/login/device',route=>route.fulfill({contentType:'text/html',body:'<title>GitHub authorization</title>'}));
    const githubPopup=settingsPage.waitForEvent('popup');
    await settingsView.locator('.community-share span').click();
    const githubPage=await githubPopup;
    await githubPage.waitForURL('https://github.com/login/device');
    assert.equal(await githubPage.evaluate(()=>window.opener===null),true);
    await githubPage.close();
    const communityDialog=settingsView.getByRole('dialog',{name:'Autorizar en GitHub',exact:true});
    await communityDialog.waitFor();
    await settingsView.getByText('ABCD-EFGH',{exact:true}).waitFor();
    const authorize=settingsView.getByRole('link',{name:'Autorizar en GitHub',exact:true});
    assert.equal(await authorize.getAttribute('href'),'https://github.com/login/device');
    assert.equal(await authorize.getAttribute('target'),'_blank');
    assert.equal(await settingsView.locator('#community-connection').isVisible(),false);
    await settingsPage.screenshot({path:'test-results/community-authorization-mobile.png',fullPage:true});
    await communityDialog.getByRole('button',{name:'Cerrar ventana',exact:true}).click();
    await settingsPage.evaluate(()=>window.testPanel.shadowRoot.querySelector('isl-settings')._renderCommunity());
    assert.equal(await communityDialog.isVisible(),false);
    const reopenGithub=settingsPage.waitForEvent('popup');
    await settingsView.getByRole('button',{name:'Ver autorización',exact:true}).click();
    const reopened=await reopenGithub;await reopened.close();
    await communityDialog.waitFor();
    await settingsPage.evaluate(()=>{
      window.communityFixture={sharing:true,connected:true,account:'tester',authorization:null};
      const settings=window.testPanel.shadowRoot.querySelector('isl-settings');
      settings._communityState=window.communityFixture;settings._renderCommunity();
    });
    await communityDialog.waitFor({state:'hidden'});
    await sharing.uncheck();
    await settingsView.locator('#community-authorization').waitFor({state:'hidden'});
    assert.equal(await settingsPage.evaluate(()=>window.communityFixture.sharing),false);
    assert.equal(await settingsView.locator('#export-community').count(),0);
    assert.equal(await settingsView.locator('.community-action #community-sharing').count(),1);
    assert.match(await settingsView.locator('#community-description').textContent(),/una vez al día/);
    assert.equal(await settingsPage.evaluate(()=>window.calls.some(call=>call.type==='improved_shopping_list/community/export')),false);
    await settingsView.getByRole("button",{name:"Listas",exact:true}).click();
    const configured = settingsView.locator("#configured-lists article");
    assert.equal(await configured.count(), 3);
    assert.equal(await configured.filter({ hasText: "todo.bring" }).locator(".list-primary").getAttribute("aria-pressed"), "true");
    assert.equal(await configured.locator('.list-primary[aria-pressed="true"]').count(),1);
    const listActions=configured.filter({hasText:"todo.bring"}).locator('.actions button');
    assert.deepEqual(await listActions.locator('ha-icon').evaluateAll(nodes=>nodes.map(node=>node.getAttribute('icon'))),['mdi:delete','mdi:star']);
    assert.deepEqual(await listActions.allTextContents(),['','']);
    assert.equal(await listActions.first().evaluate(node=>getComputedStyle(node).backgroundColor),'rgb(211, 47, 47)');
    assert.equal(await listActions.last().evaluate(node=>getComputedStyle(node).backgroundColor),'rgb(255, 202, 40)');
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
    await configured.filter({ hasText: "todo.local" }).locator('.list-primary[aria-pressed="true"]').waitFor();
    assert.equal(await configured.locator('.list-primary[aria-pressed="true"]').count(),1);
    assert.equal(await configured.filter({hasText:"todo.local"}).locator('.list-primary').getAttribute('aria-pressed'),'true');
    assert.equal(await configured.filter({hasText:"todo.bring"}).locator('.list-primary').getAttribute('aria-pressed'),'false');
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
    await configured.filter({ hasText: "todo.bring" }).locator('.list-primary[aria-pressed="true"]').waitFor();
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
    await configured.filter({ hasText: "todo.custom_provider" }).locator('.list-primary[aria-pressed="true"]').waitFor();
    // A settings snapshot from another session updates the selected provider immediately.
    await settingsPage.evaluate(() => { window.listSettings={entities:['todo.bring','todo.custom_provider'],primary_entity:'todo.bring'};window.emitSettings(); });
    await configured.filter({ hasText: "todo.bring" }).locator('.list-primary[aria-pressed="true"]').waitFor();
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
    assert.equal(await settingsView.getByLabel('Color inicial de Stock',{exact:true}).inputValue(),'#f59a23');
    await settingsView.getByLabel('Color inicial de Stock',{exact:true}).evaluate(input=>{input.value='#ffcc80';input.dispatchEvent(new Event('input',{bubbles:true}));});
    await settingsView.getByLabel('Color final de Stock',{exact:true}).evaluate(input=>{input.value='#ef6c00';input.dispatchEvent(new Event('input',{bubbles:true}));});
    assert.equal(await settingsView.locator('#stock-appearance-preview').evaluate(node=>getComputedStyle(node).backgroundImage),'linear-gradient(rgb(255, 204, 128), rgb(239, 108, 0))');
    assert.equal(await settingsView.locator('#recipe-appearance-preview').evaluate(node=>getComputedStyle(node).color),'rgb(255, 255, 255)');
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
    assert.equal(await settingsPage.evaluate(()=>window.listSettings.appearance.stock_gradient_start),'#ffcc80');
    assert.equal(await settingsPage.evaluate(()=>window.testPanel.style.getPropertyValue('--isl-stock-gradient-end')),'#ef6c00');
    for(const width of [390,1280]) {
      await settingsPage.setViewportSize({width,height:960});
      const positions=await settingsView.evaluate(node=>{
        const bounds=id=>{const box=node.shadowRoot.querySelector(id).getBoundingClientRect();return {x:box.x,y:box.y,width:box.width};};
        return {stock:bounds('#stock-appearance-preview'),recipe:bounds('#recipe-appearance-preview'),start:bounds('#stock-gradient-start'),end:bounds('#stock-gradient-end'),recipeStart:bounds('#recipe-gradient-start')};
      });
      assert.equal(positions.stock.y,positions.recipe.y);assert.ok(positions.stock.x<positions.recipe.x);
      assert.equal(positions.start.y,positions.recipeStart.y);assert.ok(positions.end.x<positions.recipeStart.x);
    }
    await settingsPage.setViewportSize({width:390,height:844});
    await settingsPage.screenshot({ path: "test-results/personalization-mobile.png", fullPage: true });
    await settingsPage.getByRole("button", { name: "Lista", exact: true }).click();
    assert.equal(await settingsPage.locator("#pending").evaluate(node => getComputedStyle(node).gridTemplateColumns.split(" ").length), 2);
    await settingsPage.getByRole("button", { name:"Catálogo", exact:true }).click();
    const settingsCatalog = settingsPage.locator("isl-catalog");
    assert.equal(await settingsCatalog.locator("#catalog-grid").evaluate(node => getComputedStyle(node).gridTemplateColumns.split(" ").length), 2);
    await settingsCatalog.getByRole("button", { name:"Categorías", exact:true }).click();
    assert.equal(await settingsCatalog.locator("#catalog-categories #category-grid").evaluate(node => getComputedStyle(node).gridTemplateColumns.split(" ").length), 2);
    await settingsCatalog.getByRole("button", { name:"Productos", exact:true }).click();
    await settingsPage.getByRole("button", { name:"Lista", exact:true }).click();
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
      await window.testPanel._hass.callWS({type:'improved_shopping_list/catalog/category/save',category:{name:'Desayuno',icon:'mdi:food',color:'#64748b'}});
      await window.testPanel._hass.callWS({type:'improved_shopping_list/catalog/save',product:{name:'Cacao',category:'Desayuno',tags:['a'.repeat(40)],brand:'Marca larga',format:'250 g',barcode:'',image_url:'/logo.png',icon:'',notes:'',price:null,currency:'EUR'}});
    });
    assert.equal(await settingsPage.locator("#pending").evaluate(node => getComputedStyle(node).gridTemplateColumns.split(" ").length), 4);
    assert.equal(await settingsPage.locator("#items-card").evaluate(node => node.scrollWidth > innerWidth), false);
    await settingsPage.getByRole("button", { name:"Catálogo", exact:true }).click();
    assert.equal(await settingsCatalog.locator("#catalog-grid").evaluate(node => getComputedStyle(node).gridTemplateColumns.split(" ").length), 4);
    assert.ok(await settingsCatalog.locator("#catalog-grid").evaluate(node => node.scrollWidth<=node.clientWidth+1));
    assert.ok(await settingsCatalog.locator("#catalog-grid .product").first().evaluate(card => {
      const bounds=card.getBoundingClientRect();
      return [...card.querySelectorAll('.image,.tag,.product-controls')].filter(child=>child.getClientRects().length>0).every(child=>{const rect=child.getBoundingClientRect();return rect.left>=bounds.left&&rect.right<=bounds.right;});
    }));
    await settingsPage.screenshot({path:"test-results/catalog-columns-mobile.png",fullPage:true});
    await settingsCatalog.getByRole("button", { name:"Categorías", exact:true }).click();
    assert.equal(await settingsCatalog.locator("#catalog-categories #category-grid").evaluate(node => getComputedStyle(node).gridTemplateColumns.split(" ").length), 2);
    assert.ok(await settingsCatalog.locator("#catalog-categories #category-grid").evaluate(node => node.scrollWidth<=node.clientWidth+1));
    await settingsPage.screenshot({path:"test-results/category-columns-mobile.png",fullPage:true});
    await settingsCatalog.getByRole("button", { name:"Productos", exact:true }).click();
    await settingsPage.getByRole("button", { name:"Lista", exact:true }).click();
    await settingsPage.setViewportSize({ width:1280,height:960 });
    assert.equal(await settingsPage.locator("#pending").evaluate(node => getComputedStyle(node).gridTemplateColumns.split(" ").length), 4);
    const listGradient = await settingsPage.locator("#pending .item").first().evaluate(node => getComputedStyle(node).backgroundImage);
    await settingsPage.getByRole("button", { name:"Catálogo", exact:true }).click();
    assert.equal(await settingsPage.locator("isl-catalog #catalog-grid .product.in-list").first().evaluate(node => getComputedStyle(node).backgroundImage), listGradient);
    assert.equal(await settingsCatalog.locator("#catalog-grid").evaluate(node => getComputedStyle(node).gridTemplateColumns.split(" ").length), 4);
    await settingsCatalog.getByRole("button", { name:"Categorías", exact:true }).click();
    assert.equal(await settingsCatalog.locator("#catalog-categories #category-grid").evaluate(node => getComputedStyle(node).gridTemplateColumns.split(" ").length), 4);
    await settingsCatalog.getByRole("button", { name:"Productos", exact:true }).click();
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
    assert.equal(await settingsView.getByRole('button',{name:'Añadir pasarela',exact:true}).isDisabled(),true);
    await settingsPage.getByRole("button", { name:"Lista", exact:true }).click();
    await settingsPage.evaluate(() => {
      window.listData['todo.bring'].push({uid:'square-long',summary:'Producto con un nombre muy largo '.repeat(6),description:'Una descripción extensa '.repeat(20),status:'needs_action'});
      window.listData['todo.bring'].push({uid:'square-completed',summary:'Producto comprado de nombre largo',status:'completed'});
      window.listData['todo.bring'].push({uid:'square-completed-category',summary:'Cacao',status:'completed'});
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
        const badges = await settingsPage.locator("#items-card .category-badge:not([hidden])").evaluateAll(nodes => nodes.map(badge => {
          const bounds=badge.getBoundingClientRect(),icon=badge.querySelector("ha-icon").getBoundingClientRect(),style=getComputedStyle(badge);
          return {width:bounds.width,height:bounds.height,iconWidth:icon.width,iconHeight:icon.height,
            dx:Math.abs((bounds.left+bounds.right-icon.left-icon.right)/2),
            dy:Math.abs((bounds.top+bounds.bottom-icon.top-icon.bottom)/2),
            border:style.borderWidth,shadow:style.boxShadow,color:style.color};
        }));
        assert.ok(badges.length>=2,"Category badges exist on pending and purchased products");
        for (const badge of badges) {
          assert.ok(badge.width>0&&Math.abs(badge.width-badge.height)<.1,`Circular list badge at ${width}px / ${columns} columns: ${JSON.stringify(badge)}`);
          assert.ok(badge.iconWidth>0&&Math.abs(badge.iconWidth-badge.iconHeight)<.1&&badge.dx<.5&&badge.dy<.5);
          assert.equal(badge.border,"0px");
          assert.notEqual(badge.shadow,"none");
          assert.equal(badge.color,"rgb(255, 255, 255)");
        }
        sizes.push(metrics[0]);
        assert.ok(metrics[0].font>=12,"Product names remain readable in narrow cards");
        await settingsPage.getByRole("button",{name:"Catálogo",exact:true}).click();
        const catalogFont = await settingsCatalog.locator("#catalog-grid .title").first().evaluate(name=>parseFloat(getComputedStyle(name).fontSize));
        assert.ok(Math.abs(catalogFont-metrics[0].font)<.05,`Matching List/Catalog names at ${width}px / ${columns} columns: ${metrics[0].font} vs ${catalogFont}`);
        if (columns===(width>650?6:4)) await settingsPage.screenshot({path:`test-results/catalog-font-size-${width}.png`,fullPage:true});
        await settingsPage.getByRole("button",{name:"Lista",exact:true}).click();
      }
      assert.ok(sizes[0].font>sizes.at(-1).font);
      assert.ok(sizes[0].mediaWidth>sizes.at(-1).mediaWidth);
      await settingsPage.screenshot({path:`test-results/list-square-${width}.png`,fullPage:true});
    }
    await settingsContext.close();
    // Reader configuration and unknown-code association use the same product form.
    const quantityContext=await browser.newContext({viewport:{width:1280,height:960}});
    const quantityPage=await quantityContext.newPage();quantityPage.on('pageerror',error=>errors.push(error.message));
    await quantityPage.goto(url);
    await quantityPage.evaluate(async()=>{
      window.catalogProducts=[{id:'pavo',revision:1,name:'Pavo',category:'',tags:[],notes:'',barcode:'',barcodes:[],nfc_tags:[],reader_actions:{},recurrence:{enabled:false,days:7},store_links:{},price:null,currency:'EUR',purchase_unit:'g',unit_quantity:250,quantity_step:50,image_url:'',icon:'mdi:food-drumstick'}];window.emitCatalog();
      window.listData['todo.bring']=[{uid:'pavo-entry',summary:'Pavo',status:'needs_action'},{uid:'default-entry',summary:'Sin catálogo',status:'needs_action'}];window.emit('todo.bring');
      window.listSettings.stores={carrefour:{enabled:true}};window.emitSettings();
      window.storePriceFixture=[{catalog_product_id:'pavo',store:'carrefour',price:'2.50',currency:'EUR',checked_at:1792490400}];
      await window.testPanel._refreshRowPrices();
    });
    const pavoCard=quantityPage.getByRole('button',{name:'Marcar como comprado: Pavo',exact:true});
    const pavoRow=pavoCard.locator('..');
    await pavoCard.locator('.quantity-corner').filter({hasText:'250 g'}).waitFor();
    assert.equal(await quantityPage.getByRole('button',{name:'Marcar como comprado: Sin catálogo',exact:true}).locator('.quantity-corner').isVisible(),false);
    assert.equal(await pavoRow.getByRole('button',{name:'Aumentar cantidad: Pavo',exact:true}).count(),0);
    await quantityPage.screenshot({path:'test-results/purchase-quantity-grid.png',fullPage:true});
    await quantityPage.locator('#toggle-list-layout').click();
    await pavoRow.locator('.row-quantity').filter({hasText:'250 g'}).waitFor();
    assert.equal(await pavoRow.locator('.row-quantity button').count(),0);
    await quantityPage.getByRole('button',{name:'Catálogo',exact:true}).click();
    const quantityCatalog=quantityPage.locator('isl-catalog');
    assert.equal(await quantityCatalog.getByRole('group',{name:'Cantidad de Pavo',exact:true}).count(),0);
    await quantityCatalog.locator('#toggle-catalog-layout').click();
    const quantityBadge=quantityCatalog.getByRole('group',{name:'Cantidad de Pavo',exact:true});
    assert.equal(await quantityBadge.locator('.quantity-value').textContent(),'250 g');
    await quantityBadge.getByRole('button',{name:'Aumentar cantidad: Pavo',exact:true}).click();
    await quantityBadge.locator('.quantity-value').filter({hasText:'300 g'}).waitFor();
    await quantityPage.evaluate(()=>{window.failQuantities=true;});
    await quantityBadge.getByRole('button',{name:'Aumentar cantidad: Pavo',exact:true}).click();
    await quantityCatalog.locator('#catalog-error').filter({hasText:'No se pudo cambiar la cantidad'}).waitFor();
    assert.equal(await quantityBadge.locator('.quantity-value').textContent(),'300 g');
    await quantityPage.evaluate(()=>{window.failQuantities=false;});

    assert.equal(await quantityBadge.locator('ha-icon').first().getAttribute('icon'),'mdi:minus-thick');
    assert.equal(await quantityBadge.locator('ha-icon').last().getAttribute('icon'),'mdi:plus-thick');
    assert.equal(await quantityCatalog.locator('.add-product button').count(),0);
    assert.equal(await quantityPage.evaluate(()=>window.listData['todo.bring'].filter(item=>item.summary==='Pavo').length),1);
    assert.equal(await quantityPage.evaluate(()=>window.listData['todo.bring'].find(item=>item.uid==='pavo-entry').status),'needs_action');
    assert.match(await quantityPage.locator('#pending-total').textContent(),/3,00/);
    await quantityPage.reload();
    // The simulated native provider lives in page memory; restore its unchanged entries.
    await quantityPage.evaluate(async()=>{
      window.listData['todo.bring']=[{uid:'pavo-entry',summary:'Pavo',status:'needs_action'},{uid:'default-entry',summary:'Sin catálogo',status:'needs_action'}];window.emit('todo.bring');
      window.storePriceFixture=[{catalog_product_id:'pavo',store:'carrefour',price:'2.50',currency:'EUR',checked_at:1792490400}];
      await window.testPanel._refreshRowPrices();
    });
    await pavoRow.locator('.row-quantity').filter({hasText:'300 g'}).waitFor();
    await quantityPage.getByRole('button',{name:'Catálogo',exact:true}).click();
    await quantityBadge.locator('.quantity-value').filter({hasText:'300 g'}).waitFor();
    await quantityCatalog.getByRole('button',{name:'Editar Pavo',exact:true}).click();
    const quantityForm=quantityCatalog.locator('#product-form');
    await quantityForm.getByRole('button',{name:'Información adicional',exact:true}).click();
    assert.equal(await quantityForm.getByLabel('Unidades',{exact:true}).inputValue(),'g');
    assert.equal(await quantityForm.getByLabel('Cantidad unitaria',{exact:true}).inputValue(),'250');
    await quantityForm.getByLabel('Tamaño del paso',{exact:true}).fill('100');
    await quantityForm.getByRole('button',{name:'Guardar producto',exact:true}).click();
    await quantityCatalog.locator('dialog[aria-labelledby="product-dialog-title"]').waitFor({state:'hidden'});
    await quantityBadge.getByRole('button',{name:'Disminuir cantidad: Pavo',exact:true}).click();
    await quantityBadge.locator('.quantity-value').filter({hasText:'200 g'}).waitFor();
    for(const width of [1280,390,320]){
      await quantityPage.setViewportSize({width,height:844});
      await quantityPage.screenshot({path:'test-results/catalog-quantity-rows-'+width+'.png'});
      assert.equal(await quantityPage.locator('main').evaluate(node=>node.scrollWidth>innerWidth),false);
      assert.ok(await quantityBadge.evaluate(node=>{
        const [minus,label,plus]=[...node.children].map(child=>child.getBoundingClientRect());
        return minus.right<=label.left&&label.right<=plus.left&&Math.abs((minus.top+minus.bottom)/2-(plus.top+plus.bottom)/2)<1&&node.scrollWidth<=node.clientWidth+1;
      }));
    }
    await quantityPage.evaluate(()=>{window.listData['todo.bring']=window.listData['todo.bring'].filter(item=>item.summary!=='Pavo');window.emit('todo.bring');});
    await quantityBadge.getByRole('button',{name:'Aumentar cantidad: Pavo',exact:true}).isDisabled().then(value=>assert.equal(value,true));
    await quantityPage.evaluate(()=>{window.listData['todo.bring'].push({uid:'pavo-entry',summary:'Pavo',status:'needs_action'});window.emit('todo.bring');});
    await quantityPage.getByRole('button',{name:'Ajustes',exact:true}).click();
    const quantitySettings=quantityPage.locator('isl-settings');
    await quantitySettings.getByRole('button',{name:'Personalización',exact:true}).click();
    await quantitySettings.getByLabel('Color del indicador de cantidad',{exact:true}).evaluate(input=>{input.value='#4caf50';input.dispatchEvent(new Event('input',{bubbles:true}));});
    await quantitySettings.getByRole('button',{name:'Guardar personalización',exact:true}).click();
    await quantitySettings.getByRole('status').filter({hasText:'Personalización guardada'}).waitFor();
    await quantityPage.getByRole('button',{name:'Lista',exact:true}).click();await quantityPage.locator('#toggle-list-layout').click();
    assert.equal(await pavoCard.locator('.quantity-corner').evaluate(node=>getComputedStyle(node).backgroundColor),'rgb(76, 175, 80)');
    assert.equal(await pavoCard.locator('.quantity-corner').evaluate(node=>getComputedStyle(node).color),'rgb(255, 255, 255)');
    await quantityContext.close();

    const gatewayContext=await browser.newContext({viewport:{width:390,height:844}});
    const gatewayPage=await gatewayContext.newPage();
    gatewayPage.on('pageerror',error=>errors.push(error.message));
    await gatewayPage.goto(url);
    await gatewayPage.getByRole('button',{name:'Ajustes',exact:true}).click();
    const gatewaySettings=gatewayPage.locator('isl-settings');
    await gatewaySettings.locator('#gateway-entity').selectOption('todo.local');
    assert.equal(await gatewaySettings.locator('#gateway-target').inputValue(),'todo.bring');
    await gatewaySettings.locator('#gateway-remove').check();
    await gatewaySettings.getByRole('button',{name:'Añadir pasarela',exact:true}).click();
    const gatewayRow=gatewaySettings.locator('#configured-gateways article');
    await gatewayRow.waitFor();
    assert.equal(await gatewaySettings.locator('#configured-lists article').count(),2);
    assert.equal(await gatewaySettings.locator('#todo-entity option[value="todo.local"]').count(),0);
    assert.equal(await gatewayRow.getByRole('checkbox').isChecked(),true);
    await gatewayRow.getByRole('checkbox').uncheck();
    await gatewayPage.waitForFunction(()=>window.listSettings.gateway_lists[0].remove_after_transfer===false);
    await gatewaySettings.getByRole('button',{name:'Personalización',exact:true}).click();
    assert.equal(await gatewaySettings.locator('#settings-gateways').isVisible(),false);
    await gatewayPage.reload();
    await gatewayPage.getByRole('button',{name:'Ajustes',exact:true}).click();
    await gatewayRow.waitFor();
    await gatewaySettings.locator('#configured-gateways').scrollIntoViewIfNeeded();
    await gatewayPage.screenshot({path:'test-results/gateway-lists-mobile.png'});
    assert.equal(await gatewaySettings.evaluate(node=>node.scrollWidth>innerWidth),false);
    await gatewayRow.getByRole('button',{name:'Quitar pasarela: Casa',exact:true}).click();
    await gatewayRow.waitFor({state:'hidden'});
    assert.equal(await gatewaySettings.locator('#todo-entity option[value="todo.local"]').count(),1);
    await gatewayPage.evaluate(()=>window.failSettings=true);
    await gatewaySettings.locator('#gateway-entity').selectOption('todo.local');
    await gatewaySettings.getByRole('button',{name:'Añadir pasarela',exact:true}).click();
    await gatewaySettings.locator('#settings-error').filter({hasText:'No se pudo guardar la pasarela'}).waitFor();
    assert.equal(await gatewayRow.count(),0);
    await gatewayContext.close();

    // Only configured shopping lists count: gateways and other todo entities do not.
    const singleListContext=await browser.newContext({viewport:{width:390,height:844}});
    const singleListPage=await singleListContext.newPage();singleListPage.on('pageerror',error=>errors.push(error.message));
    await singleListPage.goto(url);
    await singleListPage.evaluate(()=>{
      window.listSettings.entities=['todo.bring'];window.listSettings.gateway_lists=[{entity_id:'todo.local',target_entity:'todo.bring',remove_after_transfer:true}];window.emitSettings();
    });
    assert.equal(await singleListPage.locator('#choose-list').isVisible(),false);
    await singleListPage.getByRole('button',{name:'Stock',exact:true}).click();
    assert.equal(await singleListPage.locator('#choose-list').isVisible(),false);
    await singleListPage.evaluate(()=>{window.listSettings.entities.push('todo.readonly');window.emitSettings();});
    await singleListPage.locator('#choose-list').waitFor();
    await singleListPage.getByRole('button',{name:'Seleccionar lista',exact:true}).click();
    assert.equal(await singleListPage.locator('#list-options .list-option').count(),2);
    await singleListPage.evaluate(()=>{window.listSettings.entities=['todo.bring'];window.emitSettings();});
    await singleListPage.locator('#list-dialog').waitFor({state:'hidden'});
    assert.equal(await singleListPage.locator('#choose-list').isVisible(),false);
    await singleListPage.getByRole('button',{name:'Lista',exact:true}).click();
    assert.equal(await singleListPage.locator('#choose-list').isVisible(),false);
    await singleListPage.evaluate(()=>{window.listSettings.entities.push('todo.readonly');window.emitSettings();});
    await singleListPage.locator('#choose-list').waitFor();
    await singleListContext.close();

    const listGroupsContext=await browser.newContext({viewport:{width:320,height:844}});
    const listGroupsPage=await listGroupsContext.newPage();listGroupsPage.on('pageerror',error=>errors.push(error.message));
    await listGroupsPage.goto(url);
    await listGroupsPage.evaluate(()=>{
      window.catalogCategories=[{id:'d',name:'Despensa',icon:'mdi:food',color:'#ff9800'},{id:'v',name:'Verduras',icon:'mdi:carrot',color:'#4caf50'},{id:'l',name:'Lácteos',icon:'mdi:bottle-soda',color:'#2196f3'}];
      window.catalogProducts=[{id:'c',name:'Cacao',category:'Despensa'},{id:'a',name:'Arroz',category:'Despensa'},{id:'z',name:'Zanahoria',category:'Verduras'},{id:'l',name:'Leche entera',category:'Lácteos'}].map(product=>({tags:[],barcodes:[],barcode:'',icon:'',image_url:'',nfc_tags:[],reader_actions:{},...product}));window.emitCatalog();
      window.listData['todo.bring']=[{uid:'z',summary:'Zanahoria',status:'needs_action'},{uid:'c',summary:'Cacao',status:'needs_action'},{uid:'l',summary:'Leche entera',status:'needs_action'},{uid:'u',summary:'Sin ficha',status:'needs_action'},{uid:'a',summary:'Arroz',status:'completed'}];window.emit('todo.bring');
      window.stockItems=[{id:'c',catalog_product_id:'c',name:'Cacao',quantity:10,refill_quantity:100,unit:'uds',revision:1},{id:'a',catalog_product_id:'a',name:'Arroz',quantity:90,refill_quantity:100,unit:'uds',revision:1},{id:'z',catalog_product_id:'z',name:'Zanahoria',quantity:20,refill_quantity:100,unit:'uds',revision:1},{id:'u',name:'Sin ficha',quantity:5,refill_quantity:100,unit:'uds',revision:1}];window.emitStock();
    });
    assert.deepEqual(await listGroupsPage.locator('#pending .summary').allTextContents(),['Cacao','Leche entera','Sin ficha','Zanahoria']);
    await listGroupsPage.getByRole('button',{name:'Agrupar por categorías',exact:true}).click();
    assert.deepEqual(await listGroupsPage.locator('#pending .product-group-heading').allTextContents(),['Despensa','Lácteos','Verduras','Sin categoría']);
    assert.equal(await listGroupsPage.locator('#pending .product-group-heading ha-icon').first().evaluate(node=>getComputedStyle(node).color),'rgb(255, 255, 255)');
    await listGroupsPage.locator('#completed-summary').click();
    assert.deepEqual(await listGroupsPage.locator('#completed .product-group-heading').allTextContents(),['Despensa']);
    await listGroupsPage.getByRole('button',{name:'Marcar como comprado: Cacao',exact:true}).click();
    await listGroupsPage.locator('#completed .summary').filter({hasText:'Cacao'}).waitFor({state:'attached'});
    assert.deepEqual(await listGroupsPage.locator('#completed .summary').allTextContents(),['Arroz','Cacao']);
    await listGroupsPage.getByRole('button',{name:'Cambiar a vista de filas',exact:true}).click();
    assert.equal(await listGroupsPage.locator('#pending .product-group > ul.rows').count(),3);
    assert.ok(await listGroupsPage.locator('#add-form').evaluate(node=>node.scrollWidth<=node.clientWidth+1));
    await listGroupsPage.screenshot({path:'test-results/list-category-groups-mobile.png',fullPage:true});
    await listGroupsPage.getByRole('button',{name:'Stock',exact:true}).click();
    assert.equal(await listGroupsPage.locator('#toggle-product-grouping').getAttribute('aria-pressed'),'false');
    assert.deepEqual(await listGroupsPage.locator('#stock-items .summary').allTextContents(),['Sin ficha','Cacao','Zanahoria','Arroz']);
    assert.equal(await listGroupsPage.locator('#toggle-product-grouping').isVisible(),false);
    const stockOrder=listGroupsPage.locator('#toggle-stock-sort');
    assert.equal(await stockOrder.getAttribute('data-mode'),'lowest');
    await stockOrder.click();
    assert.deepEqual(await listGroupsPage.locator('#stock-items .summary').allTextContents(),['Arroz','Cacao','Sin ficha','Zanahoria']);
    assert.equal(await stockOrder.getAttribute('aria-label'),'Agrupar por categorías');
    assert.equal(await stockOrder.locator('ha-icon').getAttribute('icon'),'mdi:label');
    await stockOrder.click();
    assert.deepEqual(await listGroupsPage.locator('#stock-items .product-group-heading').allTextContents(),['Despensa','Verduras','Sin categoría']);
    assert.deepEqual(await listGroupsPage.locator('#stock-items .summary').allTextContents(),['Arroz','Cacao','Zanahoria','Sin ficha']);
    assert.equal(await listGroupsPage.locator('#stock-items .product-group-heading ha-icon').first().evaluate(node=>getComputedStyle(node).color),'rgb(255, 255, 255)');
    assert.equal(await stockOrder.getAttribute('aria-label'),'Ordenar por menor stock');
    await listGroupsPage.getByRole('button',{name:'Cambiar a vista de filas',exact:true}).click();
    assert.equal(await listGroupsPage.locator('#stock-items .product-group > ul.rows').count(),3);
    assert.ok(await listGroupsPage.locator('#stock-heading').evaluate(node=>node.scrollWidth<=node.clientWidth+1));
    await listGroupsPage.screenshot({path:'test-results/stock-category-groups-mobile.png',fullPage:true});
    await stockOrder.click();
    assert.deepEqual(await listGroupsPage.locator('#stock-items .summary').allTextContents(),['Sin ficha','Cacao','Zanahoria','Arroz']);
    assert.equal(await listGroupsPage.locator('#stock-items .product-group').count(),0);
    await stockOrder.click();await stockOrder.click();
    await listGroupsPage.reload();await listGroupsPage.getByRole('button',{name:'Stock',exact:true}).click();
    await listGroupsPage.locator('#stock-items .product-group').nth(2).waitFor();
    assert.equal(await stockOrder.getAttribute('data-mode'),'categories');
    assert.deepEqual(await listGroupsPage.locator('#stock-items .summary').allTextContents(),['Arroz','Cacao','Zanahoria','Sin ficha']);
    await listGroupsPage.setViewportSize({width:1280,height:900});
    await listGroupsPage.screenshot({path:'test-results/stock-category-groups-desktop.png',fullPage:true});
    await listGroupsPage.getByRole('button',{name:'Lista',exact:true}).click();
    assert.equal(await listGroupsPage.locator('#toggle-product-grouping').getAttribute('aria-pressed'),'true');
    await listGroupsPage.getByRole('button',{name:'Mostrar todos los productos',exact:true}).click();
    assert.equal(await listGroupsPage.locator('#pending .product-group').count(),0);
    assert.deepEqual(await listGroupsPage.locator('#pending .summary').allTextContents(),['Cacao','Leche entera']);
    await listGroupsContext.close();


    const readerContext=await browser.newContext({viewport:{width:1280,height:960}});
    const readerPage=await readerContext.newPage();readerPage.on("pageerror",error=>errors.push(error.message));
    await readerPage.clock.install();
    await readerPage.goto(url);
    await readerPage.evaluate(()=>{const panel=window.testPanel;panel.hass={...panel._hass,states:{...panel._hass.states,'sensor.lector_cb_codigo_leido':{entity_id:'sensor.lector_cb_codigo_leido',state:'',attributes:{friendly_name:'Código leído'}}}};});
    await readerPage.getByRole("button",{name:"Ajustes",exact:true}).click();
    await readerPage.locator("isl-settings").getByRole("button",{name:"Lectores",exact:true}).click();
    assert.equal(await readerPage.locator("isl-settings #settings-view-readers ha-icon").getAttribute("icon"),"mdi:barcode-scan");
    assert.equal(await readerPage.locator("#nav-readers").count(),0);
    const readersView=readerPage.locator("isl-settings isl-readers");
    assert.equal(await readersView.getByText("Los lectores funcionan aunque esta interfaz esté cerrada. Configura los códigos y la acción de cada lector en la ficha del producto.",{exact:true}).count(),0);
    assert.equal(await readersView.locator("#new-reader").textContent(),"");
    assert.equal(await readersView.locator("#new-reader ha-icon").getAttribute("icon"),"mdi:plus-thick");
    assert.equal(await readersView.locator("#reader-suggestions").count(),0);
    await readersView.getByRole("button",{name:"Añadir lector",exact:true}).click();
    const readerDialog=readersView.getByRole("dialog",{name:"Añadir lector",exact:true});
    assert.equal(await readerDialog.getByLabel("Lector activo",{exact:true}).count(),0);
    await readerDialog.getByLabel("Acción por defecto",{exact:true}).selectOption("add_list");
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
    const barcodeReader=readersView.locator("#readers-grid article").filter({hasText:"Cocina"});
    const nfcReader=readersView.locator("#readers-grid article").filter({hasText:"NFC despensa"});
    assert.equal(await barcodeReader.locator(".reader-type").getAttribute("icon"),"mdi:barcode-scan");
    assert.equal(await nfcReader.locator(".reader-type").getAttribute("icon"),"mdi:nfc-variant");
    assert.equal(await barcodeReader.locator(".source").count(),0);
    assert.equal(await nfcReader.locator(".source").count(),0);
    assert.equal(await barcodeReader.locator(".last").textContent(),"Último uso: —");
    assert.deepEqual(await barcodeReader.locator(".actions button").allTextContents(),["","",""]);
    assert.deepEqual(await barcodeReader.locator(".actions ha-icon").evaluateAll(icons=>icons.map(icon=>icon.getAttribute("icon"))),["mdi:eye-outline","mdi:note-edit","mdi:delete"]);
    const viewReader = barcodeReader.getByRole("button",{name:"Ver lector Cocina",exact:true});
    assert.equal(await viewReader.evaluate(button => getComputedStyle(button).backgroundColor), "rgb(25, 118, 210)");
    await readerPage.evaluate(() => {
      window.moreInfoEvents = [];
      document.addEventListener("hass-more-info", event => window.moreInfoEvents.push({detail:event.detail,composed:event.composed,bubbles:event.bubbles}));
    });
    await viewReader.click();
    assert.deepEqual(await readerPage.evaluate(() => window.moreInfoEvents), [{detail:{entityId:"sensor.lector_cb_codigo_leido"},composed:true,bubbles:true}]);
    assert.equal(await readersView.locator("#reader-live-dialog").evaluate(dialog=>dialog.open), false);
    await nfcReader.getByRole("button",{name:"Ver lector NFC despensa",exact:true}).click();
    const liveDialog = readersView.locator("#reader-live-dialog");
    await liveDialog.getByText("Esperando una lectura…",{exact:true}).waitFor();
    await readerPage.evaluate(() => {
      window.readerFixture.readers.find(reader=>reader.name==='NFC despensa').last={code:'04:AB:CD',product:'Cacao',message:'Añadido a Casa',time:new Date().toISOString()};
      window.emitReaders();
    });
    await liveDialog.locator("#reader-live-code").filter({hasText:'04:AB:CD'}).waitFor();
    assert.equal(await liveDialog.locator("#reader-live-product").textContent(), 'Cacao');
    assert.equal(await liveDialog.locator("#reader-live-result").textContent(), 'Añadido a Casa');
    await readerPage.evaluate(() => {
      window.readerFixture.readers.find(reader=>reader.name==='NFC despensa').last={code:'<img src=x onerror=alert(1)>',product:null,message:'Código desconocido en Sugerencias',time:new Date().toISOString()};
      window.emitReaders();
    });
    await liveDialog.locator("#reader-live-result").filter({hasText:'Código desconocido'}).waitFor();
    assert.equal(await liveDialog.locator("#reader-live-code").textContent(), '<img src=x onerror=alert(1)>');
    assert.equal(await liveDialog.locator("#reader-live-code img").count(), 0);
    assert.equal(await liveDialog.locator("#reader-live-product").textContent(), 'Sin producto identificado');
    await readerPage.screenshot({path:'test-results/reader-live.png',fullPage:true});
    await liveDialog.getByRole("button",{name:"Cerrar",exact:true}).click();
    assert.equal((await barcodeReader.textContent()).includes("Lista:"),false);
    assert.equal((await barcodeReader.textContent()).includes("Barras / QR"),false);
    assert.equal(await barcodeReader.locator(".badge").count(),0);
    assert.ok(await barcodeReader.evaluate(card=>{
      const bounds=card.getBoundingClientRect();
      return ['.reader-type','h2','.last','.actions'].every(selector=>{const rect=card.querySelector(selector).getBoundingClientRect();return Math.abs((rect.left+rect.right)/2-(bounds.left+bounds.right)/2)<1;});
    }));
    const readerToggle=barcodeReader.getByRole("switch",{name:"Activar lector Cocina",exact:true});
    assert.equal(await readerToggle.isChecked(),true);
    await readerPage.evaluate(()=>{window.failReaders=true;});
    await readerToggle.click();
    await readersView.locator("#readers-error").filter({hasText:"No se ha podido guardar el lector"}).waitFor();
    assert.equal(await readerToggle.isChecked(),true);
    await readerPage.evaluate(()=>{window.failReaders=false;});
    await readerToggle.uncheck();
    assert.equal(await readerToggle.isChecked(),false);
    assert.equal(await readerPage.evaluate(()=>window.readerFixture.readers.find(reader=>reader.name==='Cocina').enabled),false);
    await barcodeReader.getByRole('button',{name:'Editar lector Cocina',exact:true}).click();
    const disabledReaderDialog=readersView.getByRole('dialog',{name:'Editar lector',exact:true});
    assert.equal(await disabledReaderDialog.getByLabel('Acción por defecto',{exact:true}).inputValue(),'add_list');
    assert.equal(await disabledReaderDialog.getByLabel('Lector activo',{exact:true}).count(),0);
    await disabledReaderDialog.getByRole('button',{name:'Guardar lector',exact:true}).click();
    await disabledReaderDialog.waitFor({state:'hidden'});
    assert.equal(await readerToggle.isChecked(),false);
    assert.equal(await readerPage.evaluate(()=>window.readerFixture.readers.find(reader=>reader.name==='Cocina').default_action),'add_list');
    await readerToggle.check();
    assert.equal(await readerToggle.isChecked(),true);
    await readerPage.evaluate(()=>{window.testPanel.hass={...window.testPanel._hass,user:{is_admin:false}};});
    assert.equal(await readerToggle.isDisabled(),true);
    assert.equal(await viewReader.isDisabled(),false);
    await viewReader.click();
    assert.equal(await readerPage.evaluate(()=>window.moreInfoEvents.length),2);
    await readerPage.evaluate(()=>{
      window.testPanel.hass={...window.testPanel._hass,user:{is_admin:true}};
      window.readerFixture.readers.find(reader=>reader.name==='Cocina').last={time:new Date(2026,9,22,7,5).toISOString(),code:'secret-code',message:'Añadido a la lista'};window.emitReaders();
    });
    assert.equal(await barcodeReader.locator(".last").textContent(),"Último uso: 22/10 07:05");
    assert.equal((await barcodeReader.textContent()).includes("secret-code"),false);
    await readerPage.clock.fastForward(60000);
    assert.equal(await barcodeReader.locator(".last").textContent(),"Último uso: 22/10 07:05");
    await readerPage.evaluate(()=>{const reader=window.readerFixture.readers[0];window.readerFixture.pending=[{id:'scan-1',kind:'barcode',code:'0012345678905',reader_id:reader.id,reader_name:reader.name,time:new Date().toISOString()}];window.emitReaders();});
    await readerPage.screenshot({path:"test-results/readers-desktop.png",fullPage:true});
    await readerPage.getByRole("button",{name:"Catálogo",exact:true}).click();
    const readerCatalog=readerPage.locator("isl-catalog");
    await readerCatalog.getByRole("button",{name:"Nuevos",exact:true}).click();
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
    assert.deepEqual(await codeDialog.locator("#barcode-code-list .code-value").allTextContents(),["0012345678905"]);
    assert.equal(await codeDialog.getByLabel("Nombre del producto",{exact:true}).inputValue(),"");
    await codeDialog.getByLabel("Nombre del producto",{exact:true}).fill("Cacao lector");
    await codeDialog.getByRole("button",{name:"Automatización",exact:true}).click();
    await codeDialog.getByRole("heading",{name:"Recurrencia",exact:true}).waitFor();
    const recurrenceDays = codeDialog.getByRole("spinbutton",{name:"Días de recurrencia",exact:true});
    assert.equal(await recurrenceDays.isDisabled(),true);
    await codeDialog.getByRole("checkbox",{name:"Comprar cada",exact:true}).check();
    assert.equal(await recurrenceDays.isDisabled(),false);
    await recurrenceDays.fill("12");
    assert.equal(await codeDialog.locator('[name="barcode"], [name="barcodes"], [name="nfc_tags"]').count(),0);
    await captureProductCode(readerPage,codeDialog,"barcode","https://example.test/cacao");
    await captureProductCode(readerPage,codeDialog,"barcode","0012345678906");
    await captureProductCode(readerPage,codeDialog,"barcode","0012345678906");
    assert.equal(await codeDialog.locator('#barcode-code-list .code-row').count(),3);
    await captureProductCode(readerPage,codeDialog,"nfc","AA:BB:CC:DD");
    await captureProductCode(readerPage,codeDialog,"nfc","aa-bb-cc-dd","AA:BB:CC:DD");
    await captureProductCode(readerPage,codeDialog,"nfc","tag-despensa");
    assert.equal(await codeDialog.locator('#nfc-code-list .code-row').count(),2);
    await captureProductCode(readerPage,codeDialog,"nfc","remove-me");
    await codeDialog.getByRole('button',{name:'Quitar código remove-me',exact:true}).click();
    assert.equal(await codeDialog.getByText('remove-me',{exact:true}).count(),0);
    assert.equal(await readerPage.evaluate(()=>window.captureListeners.size),0);
    assert.equal(await codeDialog.getByLabel('Cocina',{exact:true}).inputValue(),'default');
    assert.match(await codeDialog.getByLabel('Cocina',{exact:true}).locator('option:checked').textContent(),/Usar acción por defecto del lector.*Añadir a la lista/);
    await codeDialog.getByLabel("Cocina",{exact:true}).selectOption("add_list");
    await codeDialog.getByLabel("NFC despensa",{exact:true}).selectOption("stock_remove");
    await codeDialog.getByRole("button",{name:"Guardar producto",exact:true}).click();
    await codeDialog.waitFor({state:"hidden"});
    assert.equal(await readerCatalog.locator("#catalog-status").isVisible(),false);
    assert.equal(await readerCatalog.getByRole("button",{name:"Crear producto con el código 0012345678905",exact:true}).count(),0);
    assert.deepEqual(await readerPage.evaluate(()=>window.catalogProducts[0].barcodes),["https://example.test/cacao","0012345678906"]);
    assert.equal(await readerPage.evaluate(()=>Object.values(window.catalogProducts[0].reader_actions).includes("stock_remove")),true);
    assert.deepEqual(await readerPage.evaluate(()=>window.catalogProducts[0].recurrence),{enabled:true,days:12});
    await readerPage.evaluate(()=>{const reader=window.readerFixture.readers[1];window.readerFixture.pending=[{id:'scan-2',kind:'nfc',code:'11223344',reader_id:reader.id,reader_name:reader.name,time:new Date().toISOString()}];window.emitReaders();});
    assert.equal(await readerCatalog.locator('[data-pending-id="scan-2"] input').count(),0);
    await readerCatalog.getByRole("button",{name:"Asignar código 11223344 a un producto del catálogo",exact:true}).click();
    const assignDialog = readerCatalog.getByRole("dialog",{name:"Asignar código a un producto",exact:true});
    const assignButton = assignDialog.getByRole("button",{name:"Asignar",exact:true});
    const linkSearch = assignDialog.getByRole("combobox",{name:"Producto para el código 11223344",exact:true});
    assert.equal(await assignButton.isDisabled(),true);
    assert.equal(await readerCatalog.locator('[data-pending-id="scan-2"] input').count(),0);
    assert.equal(await readerCatalog.getByRole("button",{name:"Asignar código 11223344 a un producto del catálogo",exact:true}).evaluate(button=>getComputedStyle(button).backgroundColor),"rgb(25, 118, 210)");
    await linkSearch.fill("zzzz");
    await assignDialog.getByText("No hay productos que coincidan con la búsqueda.",{exact:true}).waitFor();
    await linkSearch.press("Enter");
    assert.equal(await assignButton.isDisabled(),true);
    await linkSearch.fill("CACÁO");
    await linkSearch.evaluate(input=>input.setSelectionRange(2,2));
    await readerPage.evaluate(()=>window.emitReaders());
    assert.equal(await linkSearch.inputValue(),"CACÁO");
    assert.equal(await linkSearch.evaluate(input=>input.getRootNode().activeElement===input && input.selectionStart===2),true);
    await linkSearch.press("Escape");
    assert.equal(await linkSearch.getAttribute("aria-expanded"),"false");
    assert.equal(await assignDialog.isVisible(),true);
    await linkSearch.press("ArrowDown");
    await linkSearch.press("Enter");
    assert.equal(await assignButton.isDisabled(),false);
    assert.equal(await linkSearch.inputValue(),"Cacao lector");
    assert.equal(await readerPage.evaluate(()=>window.catalogProducts[0].nfc_tags.includes('11223344')),false);
    await assignDialog.getByRole("button",{name:"Cancelar",exact:true}).click();
    assert.equal(await readerPage.evaluate(()=>window.catalogProducts[0].nfc_tags.includes('11223344')),false);
    await readerCatalog.getByRole("button",{name:"Asignar código 11223344 a un producto del catálogo",exact:true}).click();
    await assignDialog.getByRole("option",{name:"Cacao lector",exact:true}).click();
    await readerPage.evaluate(()=>{window.failCatalog=true;});
    await assignButton.click();
    await assignDialog.getByRole("alert").waitFor();
    assert.equal(await assignDialog.isVisible(),true);
    assert.equal(await assignButton.isDisabled(),false);
    assert.equal(await linkSearch.inputValue(),"Cacao lector");
    await readerPage.evaluate(()=>{window.failCatalog=false;});
    await assignButton.click();
    await assignDialog.waitFor({state:"hidden"});
    assert.equal(await readerCatalog.locator("#catalog-status").isVisible(),false);
    assert.equal(await readerPage.evaluate(()=>window.catalogProducts.length),1);
    assert.equal(await readerPage.evaluate(()=>window.catalogProducts[0].nfc_tags.includes('11223344')),true);
    assert.equal(await readerPage.evaluate(()=>Object.values(window.catalogProducts[0].reader_actions).includes('add_list')),true);
    assert.deepEqual(await readerPage.evaluate(()=>window.catalogProducts[0].recurrence),{enabled:true,days:12});
    await readerCatalog.getByRole('button',{name:'Productos',exact:true}).click();
    await readerPage.evaluate(()=>{window.savedReaderMetadata=window.readerFixture.readers;window.readerFixture.readers=[];window.emitReaders();});
    await editCatalogProduct(readerCatalog,'Editar Cacao lector');
    const inheritDialog=readerCatalog.getByRole('dialog',{name:'Editar producto',exact:true});
    await inheritDialog.getByRole('button',{name:'Automatización',exact:true}).click();
    // Late metadata restores only explicit saved exceptions, never another form's selection.
    await readerPage.evaluate(()=>{window.readerFixture.readers=window.savedReaderMetadata;window.emitReaders();});
    assert.equal(await inheritDialog.getByLabel('Cocina',{exact:true}).inputValue(),'add_list');
    assert.equal(await inheritDialog.getByLabel('NFC despensa',{exact:true}).inputValue(),'stock_remove');
    await inheritDialog.getByLabel('Cocina',{exact:true}).selectOption('default');
    await readerPage.evaluate(()=>{window.readerFixture.readers.find(reader=>reader.name==='Cocina').default_action='stock_add';window.emitReaders();});
    assert.equal(await inheritDialog.getByLabel('Cocina',{exact:true}).inputValue(),'default');
    assert.match(await inheritDialog.getByLabel('Cocina',{exact:true}).locator('option:checked').textContent(),/Añadir stock/);
    assert.equal(await inheritDialog.getByLabel('NFC despensa',{exact:true}).inputValue(),'stock_remove');
    await readerPage.evaluate(()=>{window.readerFixture.readers.find(reader=>reader.name==='Cocina').default_action='add_list';window.emitReaders();});
    await inheritDialog.getByRole('button',{name:'Guardar producto',exact:true}).click();
    await inheritDialog.waitFor({state:'hidden'});
    assert.equal(await readerPage.evaluate(()=>{
      const id=window.readerFixture.readers.find(reader=>reader.name==='Cocina').id;
      return Object.hasOwn(window.catalogProducts[0].reader_actions,id);
    }),false);
    assert.equal(await readerPage.evaluate(()=>Object.values(window.catalogProducts[0].reader_actions).includes('stock_remove')),true);
    await readerCatalog.getByRole('button',{name:'Nuevo producto',exact:true}).click();
    const defaultActionsDialog=readerCatalog.getByRole('dialog',{name:'Nuevo producto',exact:true});
    await defaultActionsDialog.getByRole('button',{name:'Automatización',exact:true}).click();
    assert.equal(await defaultActionsDialog.getByLabel('Cocina',{exact:true}).inputValue(),'default');
    assert.equal(await defaultActionsDialog.getByLabel('NFC despensa',{exact:true}).inputValue(),'default');
    await defaultActionsDialog.getByLabel('Cocina',{exact:true}).selectOption('none');
    await defaultActionsDialog.getByRole('button',{name:'Cerrar ventana',exact:true}).click();
    await readerCatalog.getByRole('button',{name:'Nuevo producto',exact:true}).click();
    await defaultActionsDialog.getByRole('button',{name:'Automatización',exact:true}).click();
    assert.equal(await defaultActionsDialog.getByLabel('Cocina',{exact:true}).inputValue(),'default');
    await defaultActionsDialog.getByRole('button',{name:'Cerrar ventana',exact:true}).click();
    await readerCatalog.getByRole('button',{name:'Nuevos',exact:true}).click();
    await readerPage.evaluate(()=>{window.readerFixture.pending=[{id:'scan-discard',kind:'barcode',code:'999999',reader_name:'Cocina',time:new Date().toISOString()}];window.emitReaders();});
    await readerCatalog.getByRole("button",{name:"Descartar código 999999",exact:true}).click();
    assert.equal(await readerCatalog.locator('#scan-suggestions [data-pending-id="scan-discard"]').count(),0);
    const localCacao = await readerPage.evaluate(async()=>{
      const product=structuredClone(window.catalogProducts[0]);
      delete product.id;delete product.revision;
      const result=await window.testPanel._hass.callWS({type:'improved_shopping_list/catalog/save',product:{...product,name:'Cacao',brand:'Marca local',format:'250 g',barcode:'',barcodes:[],nfc_tags:[],reader_actions:{}}});
      window.readerFixture.pending=[{id:'scan-off',kind:'barcode',code:'8410109115543',reader_name:'Cocina',identification:{status:'found',name:'Cacao soluble',product_name:'Cacao soluble comercial',brand:'Marca externa',quantity:'500 g'}}];
      window.emitReaders();
      return result.product.id;
    });
    const identified=readerCatalog.locator('#scan-suggestions [data-pending-id="scan-off"]');
    await identified.getByRole("heading",{name:"Cacao soluble",exact:true}).waitFor();
    await identified.getByText("Posible coincidencia: Cacao",{exact:true}).waitFor();
    assert.equal(await identified.getByRole("link").getAttribute("href"),"https://world.openfoodfacts.org/product/8410109115543");
    assert.equal(await readerPage.evaluate(()=>window.catalogProducts.length),2);
    await identified.getByRole("button",{name:"Crear producto con el código 8410109115543",exact:true}).click();
    assert.equal(await codeDialog.getByLabel("Nombre del producto",{exact:true}).inputValue(),"Cacao soluble");
    assert.equal(await codeDialog.getByLabel("Marca",{exact:true}).count(),0);
    assert.equal(await codeDialog.getByLabel("Formato",{exact:true}).count(),0);
    assert.equal(await identified.getByText("Marca externa · 500 g",{exact:true}).count(),0);
    await codeDialog.getByLabel("Nombre del producto",{exact:true}).fill("Nombre elegido por mí");
    await readerPage.evaluate(()=>window.emitReaders());
    assert.equal(await codeDialog.getByLabel("Nombre del producto",{exact:true}).inputValue(),"Nombre elegido por mí");
    await codeDialog.getByRole("button",{name:"Cerrar ventana",exact:true}).click();
    await identified.getByRole("button",{name:"Asignar código 8410109115543 a un producto del catálogo",exact:true}).click();
    assert.equal(await assignDialog.getByRole("option").first().textContent(),"Sugerido: Cacao");
    await readerPage.screenshot({path:"test-results/open-food-facts-suggestion.png",fullPage:true});
    await assignDialog.getByRole("option",{name:"Sugerido: Cacao",exact:true}).click();
    assert.equal(await assignDialog.locator("#link-code-selection").textContent(),"Producto seleccionado: Cacao");
    await assignButton.click();
    assert.equal(await identified.count(),0);
    assert.equal(await readerPage.evaluate(id=>window.catalogProducts.find(product=>product.id===id).barcode,localCacao),"8410109115543");
    assert.equal(await readerPage.evaluate(()=>window.catalogProducts.length),2);
    await readerPage.evaluate(()=>{window.readerFixture.pending=[{id:'scan-off-error',kind:'barcode',code:'3017620422003',reader_name:'Cocina',identification:{status:'error'}}];window.emitReaders();});
    await readerCatalog.getByText("Consulta no disponible. Puedes identificarlo manualmente.",{exact:true}).waitFor();
    await readerCatalog.getByRole("button",{name:"Crear producto con el código 3017620422003",exact:true}).click();
    assert.equal(await codeDialog.getByLabel("Nombre del producto",{exact:true}).inputValue(),"");
    assert.deepEqual(await codeDialog.locator("#barcode-code-list .code-value").allTextContents(),["3017620422003"]);
    await codeDialog.getByRole("button",{name:"Cerrar ventana",exact:true}).click();
    await readerPage.getByRole("button",{name:"Ajustes",exact:true}).click();
    await readerPage.locator("isl-settings").getByRole("button",{name:"Lectores",exact:true}).click();
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
    await readerPage.getByRole("button",{name:"Ajustes",exact:true}).click();
    await readerPage.locator("isl-settings").getByRole("button",{name:"Lectores",exact:true}).click();
    await readersView.getByRole("heading",{name:"NFC despensa",exact:true}).waitFor();
    await readersView.getByRole("button",{name:"Quitar lector NFC despensa",exact:true}).click();
    await readersView.getByRole("dialog",{name:"Quitar lector",exact:true}).getByRole("button",{name:"Quitar lector",exact:true}).click();
    await readersView.getByRole("status").filter({hasText:"Lector quitado"}).waitFor();
    assert.equal(await readerPage.evaluate(()=>window.readerFixture.readers.length),1);
    await readerContext.close();
    // Nutrition is code-specific, optional, lazy, and stale responses cannot cross product forms.
    const nutriContext = await browser.newContext({viewport:{width:390,height:844}});
    await nutriContext.route('https://static.openfoodfacts.org/**',route=>route.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 60"><rect width="120" height="60" fill="green"/></svg>'}));
    const nutriPage = await nutriContext.newPage();
    nutriPage.on('pageerror',error=>errors.push(error.message));
    await nutriPage.goto(url);
    await nutriPage.getByRole('button',{name:'Catálogo',exact:true}).click();
    const nutriCatalog=nutriPage.locator('isl-catalog');
    const nutriForm=nutriCatalog.locator('#product-form');
    await nutriCatalog.getByRole('button',{name:'Nuevo producto',exact:true}).click();
    assert.equal(await nutriPage.evaluate(()=>window.nutriCalls?.length??0),0);
    await nutriPage.evaluate(()=>{window.nutriFixture={'8410109115543':{grade:'a',version:'2023',checked_at:1800000000},'3017620422003':{grade:'d',checked_at:1800000000}};});
    await nutriForm.getByRole('button',{name:'Automatización',exact:true}).click();
    for(const code of ['8410109115543','08410109115543','3017620422003','https://private.test/qr','3017620422004'])await captureProductCode(nutriPage,nutriForm,'barcode',code);
    await captureProductCode(nutriPage,nutriForm,'nfc','AA:BB:CC:DD');
    await nutriForm.getByRole('button',{name:'Información adicional',exact:true}).click();
    await nutriForm.getByText('Nutri-Score: D',{exact:true}).waitFor();
    assert.equal(await nutriForm.locator('.nutriscore-item').count(),2);
    assert.deepEqual(await nutriPage.evaluate(()=>window.nutriCalls),['8410109115543','3017620422003']);
    await nutriForm.getByRole('button',{name:'Características',exact:true}).click();
    await nutriForm.getByRole('button',{name:'Información adicional',exact:true}).click();
    assert.equal(await nutriPage.evaluate(()=>window.nutriCalls.length),2);
    await nutriPage.evaluate(()=>{window.listSettings.stores={carrefour:{enabled:true}};window.emitSettings();});
    await nutriForm.getByRole('button',{name:'Automatización',exact:true}).click();
    await captureProductCode(nutriPage,nutriForm,'barcode','8431876279146');
    await nutriForm.getByRole('button',{name:'Información adicional',exact:true}).click();
    await nutriForm.locator('#store-price-results').getByRole('link').waitFor();
    assert.match(await nutriForm.locator('#store-price-results').textContent(),/Carrefour: 1,35/);
    assert.match(await nutriForm.locator('#store-price-results').getByRole('link').getAttribute('href'),/awin1.com\/pclick.php/);
    await nutriForm.locator('..').getByRole('button',{name:'Cerrar ventana',exact:true}).click();
    await nutriCatalog.getByRole('button',{name:'Nuevo producto',exact:true}).click();
    await nutriForm.getByRole('button',{name:'Automatización',exact:true}).click();
    await captureProductCode(nutriPage,nutriForm,'barcode','3017620422003');
    await nutriPage.evaluate(()=>{window.delayNutriCode='3017620422003';});
    await nutriForm.getByRole('button',{name:'Información adicional',exact:true}).click();
    await nutriPage.waitForFunction(()=>typeof window.releaseNutri==='function');
    await nutriForm.locator('..').getByRole('button',{name:'Cerrar ventana',exact:true}).click();
    await nutriCatalog.getByRole('button',{name:'Nuevo producto',exact:true}).click();
    await nutriPage.evaluate(()=>window.releaseNutri());
    await nutriForm.getByRole('button',{name:'Información adicional',exact:true}).click();
    assert.equal(await nutriForm.locator('#product-nutriscore').isVisible(),false);
    await nutriForm.getByRole('button',{name:'Automatización',exact:true}).click();
    const captureGroup=nutriForm.locator('#product-barcode-codes');
    await nutriPage.evaluate(()=>{window.failCapture=true;});
    await captureGroup.getByRole('button',{name:'Escanear',exact:true}).click();
    await captureGroup.getByRole('status').filter({hasText:'Lector ocupado'}).waitFor();
    await nutriPage.evaluate(()=>{window.failCapture=false;});
    await captureGroup.getByRole('button',{name:'Escanear',exact:true}).click();
    await nutriPage.evaluate(()=>{for(const callback of window.captureListeners.values())callback({status:'expired'});});
    await captureGroup.getByRole('status').filter({hasText:'Captura finalizada'}).waitFor();
    assert.equal(await nutriPage.evaluate(()=>window.captureListeners.size),0);
    await captureGroup.getByRole('button',{name:'Escanear',exact:true}).click();
    await nutriForm.locator('..').getByRole('button',{name:'Cerrar ventana',exact:true}).click();
    await nutriPage.waitForFunction(()=>window.captureListeners.size===0);
    await nutriContext.close();
    // Stock editor, units, modes, row-only controls, persistence and permissions.
    const stockContext=await browser.newContext({viewport:{width:1280,height:960}});
    await stockContext.addInitScript(()=>localStorage.setItem('catalog-fixture',JSON.stringify([{id:'stock-cacao',revision:1,name:'Cacao',category:'',tags:[],barcode:'',barcodes:[],nfc_tags:[],image_url:'',icon:'mdi:food',price:null,currency:'EUR'}])));
    const stockPage=await stockContext.newPage();stockPage.on('pageerror',error=>errors.push(error.message));
    await stockPage.goto(url);await stockPage.getByRole('button',{name:'Stock',exact:true}).click();
    const stockInput=stockPage.locator('#product-input');
    assert.equal(await stockInput.isVisible(),false);
    assert.equal(await stockPage.locator('#add-button').isVisible(),false);
    assert.equal(await stockPage.getByRole('button',{name:'Subir ticket',exact:true}).isVisible(),false);
    assert.equal(await stockPage.locator('#stock-heading h2').count(),0);
    await stockPage.getByRole('button',{name:'Añadir producto al stock',exact:true}).click();
    const stockAdd=stockPage.getByRole('dialog',{name:'Añadir producto al stock',exact:true});
    await stockAdd.getByLabel('Nombre del producto',{exact:true}).fill('Cacao');
    await stockPage.evaluate(()=>{window.failStock=true;});
    await stockAdd.getByRole('button',{name:'Añadir',exact:true}).click();
    await stockAdd.locator('#stock-add-error').filter({hasText:'No se ha podido guardar el stock'}).waitFor();
    assert.equal(await stockPage.evaluate(()=>window.stockItems.length),0);
    await stockPage.evaluate(()=>{window.failStock=false;});
    await stockAdd.getByLabel('Nombre del producto',{exact:true}).press('Enter');
    await stockAdd.waitFor({state:'hidden'});
    const stockCard=stockPage.locator('#stock-items li').filter({hasText:'Cacao'});
    await stockCard.getByLabel('Stock de Cacao: 1 uds',{exact:true}).waitFor();
    assert.equal(await stockPage.locator('#stock-count, #stock-units').count(),0);
    assert.equal(await stockPage.getByRole('button',{name:'Ordenar alfabéticamente',exact:true}).isVisible(),true);
    assert.equal(await stockCard.locator('.stock-controls, .stock-tools').count(),0);
    assert.equal(await stockCard.locator('.item').evaluate(node=>getComputedStyle(node).backgroundImage),'linear-gradient(rgb(245, 154, 35), rgb(198, 91, 12))');
    await selectList(stockPage,'todo.local');
    await stockCard.getByRole('button',{name:'Configurar stock de Cacao',exact:true}).click();
    const stockEditor=stockPage.getByRole('dialog',{name:'Cacao · Stock',exact:true}),stockForm=stockEditor.locator('form');
    for(const control of [stockForm.getByLabel('Stock actual',{exact:true}),stockForm.getByLabel('Unidades',{exact:true})])assert.equal(await control.evaluate(node=>getComputedStyle(node).textAlign),'center');
    await stockForm.getByRole('button',{name:'Incrementar stock',exact:true}).click();
    assert.equal(await stockForm.getByLabel('Stock actual',{exact:true}).inputValue(),'2');
    await stockForm.getByRole('button',{name:'Disminuir stock',exact:true}).click();
    await stockForm.getByLabel('Stock actual',{exact:true}).fill('2.5');
    await stockForm.getByLabel('Unidades',{exact:true}).selectOption('custom');
    await stockForm.getByLabel('Unidad personalizada',{exact:true}).fill('Latas');
    await stockForm.getByLabel('Control del stock',{exact:true}).selectOption('usage');
    assert.equal(await stockForm.locator('select[name="mode"] option:checked').textContent(),'Consumo registrado');
    await stockForm.getByLabel('Entidad de consumo',{exact:true}).fill('binary_sensor.lavadora');
    await stockForm.getByLabel('Estado que representa un uso',{exact:true}).fill('on');
    await stockForm.getByLabel('Cantidad consumida por uso',{exact:true}).fill('0.5');
    await stockForm.getByLabel('Cantidad que se suma al marcarlo como comprado',{exact:true}).fill('4');
    await stockForm.getByLabel('Añadir a la lista cuando el stock llegue al mínimo',{exact:true}).check();
    await stockForm.getByLabel('Stock mínimo',{exact:true}).fill('1');
    assert.equal(await stockForm.getByLabel('Lista para reponer',{exact:true}).inputValue(),'todo.local');
    await stockForm.getByRole('button',{name:'Guardar',exact:true}).click();await stockEditor.waitFor({state:'hidden'});
    await stockCard.getByLabel('Stock de Cacao: 2.5 Latas',{exact:true}).waitFor();
    assert.equal(await stockCard.getByRole('progressbar',{name:'Stock restante'}).getAttribute('aria-valuenow'),'63');
    assert.equal(await stockCard.locator('.stock-progress').evaluate(node=>node.style.getPropertyValue('--stock-remaining')),'62.5%');
    assert.deepEqual(await stockPage.evaluate(()=>({mode:window.stockItems[0].mode,unit:window.stockItems[0].unit,usage_amount:window.stockItems[0].usage_amount,refill_quantity:window.stockItems[0].refill_quantity})),{mode:'usage',unit:'Latas',usage_amount:0.5,refill_quantity:4});
    await stockCard.getByRole('button',{name:'Configurar stock de Cacao',exact:true}).click();
    await stockForm.getByLabel('Control del stock',{exact:true}).selectOption('perishable');
    await stockForm.getByLabel('Caduca cada cuántos días desde la compra',{exact:true}).fill('3');
    await stockForm.getByLabel('Porcentaje mínimo restante (%)',{exact:true}).fill('25');
    assert.equal(await stockForm.getByLabel('Porcentaje mínimo restante (%)',{exact:true}).getAttribute('max'),'100');
    assert.equal(await stockForm.locator('#stock-recurrence-help').count(),0);
    assert.equal(await stockForm.locator('#stock-usage-fields').isVisible(),false);
    for(const width of [390,320]){
      await stockPage.setViewportSize({width,height:844});
      assert.ok(await stockEditor.evaluate(dialog=>dialog.scrollWidth<=dialog.clientWidth+1));
      assert.ok(await stockForm.locator('.stock-expiry-refill').evaluate(row=>{
        const [days,refill]=row.querySelectorAll('input');
        return Math.abs(days.getBoundingClientRect().top-refill.getBoundingClientRect().top)<1;
      }));
      assert.ok(await stockForm.locator('.stock-reorder-row').evaluate(row=>{
        const [check,minimum]=row.querySelectorAll('label');
        return check.getBoundingClientRect().right<=minimum.getBoundingClientRect().left && Math.abs(check.getBoundingClientRect().top+check.getBoundingClientRect().height/2-minimum.getBoundingClientRect().top-minimum.getBoundingClientRect().height/2)<1;
      }));
      await stockPage.screenshot({path:'test-results/stock-editor-'+width+'.png',fullPage:true});
    }
    await stockForm.getByRole('button',{name:'Guardar',exact:true}).click();await stockEditor.waitFor({state:'hidden'});
    assert.equal(await stockPage.evaluate(()=>window.stockItems[0].reorder_percent),25);
    await stockPage.evaluate(()=>{
      const item=window.stockItems[0];item.quantity=3;item.expires_at=Date.now()/1000+item.days*86400;window.emitStock();
    });
    assert.equal(await stockCard.getByRole('progressbar',{name:'Stock restante'}).getAttribute('aria-valuenow'),'75');
    const highColor=await stockCard.locator('.item').evaluate(node=>getComputedStyle(node,'::before').backgroundImage);
    await stockPage.evaluate(()=>{window.stockItems[0].quantity=1;window.emitStock();});
    assert.equal(await stockCard.getByRole('progressbar',{name:'Stock restante'}).getAttribute('aria-valuenow'),'25');
    assert.notEqual(await stockCard.locator('.item').evaluate(node=>getComputedStyle(node,'::before').backgroundImage),highColor);
    await stockPage.evaluate(()=>{Object.assign(window.stockItems[0],{quantity:20,refill_quantity:250,unit:'g'});window.emitStock();});
    assert.equal(await stockCard.getByRole('progressbar',{name:'Stock restante'}).getAttribute('aria-valuenow'),'8');
    await stockPage.screenshot({path:'test-results/stock-perishable-eight-percent.png',fullPage:true});
    await stockPage.evaluate(()=>{Object.assign(window.stockItems[0],{quantity:2.5,refill_quantity:4,unit:'Latas'});window.emitStock();});
    await stockPage.getByRole('button',{name:'Cambiar a vista de filas',exact:true}).click();
    assert.ok(await stockCard.evaluate(card=>{
      const open=card.querySelector('.stock-open').getBoundingClientRect(),controls=card.querySelector('.stock-controls').getBoundingClientRect();
      return open.right<=controls.left && Math.abs((open.top+open.bottom-controls.top-controls.bottom)/2)<1;
    }));
    await stockCard.getByRole('button',{name:'Añadir una unidad de Cacao',exact:true}).click();
    await stockCard.getByLabel('Stock de Cacao: 3.5 Latas',{exact:true}).waitFor();
    await stockPage.evaluate(()=>{window.failStock=true;});
    await stockCard.getByRole('button',{name:'Añadir una unidad de Cacao',exact:true}).click();
    await stockPage.getByRole('alert').filter({hasText:'No se ha podido guardar el stock'}).waitFor();
    assert.equal(await stockPage.evaluate(()=>window.stockItems[0].quantity),3.5);
    await stockPage.evaluate(()=>{window.failStock=false;});
    for(let index=0;index<4;index++)await stockCard.getByRole('button',{name:'Quitar una unidad de Cacao',exact:true}).click();
    await stockCard.getByLabel('Stock de Cacao: 0 Latas',{exact:true}).waitFor();
    assert.equal(await stockCard.getByRole('button',{name:'Quitar una unidad de Cacao',exact:true}).isDisabled(),true);
    await stockPage.getByRole('button',{name:'Añadir producto al stock',exact:true}).click();
    await stockAdd.getByLabel('Nombre del producto',{exact:true}).fill('Producto sin catálogo');
    await stockAdd.getByRole('button',{name:'Añadir',exact:true}).click();
    await stockAdd.waitFor({state:'hidden'});
    await stockPage.reload();await stockPage.getByRole('button',{name:'Stock',exact:true}).click();
    await stockCard.getByLabel('Stock de Cacao: 0 Latas',{exact:true}).waitFor();
    assert.equal(await stockPage.evaluate(()=>window.stockItems[0].mode),'perishable');
    for(const width of [1280,390,320]){
      await stockPage.setViewportSize({width,height:844});
      assert.ok(await stockPage.locator('#stock-card').evaluate(node=>node.scrollWidth<=node.clientWidth+1));
      assert.ok(await stockPage.locator('#stock-heading').evaluate(node=>{
        const tabs=node.querySelector('.stock-tabs').getBoundingClientRect(),actions=node.querySelector('#stock-actions').getBoundingClientRect();
        return tabs.right<=actions.left&&Math.abs((tabs.top+tabs.bottom-actions.top-actions.bottom)/2)<2&&node.scrollWidth<=node.clientWidth+1;
      }));
      await stockPage.screenshot({path:'test-results/stock-rows-'+width+'.png',fullPage:true});
    }
    await stockPage.getByRole('button',{name:'Cambiar a vista de cuadrícula',exact:true}).click();
    assert.equal(await stockCard.locator('.stock-controls, .stock-tools').count(),0);
    await stockPage.screenshot({path:'test-results/stock-grid-mobile.png',fullPage:true});
    assert.deepEqual(await stockPage.locator('#stock-items .summary').allTextContents(),['Cacao','Producto sin catálogo']);
    await stockPage.getByRole('button',{name:'Ordenar alfabéticamente',exact:true}).click();
    // A second item sorts before Cacao alphabetically but after it by remaining stock.
    await stockPage.evaluate(()=>{window.stockItems[1].name='Arroz';window.emitStock();});
    assert.deepEqual(await stockPage.locator('#stock-items .summary').allTextContents(),['Arroz','Cacao']);
    await stockPage.getByRole('button',{name:'Agrupar por categorías',exact:true}).click();
    await stockPage.getByRole('button',{name:'Ordenar por menor stock',exact:true}).click();
    assert.deepEqual(await stockPage.locator('#stock-items .summary').allTextContents(),['Cacao','Arroz']);
    await stockPage.reload();await stockPage.getByRole('button',{name:'Stock',exact:true}).click();
    assert.equal(await stockPage.getByRole('button',{name:'Ordenar alfabéticamente',exact:true}).isVisible(),true);
    assert.equal(await stockCard.getByRole('progressbar',{name:'Stock restante'}).getAttribute('aria-valuenow'),'0');
    await stockCard.getByRole('button',{name:'Configurar stock de Cacao',exact:true}).click();
    await stockForm.getByRole('button',{name:'Eliminar producto del stock',exact:true}).click();
    const stockDelete=stockPage.getByRole('dialog',{name:'Eliminar de Stock',exact:true});
    await stockDelete.getByRole('button',{name:'Cancelar',exact:true}).click();
    assert.equal(await stockPage.locator('#stock-items li').count(),2);
    await stockForm.getByRole('button',{name:'Eliminar producto del stock',exact:true}).click();
    await stockDelete.getByRole('button',{name:'Eliminar producto',exact:true}).click();
    await stockCard.waitFor({state:'hidden'});await stockEditor.waitFor({state:'hidden'});
    assert.equal(await stockPage.evaluate(()=>window.catalogProducts.length),1);
    await stockPage.getByRole('button',{name:'Cambiar a vista de filas',exact:true}).click();
    await stockPage.evaluate(()=>{const panel=window.testPanel;panel.hass={...panel._hass,user:{is_admin:false}};});
    assert.equal(await stockInput.isDisabled(),true);
    assert.equal(await stockPage.locator('#stock-items [data-stock-action="increase"]').isDisabled(),true);
    await stockPage.locator('#stock-items .stock-open').click();
    assert.equal(await stockPage.locator('#save-stock-config').isDisabled(),true);
    await stockContext.close();
    // Numeric order compares percentages across units and modes, and is the initial default.
    const stockSortContext=await browser.newContext({viewport:{width:390,height:844}});
    await stockSortContext.addInitScript(()=>{
      if(!localStorage.getItem('stock-fixture'))localStorage.setItem('stock-fixture',JSON.stringify([
        {id:'sort-rice',name:'Arroz',quantity:1,refill_quantity:4,mode:'usage',unit:'kg',revision:1},
        {id:'sort-cacao',name:'Cacao',quantity:20,refill_quantity:250,mode:'perishable',unit:'g',revision:1},
        {id:'sort-cans',name:'Botes',quantity:50,refill_quantity:100,mode:'manual',unit:'uds',revision:1}
      ]));
    });
    const stockSortPage=await stockSortContext.newPage();
    stockSortPage.on('pageerror',error=>errors.push(error.message));
    await stockSortPage.goto(url);await stockSortPage.getByRole('button',{name:'Stock',exact:true}).click();
    const stockNames=stockSortPage.locator('#stock-items .summary');
    await stockNames.first().waitFor();
    assert.deepEqual(await stockNames.allTextContents(),['Cacao','Arroz','Botes']); // 8 %, 25 %, 50 %.
    await stockSortPage.getByRole('button',{name:'Ordenar alfabéticamente',exact:true}).click();
    assert.deepEqual(await stockNames.allTextContents(),['Arroz','Botes','Cacao']);
    await stockSortPage.reload();await stockSortPage.getByRole('button',{name:'Stock',exact:true}).click();
    await stockNames.first().waitFor();
    assert.deepEqual(await stockNames.allTextContents(),['Arroz','Botes','Cacao']);
    await stockSortPage.getByRole('button',{name:'Agrupar por categorías',exact:true}).click();
    await stockSortPage.getByRole('button',{name:'Ordenar por menor stock',exact:true}).click();
    assert.deepEqual(await stockNames.allTextContents(),['Cacao','Arroz','Botes']);
    await stockSortPage.reload();await stockSortPage.getByRole('button',{name:'Stock',exact:true}).click();
    await stockNames.first().waitFor();
    assert.deepEqual(await stockNames.allTextContents(),['Cacao','Arroz','Botes']);
    await stockSortContext.close();
    // Local PDF upload is a preview first; confirmed receipts survive reload and have a detail view.
    const purchaseContext=await browser.newContext({viewport:{width:390,height:844}});
    const purchasePage=await purchaseContext.newPage();purchasePage.on('pageerror',error=>errors.push(error.message));
    await purchasePage.route('**/local/receipt-seitan.svg',route=>route.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32"><circle cx="16" cy="16" r="15" fill="green"/></svg>'}));
    await purchasePage.goto(url);await purchasePage.getByRole('button',{name:'Stock',exact:true}).click();
    await purchasePage.getByRole('tab',{name:'Compras',exact:true}).click();
    const purchases=purchasePage.locator('isl-purchases');
    await purchases.getByText('Todavía no has subido ningún ticket.',{exact:true}).waitFor();
    assert.equal(await purchasePage.locator('#list-controls').isVisible(),false);
    assert.equal(await purchasePage.getByRole('button',{name:'Subir ticket',exact:true}).isVisible(),true);
    assert.equal(await purchasePage.getByRole('button',{name:'Añadir producto al stock',exact:true}).isVisible(),false);
    assert.equal(await purchasePage.getByRole('button',{name:'Seleccionar lista',exact:true}).isVisible(),false);
    const ticketFile={name:'ticket.pdf',mimeType:'application/pdf',buffer:Buffer.from('%PDF-fixture')};
    await purchases.locator('#ticket-file').setInputFiles(ticketFile);
    const review=purchases.getByRole('dialog',{name:'Revisar ticket',exact:true});await review.waitFor();
    assert.equal(await review.locator('#step-help').textContent(),'Vincula los productos detectados en el ticket con los de tu catálogo. Si no existen, puedes crear un producto nuevo o simplemente ignorarlos.');
    assert.equal(await purchasePage.evaluate(()=>window.receiptHistory.length),0);
    assert.equal(await review.locator('.review-line').count(),3);
    await review.getByRole('button',{name:'Cerrar ventana',exact:true}).click();
    assert.equal(await purchasePage.evaluate(()=>window.receiptHistory.length),0);
    await purchases.locator('#ticket-file').setInputFiles(ticketFile);await review.waitFor();
    assert.equal(await review.locator('#step-title').isVisible(),false);
    assert.equal(await review.locator('#review-steps [aria-current=step]').evaluate(button=>getComputedStyle(button).backgroundColor),'rgb(33, 150, 243)');
    assert.deepEqual(await review.locator('.review-line').evaluateAll(rows=>rows.map(row=>row.dataset.lineId)),['1','2','0']);
    assert.equal(await review.locator('#linked-products-group').evaluate(group=>group.open),false);
    assert.equal(await review.locator('#links-only').evaluate(button=>getComputedStyle(button).backgroundColor),'rgb(38, 112, 82)');
    assert.equal(await review.locator('#confirm-ticket').evaluate(button=>getComputedStyle(button).backgroundColor),'rgb(33, 150, 243)');
    const cerealLine=review.locator('[data-line-id="1"]');
    assert.equal(await review.locator('#step-help').textContent(),'Vincula los productos detectados en el ticket con los de tu catálogo. Si no existen, puedes crear un producto nuevo o simplemente ignorarlos.');
    assert.equal(await cerealLine.locator('input,.original').count(),0);
    assert.equal(await cerealLine.locator('.link').evaluate(node=>getComputedStyle(node).backgroundColor),'rgb(33, 150, 243)');
    assert.equal(await cerealLine.locator('.create').evaluate(node=>getComputedStyle(node).backgroundColor),'rgb(38, 112, 82)');
    await cerealLine.getByRole('button',{name:'Vincular producto para FLAUTIN CEREALES',exact:true}).click();
    const association=purchases.locator('#association-dialog');
    assert.equal(await association.locator('datalist option[value="Seitán"]').count(),0);
    await association.getByLabel('Producto del catálogo',{exact:true}).fill('Seitán');
    await association.getByRole('button',{name:'Vincular',exact:true}).click();
    await association.getByText('Este producto ya está vinculado a otra línea. Libera primero esa vinculación.',{exact:true}).waitFor();
    await purchasePage.screenshot({path:'test-results/receipt-link-dialog-mobile.png',fullPage:true});
    await association.getByRole('button',{name:'Cerrar ventana',exact:true}).click();
    await cerealLine.getByRole('button',{name:'Crear producto para FLAUTIN CEREALES',exact:true}).click();
    const receiptProduct=purchasePage.locator('isl-catalog').getByRole('dialog',{name:'Nuevo producto',exact:true});
    await receiptProduct.getByLabel('Nombre del producto',{exact:true}).fill('Flautines');
    await receiptProduct.getByRole('button',{name:'Guardar producto',exact:true}).click();
    await receiptProduct.waitFor({state:'hidden'});
    // Closing the catalog dialog precedes the receipt's asynchronous options refresh.
    await purchasePage.waitForFunction(()=>window.testPanel.shadowRoot.querySelector('isl-purchases')
      ?.shadowRoot.querySelector('[data-line-id="1"] .linked-name')?.textContent==='→ Flautines');
    assert.equal(await cerealLine.locator('.linked-name').textContent(),'→ Flautines');
    assert.equal(await review.locator('.ignore').count(),0);
    assert.equal(await review.locator('#linked-products-group').evaluate(group=>group.open),false);
    await review.locator('#linked-products-group > summary').click();
    const linkedReceiptLine=review.locator('[data-line-id="0"]');
    await linkedReceiptLine.locator('.association-image img').waitFor();
    assert.equal(await linkedReceiptLine.locator('.association-image img').getAttribute('src'),new URL('/local/receipt-seitan.svg',url).href);
    assert.ok(await linkedReceiptLine.evaluate(row=>row.querySelector('.association-image').getBoundingClientRect().right<=row.querySelector('.association-name').getBoundingClientRect().left));
    assert.equal(await review.locator('[data-line-id="2"] .association-image').count(),0);

    await cerealLine.getByRole('button',{name:'Vincular producto para FLAUTIN CEREALES',exact:true}).click();
    await association.getByLabel('Producto del catálogo',{exact:true}).fill('flautines');
    await association.getByRole('button',{name:'Vincular',exact:true}).click();
    await association.waitFor({state:'hidden'});
    assert.equal(await cerealLine.locator('.linked-name').textContent(),'→ Flautines');
    for(const width of [320,1280]){await purchasePage.setViewportSize({width,height:844});assert.ok(await review.evaluate(dialog=>dialog.scrollWidth<=dialog.clientWidth+1));assert.ok(await cerealLine.evaluate(row=>{const actions=row.querySelector('.association-buttons').getBoundingClientRect(),name=row.querySelector('.association-name').getBoundingClientRect();return (name.right<=actions.left||name.bottom<=actions.top)&&actions.right<=row.getBoundingClientRect().right&&row.scrollWidth<=row.clientWidth+1;}));}
    await purchasePage.screenshot({path:'test-results/receipt-link-lines-desktop.png',fullPage:true});
    await purchasePage.setViewportSize({width:390,height:844});
    await purchasePage.screenshot({path:'test-results/receipt-link-lines-mobile.png',fullPage:true});
    await review.getByRole('button',{name:'Guardar vinculaciones y cerrar',exact:true}).click();
    await review.waitFor({state:'hidden'});
    assert.equal(await purchasePage.evaluate(()=>window.receiptHistory.length),0);
    assert.equal(await purchasePage.evaluate(()=>window.stockItems.length),0);
    assert.equal(await purchasePage.evaluate(()=>window.receiptLinks.filter(line=>line.product_id).length),2);
    await purchases.locator('#ticket-file').setInputFiles(ticketFile);await review.waitFor();
    assert.equal(await cerealLine.locator('.linked-name').textContent(),'→ Flautines');
    await review.getByRole('button',{name:'Continuar',exact:true}).click();
    await review.locator('#stock-only').waitFor();
    assert.equal(await review.locator('#step-title').isVisible(),false);
    assert.equal(await review.locator('#step-help').textContent(),'Marca aquellos productos que quieres añadir al registro de stock.');
    assert.equal(await review.getByRole('button',{name:'Volver a vinculación',exact:true}).isVisible(),true);
    assert.equal(await review.locator('#unregistered-stock-group').evaluate(group=>group.open),false);
    assert.deepEqual(await review.locator('.review-line').evaluateAll(rows=>rows.map(row=>row.dataset.lineId)),['0','1']);
    assert.equal(await review.locator('[data-line-id="0"] .stock-select').getAttribute('aria-pressed'),'true');
    await review.locator('#unregistered-stock-group > summary').click();
    assert.equal(await cerealLine.locator('.stock-select').getAttribute('aria-pressed'),'false');
    assert.equal(await cerealLine.locator('input[type=checkbox],.original').count(),0);
    assert.equal(await cerealLine.textContent().then(text=>text.includes('€')),false);
    assert.equal(await review.locator('#stock-only').evaluate(button=>getComputedStyle(button).backgroundColor),'rgb(38, 112, 82)');
    assert.equal(await review.locator('#confirm-ticket').evaluate(button=>getComputedStyle(button).backgroundColor),'rgb(33, 150, 243)');
    await cerealLine.click({position:{x:8,y:8}});
    assert.equal(await cerealLine.locator('.stock-select').getAttribute('aria-pressed'),'true');
    assert.equal(await cerealLine.evaluate(row=>getComputedStyle(row).borderColor),'rgb(255, 152, 0)');
    assert.equal(await review.locator('[data-line-id="0"] .association-image img').getAttribute('src'),new URL('/local/receipt-seitan.svg',url).href);
    for(const width of [320,390,1280]){
      await purchasePage.setViewportSize({width,height:844});
      assert.equal(await review.locator('#review-lines').evaluate(el=>getComputedStyle(el).gridTemplateColumns.split(' ').length),2);
      assert.ok(await review.locator('.stock-line-main').evaluateAll(rows=>rows.every(row=>row.scrollWidth<=row.clientWidth+1)));
      assert.ok(await review.locator('.stock-line-main').evaluateAll(rows=>rows.every(row=>{const name=row.querySelector('.stock-line-name').getBoundingClientRect(),fields=row.querySelector('.stock-quantity').getBoundingClientRect(),quantity=row.querySelector('.stock-quantity input').getBoundingClientRect(),unit=row.querySelector('.stock-quantity').lastElementChild.getBoundingClientRect();return name.right<=fields.left&&Math.abs((name.top+name.bottom-fields.top-fields.bottom)/2)<1&&quantity.right<=unit.left&&Math.abs((quantity.top+quantity.bottom-unit.top-unit.bottom)/2)<1;})));
      assert.ok(await review.evaluate(el=>el.scrollWidth<=el.clientWidth+1));
    }
    await purchasePage.setViewportSize({width:390,height:844});
    await review.getByRole('button',{name:'Volver a vinculación',exact:true}).click();
    assert.equal(await review.locator('#linked-products-group').evaluate(group=>group.open),false);
    await review.getByRole('button',{name:'Continuar',exact:true}).click();
    assert.equal(await cerealLine.locator('.stock-select').getAttribute('aria-pressed'),'true');
    assert.equal(await review.locator('#unregistered-stock-group').evaluate(group=>group.open),true);
    assert.equal(await review.getByRole('button',{name:'1. Vinculación',exact:true}).evaluate(button=>getComputedStyle(button).backgroundColor),'rgb(38, 112, 82)');
    assert.equal(await review.getByRole('button',{name:'2. Stock',exact:true}).getAttribute('aria-current'),'step');
    assert.equal(await review.getByRole('button',{name:'3. Precios',exact:true}).isDisabled(),true);
    await review.getByRole('button',{name:'1. Vinculación',exact:true}).click();
    assert.equal(await review.locator('#links-only').isVisible(),true);
    assert.equal(await review.getByRole('button',{name:'1. Vinculación',exact:true}).getAttribute('aria-current'),'step');
    await review.getByRole('button',{name:'Continuar',exact:true}).click();
    assert.equal(await cerealLine.getByLabel('Cantidad para FLAUTIN CEREALES',{exact:true}).inputValue(),'2');
    assert.equal(await cerealLine.locator('.stock-select').getAttribute('aria-pressed'),'true');
    assert.equal(await cerealLine.getByLabel('Cantidad para FLAUTIN CEREALES',{exact:true}).inputValue(),'2');
    await purchasePage.screenshot({path:'test-results/receipt-wizard-stock-mobile.png',fullPage:true});
    assert.ok(await review.evaluate(el=>el.scrollWidth<=el.clientWidth+1));
    await review.getByRole('button',{name:'Continuar',exact:true}).click();
    assert.equal(await review.locator('#step-title').isVisible(),false);
    assert.equal(await review.locator('#step-help').textContent(),'Selecciona los productos cuyo precio quieres actualizar en el catálogo, para esta tienda.');
    assert.equal(await review.locator('[data-line-id="2"]').count(),0);
    assert.equal(await review.locator('[data-line-id="0"] .price-product-name strong').textContent(),'Seitán');
    assert.equal(await review.locator('[data-line-id="0"] .association-image img').getAttribute('src'),new URL('/local/receipt-seitan.svg',url).href);
    assert.equal(await review.locator('input[type=checkbox]').count(),1);
    assert.match(await review.locator('[data-line-id="0"] .price-value').textContent(),/2,65.*3,80/);
    assert.equal(await review.locator('[data-line-id="0"] .price-value del').count(),1);
    assert.equal(await cerealLine.locator('.price-value del').count(),0);
    assert.ok(await review.locator('.select-all-prices').evaluate(el=>Math.abs(el.getBoundingClientRect().right-el.parentElement.getBoundingClientRect().right)<1));
    const priceToggle=review.getByRole('button',{name:'Guardar precio de Seitán',exact:true});
    await priceToggle.click();assert.equal(await priceToggle.getAttribute('aria-pressed'),'false');
    await review.getByLabel('Seleccionar todos los precios',{exact:true}).check();
    assert.equal(await priceToggle.getAttribute('aria-pressed'),'true');
    const selectedPriceColor=await review.locator('[data-line-id="0"]').evaluate(el=>getComputedStyle(el).backgroundColor);
    await priceToggle.click();assert.equal(await priceToggle.getAttribute('aria-pressed'),'false');
    assert.notEqual(await review.locator('[data-line-id="0"]').evaluate(el=>getComputedStyle(el).backgroundColor),selectedPriceColor);
    for(const width of [320,390,1280]){await purchasePage.setViewportSize({width,height:844});assert.equal(await review.locator('#review-lines').evaluate(el=>getComputedStyle(el).gridTemplateColumns.split(' ').length),2);assert.ok(await review.evaluate(el=>el.scrollWidth<=el.clientWidth+1));}
    await purchasePage.setViewportSize({width:390,height:844});
    assert.equal(await review.locator('#review-steps [data-completed=true]').count(),2);
    await review.getByRole('button',{name:'2. Stock',exact:true}).focus();
    await review.getByRole('button',{name:'2. Stock',exact:true}).press('Enter');
    assert.equal(await review.locator('#stock-only').isVisible(),true);
    await review.getByRole('button',{name:'Continuar',exact:true}).click();
    assert.equal(await review.getByRole('button',{name:'Guardar precio de Seitán',exact:true}).getAttribute('aria-pressed'),'false');
    await purchasePage.screenshot({path:'test-results/receipt-wizard-prices-mobile.png',fullPage:true});
    assert.equal(await review.locator('#review-result').isVisible(),false);
    assert.equal(await review.getByRole('button',{name:'Actualizar precios y cerrar',exact:true}).isVisible(),true);
    await review.getByRole('button',{name:'Continuar',exact:true}).click();
    assert.equal(await review.locator('#review-result').isVisible(),true);
    assert.equal(await review.locator('#review-lines').isVisible(),false);
    assert.equal(await review.locator('#review-steps [data-completed=true]').count(),3);
    assert.equal(await purchasePage.evaluate(()=>window.receiptHistory.length),0);
    await review.getByRole('button',{name:'3. Precios',exact:true}).click();
    assert.equal(await review.getByRole('button',{name:'Guardar precio de Seitán',exact:true}).getAttribute('aria-pressed'),'false');
    await review.getByRole('button',{name:'Continuar',exact:true}).click();
    for(const width of [320,390,1280]){await purchasePage.setViewportSize({width,height:844});assert.ok(await review.evaluate(el=>el.scrollWidth<=el.clientWidth+1));}
    await purchasePage.setViewportSize({width:390,height:844});
    await purchasePage.screenshot({path:'test-results/receipt-wizard-summary-mobile.png',fullPage:true});
    await purchasePage.evaluate(()=>{window.failReceipt=true;});
    await review.getByRole('button',{name:'Confirmar compra',exact:true}).click();
    await review.getByText('No se ha podido guardar el ticket.',{exact:true}).waitFor();
    assert.equal(await purchasePage.evaluate(()=>window.receiptHistory.length),0);
    await purchasePage.evaluate(()=>{window.failReceipt=false;});
    await review.getByRole('button',{name:'Confirmar compra',exact:true}).click();
    await review.waitFor({state:'hidden'});await purchases.locator('#history .ticket-open').click();
    const confirmed=await purchasePage.evaluate(()=>window.lastReceiptConfirmation);
    assert.equal(confirmed.lines[0].save_price,false);assert.equal(confirmed.lines[1].save_price,true);
    assert.equal(confirmed.lines[1].quantity,2);assert.equal(confirmed.lines[1].unit,'uds');
    assert.equal(await purchasePage.evaluate(()=>window.stockItems.find(item=>item.name==='Flautines').quantity),2);
    await purchases.getByText('Seitán: 250 g repuestos',{exact:true}).waitFor();
    assert.ok(await purchases.evaluate(el=>el.scrollWidth<=el.clientWidth+1));
    await purchasePage.screenshot({path:'test-results/purchase-history-mobile.png',fullPage:true});
    await purchases.locator('#ticket-file').setInputFiles(ticketFile);
    await purchases.getByText('Este ticket ya se ha importado.',{exact:true}).waitFor();
    await purchasePage.reload();await purchasePage.getByRole('button',{name:'Stock',exact:true}).click();
    await purchasePage.getByRole('tab',{name:'Compras',exact:true}).click();
    await purchases.locator('#history .ticket-open').waitFor();
    await purchasePage.getByRole('tab',{name:'Stock',exact:true}).click();
    assert.equal(await purchasePage.locator('#list-controls').isVisible(),false);
    assert.equal(await purchasePage.getByRole('button',{name:'Subir ticket',exact:true}).isVisible(),false);
    assert.equal(await purchasePage.getByRole('button',{name:'Añadir producto al stock',exact:true}).isVisible(),true);
    await purchasePage.getByRole('button',{name:'Lista',exact:true}).click();
    assert.equal(await purchasePage.locator('#product-input').isVisible(),true);
    assert.equal(await purchasePage.getByRole('button',{name:'Seleccionar lista',exact:true}).isVisible(),true);
    await purchaseContext.close();
    // Finishing at Stock records one purchase and replenishes without saving prices.
    const stockOnlyContext=await browser.newContext({viewport:{width:390,height:844}});
    const stockOnlyPage=await stockOnlyContext.newPage();stockOnlyPage.on('pageerror',error=>errors.push(error.message));
    await stockOnlyPage.goto(url);await stockOnlyPage.getByRole('button',{name:'Stock',exact:true}).click();
    await stockOnlyPage.getByRole('tab',{name:'Compras',exact:true}).click();
    const stockOnlyPurchases=stockOnlyPage.locator('isl-purchases');
    await stockOnlyPurchases.locator('#ticket-file').setInputFiles(ticketFile);
    const stockOnlyReview=stockOnlyPurchases.getByRole('dialog',{name:'Revisar ticket',exact:true});await stockOnlyReview.waitFor();
    await stockOnlyReview.getByRole('button',{name:'Continuar',exact:true}).click();
    assert.equal(await stockOnlyReview.locator('#unregistered-stock-group').count(),0);
    await stockOnlyPage.evaluate(()=>{window.failReceipt=true;});
    await stockOnlyReview.getByRole('button',{name:'Añadir stock y cerrar',exact:true}).click();
    await stockOnlyReview.locator('#review-error').filter({hasText:'No se ha podido guardar el ticket.'}).waitFor();
    assert.equal(await stockOnlyPage.evaluate(()=>window.receiptHistory.length),0);
    await stockOnlyPage.evaluate(()=>{window.failReceipt=false;});
    await stockOnlyReview.getByRole('button',{name:'Añadir stock y cerrar',exact:true}).click();
    await stockOnlyReview.waitFor({state:'hidden'});
    assert.equal(await stockOnlyPage.evaluate(()=>window.lastReceiptConfirmation.update_prices),false);
    assert.equal(await stockOnlyPage.evaluate(()=>window.lastReceiptConfirmation.lines.some(line=>line.save_price)),false);
    assert.equal(await stockOnlyPage.evaluate(()=>window.stockItems.find(item=>item.catalog_product_id==='cacao').quantity),250);
    assert.equal(await stockOnlyPage.evaluate(()=>window.receiptHistory.length),1);
    await stockOnlyContext.close();

    // Purchase history uses a ticket button for details and stacks monthly spend by store.
    const spendingContext=await browser.newContext({viewport:{width:390,height:844}});
    await spendingContext.route('https://images.seeklogo.com/**',route=>route.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32"><circle cx="16" cy="16" r="14" fill="blue"/></svg>'}));
    const spendingPage=await spendingContext.newPage();spendingPage.on('pageerror',error=>errors.push(error.message));
    await spendingPage.addInitScript(()=>{
      const receipts=[['j1','carrefour','Carrefour','2026-01-10T12:00:00',10.25],['j2','mercadona','Mercadona','2026-01-15T12:00:00',20],['j3','carrefour','Carrefour','2026-01-20T12:00:00',5.5],['f1','mercadona','Mercadona','2026-02-15T12:00:00',40]];
      localStorage.setItem('receipt-fixture',JSON.stringify(receipts.map(([id,store,store_name,purchased_at,total])=>({id,store,store_name,purchased_at,total,article_count:1,lines:[{description:'Producto '+id,count:1,unit_price:total,amount:total}]}))));
    });
    await spendingPage.goto(url);await spendingPage.getByRole('button',{name:'Stock',exact:true}).click();await spendingPage.getByRole('tab',{name:'Compras',exact:true}).click();
    const spending=spendingPage.locator('isl-purchases');await spending.locator('#history .ticket').first().waitFor();
    assert.equal(await spending.locator('#history details,#history summary').count(),0);
    assert.equal(await spending.locator('#history .ticket').count(),4);
    const firstPurchase=spending.locator('#history .ticket').first();
    assert.match(await firstPurchase.locator('.store-image').getAttribute('src'),/carrefour-logo/);
    assert.ok(await firstPurchase.evaluate(card=>card.querySelector('.total').getBoundingClientRect().right<=card.querySelector('.ticket-open').getBoundingClientRect().left));
    await firstPurchase.locator('.title').click();assert.equal(await spending.locator('#purchase-detail').isVisible(),false);
    await firstPurchase.locator('.ticket-open').focus();await firstPurchase.locator('.ticket-open').press('Enter');
    const purchaseDetail=spending.getByRole('dialog',{name:'Detalle de la compra',exact:true});await purchaseDetail.waitFor();
    await purchaseDetail.getByText('Producto j1',{exact:true}).waitFor();
    await purchaseDetail.getByRole('button',{name:'Cerrar ventana',exact:true}).click();
    assert.equal(await spending.locator('.month-column').count(),6);
    const defaultMonths=await spendingPage.evaluate(()=>{const now=new Date();return Array.from({length:6},(_,i)=>{const month=new Date(now.getFullYear(),now.getMonth()-5+i,1);return month.getFullYear()+'-'+String(month.getMonth()+1).padStart(2,'0');});});
    assert.deepEqual(await spending.locator('.month-column').evaluateAll(columns=>columns.map(column=>column.dataset.month)),defaultMonths);
    const previousPeriod=spending.getByRole('button',{name:'Mostrar seis meses anteriores',exact:true});
    const nextPeriod=spending.getByRole('button',{name:'Mostrar seis meses siguientes',exact:true});
    assert.equal(await nextPeriod.isDisabled(),true);
    while(!await spending.locator('.month-column[data-month="2026-01"]').count())await previousPeriod.click();
    const jan=spending.locator('.month-column[data-month="2026-01"]'),feb=spending.locator('.month-column[data-month="2026-02"]');
    assert.equal(await jan.getAttribute('data-total'),'35.75');assert.equal(await feb.getAttribute('data-total'),'40');
    assert.equal(await jan.locator('[data-store="carrefour"]').getAttribute('data-amount'),'15.75');
    assert.equal(await jan.locator('[data-store="mercadona"]').getAttribute('data-amount'),'20');
    assert.equal(await jan.locator('.store-segment').count(),2);assert.equal(await feb.locator('.store-segment').count(),1);
    assert.match(await jan.getAttribute('aria-label'),/Carrefour.*15,75.*Mercadona.*20,00/);
    assert.equal(await previousPeriod.isDisabled(),true);
    while(!await nextPeriod.isDisabled())await nextPeriod.click();
    assert.deepEqual(await spending.locator('.month-column').evaluateAll(columns=>columns.map(column=>column.dataset.month)),defaultMonths);
    for(const width of [320,390,1280]){
      await spendingPage.setViewportSize({width,height:844});
      assert.ok(await spending.evaluate(el=>el.scrollWidth<=el.clientWidth+1));
      assert.ok(await spending.locator('.monthly-bars').evaluate(el=>Math.abs(el.getBoundingClientRect().width-el.parentElement.getBoundingClientRect().width)<1));
      assert.equal(await spending.locator('.month-column').count(),6);
    }
    await spendingPage.screenshot({path:'test-results/purchases-monthly-chart-desktop.png',fullPage:true});
    await spendingPage.setViewportSize({width:390,height:844});await spendingPage.screenshot({path:'test-results/purchases-monthly-chart-mobile.png',fullPage:true});
    await firstPurchase.locator('.ticket-open').click();await spendingPage.screenshot({path:'test-results/purchase-detail-mobile.png',fullPage:true});
    await spendingContext.close();

    // Store bindings persist without barcodes; all product-price UI reads use cache.
    const linksContext=await browser.newContext({viewport:{width:390,height:844}});
    const linksPage=await linksContext.newPage();
    linksPage.on('pageerror',error=>errors.push(error.message));
    await linksPage.goto(url);
    await linksPage.getByRole('button',{name:'Catálogo',exact:true}).click();
    const linksCatalog=linksPage.locator('isl-catalog');
    await linksCatalog.getByRole('button',{name:'Nuevo producto',exact:true}).click();
    const linksForm=linksCatalog.locator('#product-form');
    await linksForm.getByLabel('Nombre del producto',{exact:true}).fill('Arroz vinculado');
    await linksForm.getByRole('button',{name:'Información adicional',exact:true}).click();
    await linksForm.getByLabel('Tienda del producto',{exact:true}).selectOption('mercadona');
    await linksForm.getByLabel('Enlace o ID del producto',{exact:true}).fill('69938');
    await linksForm.getByRole('button',{name:'Añadir vinculación',exact:true}).click();
    await linksForm.getByLabel('Tienda del producto',{exact:true}).selectOption('alcampo');
    await linksForm.getByLabel('Enlace o ID del producto',{exact:true}).fill('https://www.compraonline.alcampo.es/products/arroz/24097');
    await linksForm.getByLabel('Enlace o ID del producto',{exact:true}).press('Enter');
    assert.equal(await linksPage.evaluate(()=>window.catalogProducts.length),0);
    assert.equal(await linksForm.getByLabel('Enlace o ID de Mercadona',{exact:true}).inputValue(),'69938');
    assert.equal(await linksForm.locator('.store-reference').count(),2);
    assert.equal(await linksForm.locator('.store-reference img').count(),2);
    assert.equal(await linksForm.locator('#product-store-links label').count(),0);
    assert.equal(await linksForm.getByRole('button',{name:'Quitar vinculación de Mercadona',exact:true}).evaluate(node=>getComputedStyle(node).backgroundColor),'rgb(211, 47, 47)');
    assert.ok(await linksForm.locator('.product-store-link').first().evaluate(row=>{
      const [store,input,remove]=[...row.children].map(node=>node.getBoundingClientRect());
      return store.right<=input.left && input.right<=remove.left && Math.abs(store.top-input.top)<1;
    }));
    await linksPage.screenshot({path:'test-results/store-links-mobile.png',fullPage:true});
    assert.ok(await linksCatalog.locator('dialog[open]').evaluate(dialog=>dialog.scrollWidth<=dialog.clientWidth+1));
    await linksForm.getByRole('button',{name:'Guardar producto',exact:true}).click();
    assert.equal(await linksPage.evaluate(()=>window.catalogProducts[0].barcode),'');
    assert.equal(await linksPage.evaluate(()=>window.catalogProducts[0].store_links.mercadona),'69938');
    await editCatalogProduct(linksCatalog,'Editar Arroz vinculado');
    await linksForm.getByRole('button',{name:'Información adicional',exact:true}).click();
    assert.match(await linksForm.getByLabel('Enlace o ID de Alcampo',{exact:true}).inputValue(),/24097$/);
    await linksForm.getByRole('button',{name:'Quitar vinculación de Mercadona',exact:true}).click();
    await linksForm.getByRole('button',{name:'Guardar producto',exact:true}).click();
    assert.equal(await linksPage.evaluate(()=>window.catalogProducts[0].store_links.mercadona),undefined);
    await linksPage.getByRole('button',{name:'Ajustes',exact:true}).click();
    const linkedSettings=linksPage.locator('isl-settings');
    await linkedSettings.getByRole('button',{name:'Tiendas',exact:true}).click();
    await linkedSettings.getByRole('button',{name:'Actualización de precios',exact:true}).click();
    const priceScheduleDialog=linkedSettings.getByRole('dialog',{name:'Actualización de precios',exact:true});
    await priceScheduleDialog.waitFor();
    assert.equal(await priceScheduleDialog.getByRole("button",{name:"Cancelar",exact:true}).count(),0);
    assert.ok(await priceScheduleDialog.locator('.price-config-row').evaluateAll(rows=>rows.every(row=>{
      const label=row.querySelector('label').getBoundingClientRect(),input=row.querySelector('input').getBoundingClientRect();
      return label.right<=input.left && input.top<label.bottom && label.top<input.bottom;
    })));
    await priceScheduleDialog.getByLabel('Frecuencia de actualización (días)',{exact:true}).fill('3');
    await linkedSettings.locator('#price-update-time').fill('02:30');
    await linkedSettings.getByRole('button',{name:'Guardar',exact:true}).click();
    await linksPage.waitForFunction(()=>window.listSettings.price_update_time==='02:30' && window.listSettings.price_update_days===3);
    await priceScheduleDialog.waitFor({state:'hidden'});
    await linkedSettings.getByRole('button',{name:'Actualización de precios',exact:true}).click();
    assert.equal(await linkedSettings.locator('#price-update-time').inputValue(),'02:30');
    assert.equal(await priceScheduleDialog.getByLabel('Frecuencia de actualización (días)',{exact:true}).inputValue(),'3');
    await priceScheduleDialog.getByRole('switch',{name:'Actualización automática de precios',exact:true}).uncheck();
    await priceScheduleDialog.getByRole('button',{name:'Guardar',exact:true}).click();
    await priceScheduleDialog.waitFor({state:'hidden'});
    assert.equal(await linkedSettings.getByRole('button',{name:'Actualizar ahora',exact:true}).isDisabled(),true);
    assert.equal(await linksPage.locator('#pending-total').evaluate(node=>node.hidden),true);
    await linkedSettings.getByRole('button',{name:'Actualización de precios',exact:true}).click();
    await priceScheduleDialog.getByRole('switch',{name:'Actualización automática de precios',exact:true}).check();
    await priceScheduleDialog.getByRole('button',{name:'Guardar',exact:true}).click();
    await priceScheduleDialog.waitFor({state:'hidden'});
    await linkedSettings.getByRole('button',{name:'Actualización de precios',exact:true}).click();
    await priceScheduleDialog.getByRole('button',{name:'Cerrar ventana',exact:true}).click();
    await linkedSettings.getByLabel('Habilitar Alcampo',{exact:true}).check();
    await linkedSettings.getByRole('button',{name:'Ajustes de Alcampo',exact:true}).click();
    const alcampoDialog=linkedSettings.getByRole('dialog',{name:'Alcampo',exact:true});
    assert.equal(await alcampoDialog.locator('input,select').count(),0);
    await alcampoDialog.getByRole('button',{name:'Cerrar ventana',exact:true}).click();
    assert.equal(await linkedSettings.getByRole('button',{name:'Código postal de las tiendas',exact:true}).count(),0);
    await linksContext.close();
    // Clearing completed items uses the native provider action, with no effect on pending items.
    const clearContext = await browser.newContext({viewport:{width:320,height:844}});
    const clearPage = await clearContext.newPage();
    clearPage.on("pageerror", error => errors.push(error.message));
    await clearPage.goto(url);
    const clearButton = clearPage.getByRole("button",{name:"Limpiar productos",exact:true});
    await clearButton.waitFor();
    assert.equal(await clearButton.isDisabled(),true);
    await clearPage.evaluate(()=>{
      const panel=window.testPanel;
      panel.hass={...panel._hass,states:{...panel._hass.states,'todo.bring':{...panel._hass.states['todo.bring'],attributes:{...panel._hass.states['todo.bring'].attributes,supported_features:7}}}};
    });
    assert.ok(await clearButton.evaluate(button=>{
      const row=button.closest('summary').getBoundingClientRect();const rect=button.getBoundingClientRect();
      return Math.abs(row.right-rect.right)<1 && rect.right<=innerWidth && rect.width>0;
    }));
    await clearPage.evaluate(()=>{window.fail=true;});
    await clearButton.click();
    await clearPage.getByRole('alert').filter({hasText:'Proveedor sin conexión'}).waitFor();
    assert.equal(await clearPage.evaluate(()=>window.listData['todo.bring'].filter(item=>item.status==='completed').length),1);
    assert.equal(await clearPage.locator('#completed-details').evaluate(node=>node.open),false);
    await clearPage.evaluate(()=>{window.fail=false;window.delayClear=true;});
    await clearButton.click();
    await clearPage.waitForFunction(()=>typeof window.releaseClear==='function');
    assert.equal(await clearButton.isDisabled(),true);
    await clearPage.evaluate(()=>window.releaseClear());
    await clearPage.locator('#completed-details').waitFor({state:'hidden'});
    assert.equal(await clearPage.locator('#pending > li').count(),2);
    assert.equal(await clearPage.evaluate(()=>window.listData['todo.local'].length),1);
    assert.equal(await clearPage.evaluate(()=>window.calls.filter(call=>call.service==='remove_completed_items').length),1);
    await clearContext.close();
    // Automatic picker: up to six suggestions, no search field or pagination.
    const iconContext = await browser.newContext({viewport:{width:1280,height:960}});
    const iconPage = await iconContext.newPage();
    iconPage.on("pageerror", error => errors.push(error.message));
    await iconPage.route("https://api.iconify.design/**", route => route.fulfill({contentType:"image/svg+xml",body:'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path fill="#267052" d="M4 4h16v16H4z"/></svg>'}));
    await iconPage.goto(url);
    await iconPage.getByRole("button",{name:"Catálogo",exact:true}).click();
    const iconCatalog = iconPage.locator("isl-catalog");
    const iconForm = iconCatalog.getByRole("dialog",{name:"Nuevo producto",exact:true});
    const picker = iconCatalog.locator("isl-icon-picker");
    const pickerDialog = picker;
    await iconCatalog.getByRole("button",{name:"Nuevo producto",exact:true}).click();
    await iconForm.getByLabel("Nombre del producto",{exact:true}).fill("Leche");
    await pickerDialog.getByRole("button",{name:"Elegir Milk 1 (Fluent Emoji Flat)",exact:true}).waitFor();
    assert.equal(await picker.getByRole("button",{name:"Buscar icono",exact:true}).count(),0);
    assert.equal(await picker.locator("dialog").count(),0);
    assert.deepEqual(await picker.locator("button.option").allTextContents(),["","","","","",""]);
    assert.equal(await pickerDialog.locator(".option").count(),6);
    assert.equal(await pickerDialog.locator("button.option").count(),6);
    assert.equal(await pickerDialog.getByLabel("Buscar iconos",{exact:true}).count(),0);
    assert.equal(await pickerDialog.locator('#more-icons').count(),0);
    assert.equal(await pickerDialog.getByText('Las sugerencias se actualizan con el nombre del producto.',{exact:false}).count(),0);
    await pickerDialog.getByRole('button',{name:'Elegir Milk 6 (Fluent Emoji Flat)',exact:true}).waitFor();
    assert.equal(await iconPage.evaluate(()=>window.iconCalls.length),1);
    // Product-name changes drive suggestions and stale responses cannot replace them.
    await iconForm.getByLabel('Nombre del producto',{exact:true}).fill('slow');
    await iconPage.waitForFunction(()=>typeof window.releaseIconSearch==='function');
    await iconForm.getByLabel('Nombre del producto',{exact:true}).fill('Leche');
    await pickerDialog.getByRole('button',{name:'Elegir Milk 1 (Fluent Emoji Flat)',exact:true}).waitFor();
    await iconPage.evaluate(()=>window.releaseIconSearch());
    assert.equal(await pickerDialog.getByRole('button',{name:'Elegir slow 1 (Fluent Emoji Flat)',exact:true}).count(),0);
    assert.equal(await iconPage.evaluate(()=>window.catalogProducts.length),0);
    await iconPage.evaluate(()=>{window.failIconSearch=true;});
    await iconForm.getByLabel('Nombre del producto',{exact:true}).fill('Pan');
    await pickerDialog.getByRole('status').filter({hasText:'Iconify sin conexión'}).waitFor();
    await iconPage.evaluate(()=>{window.failIconSearch=false;});
    await iconForm.getByLabel('Nombre del producto',{exact:true}).fill('zzzz');
    await pickerDialog.getByRole('status').filter({hasText:'No se han encontrado iconos. Puedes indicar una URL Imagen/Icono.'}).waitFor();
    assert.equal(await pickerDialog.locator('button.option').count(),0);
    await iconForm.getByLabel('Nombre del producto',{exact:true}).fill('few');
    await pickerDialog.getByRole('button',{name:'Elegir few 1 (Fluent Emoji Flat)',exact:true}).waitFor();
    assert.equal(await pickerDialog.locator('button.option').count(),3);
    await iconForm.getByLabel('Nombre del producto',{exact:true}).fill('Leche');
    await pickerDialog.getByRole('button',{name:'Elegir Milk 1 (Fluent Emoji Flat)',exact:true}).waitFor();
    await iconPage.evaluate(()=>{window.failIconImport=true;});
    await pickerDialog.getByRole("button",{name:"Elegir Milk 1 (Fluent Emoji Flat)",exact:true}).click();
    await pickerDialog.getByRole("status").filter({hasText:"No se ha podido guardar"}).waitFor();
    assert.equal(await iconForm.getByLabel("URL Imagen/Icono",{exact:true}).inputValue(),"");
    await iconPage.evaluate(()=>{window.failIconImport=false;});
    await iconPage.screenshot({path:"test-results/icon-picker-desktop.png",fullPage:true});
    await iconPage.setViewportSize({width:320,height:844});
    assert.equal(await pickerDialog.evaluate(dialog=>dialog.scrollWidth<=dialog.clientWidth),true);
    await iconPage.screenshot({path:"test-results/icon-picker-mobile.png",fullPage:true});
    assert.equal(await pickerDialog.evaluate(dialog=>dialog.scrollWidth<=dialog.clientWidth),true);
    await pickerDialog.getByRole("button",{name:"Elegir Milk 1 (Fluent Emoji Flat)",exact:true}).click();
    await picker.getByRole("link",{name:"MIT",exact:true}).waitFor();
    assert.equal(await picker.locator("button.option").count(),6);
    assert.equal(await iconForm.getByLabel("URL Imagen/Icono",{exact:true}).inputValue(),"/improved_shopping_list_icons/fixture.svg");
    await picker.getByRole("link",{name:"MIT",exact:true}).waitFor();
    assert.equal(await iconPage.evaluate(()=>window.catalogProducts.length),0);
    await iconForm.getByRole("button",{name:"Guardar producto",exact:true}).click();
    await iconCatalog.getByRole("heading",{name:"Leche",exact:true}).waitFor();
    const savedIconProduct = await iconPage.evaluate(()=>structuredClone(window.catalogProducts[0]));
    assert.equal(savedIconProduct.name,"Leche");
    assert.equal(savedIconProduct.name_en,"Milk");
    assert.equal(savedIconProduct.image_url,"/improved_shopping_list_icons/fixture.svg");
    await iconCatalog.locator(".product img").evaluate(image=>image.decode());
    // The chosen file and its attribution survive a panel reload without accessing the provider.
    await iconPage.reload();
    await iconPage.getByRole("button",{name:"Catálogo",exact:true}).click();
    await editCatalogProduct(iconCatalog,"Editar Leche");
    const editIconForm = iconCatalog.getByRole("dialog",{name:"Editar producto",exact:true});
    await picker.getByRole("link",{name:"MIT",exact:true}).waitFor();
    assert.equal(await editIconForm.getByLabel("URL Imagen/Icono",{exact:true}).inputValue(),savedIconProduct.image_url);
    await pickerDialog.getByRole("button",{name:"Elegir Milk 1 (Fluent Emoji Flat)",exact:true}).waitFor();
    assert.equal(await iconPage.evaluate(()=>window.iconCalls?.length??0),1);
    // Cancel a download, open a different draft, then resolve the old request: it must not change the draft.
    await pickerDialog.getByRole("button",{name:"Elegir Milk 1 (Fluent Emoji Flat)",exact:true}).waitFor();
    assert.equal(await pickerDialog.getByLabel("Buscar iconos",{exact:true}).count(),0);
    // Editing the displayed name must not reuse an English term for a different product.
    await editIconForm.getByLabel("Nombre del producto",{exact:true}).fill("Pan");
    await pickerDialog.getByRole("button",{name:"Elegir Bread 1 (Fluent Emoji Flat)",exact:true}).waitFor();
    await editIconForm.getByLabel("Nombre del producto",{exact:true}).fill("Leche");
    await pickerDialog.getByRole("button",{name:"Elegir Milk 1 (Fluent Emoji Flat)",exact:true}).waitFor();
    await iconPage.evaluate(()=>{window.delayIconImport=true;});
    await pickerDialog.getByRole("button",{name:"Elegir Milk 1 (Fluent Emoji Flat)",exact:true}).click();
    await iconPage.waitForFunction(()=>typeof window.releaseIconImport==='function');
    assert.equal(await editIconForm.getByRole("button",{name:"Guardar producto",exact:true}).isDisabled(),true);
    await editIconForm.getByRole("button",{name:"Cerrar ventana",exact:true}).click();
    await iconCatalog.getByRole("button",{name:"Nuevo producto",exact:true}).click();
    await iconForm.getByLabel("Nombre del producto",{exact:true}).fill("Pan");
    await iconPage.evaluate(()=>window.releaseIconImport());
    assert.equal(await iconForm.getByLabel("URL Imagen/Icono",{exact:true}).inputValue(),"");
    assert.equal(await iconForm.getByLabel("Nombre del producto",{exact:true}).inputValue(),"Pan");
    await iconForm.getByRole("button",{name:"Cerrar ventana",exact:true}).click();
    // Clicking the tile adds to the provider; deleting through the editor preserves the list.
    await iconCatalog.locator("#catalog-grid .product .add-product").click({position:{x:8,y:8}});
    await iconPage.waitForFunction(()=>window.listData['todo.bring'].some(item=>item.summary==='Leche'&&item.status==='needs_action'));
    const providerCallsBeforeDelete = await iconPage.evaluate(()=>window.calls.length);
    assert.equal(await iconCatalog.getByRole("button",{name:"Eliminar Leche",exact:true}).count(),0);
    await editCatalogProduct(iconCatalog,"Editar Leche");
    const productEditor = iconCatalog.locator('#product-form');
    assert.equal(await productEditor.getByRole("button",{name:"Cancelar",exact:true}).count(),0);
    assert.ok(await productEditor.locator(".product-actions").evaluate(node=>{
      const remove=node.querySelector("#delete-product").getBoundingClientRect(),save=node.querySelector("#save-product").getBoundingClientRect();
      return remove.right<=save.left&&Math.abs(remove.top-save.top)<1;
    }));
    await productEditor.getByRole("button",{name:"Eliminar producto",exact:true}).click();
    const deleteProductDialog = iconCatalog.getByRole("dialog",{name:"Eliminar producto",exact:true});
    await deleteProductDialog.getByRole("button",{name:"Cancelar",exact:true}).click();
    assert.equal(await productEditor.isVisible(),true);
    assert.equal(await iconPage.evaluate(()=>window.catalogProducts.length),1);
    await productEditor.getByRole("button",{name:"Eliminar producto",exact:true}).click();
    await iconPage.evaluate(()=>{window.failDeleteProduct=true;});
    await deleteProductDialog.getByRole("button",{name:"Eliminar producto",exact:true}).click();
    await deleteProductDialog.getByRole("alert").filter({hasText:"No se ha podido eliminar"}).waitFor();
    assert.equal(await iconPage.evaluate(()=>window.catalogProducts.length),1);
    await iconPage.evaluate(()=>{window.failDeleteProduct=false;});
    await deleteProductDialog.getByRole("button",{name:"Eliminar producto",exact:true}).click();
    await deleteProductDialog.waitFor({state:"hidden"});
    await productEditor.waitFor({state:'hidden'});
    assert.equal(await iconCatalog.locator("#catalog-status").isVisible(),false);
    assert.equal(await iconPage.evaluate(()=>window.catalogProducts.length),0);
    assert.equal(await iconPage.evaluate(()=>window.calls.length),providerCallsBeforeDelete);
    assert.equal(await iconPage.evaluate(()=>window.listData['todo.bring'].some(item=>item.summary==='Leche')),true);
    await iconPage.reload();
    await iconPage.getByRole("button",{name:"Catálogo",exact:true}).click();
    await iconCatalog.getByText("Tu catálogo empieza aquí.",{exact:false}).waitFor();
    await iconContext.close();
    // Older products without name_en translate on first search and retain the result.
    const oldIconContext=await browser.newContext({viewport:{width:1280,height:960}});
    const oldIconPage=await oldIconContext.newPage();
    oldIconPage.on('pageerror',error=>errors.push(error.message));
    await oldIconPage.route('https://api.iconify.design/**',route=>route.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path fill="#f9a825" d="M2 2h20v20H2z"/></svg>'}));
    await oldIconPage.goto(url);
    await oldIconPage.getByRole('button',{name:'Catálogo',exact:true}).click();
    const oldCatalog=oldIconPage.locator('isl-catalog');
    await oldCatalog.getByRole('button',{name:'Nuevo producto',exact:true}).click();
    await oldCatalog.locator('#product-form').getByLabel('Nombre del producto',{exact:true}).fill('Arroz');
    await oldCatalog.locator('#product-form').getByRole('button',{name:'Guardar producto',exact:true}).click();
    await oldCatalog.getByRole('heading',{name:'Arroz',exact:true}).waitFor();
    assert.equal(await oldIconPage.evaluate(()=>window.catalogProducts[0].name_en),'');
    await editCatalogProduct(oldCatalog,'Editar Arroz');
    const oldPicker=oldCatalog.locator('isl-icon-picker');
    await oldPicker.getByRole('button',{name:'Elegir Rice 1 (Fluent Emoji Flat)',exact:true}).waitFor();
    assert.equal(await oldPicker.getByLabel('Buscar iconos',{exact:true}).count(),0);
    assert.equal(await oldIconPage.evaluate(()=>window.catalogProducts[0].name_en),'Rice');
    assert.equal(await oldIconPage.evaluate(()=>window.iconCalls.at(-1).translate),true);
    await oldCatalog.locator('#product-form').locator('..').getByRole('button',{name:'Cerrar ventana',exact:true}).click();
    await oldIconPage.reload();
    await oldIconPage.getByRole('button',{name:'Catálogo',exact:true}).click();
    await editCatalogProduct(oldCatalog,'Editar Arroz');
    await oldPicker.getByRole('button',{name:'Elegir Rice 1 (Fluent Emoji Flat)',exact:true}).waitFor();
    assert.equal(await oldIconPage.evaluate(()=>window.iconCalls.at(-1).translate),false);
    // A hand-entered URL wins over an in-flight icon import, and persists on save/reload.
    const customImage='https://example.test/custom-icon.svg';
    await oldIconContext.route(customImage,route=>route.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path fill="#f9a825" d="M2 2h20v20H2z"/></svg>'}));
    await oldIconPage.evaluate(()=>{window.delayIconImport=true;});
    await oldPicker.getByRole('button',{name:'Elegir Rice 1 (Fluent Emoji Flat)',exact:true}).click();
    await oldIconPage.waitForFunction(()=>typeof window.releaseIconImport==='function');
    await oldCatalog.locator('#product-form').getByLabel('URL Imagen/Icono',{exact:true}).fill(customImage);
    await oldIconPage.evaluate(()=>window.releaseIconImport());
    assert.equal(await oldCatalog.locator('#product-form').getByLabel('URL Imagen/Icono',{exact:true}).inputValue(),customImage);
    assert.equal(await oldCatalog.getByRole('button',{name:'Guardar producto',exact:true}).isDisabled(),false);
    await oldCatalog.getByRole('button',{name:'Guardar producto',exact:true}).click();
    await oldCatalog.getByRole('heading',{name:'Arroz',exact:true}).waitFor();
    await oldIconPage.reload();
    await oldIconPage.getByRole('button',{name:'Catálogo',exact:true}).click();
    assert.equal(await oldIconPage.evaluate(()=>window.catalogProducts[0].image_url),customImage);
    await editCatalogProduct(oldCatalog,'Editar Arroz');
    assert.equal(await oldCatalog.locator('#product-form').getByLabel('URL Imagen/Icono',{exact:true}).inputValue(),customImage);
    await oldIconContext.close();
    // Correcting a list suggestion renames original UIDs, preserving status and avoiding catalog duplicates on retry.
    const renameContext=await browser.newContext({viewport:{width:1280,height:960}});
    const renamePage=await renameContext.newPage();
    renamePage.on("pageerror",error=>errors.push(error.message));
    await renamePage.goto(url);
    await renamePage.evaluate(()=>{
      window.listData['todo.bring']=[
        {uid:'seitan-1',summary:'Seitan',status:'needs_action',description:'Conservar descripción'},
        {uid:'seitan-2',summary:'SEITÁN',status:'completed'},
        {uid:'avocado',summary:'Aguacat',status:'needs_action'},
      ];
      window.listData['todo.local']=[{uid:'other-seitan',summary:'Seitan',status:'needs_action'}];
      window.emit('todo.bring');
    });
    await renamePage.getByRole("button",{name:"Catálogo",exact:true}).click();
    const renameCatalog=renamePage.locator("isl-catalog");
    await renameCatalog.getByRole("button",{name:"Nuevos",exact:true}).click();
    await renameCatalog.locator("#list-suggestions-summary").click();
    const renameSuggestions=renameCatalog.locator("#list-suggestions");
    assert.deepEqual(await renameSuggestions.locator("h2").allTextContents(),["Aguacat","Seitan"]);
    await renameSuggestions.getByRole("button",{name:"Añadir al catálogo: Seitan",exact:true}).click();
    const renameForm=renameCatalog.locator("#product-form");
    await renameForm.getByLabel("Nombre del producto",{exact:true}).fill("Seitán");
    assert.equal(await renameForm.getByLabel("Icono del producto",{exact:true}).count(),0);
    await renamePage.evaluate(()=>{window.fail=true;});
    await renameForm.getByRole("button",{name:"Guardar producto",exact:true}).click();
    await renameForm.getByRole("alert").filter({hasText:"guardado en el catálogo, pero"}).waitFor();
    assert.equal(await renamePage.evaluate(()=>window.catalogProducts.length),1);
    assert.equal(await renamePage.evaluate(()=>window.listData['todo.bring'][0].summary),"Seitan");
    await renamePage.evaluate(()=>{window.fail=false;});
    await renameForm.getByRole("button",{name:"Guardar producto",exact:true}).click();
    await renameCatalog.locator('dialog[aria-labelledby="product-dialog-title"]').waitFor({state:"hidden"});
    assert.equal(await renameCatalog.locator("#catalog-status").isVisible(),false);
    assert.equal(await renamePage.evaluate(()=>window.catalogProducts.length),1);
    assert.deepEqual(await renamePage.evaluate(()=>window.listData['todo.bring'].slice(0,2)),[
      {uid:'seitan-1',summary:'Seitán',status:'needs_action',description:'Conservar descripción'},
      {uid:'seitan-2',summary:'Seitán',status:'completed'},
    ]);
    assert.equal(await renamePage.evaluate(()=>window.listData['todo.local'][0].summary),"Seitan");
    assert.deepEqual(await renameSuggestions.locator("h2").allTextContents(),["Aguacat"]);
    assert.equal(await renamePage.evaluate(()=>window.calls.every(call=>call.service==='update_item'&&call.rename==='Seitán'&&!('status' in call))),true);
    await renameSuggestions.getByRole("button",{name:"Añadir al catálogo: Aguacat",exact:true}).click();
    await renameForm.getByLabel("Nombre del producto",{exact:true}).fill("Aguacate");
    await renameForm.getByRole("button",{name:"Guardar producto",exact:true}).click();
    await renameCatalog.locator('dialog[aria-labelledby="product-dialog-title"]').waitFor({state:"hidden"});
    assert.equal(await renameCatalog.locator("#catalog-status").isVisible(),false);
    assert.equal(await renamePage.evaluate(()=>window.listData['todo.bring'].find(item=>item.uid==='avocado').summary),"Aguacate");
    assert.equal(await renameSuggestions.locator("h2").count(),0);
    // Later accent/case variants remain associated with the catalog and do not become suggestions.
    await renamePage.evaluate(()=>{
      window.listData['todo.bring'].push({uid:'seitan-later',summary:'sEiTaN',status:'needs_action'});
      window.emit('todo.bring');
    });
    assert.equal(await renameSuggestions.locator("h2").count(),0);
    await renamePage.getByRole("button",{name:"Lista",exact:true}).click();
    assert.equal(await renamePage.getByRole("button",{name:"Marcar como comprado: sEiTaN",exact:true}).locator(".placeholder ha-icon").getAttribute("icon"),"mdi:shopping");
    await renamePage.evaluate(()=>{window.listData['todo.bring'].push({uid:'tea-1',summary:'Té',status:'needs_action'});window.emit('todo.bring');});
    await renamePage.getByRole("button",{name:"Catálogo",exact:true}).click();
    await renameSuggestions.getByRole("button",{name:"Descartar: Té",exact:true}).click();
    await renamePage.evaluate(()=>{window.listData['todo.bring'].push({uid:'tea-2',summary:'TE',status:'needs_action'});window.emit('todo.bring');});
    assert.equal(await renameSuggestions.locator("h2").count(),0);
    await renameContext.close();
    // Category grouping sorts headings and products, preserves searching, layouts and user preference.
    const notificationContext=await browser.newContext({viewport:{width:1280,height:960}});
    const notificationPage=await notificationContext.newPage();notificationPage.on('pageerror',error=>errors.push(error.message));
    await notificationPage.goto(url);await notificationPage.getByRole('button',{name:'Ajustes',exact:true}).click();
    const notificationSettings=notificationPage.locator('isl-settings');
    await notificationSettings.getByRole('button',{name:'Notificaciones',exact:true}).click();
    const notifications=notificationSettings.locator('isl-notification-settings'),listRule=notifications.locator('[data-rule=shopping_list]'),stockRule=notifications.locator('[data-rule=low_stock]');
    assert.equal(await notificationSettings.locator('#settings-view-notifications ha-icon').getAttribute('icon'),'mdi:bell-outline');
    await listRule.getByRole('checkbox',{name:'Activar aviso de Lista de la compra',exact:true}).check();
    await listRule.getByLabel('Límite de productos de Lista de la compra',{exact:true}).fill('5');
    await listRule.locator('input[value="service:notify.mobile_app_one"]').check();await listRule.locator('input[value="service:notify.mobile_app_two"]').check();
    await listRule.getByLabel('Título',{exact:true}).fill('Compra: {lista}');await listRule.getByLabel('Mensaje',{exact:true}).fill('{cantidad} productos: {productos}');
    await stockRule.getByRole('checkbox',{name:'Activar aviso de Stock bajo',exact:true}).check();await stockRule.getByLabel('Límite de productos de Stock bajo',{exact:true}).fill('0');
    await stockRule.locator('input[value="entity:notify.kitchen"]').check();
    const newProductsRule=notifications.locator('[data-rule=catalog_new]');
    assert.equal(await newProductsRule.getByRole('checkbox',{name:'Activar aviso de Productos nuevos',exact:true}).isChecked(),false);
    assert.equal(await newProductsRule.getByLabel('Límite de productos de Productos nuevos',{exact:true}).inputValue(),'0');
    await newProductsRule.getByRole('checkbox',{name:'Activar aviso de Productos nuevos',exact:true}).check();
    await newProductsRule.getByLabel('Límite de productos de Productos nuevos',{exact:true}).fill('3');
    await newProductsRule.locator('input[value="service:notify.mobile_app_one"]').check();
    await newProductsRule.getByLabel('Mensaje',{exact:true}).fill('{cantidad} pendientes de catálogo: {productos}');
    assert.equal(await notifications.locator('input[value="service:notify.notify"]').count(),0);
    await notifications.getByRole('button',{name:'Guardar notificaciones',exact:true}).click();
    await notificationPage.waitForFunction(()=>window.listSettings.notifications?.shopping_list?.threshold===5);
    assert.deepEqual(await notificationPage.evaluate(()=>window.listSettings.notifications.shopping_list.targets),['service:notify.mobile_app_two','service:notify.mobile_app_one']);
    assert.deepEqual(await notificationPage.evaluate(()=>window.listSettings.notifications.low_stock.targets),['entity:notify.kitchen']);
    assert.equal(await notificationPage.evaluate(()=>window.listSettings.notifications.catalog_new.threshold),3);
    await notificationPage.reload();await notificationPage.getByRole('button',{name:'Ajustes',exact:true}).click();await notificationSettings.getByRole('button',{name:'Notificaciones',exact:true}).click();
    assert.equal(await listRule.getByLabel('Título',{exact:true}).inputValue(),'Compra: {lista}');assert.equal(await listRule.getByLabel('Límite de productos de Lista de la compra',{exact:true}).inputValue(),'5');
    assert.equal(await listRule.locator('input[value="service:notify.mobile_app_one"]').isChecked(),true);
    assert.equal(await newProductsRule.getByRole('checkbox',{name:'Activar aviso de Productos nuevos',exact:true}).isChecked(),true);
    assert.equal(await newProductsRule.getByLabel('Mensaje',{exact:true}).inputValue(),'{cantidad} pendientes de catálogo: {productos}');
    await notificationPage.evaluate(()=>{window.failSettings=true;});await listRule.getByLabel('Mensaje',{exact:true}).fill('Nuevo mensaje');
    await notifications.getByRole('button',{name:'Guardar notificaciones',exact:true}).click();await notifications.getByRole('alert').filter({hasText:'No se han podido guardar'}).waitFor();
    assert.equal(await listRule.getByLabel('Mensaje',{exact:true}).inputValue(),'Nuevo mensaje');
    await notificationPage.evaluate(()=>{window.failSettings=false;});await notifications.getByRole('button',{name:'Guardar notificaciones',exact:true}).click();
    await notificationPage.waitForFunction(()=>window.listSettings.notifications.shopping_list.message==='Nuevo mensaje');
    for(const width of [390,320]){await notificationPage.setViewportSize({width,height:844});assert.ok(await notifications.evaluate(node=>node.scrollWidth<=node.clientWidth+1));assert.equal(await notificationSettings.locator('.settings-tabs .tab-label:visible').count(),1);await notificationPage.screenshot({path:'test-results/notifications-'+width+'.png',fullPage:true});}
    assert.equal(await notificationPage.evaluate(()=>window.calls.some(call=>call.domain==='notify')),false);
    await notificationPage.evaluate(()=>{window.testPanel.hass={...window.testPanel._hass,user:{is_admin:false}};});
    assert.equal(await notifications.getByRole('button',{name:'Guardar notificaciones',exact:true}).isDisabled(),true);
    await notificationContext.close();

    const recipeContext=await browser.newContext({viewport:{width:1280,height:960}});
    const recipePage=await recipeContext.newPage();recipePage.on('pageerror',error=>errors.push(error.message));
    await recipePage.addInitScript(()=>{
      if(localStorage.getItem('recipe-test-ready'))return;localStorage.setItem('recipe-test-ready','1');
      localStorage.setItem('catalog-fixture',JSON.stringify([
        {id:'recipe-cacao',name:'Cacao',unit_quantity:100},{id:'recipe-pavo',name:'Pavo',unit_quantity:250}
      ].map(product=>({...product,revision:1,category:'',tags:[],notes:'',price:null,currency:'EUR',barcode:'',barcodes:[],nfc_tags:[],reader_actions:{},purchase_unit:'g',quantity_step:10,image_url:'',icon:''}))));
    });
    await recipePage.goto(url);await recipePage.getByRole('button',{name:'Catálogo',exact:true}).click();
    const recipeCatalog=recipePage.locator('isl-catalog'),recipeEditor=recipeCatalog.locator('isl-recipe-editor');
    await recipeCatalog.getByRole('button',{name:'Recetas',exact:true}).click();
    await recipeCatalog.getByRole('button',{name:'Nueva receta',exact:true}).click();
    const recipeDialog=recipeEditor.getByRole('dialog',{name:'Nueva receta',exact:true});
    await recipeDialog.getByLabel('Nombre de la receta',{exact:true}).fill('Desayuno');
    await recipePage.route('**/local/recipe-test.svg',route=>route.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64"><circle cx="32" cy="32" r="30" fill="green"/></svg>'}));
    await recipeDialog.getByLabel('URL Imagen',{exact:true}).fill('/local/recipe-test.svg');

    await recipeDialog.getByLabel('Producto del catálogo',{exact:true}).fill('Cacao');
    await recipeDialog.getByLabel('Producto del catálogo',{exact:true}).press('Enter');
    await recipeDialog.getByLabel('Cantidad de Cacao',{exact:true}).fill('30');
    await recipeDialog.getByLabel('Producto del catálogo',{exact:true}).fill('Pavo');
    await recipeDialog.getByRole('button',{name:'Añadir ingrediente',exact:true}).click();
    await recipeDialog.getByLabel('Cantidad de Pavo',{exact:true}).fill('200');
    assert.deepEqual(await recipeDialog.locator('.unit').allTextContents(),['g','g']);
    assert.equal(await recipeDialog.getByLabel('Cantidad de Cacao',{exact:true}).evaluate(input=>getComputedStyle(input).textAlign),'center');
    await recipeDialog.getByRole('button',{name:'Guardar receta',exact:true}).click();await recipeDialog.waitFor({state:'hidden'});
    const recipeCard=recipeCatalog.locator('#recipe-grid .recipe-card');await recipeCard.waitFor();
    assert.equal(await recipeCard.locator('img.image').getAttribute('src'),new URL('/local/recipe-test.svg',url).href);
    assert.equal(await recipeCard.evaluate(node=>getComputedStyle(node).backgroundImage),'linear-gradient(rgb(102, 187, 106), rgb(46, 125, 50))');
    await recipeCard.getByRole('button',{name:'Añadir receta Desayuno a la lista',exact:true}).click();
    await recipePage.waitForFunction(()=>window.quantityEntries['todo.bring']?.['cacao-1']?.quantity===130);
    await recipeCard.getByRole('button',{name:'Añadir receta Desayuno a la lista',exact:true}).click();
    await recipePage.waitForFunction(()=>window.quantityEntries['todo.bring']?.['cacao-1']?.quantity===160);
    assert.equal(await recipePage.evaluate(()=>window.listData['todo.bring'].filter(item=>item.summary==='Pavo').length),1);
    assert.equal(await recipePage.evaluate(()=>{const item=window.listData['todo.bring'].find(item=>item.summary==='Pavo');return window.quantityEntries['todo.bring'][item.uid].quantity;}),400);
    for(const width of [390,320]){await recipePage.setViewportSize({width,height:844});assert.ok(await recipeCard.evaluate(node=>Math.abs(node.getBoundingClientRect().width-node.getBoundingClientRect().height)<1));await recipePage.screenshot({path:'test-results/recipes-'+width+'.png',fullPage:true});}
    await recipeCard.getByRole('button',{name:'Editar receta Desayuno',exact:true}).click();
    const editRecipe=recipeEditor.getByRole('dialog',{name:'Editar receta',exact:true});
    assert.equal(await editRecipe.getByLabel('URL Imagen',{exact:true}).inputValue(),'/local/recipe-test.svg');
    await editRecipe.getByLabel('Nombre de la receta',{exact:true}).fill('Almuerzo');await editRecipe.getByLabel('Cantidad de Pavo',{exact:true}).fill('300');
    await recipePage.screenshot({path:'test-results/recipe-editor-mobile.png',fullPage:true});
    await editRecipe.getByRole('button',{name:'Guardar receta',exact:true}).click();await editRecipe.waitFor({state:'hidden'});
    await recipePage.reload();await recipePage.getByRole('button',{name:'Catálogo',exact:true}).click();await recipeCatalog.getByRole('button',{name:'Recetas',exact:true}).click();
    await recipeCatalog.getByRole('button',{name:'Editar receta Almuerzo',exact:true}).waitFor();
    assert.equal(await recipeCard.locator('img.image').getAttribute('src'),new URL('/local/recipe-test.svg',url).href);
    await recipeCatalog.getByRole('button',{name:'Sugerencias',exact:true}).click();await recipeCatalog.getByRole('button',{name:'Nueva categoría de sugerencias',exact:true}).click();
    const groupEditor=recipeCatalog.locator('#recommendation-category-editor'),groupDialog=groupEditor.getByRole('dialog',{name:'Nueva categoría de sugerencias',exact:true});
    await groupDialog.getByLabel('Nombre de la categoría',{exact:true}).fill('Menús');await groupDialog.getByLabel('Receta · Almuerzo',{exact:true}).check();
    await groupDialog.getByRole('button',{name:'Guardar categoría',exact:true}).click();await groupDialog.waitFor({state:'hidden'});
    assert.equal(await recipeCatalog.locator('.recommendation-products .recipe-card').count(),0);
    await recipeCatalog.getByRole('button',{name:'Productos de temporada',exact:true}).click();
    await recipeCatalog.getByRole('button',{name:'Añadir producto a Enero',exact:true}).click();
    const seasonRecipe=recipeCatalog.locator('#season-add-dialog');await seasonRecipe.getByLabel('Producto o receta del catálogo',{exact:true}).fill('Receta · Almuerzo');
    const recipeMonth=await recipeCatalog.evaluate(node=>node._seasonMonth());await seasonRecipe.locator('input[name=season_month][value="'+recipeMonth+'"]').check();
    await seasonRecipe.getByRole('button',{name:'Añadir',exact:true}).click();await seasonRecipe.waitFor({state:'hidden'});
    await recipeCatalog.locator('#season-calendar-dialog').getByRole('button',{name:'Cerrar ventana',exact:true}).click();
    assert.equal(await recipeCatalog.locator('#season-current-products .recipe-card').count(),0);
    await recipePage.getByRole('button',{name:'Ajustes',exact:true}).click();const recipeSettings=recipePage.locator('isl-settings');
    await recipeSettings.getByRole('button',{name:'Personalización',exact:true}).click();await recipeSettings.getByLabel('Color inicial de Recetas',{exact:true}).fill('#a5d6a7');
    await recipeSettings.getByLabel('Color final de Recetas',{exact:true}).fill('#1b5e20');await recipeSettings.getByRole('button',{name:'Guardar personalización',exact:true}).click();
    await recipePage.getByRole('button',{name:'Catálogo',exact:true}).click();await recipeCatalog.getByRole('button',{name:'Recetas',exact:true}).click();
    assert.equal(await recipeCard.evaluate(node=>getComputedStyle(node).backgroundImage),'linear-gradient(rgb(165, 214, 167), rgb(27, 94, 32))');
    await recipeCatalog.getByRole('button',{name:'Editar receta Almuerzo',exact:true}).click();await editRecipe.getByRole('button',{name:'Eliminar receta',exact:true}).click();
    await recipeEditor.locator('#delete-recipe-dialog').getByRole('button',{name:'Eliminar receta',exact:true}).click();await editRecipe.waitFor({state:'hidden'});
    assert.equal(await recipePage.evaluate(()=>window.catalogProducts.length),2);assert.equal(await recipeCatalog.locator('#recipe-grid .recipe-card').count(),0);
    assert.deepEqual(await recipePage.evaluate(()=>window.recommendationCategories[0].recipe_ids),[]);
    await recipeContext.close();

    const seasonContext=await browser.newContext({viewport:{width:1280,height:960}});
    const seasonPage=await seasonContext.newPage();
    seasonPage.on('pageerror',error=>errors.push(error.message));
    await seasonPage.addInitScript(()=>{
      if(localStorage.getItem('season-fixture'))return;
      localStorage.setItem('season-fixture','1');
      localStorage.setItem('catalog-fixture',JSON.stringify(['Fresas','Calabaza'].map((name,index)=>({id:'season-'+index,revision:1,name,category:'',tags:[],price:null,currency:'EUR',barcode:'',barcodes:[],nfc_tags:[],reader_actions:{},image_url:'/logo.png',icon:'',notes:''}))));
    });
    await seasonPage.goto(url);
    await seasonPage.getByRole('button',{name:'Catálogo',exact:true}).click();
    const seasonCatalog=seasonPage.locator('isl-catalog');
    assert.deepEqual(await seasonCatalog.locator('.catalog-tabs .tab-label').allTextContents(),['Productos','Categorías','Recetas','Sugerencias','Nuevos']);
    await seasonCatalog.getByRole('button',{name:'Sugerencias',exact:true}).click();
    await seasonCatalog.getByRole('button',{name:'Productos de temporada',exact:true}).click();
    const calendar=seasonCatalog.locator('#season-calendar-dialog');
    assert.equal(await calendar.locator('.season-month').count(),12);
    await calendar.getByRole('button',{name:'Añadir producto a Enero',exact:true}).click();
    const seasonForm=seasonCatalog.locator('#season-add-dialog');
    await seasonForm.getByLabel('Producto o receta del catálogo',{exact:true}).fill('Fresas');
    await seasonForm.getByLabel('Marzo',{exact:true}).check();
    await seasonForm.getByLabel('Diciembre',{exact:true}).check();
    const currentMonth=await seasonCatalog.evaluate(node=>node._seasonMonth());
    await seasonForm.locator('input[name=season_month][value="'+currentMonth+'"]').check();
    await seasonForm.getByRole('button',{name:'Añadir',exact:true}).click();
    await seasonForm.waitFor({state:'hidden'});
    await calendar.locator('.season-month[data-month="1"] .season-product').waitFor();
    assert.equal(await calendar.locator('.season-month[data-month="1"] .season-product').evaluate(node=>getComputedStyle(node).backgroundColor),'rgb(38, 112, 82)');
    assert.equal(await calendar.locator('.season-month[data-month="1"] .season-product').evaluate(node=>node.lastElementChild.textContent),'Fresas');
    assert.equal(await calendar.locator('.season-month[data-month="1"] .season-product-circle').evaluate(node=>node.getBoundingClientRect().width),14);
    assert.equal(await calendar.locator('#season-delete-mode').textContent(),'');
    await calendar.getByRole('button',{name:'Eliminar productos',exact:true}).click();
    assert.equal(await calendar.locator('.season-month[data-month="1"] .season-product').evaluate(node=>getComputedStyle(node).backgroundColor),'rgb(211, 47, 47)');
    assert.equal(await calendar.locator('#season-delete-mode').evaluate(node=>getComputedStyle(node).backgroundColor),'rgb(38, 112, 82)');
    assert.equal(await calendar.locator('#season-delete-mode ha-icon').getAttribute('icon'),'mdi:plus-thick');
    await calendar.getByRole('button',{name:'Eliminar Fresas de Enero',exact:true}).click();
    await seasonPage.waitForFunction(()=>!window.catalogProducts.find(p=>p.name==='Fresas').season_months.includes(1));
    assert.ok(await seasonPage.evaluate(()=>window.catalogProducts.find(p=>p.name==='Fresas').season_months.includes(3)));
    // Add the current month again in case the browser date happens to be January.
    await seasonPage.evaluate(async month=>window.testPanel._hass.callWS({type:'improved_shopping_list/catalog/season_months',product_id:'season-0',months:[month],enabled:true}),currentMonth);
    await calendar.getByRole('button',{name:'Cerrar ventana',exact:true}).click();
    assert.equal(await seasonCatalog.locator('#recommendations-view .product,#recommendations-view .recipe-card').count(),0);
    await seasonCatalog.getByRole('button',{name:'Productos',exact:true}).click();
    await seasonCatalog.locator('#catalog-grid').getByRole('button',{name:'Añadir Fresas a la lista',exact:true}).click();
    await seasonPage.waitForFunction(()=>window.listData['todo.bring'].some(item=>item.summary==='Fresas'));
    await seasonCatalog.getByRole('button',{name:'Sugerencias',exact:true}).click();
    await seasonCatalog.getByRole('button',{name:'Productos de temporada',exact:true}).click();
    await seasonPage.screenshot({path:'test-results/season-calendar-desktop.png',fullPage:true});
    for(const width of [390,320]){
      await seasonPage.setViewportSize({width,height:844});
      assert.ok(await calendar.evaluate(node=>node.scrollWidth<=node.clientWidth+1));
      assert.ok(await calendar.locator(".season-month-add").evaluateAll(buttons=>buttons.every(button=>button.getBoundingClientRect().width>=30)));
      await seasonPage.screenshot({path:'test-results/season-calendar-'+width+'.png',fullPage:true});
    }
    await calendar.getByRole('button',{name:'Cerrar ventana',exact:true}).click();
    await seasonCatalog.getByRole('button',{name:'Productos',exact:true}).click();
    await seasonCatalog.locator('#toggle-catalog-order').click();
    await seasonCatalog.getByRole('button',{name:'Cambiar criterio de agrupación',exact:true}).click();
    await seasonCatalog.locator('#catalog-grouping-dialog').getByRole('button',{name:'Sugerencias',exact:true}).click();
    assert.deepEqual(await seasonCatalog.locator('#catalog-grid .category-group-title').allTextContents(),['Productos de temporada']);
    await seasonPage.reload();
    await seasonPage.getByRole('button',{name:'Catálogo',exact:true}).click();
    await seasonCatalog.locator('#catalog-grid .category-group').first().waitFor();
    assert.deepEqual(await seasonCatalog.locator('#catalog-grid .category-group-title').allTextContents(),['Productos de temporada']);
    assert.equal(await seasonPage.evaluate(()=>window.calls.some(call=>/nutriscore|refresh_prices/.test(call.type??''))),false);
    await seasonCatalog.getByRole('button',{name:'Sugerencias',exact:true}).click();
    await seasonCatalog.getByRole('button',{name:'Nueva categoría de sugerencias',exact:true}).click();
    const recommendationEditor=seasonCatalog.locator('#recommendation-category-editor');
    const recommendationDialog=recommendationEditor.getByRole('dialog',{name:'Nueva categoría de sugerencias',exact:true});
    await recommendationDialog.getByLabel('Nombre de la categoría',{exact:true}).fill('Para cocinar');
    await recommendationDialog.getByLabel('Icono MDI',{exact:true}).fill('mdi:chef-hat');
    await recommendationDialog.getByLabel('Color',{exact:true}).fill('#8e44ad');
    await recommendationDialog.getByLabel('Fresas',{exact:true}).check();
    await recommendationDialog.getByLabel('Calabaza',{exact:true}).check();
    await recommendationDialog.getByRole('button',{name:'Guardar categoría',exact:true}).click();
    await recommendationDialog.waitFor({state:'hidden'});
    await seasonCatalog.getByRole('button',{name:'Editar categoría de sugerencias Para cocinar',exact:true}).waitFor();
    assert.equal(await seasonCatalog.locator('.recommendation-icon').evaluate(node=>getComputedStyle(node).backgroundColor),'rgb(142, 68, 173)');
    assert.equal(await seasonCatalog.locator('#recommendations-view .product').count(),0);
    await seasonPage.reload();
    await seasonPage.getByRole('button',{name:'Catálogo',exact:true}).click();
    await seasonCatalog.locator('#catalog-grid .category-group').nth(1).waitFor();
    assert.deepEqual(await seasonCatalog.locator('#catalog-grid .category-group-title').allTextContents(),['Para cocinar','Productos de temporada']);
    assert.equal(await seasonCatalog.locator('#catalog-grid .product[data-product-id="season-0"]').count(),2);
    await seasonCatalog.getByRole('button',{name:'Sugerencias',exact:true}).click();
    await seasonCatalog.getByRole('button',{name:'Editar categoría de sugerencias Para cocinar',exact:true}).click();
    const editRecommendation=recommendationEditor.getByRole('dialog',{name:'Editar categoría de sugerencias',exact:true});
    await editRecommendation.getByLabel('Buscar productos para asociar',{exact:true}).fill('calabaza');
    assert.equal(await editRecommendation.locator('#category-product-options label:visible').count(),1);
    await editRecommendation.getByLabel('Calabaza',{exact:true}).uncheck();
    await editRecommendation.getByLabel('Nombre de la categoría',{exact:true}).fill('Postres');
    await editRecommendation.getByRole('button',{name:'Guardar categoría',exact:true}).click();
    await editRecommendation.waitFor({state:'hidden'});
    assert.equal(await seasonCatalog.locator('#recommendations-view .product').count(),0);
    await seasonPage.screenshot({path:'test-results/recommendation-categories-mobile.png',fullPage:true});
    await seasonCatalog.getByRole('button',{name:'Editar categoría de sugerencias Postres',exact:true}).click();
    const listBeforeGroupDelete=await seasonPage.evaluate(()=>structuredClone(window.listData));
    await editRecommendation.getByRole('button',{name:'Eliminar categoría',exact:true}).click();
    await recommendationEditor.locator('#delete-category-dialog').getByRole('button',{name:'Eliminar categoría',exact:true}).click();
    await editRecommendation.waitFor({state:'hidden'});
    assert.equal(await seasonCatalog.locator('.recommendation-products .product').count(),0);
    assert.equal(await seasonPage.evaluate(()=>window.catalogProducts.length),2);
    assert.deepEqual(await seasonPage.evaluate(()=>window.listData),listBeforeGroupDelete);
    await seasonContext.close();

    const groupingContext=await browser.newContext({viewport:{width:1280,height:960}});
    const groupingPage=await groupingContext.newPage();
    groupingPage.on('pageerror',error=>errors.push(error.message));
    await groupingPage.addInitScript(()=>{
      if(localStorage.getItem('grouping-fixture'))return;
      localStorage.setItem('grouping-fixture','1');
      localStorage.setItem('category-fixture',JSON.stringify([
        {id:'vegetables',name:'Verduras',icon:'mdi:carrot',color:'#008800'},
        {id:'pantry',name:'Despensa',icon:'mdi:food',color:'#aa8800'}]));
      localStorage.setItem('catalog-fixture',JSON.stringify([
        ['z','Zanahoria','Verduras'],['a','Azúcar','Despensa'],['p','Patatas','Verduras'],['r','Arroz','Despensa'],['u','Agua','']
      ].map(([id,name,category])=>({id,revision:1,name,category,tags:[],price:null,currency:'EUR',barcode:'',barcodes:[],nfc_tags:[],reader_actions:{},image_url:'',icon:'',notes:''}))));
    });
    await groupingPage.goto(url);
    await groupingPage.getByRole('button',{name:'Catálogo',exact:true}).click();
    const groupedCatalog=groupingPage.locator('isl-catalog');
    const productNames=()=>groupedCatalog.locator('#catalog-grid .product .title').allTextContents();
    await groupedCatalog.locator('#catalog-grid .product').nth(4).waitFor();
    assert.deepEqual(await productNames(),['Agua','Arroz','Azúcar','Patatas','Zanahoria']);
    await groupedCatalog.getByRole('button',{name:'Agrupar por categorías',exact:true}).click();
    assert.deepEqual(await groupedCatalog.locator('.category-group-title').allTextContents(),['Despensa','Verduras','Sin categoría']);
    assert.deepEqual(await groupedCatalog.locator('.category-group-title ha-icon').evaluateAll(nodes=>nodes.map(node=>[node.getAttribute('icon'),getComputedStyle(node).color])),[['mdi:food','rgb(255, 255, 255)'],['mdi:carrot','rgb(255, 255, 255)'],['mdi:label-outline','rgb(255, 255, 255)']]);
    assert.deepEqual(await productNames(),['Arroz','Azúcar','Patatas','Zanahoria','Agua']);
    for (const group of await groupedCatalog.locator('.category-group').all()) {
      assert.ok(await group.locator('.product').count()>0);
    }
    await groupedCatalog.getByLabel('Buscar productos',{exact:true}).fill('Patatas');
    assert.deepEqual(await groupedCatalog.locator('.category-group-title').allTextContents(),['Verduras']);
    assert.deepEqual(await productNames(),['Patatas']);
    await groupedCatalog.getByLabel('Buscar productos',{exact:true}).fill('inexistente');
    assert.equal(await groupedCatalog.locator('.category-group').count(),0);
    assert.equal(await groupedCatalog.locator('#catalog-empty').isVisible(),true);
    await groupedCatalog.getByLabel('Buscar productos',{exact:true}).fill('');
    await groupedCatalog.getByRole('button',{name:'Cambiar a vista de filas',exact:true}).click();
    assert.equal(await groupedCatalog.locator('.category-products.rows').count(),3);
    assert.equal(await groupedCatalog.getByRole('button',{name:'Editar Patatas',exact:true}).isVisible(),true);
    await groupingPage.reload();
    await groupingPage.getByRole('button',{name:'Catálogo',exact:true}).click();
    await groupedCatalog.locator('.category-group').nth(2).waitFor();
    assert.equal(await groupedCatalog.locator('#toggle-catalog-order ha-icon').getAttribute('icon'),'mdi:sort-alphabetical-ascending');
    assert.equal(await groupedCatalog.locator('.category-products.rows').count(),3);
    await groupingPage.screenshot({path:'test-results/catalog-groups-desktop.png',fullPage:true});
    await groupedCatalog.getByRole('button',{name:'Cambiar a vista de cuadrícula',exact:true}).click();
    await groupingPage.setViewportSize({width:390,height:844});
    assert.ok(await groupedCatalog.locator('.product').first().evaluate(card=>Math.abs(card.getBoundingClientRect().width-card.getBoundingClientRect().height)<1));
    assert.ok(await groupedCatalog.evaluate(node=>node.scrollWidth<=node.clientWidth+1));
    await groupingPage.screenshot({path:'test-results/catalog-groups-mobile.png',fullPage:true});
    await groupedCatalog.getByRole('button',{name:'Ordenar alfabéticamente',exact:true}).click();
    assert.equal(await groupedCatalog.locator('.category-group').count(),0);
    assert.deepEqual(await productNames(),['Agua','Arroz','Azúcar','Patatas','Zanahoria']);
    assert.equal(await groupedCatalog.locator('#toggle-catalog-order ha-icon').getAttribute('icon'),'mdi:label');
    assert.equal(await groupingPage.evaluate(()=>window.calls.length),0);
    assert.equal(await groupedCatalog.locator('#configure-catalog-grouping').isVisible(),false);
    await groupingPage.evaluate(async()=>{
      const ean=prefix=>{
        const sum=[...prefix].reverse().reduce((sum,digit,index)=>sum+Number(digit)*(index%2?1:3),0);
        return prefix+String((10-sum%10)%10);
      };
      const codes=['123456789001','123456789002','123456789003','123456789004'].map(ean);
      window.groupingNutritionCodes=codes;
      window.nutriFixture={[codes[0]]:{grade:'b'},[codes[1]]:{grade:'e'},[codes[2]]:{grade:'a'}};
      window.failNutriCode=codes[3];
      for (const [id,code] of [['r',codes[0]],['a',codes[1]],['z',codes[2]],['p',codes[3]]]) {
        const product=structuredClone(window.catalogProducts.find(product=>product.id===id));
        product.barcode=code;
        if(id==='r')product.barcodes=[code.padStart(14,'0'),'https://example.test/qr'];
        await window.testPanel._hass.callWS({type:'improved_shopping_list/catalog/save',product});
      }
    });
    assert.equal(await groupingPage.evaluate(()=>window.nutriCalls?.length??0),0);
    await groupedCatalog.getByRole('button',{name:'Agrupar por categorías',exact:true}).click();
    const groupingButton=groupedCatalog.getByRole('button',{name:'Cambiar criterio de agrupación',exact:true});
    await groupingButton.click();
    const groupingDialog=groupedCatalog.getByRole('dialog',{name:'Agrupar productos por',exact:true});
    assert.equal(await groupingDialog.getByRole('button',{name:'Categoría',exact:true}).getAttribute('aria-pressed'),'true');
    assert.equal(await groupingDialog.getByRole('button',{name:'Nutri-Score',exact:true}).count(),0);
    await groupingDialog.getByRole('button',{name:'Cerrar ventana',exact:true}).click();
    await groupedCatalog.getByRole('button',{name:'Cambiar a vista de filas',exact:true}).click();
    await groupingPage.getByRole('button',{name:'Ajustes',exact:true}).click();
    const nutritionSettings=groupingPage.locator('isl-settings');
    await nutritionSettings.getByRole('button',{name:'Nutri-Score',exact:true}).click();
    await nutritionSettings.locator('#nutrition-total').filter({hasText:'3 productos'}).waitFor();
    assert.deepEqual(await nutritionSettings.locator('.nutrition-value').allTextContents(),['1 (33,3 %)','1 (33,3 %)','0 (0 %)','0 (0 %)','1 (33,3 %)']);
    assert.equal(await nutritionSettings.locator('.nutrition-bar').first().evaluate(node=>getComputedStyle(node).backgroundColor),'rgb(3, 129, 65)');
    const gradeA=nutritionSettings.locator('.nutrition-group[data-grade="a"]');
    assert.equal(await gradeA.locator('.nutrition-products').isVisible(),false);
    await gradeA.locator('summary').click();
    assert.equal(await gradeA.locator('.nutrition-products').isVisible(),true);
    assert.deepEqual(await gradeA.locator('li').allTextContents(),['Zanahoria']);
    const gradeB=nutritionSettings.locator('.nutrition-group[data-grade="b"]');
    await gradeB.locator('summary').focus();await groupingPage.keyboard.press('Enter');
    assert.deepEqual(await gradeB.locator('li').allTextContents(),['Arroz']);
    assert.equal(await gradeB.locator('.nutrition-products').isVisible(),true);
    await gradeA.locator('summary').click();
    assert.equal(await gradeA.locator('.nutrition-products').isVisible(),false);

    assert.equal(await groupingPage.evaluate(()=>window.nutriCalls?.length??0),0);
    await groupingPage.screenshot({path:'test-results/nutrition-distribution-mobile.png',fullPage:true});
    for(const width of [320,1280]){await groupingPage.setViewportSize({width,height:844});assert.ok(await nutritionSettings.locator('#settings-nutrition').evaluate(node=>node.scrollWidth<=node.clientWidth+1));}
    await groupingPage.screenshot({path:'test-results/nutrition-distribution-desktop.png',fullPage:true});
    await groupingPage.evaluate(()=>{window.nutriFixture={};});
    await nutritionSettings.getByRole('button',{name:'Listas',exact:true}).click();
    await nutritionSettings.getByRole('button',{name:'Nutri-Score',exact:true}).click();
    await nutritionSettings.locator('#nutrition-status').filter({hasText:'Todavía no hay productos'}).waitFor();
    assert.equal(await nutritionSettings.locator('#nutrition-chart').isVisible(),false);
    await groupingPage.evaluate(()=>{window.failNutritionDistribution=true;});
    await nutritionSettings.getByRole('button',{name:'Listas',exact:true}).click();
    await nutritionSettings.getByRole('button',{name:'Nutri-Score',exact:true}).click();
    await nutritionSettings.locator('#nutrition-status').filter({hasText:'No se ha podido cargar'}).waitFor();
    await groupingPage.evaluate(()=>{window.failNutritionDistribution=false;localStorage.setItem('isl-catalog-grouping','nutriscore');});
    await groupingPage.reload();
    await groupingPage.getByRole('button',{name:'Catálogo',exact:true}).click();
    await groupedCatalog.locator('.category-group').nth(2).waitFor();
    await groupingButton.click();
    assert.equal(await groupingDialog.getByRole('button',{name:'Categoría',exact:true}).getAttribute('aria-pressed'),'true');
    assert.equal(await groupingDialog.getByRole('button',{name:'Nutri-Score',exact:true}).count(),0);
    await groupingDialog.getByRole('button',{name:'Cerrar ventana',exact:true}).click();
    await groupingPage.setViewportSize({width:390,height:844});
    // Removed grouping preferences fall back to categories after reloading.
    await groupingPage.evaluate(()=>localStorage.setItem('isl-catalog-grouping','linked'));
    await groupingPage.reload();
    await groupingPage.getByRole('button',{name:'Catálogo',exact:true}).click();
    await groupedCatalog.locator('.category-group').nth(2).waitFor();
    await groupingButton.click();
    assert.equal(await groupingDialog.getByRole('button',{name:'Vinculados',exact:true}).count(),0);
    assert.equal(await groupingDialog.getByRole('button',{name:'Categoría',exact:true}).getAttribute('aria-pressed'),'true');
    await groupingDialog.getByRole('button',{name:'Cerrar ventana',exact:true}).click();
    await groupedCatalog.getByRole('button',{name:'Ordenar alfabéticamente',exact:true}).click();
    assert.deepEqual(await productNames(),['Agua','Arroz','Azúcar','Patatas','Zanahoria']);
    assert.equal(await groupedCatalog.getByRole('button',{name:'Agrupar por categorías',exact:true}).count(),1);
    await groupingPage.getByRole('button',{name:'Lista',exact:true}).click();
    await groupingContext.close();
    // Invoices reuse the review workflow, preserve EAN and keep delivery out of product prices.
    const invoiceContext=await browser.newContext({viewport:{width:390,height:844}});
    const invoicePage=await invoiceContext.newPage();invoicePage.on('pageerror',error=>errors.push(error.message));
    await invoicePage.addInitScript(()=>{window.receiptInvoice=true;});
    await invoicePage.goto(url);await invoicePage.getByRole('button',{name:'Stock',exact:true}).click();
    await invoicePage.getByRole('tab',{name:'Compras',exact:true}).click();
    const invoicePurchases=invoicePage.locator('isl-purchases');
    await invoicePurchases.locator('#ticket-file').setInputFiles({name:'factura.pdf',mimeType:'application/pdf',buffer:Buffer.from('%PDF-fixture')});
    const invoiceReview=invoicePurchases.getByRole('dialog',{name:'Revisar ticket',exact:true});await invoiceReview.waitFor();
    assert.match(await invoiceReview.locator('#review-summary').textContent(),/Factura/);
    await invoiceReview.locator('#linked-products-group > summary').click();
    assert.equal(await invoiceReview.locator('[data-line-id="0"] .receipt-ean').textContent(),'EAN: 1234567890128');
    await invoiceReview.getByRole('button',{name:'Continuar',exact:true}).click();
    await invoiceReview.getByRole('button',{name:'Continuar',exact:true}).click();
    assert.match(await invoiceReview.locator('#step-help').textContent(),/antes de descuentos y no incluye el envío/);
    assert.match(await invoiceReview.locator('[data-line-id="0"] .price-value').textContent(),/2,65/);
    assert.equal(await invoiceReview.locator('[data-line-id="0"] .original').count(),0);
    assert.equal(await invoiceReview.locator('#review-result').isVisible(),false);
    await invoiceReview.getByRole('button',{name:'Actualizar precios y cerrar',exact:true}).click();await invoiceReview.waitFor({state:'hidden'});
    await invoicePurchases.locator('#history .ticket-open').click();
    assert.match(await invoicePurchases.locator('#purchase-detail').textContent(),/Gastos de envío/);
    assert.match(await invoicePurchases.locator('#purchase-detail').textContent(),/Descuento de línea/);
    assert.equal(await invoicePage.evaluate(()=>window.receiptHistory[0].lines[0].ean),'1234567890128');
    await invoicePage.screenshot({path:'test-results/carrefour-invoice-mobile.png',fullPage:true});
    assert.ok(await invoicePurchases.evaluate(node=>node.scrollWidth<=node.clientWidth+1));
    await invoiceContext.close();
    // A proposed match is not a linked catalog product until the user confirms it.
    const suggestionReceiptContext=await browser.newContext({viewport:{width:390,height:844}});
    const suggestionReceiptPage=await suggestionReceiptContext.newPage();
    await suggestionReceiptPage.addInitScript(()=>{window.receiptSuggestionOnly=true;});
    await suggestionReceiptPage.goto(url);await suggestionReceiptPage.getByRole('button',{name:'Stock',exact:true}).click();
    await suggestionReceiptPage.getByRole('tab',{name:'Compras',exact:true}).click();
    const suggestionPurchase=suggestionReceiptPage.locator('isl-purchases');
    await suggestionPurchase.locator('#ticket-file').setInputFiles({name:'ticket.pdf',mimeType:'application/pdf',buffer:Buffer.from('%PDF-fixture')});
    const suggestionReview=suggestionPurchase.getByRole('dialog',{name:'Revisar ticket',exact:true});await suggestionReview.waitFor();
    assert.equal(await suggestionReview.locator('[data-line-id="0"] .linked-name').count(),0);
    await suggestionReview.getByRole('button',{name:'Continuar',exact:true}).click();
    await suggestionReview.locator('#stock-only').waitFor();
    assert.equal(await suggestionReview.locator('.review-line').count(),0);
    assert.ok(await suggestionReceiptPage.evaluate(()=>window.receiptLinks.length>0&&window.receiptLinks.every(line=>!line.product_id)));
    await suggestionReview.getByRole('button',{name:'Continuar',exact:true}).click();
    assert.equal(await suggestionReview.locator('.price-select').count(),0);
    await suggestionReview.getByRole('button',{name:'Continuar',exact:true}).click();
    await suggestionReview.getByRole('button',{name:'Confirmar compra',exact:true}).waitFor();
    await suggestionReview.getByRole('button',{name:'Confirmar compra',exact:true}).click();
    await suggestionReview.waitFor({state:'hidden'});
    assert.equal(await suggestionReceiptPage.evaluate(()=>window.stockItems.length),0);
    await suggestionReceiptContext.close();
    // Carrefour account access is entirely manual; tickets open the existing review wizard.
    const accountContext=await browser.newContext({viewport:{width:390,height:844}});
    const accountPage=await accountContext.newPage();accountPage.on('pageerror',error=>errors.push(error.message));
    await accountPage.goto(url);await accountPage.getByRole('button',{name:'Ajustes',exact:true}).click();
    const accountSettings=accountPage.locator('isl-settings');await accountSettings.getByRole('button',{name:'Tiendas',exact:true}).click();
    await accountSettings.getByRole('button',{name:'Ajustes de Carrefour',exact:true}).click();
    const account=accountSettings.locator('isl-carrefour-account');
    await account.getByRole('button',{name:'Conectar cuenta',exact:true}).waitFor();
    assert.equal(await account.getByRole('button',{name:'Consultar compras',exact:true}).count(),0);
    assert.equal(await accountPage.evaluate(()=>window.calls.filter(call=>/carrefour_account\/(login|purchases|preview)/.test(call.type??'')).length),0);
    await account.getByRole('button',{name:'Conectar cuenta',exact:true}).click();
    const login=account.getByRole('dialog',{name:'Conectar cuenta de Carrefour',exact:true});
    await login.getByLabel('Correo',{exact:true}).fill('test@example.test');
    await login.getByLabel('Contraseña',{exact:true}).fill('test-password');
    await login.getByRole('button',{name:'Conectar',exact:true}).click();
    await login.getByRole('button',{name:'Enviar código',exact:true}).waitFor();
    assert.equal(await login.getByLabel('Contraseña',{exact:true}).inputValue(),'');
    assert.equal(await accountPage.evaluate(()=>window.calls.filter(call=>call.type==='improved_shopping_list/carrefour_account/send_code').length),0);
    await login.getByRole('button',{name:'Enviar código',exact:true}).click();
    await login.getByLabel('Código de verificación',{exact:true}).fill('123456');
    await login.getByRole('button',{name:'Verificar',exact:true}).click();
    await account.getByRole('button',{name:'Desconectar cuenta',exact:true}).waitFor();
    assert.equal(await accountPage.evaluate(()=>window.receiptHistory.length),0);
    await accountPage.screenshot({path:'test-results/carrefour-account-login-mobile.png',fullPage:true});
    assert.ok(await login.evaluate(el=>el.scrollWidth<=el.clientWidth+1));
    await login.getByRole('button',{name:'Cerrar ventana',exact:true}).click();
    await account.getByRole('switch',{name:'Recuperar compras del último año',exact:true}).check();
    await accountPage.waitForFunction(()=>window.receiptHistory.length===2);
    assert.equal(await account.locator('#account-email').textContent(),'test@example.test');
    await account.getByRole('switch',{name:'Descargar ticket automáticamente',exact:true}).check();
    assert.equal(await account.getByRole('switch',{name:'Actualizar precios públicos en el catálogo',exact:true}).count(),0);
    await accountSettings.locator('#carrefour-dialog').getByRole('button',{name:'Cerrar ventana',exact:true}).click();
    await accountPage.getByRole('button',{name:'Stock',exact:true}).click();
    const accountHistory=accountPage.locator('isl-purchases');
    await accountPage.getByRole('tab',{name:'Compras',exact:true}).click();
    await accountHistory.locator('#history .ticket').nth(1).waitFor();
    assert.equal(await accountHistory.locator('#history .ticket').count(),2);
    assert.equal(await accountHistory.locator('#history .ticket-open').count(),1);
    assert.ok((await accountHistory.locator('#history .muted').allTextContents()).every(text=>!text.includes('artículos')));
    assert.equal(await accountHistory.locator('.month-column[data-month="2026-10"]').getAttribute('data-total'),'15.22');
    await accountHistory.locator('#history .ticket-open').click();
    const accountReview=accountHistory.getByRole('dialog',{name:'Revisar ticket',exact:true});await accountReview.waitFor();
    assert.equal(await accountPage.evaluate(()=>window.calls.filter(call=>call.type==='improved_shopping_list/carrefour_account/preview_saved').length),1);
    assert.equal(await accountPage.evaluate(()=>window.receiptHistory.length),2);
    assert.equal(await accountPage.evaluate(()=>window.stockItems.length),0);
    await accountPage.screenshot({path:'test-results/carrefour-account-purchases-mobile.png',fullPage:true});
    await accountReview.getByRole('button',{name:'Cerrar ventana',exact:true}).click();
    await accountPage.evaluate(()=>window.failCarrefourAccount=true);
    await accountHistory.locator('#history .ticket-open').click();
    await accountHistory.locator('#message').filter({hasText:'HTTP 403'}).waitFor();
    await accountPage.getByRole('button',{name:'Ajustes',exact:true}).click();
    await accountSettings.getByRole('button',{name:'Ajustes de Carrefour',exact:true}).click();
    await account.getByRole('button',{name:'Desconectar cuenta',exact:true}).click();
    await account.getByRole('button',{name:'Conectar cuenta',exact:true}).waitFor();
    assert.equal(await account.getByRole('button',{name:'Consultar compras',exact:true}).count(),0);
    await accountContext.close();
    // Logs display live changes as text, filter by origin/type and clean up on navigation.
    await page.setViewportSize({width:1280,height:960});
    await page.evaluate(()=>{
      window.logFixture.entries=[
        {id:'auto',time:'2026-10-20T10:00:00Z',kind:'list.added',source:'automatic',message:'Añadido a la lista: Seitán',product:'Seitán',list_name:'La compra'},
        {id:'scan',time:'2026-10-20T09:00:00Z',kind:'reader.scan',source:'reader',message:'Código desconocido en Sugerencias',reader:'Cocina',code:'001234'},
        {id:'category',time:'2026-10-20T08:00:00Z',kind:'catalog.categories.updated',source:'integration',message:'Categoría modificada: <img src=x onerror=alert(1)>',category:'Despensa',changed_fields:['color','icon']},
      ];
    });
    await page.getByRole('button',{name:'Ajustes',exact:true}).click();
    assert.equal(await page.locator('#nav-logs').count(),0);
    await page.getByRole('button',{name:'Logs',exact:true}).click();
    const logs=page.locator('isl-logs');
    await logs.locator('#entries > li').nth(2).waitFor();
    assert.equal(await page.locator('isl-settings #settings-view-logs ha-icon').getAttribute('icon'),'mdi:format-list-group');
    assert.equal(await logs.locator('#entries img').count(),0);
    assert.equal(await page.locator('isl-settings #settings-view-logs').getAttribute('aria-pressed'),'true');
    assert.equal(await page.evaluate(()=>window.logListenerCount()),1);
    await page.locator('isl-settings').getByRole('button',{name:'Tiendas',exact:true}).click();
    assert.equal(await logs.isVisible(),false);
    assert.equal(await page.evaluate(()=>window.logListenerCount()),0);
    await page.locator('isl-settings').getByRole('button',{name:'Logs',exact:true}).click();
    await logs.locator('#entries > li').nth(2).waitFor();
    assert.equal(await page.evaluate(()=>window.logListenerCount()),1);

    await logs.getByLabel('Buscar en el historial',{exact:true}).fill('SEITAN');
    assert.equal(await logs.locator('#entries > li').count(),1);
    await logs.getByLabel('Buscar en el historial',{exact:true}).fill('');
    await logs.getByLabel('Origen',{exact:true}).selectOption('reader');
    assert.equal(await logs.locator('#entries > li').count(),1);
    await logs.getByText('Código: 001234',{exact:true}).waitFor();
    await logs.getByLabel('Origen',{exact:true}).selectOption('');
    await logs.getByLabel('Actividad',{exact:true}).selectOption('catalog');
    await logs.getByText('Campos: color, icono',{exact:true}).waitFor();
    await logs.getByLabel('Actividad',{exact:true}).selectOption('');
    await page.evaluate(()=>{window.logFixture.entries.unshift({id:'new',time:new Date().toISOString(),kind:'list.removed',source:'manual',message:'Eliminado de la lista: Cacao'});window.emitLogs();});
    await logs.getByText('Eliminado de la lista: Cacao',{exact:true}).waitFor();
    await page.evaluate(()=>{
      window.logFixture.entries.unshift({id:'store-error',time:new Date().toISOString(),kind:'stores.error',source:'integration',message:'Mercadona: HTTP 403',diagnostics:{http_status:403,warehouse:'mad3',response_class:'service_misuse','x-request-id':'reference-test-403',query_type:'<img src=x onerror=alert(1)>'}});
      window.emitLogs();
    });
    await logs.getByLabel('Actividad',{exact:true}).selectOption('stores');
    assert.equal(await logs.locator('#entries > li').count(),1);
    await logs.getByText('Información técnica',{exact:true}).click();
    assert.match(await logs.locator('.technical pre').textContent(),/reference-test-403/);
    assert.equal(await logs.locator('.technical img').count(),0);
    await logs.getByLabel('Buscar en el historial',{exact:true}).fill('reference-test-403');
    assert.equal(await logs.locator('#entries > li').count(),1);
    await logs.getByLabel('Buscar en el historial',{exact:true}).fill('');
    await logs.getByLabel('Actividad',{exact:true}).selectOption('');
    await page.screenshot({path:'test-results/logs-desktop.png',fullPage:true});
    await page.setViewportSize({width:320,height:844});
    await logs.locator('[data-entry-id="store-error"] summary').click();
    assert.equal(await logs.evaluate(node=>node.scrollWidth<=node.clientWidth),true);
    await page.screenshot({path:'test-results/logs-mobile.png',fullPage:true});
    await page.evaluate(()=>{window.failLogs=true;});
    await logs.getByRole('button',{name:'Actualizar logs',exact:true}).click();
    await logs.getByRole('status').filter({hasText:'Error al cargar logs'}).waitFor();
    await page.evaluate(()=>{window.failLogs=false;});
    await logs.getByRole('button',{name:'Actualizar logs',exact:true}).click();
    await logs.getByRole('status').waitFor({state:'hidden'});
    await page.getByRole('button',{name:'Lista',exact:true}).click();
    assert.equal(await page.evaluate(()=>window.logListenerCount()),0);
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
