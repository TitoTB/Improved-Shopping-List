import {test} from 'node:test';
import assert from 'node:assert/strict';
globalThis.HTMLElement=class {};globalThis.customElements={get:()=>true};
const {normalizeObservation,analyzeCatalog,analyzePurchase}=await import('../custom_components/improved_shopping_list/frontend/analytics-panel.js');
const {packageCost,referenceRate,suggestedContent,validReferenceContent}=await import('../custom_components/improved_shopping_list/frontend/reference-formats.js');
const {cachedProductPrice,storeProductLink,storeFromProductUrl}=await import('../custom_components/improved_shopping_list/frontend/product-display.js');
const now=1800000000,ean='1234567890128';
const offer=(store,price,extra={})=>({store,product_id:'p',price,currency:'EUR',at:now-3600,ean,...extra});
const products=[{id:'p',name:'Arroz',category:'Despensa'},{id:'q',name:'Pavo',category:'Fresco'},{id:'none',name:'Sin precio'}];
const purchase=(extra={})=>({id:'receipt',store:'carrefour',currency:'EUR',at:now,total:8,discount:0,shipping:0,lines:[{id:'l',product_id:'p',description:'ARROZ',count:2,amount:8,ean}],...extra});

test('Carrefour outgoing product links use the affiliate destination without changing source URLs',()=>{
 const original='https://www.carrefour.es/supermercado/cafe-molido-natural-cultivo-sostenible-nestle-bonka-500-g/R-prod310215/p';
 const affiliate=new URL(storeProductLink('carrefour',original));
 assert.equal(affiliate.origin,'https://www.awin1.com');assert.equal(affiliate.pathname,'/cread.php');
 assert.equal(affiliate.searchParams.get('awinmid'),'25399');assert.equal(affiliate.searchParams.get('awinaffid'),'1535625');assert.equal(affiliate.searchParams.get('ued'),original);
 assert.equal(storeProductLink('lidl',original),original);
 for(const url of ['https://www.awin1.com/cread.php?awinmid=25399','https://www.carrefour.es.example.org/supermercado/a/R-prod1/p','R-prod310215'])assert.equal(storeProductLink('carrefour',url),url);
});

test('official product URLs identify their store without a selected store',()=>{
 for(const [host,store] of [['www.carrefour.es','carrefour'],['www.compraonline.alcampo.es','alcampo'],['tienda.mercadona.es','mercadona'],['tienda.consum.es','consum'],['www.lasirena.es','lasirena'],['supermercado.eroski.es','eroski'],['www.dia.es','dia'],['www.lidl.es','lidl']])assert.equal(storeFromProductUrl(`https://${host}/product`),store);
 for(const value of ['R-521002958','http://www.carrefour.es/a','https://www.carrefour.es.example.org/a','https://user:password@www.carrefour.es/a'])assert.equal(storeFromProductUrl(value),'');
});

test('list estimates select whole packages for the requested amount and leave pending formats unknown',()=>{
 for(const ref of [{content_quantity:250,content_unit:'g',content_confirmed:false},{content_quantity:12,content_unit:'uds'}])assert.equal(validReferenceContent(ref),true);
 for(const ref of [{content_quantity:null,content_unit:'g'},{content_quantity:0,content_unit:'g'},{content_quantity:1.5,content_unit:'uds'},{content_quantity:250,content_unit:''}])assert.equal(validReferenceContent(ref),false);
 const p={id:'p',purchase_unit:'uds',unit_quantity:6};
 const obs=[{catalog_product_id:'p',store:'lidl',price:1.8,currency:'EUR',pack_quantity:6,pack_unit:'uds'},
 {catalog_product_id:'p',store:'lidl',price:3,currency:'EUR',pack_quantity:12,pack_unit:'uds'}];
 assert.equal(cachedProductPrice(p,obs,'lidl').price,1.8);
 assert.equal(cachedProductPrice(p,obs,'lidl',{quantity:12,unit:'uds'}).price,3);
 assert.deepEqual(packageCost(obs[1],6,'uds'),{price:3,packages:1});
 assert.equal(packageCost({...obs[0],format_pending:true},6,'uds'),null);
 assert.equal(referenceRate(4,{content_quantity:500,content_unit:'g',content_confirmed:true}).price,8);
 assert.deepEqual(suggestedContent({description:'PACK 2 X 6 UDS'}),{quantity:12,unit:'uds'});
 assert.deepEqual(suggestedContent({description:'CAFE 500 G',count:2}),{quantity:500,unit:'g'});
 assert.deepEqual(suggestedContent({description:'PACK 6 X 330 ML',count:3,pack_quantity:330,pack_unit:'ml'}),{quantity:1980,unit:'ml'});
});

test('egg packages compare per egg, retaining multiple formats per store and their latest prices',()=>{
 const obs=[offer('carrefour',1.8,{ean:'',commercial_reference_id:'six',pack_quantity:6,pack_unit:'uds'}),offer('carrefour',3,{ean:'',commercial_reference_id:'twelve',pack_quantity:12,pack_unit:'uds'}),offer('lidl',1.6,{ean:'',commercial_reference_id:'six-lidl',pack_quantity:6,pack_unit:'uds'})];
 const row=analyzeCatalog(products,obs,{stores:['carrefour','lidl'],now}).rows[0];
 assert.equal(row.unit,'uds');assert.equal(row.min,.25);assert.deepEqual(row.bestStores,['carrefour']);
 assert.equal(analyzeCatalog(products,obs.slice(0,2),{stores:['carrefour'],now}).comparable,0);
 const bought=purchase({total:1.8,lines:[{id:'l',product_id:'p',count:1,amount:1.8,ean:'',pack_quantity:6,pack_unit:'uds'}]});
 const alt=analyzePurchase(bought,[obs[1]],{stores:['carrefour'],now});assert.equal(alt.alternatives.length,0);
 const alternative=analyzePurchase(bought,[{...obs[1],store:'lidl'}],{stores:['lidl'],now}).alternatives[0];
 assert.equal(alternative.cost,3);assert.equal(alternative.lines[0].packages,1);assert.equal(alternative.savings,-1.2);
});

test('unconfirmed package contents cannot create a per-unit saving for distinct EANs',()=>{
 const obs=[offer('carrefour',1.8,{pack_quantity:6,pack_unit:'uds',format_pending:true}),offer('lidl',3,{ean:'4006381333931',pack_quantity:12,pack_unit:'uds',format_pending:true})];
 assert.equal(analyzeCatalog(products,obs,{stores:['carrefour','lidl'],now}).comparable,0);
});

test('catalog normalizes pack weights and only includes products with prices in two stores',()=>{
 const result=analyzeCatalog(products,[offer('carrefour',2,{ean:'',pack_quantity:200,pack_unit:'g'}),offer('alcampo',4,{ean:'',pack_quantity:500,pack_unit:'g'})],{stores:['carrefour','alcampo'],now});
 const row=result.rows.find(r=>r.product.id==='p');assert.equal(row.min,8);assert.equal(row.max,10);assert.deepEqual(row.bestStores,['alcampo']);assert.equal(result.rows.length,1);assert.equal(result.comparable,1);assert.equal(result.common,1);assert.equal(result.ranking[0].store,'alcampo');
 assert.equal(result.rows.some(r=>r.product.id==='none'),false);
});
test('catalog compares units across brands and EANs, never unknown package contents',()=>{
 const options={stores:['carrefour','alcampo'],now};
 assert.equal(analyzeCatalog(products,[offer('carrefour',1),offer('alcampo',2)],options).rows.length,0);
 const obs=[offer('carrefour',2,{brand:'Marca A',pack_quantity:500,pack_unit:'g'}),offer('alcampo',3,{brand:'Marca B',ean:'4006381333931',pack_quantity:1,pack_unit:'kg'})];
 const row=analyzeCatalog(products,obs,options).rows[0];
 assert.equal(row.unit,'kg');assert.equal(row.min,3);assert.equal(row.max,4);assert.deepEqual(row.bestStores,['alcampo']);
 const zero=analyzeCatalog(products,[offer('carrefour',0,{pack_quantity:1,pack_unit:'uds'}),offer('alcampo',0,{ean:'4006381333931',pack_quantity:1,pack_unit:'uds'})],options).rows[0];
 assert.equal(zero.min,0);assert.deepEqual(zero.bestStores,['carrefour','alcampo']);
 assert.equal(analyzeCatalog(products,[obs[0],offer('alcampo',1,{pack_quantity:1,pack_unit:'l'})],options).rows.length,0);
 const litres=analyzeCatalog(products,[offer('carrefour',1,{pack_quantity:500,pack_unit:'ml'}),offer('alcampo',3,{ean:'',pack_quantity:2,pack_unit:'l'})],options).rows[0];
 assert.equal(litres.unit,'l');assert.equal(litres.min,1.5);
});
test('catalog uses latest price per store, filters age/category/store and separates currency',()=>{
 const obs=[offer('carrefour',4,{pack_quantity:1,pack_unit:'uds'}),offer('carrefour',3,{at:now-100,pack_quantity:1,pack_unit:'uds'}),offer('alcampo',1,{at:now+1}),offer('dia',1,{currency:'USD'}),offer('consum',2,{at:now-100*86400,pack_quantity:1,pack_unit:'uds'})];
 const result=analyzeCatalog(products,obs,{stores:['carrefour','alcampo','dia','consum'],category:'Despensa',maxAge:30,now});assert.equal(result.rows.length,0);assert.equal(result.known,0);assert.equal(result.comparable,0);
 const unfiltered=analyzeCatalog(products,obs,{stores:['carrefour','consum'],now});assert.equal(unfiltered.rows[0].offers.find(o=>o.store==='carrefour').price,3);
 assert.equal(analyzeCatalog(products,obs,{stores:['carrefour'],store:'alcampo',now}).rows.length,0);
 assert.equal(analyzeCatalog(products,obs,{stores:['dia'],currency:'USD',now}).known,0);
});
test('reference price per 100g converts to kg; invalid values are rejected',()=>{
 assert.equal(normalizeObservation(offer('alcampo',3,{reference_price:1.5,reference_unit:'PER_100G'})).rate,15);
 for(const value of [null,true,'',-1,Infinity,'invalid'])assert.equal(normalizeObservation(offer('alcampo',value)),null);
});
test('historical savings exclude future observations; current mode is explicitly separate',()=>{
 const obs=[offer('alcampo',3),offer('alcampo',1,{at:now+1})];
 const historical=analyzePurchase(purchase(),obs,{stores:['carrefour','alcampo'],now:now+100});assert.equal(historical.alternatives[0].cost,6);assert.equal(historical.alternatives[0].savings,2);assert.equal(historical.alternatives[0].complete,true);
 const current=analyzePurchase(purchase(),obs,{stores:['carrefour','alcampo'],mode:'current',now:now+100});assert.equal(current.alternatives[0].cost,2);assert.equal(current.mode,'current');
});
test('purchase conversion uses package quantities, not pantry refill amounts, and excludes stale/cross-currency prices',()=>{
 const p=purchase({lines:[{id:'l',product_id:'p',description:'ARROZ',count:2,amount:8,ean:'',pack_quantity:250,pack_unit:'g',quantity:175,unit:'g'}]});
 const obs=[offer('alcampo',6,{ean:'',pack_quantity:1,pack_unit:'kg'}),offer('dia',1,{at:now-31*86400}),offer('consum',1,{currency:'USD'})];
 const result=analyzePurchase(p,obs,{stores:['alcampo','dia','consum'],now});assert.equal(result.alternatives.length,1);assert.equal(result.alternatives[0].cost,6);assert.equal(result.alternatives[0].savings,2);assert.equal(result.alternatives[0].lines[0].packages,1);
 assert.equal(analyzePurchase(purchase({lines:[{id:'l',product_id:'p',count:1,amount:8,ean:''}]}),[offer('alcampo',1)],{stores:['alcampo'],now}).alternatives.length,0);
});
test('partial basket discounts cannot be advertised as net savings; complete comparison uses net paid excluding shipping',()=>{
 const p=purchase({total:12,shipping:2,discount:1,lines:[{id:'l',product_id:'p',count:1,amount:8,ean},{id:'unknown',product_id:'',count:1,amount:3}]});
 const partial=analyzePurchase(p,[offer('alcampo',7)],{stores:['alcampo'],now}).alternatives[0];assert.equal(partial.coverage,1);assert.equal(partial.complete,false);assert.equal(partial.paid,8);assert.equal(partial.savings,null);assert.equal(partial.discountAmbiguous,true);
 const complete=analyzePurchase(purchase({total:9,shipping:2,discount:1}),[offer('alcampo',3)],{stores:['alcampo'],now}).alternatives[0];assert.equal(complete.paid,7);assert.equal(complete.savings,1);
});
test('unreviewed unknown identifiers and missing alternative prices never count as zero-cost products',()=>{
 const result=analyzePurchase(purchase(),[],{stores:['alcampo'],now});assert.equal(result.alternatives.length,0);assert.equal(result.changed,0);assert.equal(result.splitCost,8);
});

test('several alternatives from one store do not qualify as a two-store comparison',()=>{
 const obs=[offer('alcampo',2,{reference_id:'one',pack_quantity:1,pack_unit:'uds'}),offer('alcampo',3,{reference_id:'two',pack_quantity:1,pack_unit:'uds'}),offer('carrefour',null),offer('lidl',5,{at:now+1})];
 assert.equal(analyzeCatalog(products,obs,{stores:['alcampo','carrefour','lidl'],now}).rows.length,0);
 assert.equal(analyzeCatalog(products,[...obs,offer('carrefour',4,{pack_quantity:1,pack_unit:'uds'})],{stores:['alcampo','carrefour','lidl'],now}).rows.length,1);
});
