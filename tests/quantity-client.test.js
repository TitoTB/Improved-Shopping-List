import assert from 'node:assert/strict';
import test from 'node:test';
import { purchaseQuantity, quantityLabel, QuantitySession } from '../custom_components/improved_shopping_list/frontend/quantity-client.js';
import { recoveredStockQuantity } from '../custom_components/improved_shopping_list/frontend/reference-formats.js';

test('stock replenishment prioritizes recovered or estimated quantities and leaves unknown amounts to the stock default',()=>{
  const product={unit:'g',refill_quantity:1000,commercial_references:[]};
  assert.equal(recoveredStockQuantity({count:1,purchased_quantity:.45,purchased_unit:'kg'},product,'carrefour'),450);
  assert.equal(recoveredStockQuantity({count:1,purchased_quantity:.5,purchased_unit:'kg',quantity_estimated:true},product,'carrefour'),500);
  assert.equal(recoveredStockQuantity({count:2,pack_quantity:250,pack_unit:'g'},product,'carrefour'),500);
  assert.equal(recoveredStockQuantity({count:1,pack_quantity:null,pack_unit:''},product,'carrefour')??product.refill_quantity,1000);
  assert.equal(recoveredStockQuantity({count:1,purchased_quantity:500,purchased_unit:'ml'},product,'carrefour')??product.refill_quantity,1000);
  const capsules={unit:'uds',refill_quantity:10,commercial_references:[{store:'carrefour',reference_id:'R-1',name:'Producto',content_quantity:33,content_unit:'uds',content_confirmed:true}]};
  assert.equal(recoveredStockQuantity({count:2,reference_id:'R-1'},capsules,'carrefour'),66);
  capsules.commercial_references[0]={...capsules.commercial_references[0],name:'Verdura a granel 1 kg aprox',content_quantity:1,content_unit:'kg'};
  assert.equal(recoveredStockQuantity({count:1,reference_id:'R-1'},{...capsules,unit:'g'},'carrefour'),null);
});

test('purchase defaults, physical quantities and custom units share display semantics',()=>{
  assert.deepEqual(purchaseQuantity(null),{quantity:1,unit:'uds',step:1,unit_quantity:1});
  const product={purchase_unit:'g',unit_quantity:250,quantity_step:50};
  assert.equal(quantityLabel(purchaseQuantity(product)),'250 g');
  assert.equal(purchaseQuantity(product,{quantity:300,unit:'g'}).quantity,300);
  assert.equal(purchaseQuantity(product,{quantity:3,unit:'uds'}).quantity,250);
  assert.equal(quantityLabel(purchaseQuantity(null,{quantity:2.5,unit:'Latas',step:.5})),'2,5 Latas');
});

test('quantity adjustments preserve newer pushed snapshots and propagate errors',async()=>{
  let resolve,message;const response=new Promise(done=>resolve=done);
  const session=new QuantitySession(()=>({callWS:msg=>{message=msg;return response;}}),()=>{});
  const saving=session.adjust('todo.main','entry',1);
  assert.deepEqual(message,{type:'improved_shopping_list/quantities/adjust',entity_id:'todo.main',uid:'entry',direction:1});
  session._revision++;session._receive({entries:{'todo.main':{entry:{quantity:350,unit:'g'}}}});
  resolve({entries:{'todo.main':{entry:{quantity:300,unit:'g'}}}});await saving;
  assert.equal(session.entries['todo.main'].entry.quantity,350);
  session.getHass=()=>({callWS:async()=>{throw new Error('Proveedor no disponible');}});
  await assert.rejects(session.adjust('todo.main','entry',-1),/Proveedor no disponible/);
  assert.equal(session.entries['todo.main'].entry.quantity,350);
});
