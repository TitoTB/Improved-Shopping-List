import test from "node:test";
import assert from "node:assert/strict";
import { matchCatalogProducts } from "../custom_components/improved_shopping_list/frontend/product-matching.js";

test("ranks exact and generic whole-word names without treating similarity as an association", () => {
  const products = [{id:"generic",name:"Cacao"},{id:"exact",name:"Cacao soluble"},{id:"other",name:"Café"}];
  assert.deepEqual(matchCatalogProducts({status:"found",name:"CACAO soluble"}, products).map(product => product.id), ["exact", "generic"]);
  assert.equal(products[0].barcode, undefined);
  assert.equal(matchCatalogProducts({status:"found",name:"Café molido"}, products)[0].id,"other");
  assert.deepEqual(matchCatalogProducts({status:"pending"}, products),[]);
  assert.deepEqual(matchCatalogProducts({status:"found",name:"Cacahuetes"}, products),[]);
});

test("does not match distinct milk names merely because they share a token", () => {
  const products=[{id:"generic",name:"Leche"},{id:"wrong",name:"Leche sin lactosa"},{id:"exact",name:"Leche entera"}];
  assert.deepEqual(matchCatalogProducts({status:"found",name:"Leche entera"},products).map(product=>product.id),["exact","generic"]);
});
