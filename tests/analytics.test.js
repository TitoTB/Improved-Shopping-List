import {test} from 'node:test';
import assert from 'node:assert/strict';
globalThis.HTMLElement=class {};globalThis.customElements={get:()=>true};
const {compareBaskets}=await import('../custom_components/improved_shopping_list/frontend/analytics-panel.js');
const shop=(store,values,currency='EUR')=>({store,lines:values.map((price,index)=>({name:'Producto '+index,offer:price===null?null:{price,currency}}))});
test('unknown prices cannot win a complete basket; compare common products and split the same coverage',()=>{
 const [c]=compareBaskets([shop('carrefour',[2,5,3]),shop('alcampo',[1,null,4]),shop('dia',[3,4,4])]);
 assert.equal(c.complete[0].store,'carrefour');assert.equal(c.complete[0].total,1000);
 assert.deepEqual(c.common,[0,2]);assert.equal(c.commonRank[0].commonTotal,500);
 assert.equal(c.covered,3);assert.equal(c.splitTotal,800);assert.equal(c.savings,200);
 assert.deepEqual(c.split.map(s=>s.store),['carrefour','alcampo','dia']);
});
test('partial coverage never declares a complete winner or savings against a different basket',()=>{
 const [c]=compareBaskets([shop('carrefour',[1,null,null]),shop('alcampo',[null,2,null])]);
 assert.equal(c.complete.length,0);assert.equal(c.common.length,0);assert.equal(c.savings,null);assert.equal(c.covered,2);
});
test('currencies stay separate; zero is a known price and ties remain cheapest',()=>{
 const groups=compareBaskets([shop('carrefour',[0,2]),shop('alcampo',[0,1]),shop('dia',[0,1],'USD')]);
 assert.deepEqual(groups.map(c=>c.currency),['EUR','USD']);assert.equal(groups[0].rows[0].min,0);assert.equal(groups[0].shops.length,2);assert.equal(groups[1].shops.length,1);
 assert.deepEqual(compareBaskets([shop('carrefour',[null])]),[]);
});
test('all active stores are compared, beyond the four ticket shortcuts',()=>{
 const [c]=compareBaskets(['carrefour','alcampo','dia','mercadona','consum','eroski'].map((store,i)=>shop(store,[6-i])));
 assert.equal(c.shops.length,6);assert.equal(c.complete[0].store,'eroski');
});
