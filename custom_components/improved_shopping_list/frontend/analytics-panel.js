const node=(tag,cls,text)=>{const el=document.createElement(tag);if(cls)el.className=cls;if(text!==undefined)el.textContent=text;return el;};
const names={mercadona:'Mercadona',carrefour:'Carrefour',alcampo:'Alcampo',consum:'Consum',lasirena:'La Sirena',eroski:'Eroski',dia:'DIA',lidl:'Lidl'};
const money=(cents,currency)=>new Intl.NumberFormat('es-ES',{style:'currency',currency}).format(cents/100);
const scales={uds:['uds',1],ud:['uds',1],kg:['kg',1],g:['kg',.001],gr:['kg',.001],ml:['l',.001],cl:['l',.01],l:['l',1]};
const number=value=>typeof value==='boolean'||value===null||value===''?NaN:Number(value);
const validMoney=value=>Number.isFinite(number(value))&&number(value)>=0;
const gtin=value=>{if(typeof value!=='string'||!/^(?:\d{8}|\d{12,14})$/.test(value))return '';const sum=[...value.slice(0,-1)].reverse().reduce((total,digit,i)=>total+Number(digit)*(i%2?1:3),0);return (10-sum%10)%10===Number(value.at(-1))?value.padStart(14,'0'):'';};
export function normalizeObservation(raw){
  if(!raw||raw.reference_excluded||!validMoney(raw.price)||!Number.isFinite(number(raw.at))||number(raw.at)<=0||!/^[A-Z]{3}$/.test(raw.currency??''))return null;
  const price=number(raw.price),ean=gtin(raw.ean),reference=String(raw.reference_unit??'').toLowerCase().trim().replace(/^€\s*\/\s*/,'');
  const refs={per_each:['uds',1],per_1kg:['kg',1],per_1l:['l',1],per_100g:['kg',.1],per_100ml:['l',.1],...scales};
  let unit='',quantity=null,rate=null;
  const pack=scales[String(raw.pack_unit??'').toLowerCase()];
  if(!raw.format_pending&&pack&&number(raw.pack_quantity)>0){unit=pack[0];quantity=number(raw.pack_quantity)*pack[1];rate=price/quantity;}
  else if(!raw.format_pending&&refs[reference]&&validMoney(raw.reference_price)){unit=refs[reference][0];rate=number(raw.reference_price)/refs[reference][1];quantity=rate>0?price/rate:null;}
  else if(!raw.format_pending&&raw.source==='web'){
    const match=String(raw.store_name||raw.name||'').match(/(\d+(?:[.,]\d+)?)\s*(kg|g|ml|cl|l)\b/i);
    if(match&&Number(match[1].replace(',','.'))>0){const factor=scales[match[2].toLowerCase()];unit=factor[0];quantity=Number(match[1].replace(',','.'))*factor[1];rate=price/quantity;}
  }
  return {...raw,price,at:number(raw.at),ean,basis:unit|| (ean?'ean:'+ean:null),unit:unit||'envase',quantity,rate:unit?rate:ean?price:null};
}
export function analyzeCatalog(products,observations,options={}){
  const now=options.now??Date.now()/1000,stores=options.stores??[],currency=options.currency??'EUR',age=options.maxAge?options.maxAge*86400:Infinity;
  const latest=new Map();
  for(const raw of observations){const offer=normalizeObservation(raw);if(!offer||offer.currency!==currency||!stores.includes(offer.store)||offer.at>now||now-offer.at>age)continue;const key=offer.product_id+':'+offer.store+':'+(offer.commercial_reference_id||offer.reference_id||offer.ean||'legacy');const candidate={...offer,basis:scales[offer.unit]?.[0]??null,rate:scales[offer.unit]?offer.rate:null},previous=latest.get(key);if(!previous||candidate.basis&&!previous.basis||Boolean(candidate.basis)===Boolean(previous.basis)&&previous.at<candidate.at)latest.set(key,candidate);}
  const filtered=products.filter(p=>(!options.category||p.category===options.category)&&(!options.store||[...latest.values()].some(offer=>offer.product_id===p.id&&offer.store===options.store)));
  const rows=filtered.map(product=>{
    const allOffers=[...latest.values()].filter(offer=>offer.product_id===product.id),groups=new Map();
    for(const offer of allOffers)if(offer.basis){if(!groups.has(offer.basis))groups.set(offer.basis,[]);const group=groups.get(offer.basis),before=group.find(o=>o.store===offer.store);if(!before)group.push(offer);else if(offer.rate<before.rate)group.splice(group.indexOf(before),1,offer);}
    const comparable=[...groups.values()].sort((a,b)=>b.length-a.length||a[0].basis.localeCompare(b[0].basis))[0]??[];
    const offers=stores.map(store=>comparable.find(offer=>offer.store===store)||allOffers.filter(offer=>offer.store===store).sort((a,b)=>b.at-a.at)[0]).filter(Boolean);
    const min=comparable.length>1?Math.min(...comparable.map(o=>o.rate)):null,max=min===null?null:Math.max(...comparable.map(o=>o.rate));
    return {product,offers,basis:comparable[0]?.basis??null,unit:comparable[0]?.unit??'envase',comparable:comparable.length>1,min,max,difference:min===null?null:max-min,bestStores:min===null?[]:comparable.filter(o=>Math.abs(o.rate-min)<.000001).map(o=>o.store)};
  }).filter(row=>row.offers.length>=2).sort((a,b)=>a.product.name.localeCompare(b.product.name,'es'));
  const ranking=stores.map(store=>({store,known:rows.filter(r=>r.offers.some(o=>o.store===store)).length,wins:rows.filter(r=>r.bestStores.includes(store)).length})).sort((a,b)=>b.wins-a.wins||b.known-a.known||a.store.localeCompare(b.store));
  const participating=ranking.filter(shop=>shop.known).map(shop=>shop.store);
  const common=participating.length>1?rows.filter(row=>row.comparable&&participating.every(store=>row.offers.some(o=>o.store===store&&o.basis===row.basis))):[];
  const totals=common.length?participating.map(store=>({store,total:common.reduce((sum,row)=>sum+row.offers.find(o=>o.store===store).rate,0)})).sort((a,b)=>a.total-b.total):[];
  return {rows,ranking,common:common.length,totals,known:rows.filter(r=>r.offers.length).length,comparable:rows.filter(r=>r.comparable).length,oldest:Math.min(...rows.flatMap(r=>r.offers.map(o=>o.at))),currency};
}
export function indexObservations(observations){
  const index=new Map();for(const raw of observations){const offer=normalizeObservation(raw);if(!offer)continue;const key=offer.product_id+':'+offer.store+':'+offer.currency;if(!index.has(key))index.set(key,[]);index.get(key).push(offer);}for(const values of index.values())values.sort((a,b)=>b.at-a.at);return index;
}
export function analyzePurchase(purchase,observations,options={}){
  const now=options.now??Date.now()/1000,historical=options.mode!=='current',cutoff=historical?purchase.at:now,window=(options.days??30)*86400;
  const index=options.index??indexObservations(observations);
  const lines=purchase.lines??[],stores=(options.stores??[]).filter(store=>store!==purchase.store);
  const alternatives=stores.map(store=>{
    const compared=lines.map(line=>{
      if(!line.product_id||!validMoney(line.amount)||!(number(line.count)>0))return null;
      const original=normalizeObservation({...line,price:number(line.amount)/number(line.count),at:purchase.at,currency:purchase.currency});
      if(!original)return null;
      const fresh=new Map();for(const o of index.get(line.product_id+':'+store+':'+purchase.currency)??[]){if(o.at>cutoff||(historical&&cutoff-o.at>window))continue;const key=o.commercial_reference_id||o.reference_id||o.ean||'legacy';if(!fresh.has(key))fresh.set(key,o);}
      const candidates=[...fresh.values()].filter(o=>(original.ean&&o.ean===original.ean)||(original.basis&&original.quantity>0&&o.basis===original.basis)).map(offer=>{
        if(original.ean&&offer.ean===original.ean)return {offer,cost:offer.price*number(line.count),packages:number(line.count)};
        const required=original.quantity*number(line.count),packages=offer.quantity>0?Math.ceil(Math.max(0,required/offer.quantity-1e-9)):null;
        return {offer,cost:packages===null?offer.rate*required:packages*offer.price,packages};
      }).sort((a,b)=>a.cost-b.cost);if(!candidates.length)return null;
      const {offer,cost,packages}=candidates[0];
      return {line,offer,paid:number(line.amount),cost:Math.round(cost*100)/100,packages};
    }).filter(Boolean);
    const complete=compared.length===lines.length&&lines.length>0;
    const paid=complete?number(purchase.total)-(number(purchase.shipping)||0):compared.reduce((sum,l)=>sum+l.paid,0),cost=compared.reduce((sum,l)=>sum+l.cost,0);
    const discountAmbiguous=!complete&&Math.abs(number(purchase.discount)||0)>.001;
    return {store,lines:compared,coverage:compared.length,complete,paid,cost,difference:paid-cost,savings:discountAmbiguous?null:paid-cost,discountAmbiguous};
  }).filter(a=>a.coverage).sort((a,b)=>Number(b.complete)-Number(a.complete)||b.coverage-a.coverage||a.cost-b.cost);
  const split=lines.map(line=>{
    const candidates=alternatives.flatMap(a=>a.lines.filter(l=>l.line===line).map(l=>({...l,store:a.store})));
    const chosen=candidates.sort((a,b)=>a.cost-b.cost)[0];
    return chosen&&chosen.cost<number(line.amount)?chosen:{line,store:purchase.store,cost:number(line.amount),paid:number(line.amount)};
  });
  const splitCost=split.reduce((sum,l)=>sum+l.cost,0),changed=split.filter(l=>l.store!==purchase.store).length;
  return {purchase,alternatives,split,splitCost,changed,splitSavings:Math.abs(number(purchase.discount)||0)>.001?null:lines.reduce((sum,l)=>sum+number(l.amount),0)-splitCost,mode:historical?'historical':'current'};
}

class ImprovedShoppingAnalytics extends HTMLElement {
  constructor(){super();this.attachShadow({mode:'open'});this._catalogLimit=30;}
  set data(value){if(value.active&&value.view==='comparison'&&(!this._active||this._view!=='comparison'))this._comparisonKey=null;const entering=value.active&&value.view==='nutrition'&&(!this._active||this._view!=='nutrition');this._data=value;this._active=value.active;this._view=value.view;if(entering)this._nutritionKey=null;if(!this._built)this._build();this._render();}
  disconnectedCallback(){this._nutritionToken=null;this._nutritionKey=null;this._comparisonToken=null;this._comparisonKey=null;}
  _build(){this._built=true;this.shadowRoot.innerHTML=`<style>
    :host{display:block;color:inherit;font:inherit}*{box-sizing:border-box}[hidden]{display:none!important}
    .card{padding:22px;border:1px solid var(--divider-color,#dfe7e1);border-radius:18px;background:var(--card-background-color,#fff);margin-bottom:18px;min-width:0}
    h2{font-size:18px;margin:0 0 14px}h3{font-size:16px}p{line-height:1.5}.muted{color:var(--secondary-text-color,#63766b);font-size:12px}
    .list-select{display:flex;align-items:center;gap:12px;margin-bottom:18px}select{font:inherit;color:inherit;background:var(--card-background-color,#fff);border:1px solid var(--divider-color,#dfe7e1);border-radius:10px;padding:10px;min-width:0;max-width:100%}
    .shops{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,180px),1fr));gap:10px}.shop{padding:14px;border-radius:12px;background:var(--secondary-background-color,#edf4ee)}.shop img{width:32px;height:32px;object-fit:contain;background:#fff;padding:3px;border-radius:50%;vertical-align:middle;margin-right:8px}.shop strong,.shop small{display:block;margin-top:8px}
    .stats .stat-text strong{font-size:clamp(15px,4vw,24px)}.stats .stat-date strong{white-space:nowrap;font-variant-numeric:tabular-nums;font-size:26px}@media(max-width:540px){.stats .stat-date strong{font-size:14px}}
    .best{color:var(--success-color,#268455);font-weight:700}.scroll{overflow:auto;max-width:100%}table{border-collapse:collapse;width:100%;font-size:14px}th,td{text-align:right;padding:12px 10px;border-bottom:1px solid var(--divider-color,#dfe7e1);white-space:nowrap}th:first-child,td:first-child{text-align:left;white-space:normal;min-width:120px}caption{text-align:left;font-weight:700;padding:12px 0}td small,th small{display:block;font-weight:400;font-size:11px;color:var(--secondary-text-color,#63766b)}
    ul{padding-left:22px}li{margin:8px 0}select:focus-visible,summary:focus-visible{outline:3px solid var(--primary-color,#267052);outline-offset:3px}
            .nutrition-row { display:grid; grid-template-columns:36px minmax(0,1fr) 105px; align-items:center; gap:12px; margin:18px 0; }
        .nutrition-grade { display:grid; place-items:center; width:36px; height:36px; border-radius:9px; font-weight:750; }
        .nutrition-track { background:var(--secondary-background-color,#edf4ee); height:28px; border-radius:6px; overflow:hidden; }
        .nutrition-bar { height:100%; border-radius:6px; }
        .nutrition-value { text-align:right; font-size:13px; font-variant-numeric:tabular-nums; }
        .nutrition-row { cursor:pointer; list-style:none; }
        .nutrition-row::-webkit-details-marker { display:none; }
        .nutrition-row::before,.nutrition-group[open]>.nutrition-row::before { content:none; }
        .nutrition-row:focus-visible { outline:3px solid var(--primary-color,#267052); outline-offset:3px; }
        .nutrition-value::after { content:" ▾"; }
        .nutrition-group[open] .nutrition-value::after { content:" ▴"; }
        .nutrition-products { margin:0 0 20px; padding:0; list-style:none; }
        .nutrition-products li { padding:10px 12px; border-bottom:1px solid var(--divider-color,#dfe7e1); overflow-wrap:anywhere; }
        @media(max-width:390px) { .nutrition-row { grid-template-columns:30px minmax(0,1fr) 90px; gap:8px; } .nutrition-grade { width:30px; height:30px; } }
    @media(max-width:540px){.card{padding:18px 14px}.list-select{flex-wrap:wrap}}

    button,input{font:inherit;color:inherit}button{cursor:pointer}.comparison-tabs{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:18px}.comparison-tabs button{display:flex;align-items:center;gap:7px;border:0;border-radius:10px;padding:11px 16px;background:transparent}.comparison-tabs [aria-pressed=true]{background:var(--secondary-background-color,#edf4ee);font-weight:700}.comparison-tabs ha-icon{--mdc-icon-size:20px;width:20px;height:20px}
    .filters{display:flex;gap:10px;flex-wrap:wrap;align-items:end;margin-bottom:18px}.filters label{font-size:12px;display:flex;flex-direction:column;gap:6px;min-width:0;flex:1 1 135px}.filters input{width:100%;min-width:0;border:1px solid var(--divider-color,#dfe7e1);background:var(--card-background-color,#fff);border-radius:10px;padding:10px;min-height:42px}.filters select{width:100%;min-height:42px}.stats{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin-bottom:18px}.stat{padding:18px;border-radius:15px;background:var(--card-background-color,#fff);border:1px solid var(--divider-color,#dfe7e1);min-width:0}.stat strong{display:block;font-size:clamp(20px,3vw,30px);line-height:1.2;margin-bottom:8px;color:var(--primary-color,#267052);overflow-wrap:anywhere}.stat span{font-size:12px;opacity:.7}.stat small{display:block;font-size:11px;opacity:.6;margin-top:5px}.chart-title{margin-bottom:20px}.rank-row{display:grid;grid-template-columns:140px minmax(40px,1fr) 100px;align-items:center;gap:12px;margin:16px 0}.shop-label{display:flex;align-items:center;gap:8px;min-width:0;font-weight:650;font-size:13px}.shop-label img{width:30px;height:30px;padding:3px;border-radius:8px;background:#fff;object-fit:contain;flex:none}.rank-track{height:24px;background:var(--secondary-background-color,#edf4ee);border-radius:8px;overflow:hidden}.rank-bar{height:100%;border-radius:8px;background:linear-gradient(90deg,#268a71,#5bbc95)}.rank-total{text-align:right;font-size:12px}.rank-total small{display:block;font-size:10px;opacity:.65}.table-product{display:flex;align-items:center;gap:9px;min-width:150px}.table-product img,.table-product ha-icon{width:32px;height:32px;--mdc-icon-size:30px;object-fit:contain;flex:none}.table-product span{overflow-wrap:anywhere}.saving{display:inline-block;border-radius:7px;padding:4px 7px;background:color-mix(in srgb,var(--success-color,#268455) 12%,transparent);color:var(--success-color,#268455);font-size:12px;font-weight:700}.costlier{color:var(--error-color,#d32f2f)}.comparison-more{display:block;margin:14px auto;border:0;background:var(--secondary-background-color,#edf4ee);border-radius:10px;padding:12px 20px}.purchase-comparison{margin-bottom:16px;padding:0;overflow:hidden}.purchase-comparison>summary{list-style:none;display:flex;align-items:center;gap:12px;cursor:pointer;padding:18px}.purchase-comparison>summary::-webkit-details-marker{display:none}.purchase-comparison>summary::after{content:'▾';margin-left:8px}.purchase-comparison[open]>summary::after{content:'▴'}.purchase-comparison>summary>.shop-label{flex:1;min-width:0}.purchase-identity{display:flex;flex-direction:column;gap:5px}.purchase-paid{text-align:right;white-space:nowrap;font-weight:700}.purchase-paid small{display:block;font-size:11px;font-weight:400;opacity:.65}.purchase-body{padding:0 18px 18px}.purchase-note{font-size:12px;opacity:.7}.alternative{border-top:1px solid var(--divider-color,#dfe7e1);padding:16px 0}.alternative-heading{display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap}.pair-bars{display:grid;grid-template-columns:90px minmax(0,1fr) 80px;gap:7px;align-items:center;margin-top:10px;font-size:12px}.pair-track{height:18px;background:var(--secondary-background-color,#edf4ee);border-radius:6px;overflow:hidden}.pair-value{height:100%;background:#94a3b8;border-radius:6px}.pair-value.alternative-value{background:#38a583}.pair-price{text-align:right;white-space:nowrap}.row-detail{margin-top:12px}.row-detail table{font-size:12px}.pill{font-size:11px;display:inline-block;border-radius:7px;background:var(--secondary-background-color,#edf4ee);padding:4px 7px;margin-top:5px}.empty-state{padding:25px;text-align:center;border:1px dashed var(--divider-color,#dfe7e1);border-radius:14px;font-size:14px}.comparison-message{padding:12px 0}.common-cards{display:flex;gap:10px;flex-wrap:wrap}.common-shop{padding:12px;background:var(--secondary-background-color,#edf4ee);border-radius:10px;flex:1 1 140px}.common-shop strong{display:block;margin-top:8px}.comparison-note{font-size:12px;line-height:1.6;opacity:.7;margin:10px 0 18px}.card-head{display:flex;align-items:center;justify-content:space-between;gap:8px}.comparison-retry{padding:10px 16px;border:0;border-radius:8px;background:var(--secondary-background-color,#edf4ee)}
    @media(max-width:540px){.stats{gap:7px;grid-template-columns:repeat(2,minmax(0,1fr))}.stats>.stat:last-child{grid-column:1/-1;display:flex;align-items:center;gap:10px;flex-wrap:wrap}.stats>.stat:last-child strong{margin:0;font-size:20px}.stats>.stat:last-child small{margin:0}.stat{padding:12px 9px}.stat strong{font-size:20px}.stat span{font-size:11px}.rank-row{grid-template-columns:95px minmax(30px,1fr) 68px;gap:7px}.rank-total{font-size:11px}.shop-label{font-size:12px;gap:6px}.shop-label img{width:26px;height:26px}.purchase-comparison>summary{padding:14px;gap:8px}.purchase-body{padding:0 14px 14px}.pair-bars{grid-template-columns:62px minmax(25px,1fr) 65px;font-size:11px;gap:5px}.comparison-tabs button{padding:10px 12px}.comparison-note{font-size:11px}}
    </style><section id="comparison"><p id="comparison-status" class="comparison-message" role="status" hidden></p><button id="comparison-retry" class="comparison-retry" type="button" hidden>Reintentar</button><div id="catalog-filters" class="filters"><label>Buscar producto<input id="analysis-search" type="search" placeholder="Nombre o etiquetas"></label><label>Categoría<select id="analysis-category" aria-label="Categoría"><option value="">Todas</option></select></label><label>Tienda<select id="analysis-store" aria-label="Tienda"><option value="">Todas</option></select></label><label>Antigüedad del precio<select id="analysis-age" aria-label="Antigüedad del precio"><option value="0">Todos los guardados</option><option value="30">Últimos 30 días</option><option value="90">Últimos 90 días</option><option value="365">Último año</option></select></label><label>Moneda<select id="analysis-currency" aria-label="Moneda"><option>EUR</option></select></label></div><div id="comparison-data"></div></section>
    <section id="analytics-nutrition" class="card" hidden><h2>Nutri-Score del catálogo</h2><p>Distribución de los productos con Nutri-Score guardado. Cada producto cuenta una vez; los productos sin Nutri-Score no se incluyen.</p><p id="nutrition-status" role="status"></p><div id="nutrition-chart" role="group" hidden></div><p id="nutrition-total" hidden></p></section>`;
    for(const id of ['analysis-search','analysis-category','analysis-store','analysis-age','analysis-currency'])this.shadowRoot.querySelector('#'+id).addEventListener(id==='analysis-search'?'input':'change',()=>{this._catalogLimit=30;this._renderComparison();});
    this.shadowRoot.querySelector('#comparison-retry').addEventListener('click',()=>{this._comparisonKey=null;this._render();});
  }
  _render(){
    const root=this.shadowRoot,d=this._data;
    root.querySelector('#comparison').hidden=this._view!=='comparison';root.querySelector('#analytics-nutrition').hidden=this._view!=='nutrition';
    if(!this._active)return;
    if(this._view==='nutrition'){this._renderNutrition();return;}if(this._view!=='comparison')return;
    this._ensureComparison();this._renderComparison();
  }

  _ensureComparison(){
    const d=this._data;if(!d.enabled)return;
    const key=JSON.stringify([(d.products??[]).map(p=>[p.id,p.revision]),d.stores,d.comparisonRevision,d.priceKey]);
    if(this._comparisonKey===key)return;this._comparisonKey=key;this._comparisonLoading=true;this._comparisonError='';
    const token=this._comparisonToken={};
    void d.hass.callWS({type:'improved_shopping_list/analytics/comparison'}).then(result=>{
      if(token!==this._comparisonToken||!this.isConnected)return;
      this._comparisonSnapshot=result;this._comparisonDataRevision=(this._comparisonDataRevision||0)+1;this._comparisonLoading=false;this._syncComparisonFilters();this._renderComparison();
    }).catch(error=>{if(token!==this._comparisonToken||!this.isConnected)return;this._comparisonLoading=false;this._comparisonError=error.message||'No se han podido cargar los datos de comparación.';this._renderComparison();});
  }
  _syncComparisonFilters(){
    const root=this.shadowRoot,data=this._comparisonSnapshot;
    const fill=(id,entries,empty)=>{const select=root.querySelector('#'+id),old=select.value;select.replaceChildren(...(empty?[new Option(empty,'')]:[]),...entries.map(([value,text])=>new Option(text,value)));if([...select.options].some(o=>o.value===old))select.value=old;};
    fill('analysis-category',[...new Set((this._data.products??[]).map(p=>p.category).filter(Boolean))].sort((a,b)=>a.localeCompare(b,'es')).map(value=>[value,value]),'Todas');
    fill('analysis-store',(data.stores??[]).map(store=>[store,names[store]??store]),'Todas');
    fill('analysis-currency',[...new Set(['EUR',...(data.observations??[]).map(o=>o.currency).filter(c=>/^[A-Z]{3}$/.test(c??''))])].sort().map(c=>[c,c]));
  }
  _shopLabel(store,caption){const label=node('span','shop-label');if(this._data.logos?.[store]){const image=node('img');image.src=this._data.logos[store];image.alt='';image.referrerPolicy='no-referrer';label.append(image);}label.append(node('span','',caption||names[store]||store));return label;}
  _stat(value,label,detail){const card=node('div','stat'+(/^\d{1,2}\/\d{1,2}\/\d{4}$/.test(String(value))?' stat-date':typeof value==='string'?' stat-text':''));card.append(node('strong','',value),node('span','',label));if(detail)card.append(node('small','',detail));return card;}
  _amount(value,currency='EUR'){return money(Math.round(value*100),currency);}
  _empty(text){return node('p','empty-state',text);}
  _renderComparison(){
    if(!this._built||!this._active||this._view!=='comparison')return;
    const root=this.shadowRoot,container=root.querySelector('#comparison-data'),status=root.querySelector('#comparison-status');
    const renderKey=JSON.stringify([this._comparisonKey,this._comparisonLoading,this._comparisonError,this._comparisonDataRevision,this._data.enabled,this._catalogLimit,...['analysis-search','analysis-category','analysis-store','analysis-age','analysis-currency'].map(id=>root.querySelector('#'+id).value)]);
    if(renderKey===this._comparisonRenderKey)return;this._comparisonRenderKey=renderKey;
    container.replaceChildren();root.querySelector('#comparison-retry').hidden=!this._comparisonError;
    const message=!this._data.enabled?'Los precios están desactivados en Ajustes → Tiendas.':this._comparisonLoading?'Preparando el análisis de precios guardados…':this._comparisonError;
    status.textContent=message||'';status.hidden=!message;if(message)return;
    if(!this._comparisonSnapshot)return;
    this._renderCatalogComparison(container);
  }
  _renderCatalogComparison(container){
    const root=this.shadowRoot,data=this._comparisonSnapshot,query=root.querySelector('#analysis-search').value.normalize('NFD').replace(/\p{M}/gu,'').toLowerCase().trim();
    const products=(this._data.products??[]).filter(p=>!query||[p.name,...(p.tags??[])].join(' ').normalize('NFD').replace(/\p{M}/gu,'').toLowerCase().includes(query));
    const result=analyzeCatalog(products,data.observations??[],{stores:data.stores??[],currency:root.querySelector('#analysis-currency').value,category:root.querySelector('#analysis-category').value,store:root.querySelector('#analysis-store').value,maxAge:Number(root.querySelector('#analysis-age').value)});
    const stats=node('div','stats'),winner=result.ranking[0]?.wins?result.ranking[0]:null,winners=winner?result.ranking.filter(shop=>shop.wins===winner.wins):[];
    stats.append(this._stat(result.comparable,'Productos comparables',result.rows.length+' con precios en varias tiendas · '+(result.rows.length-result.comparable)+' pendientes de contenido comparable'),this._stat(winners.length>1?winners.length+' tiendas':winner?names[winner.store]:'—',winners.length>1?'Empate en mínimos':'Más productos al menor precio',winner?winner.wins+(winner.wins===1?' mínimo':' mínimos')+(winners.length>1?' por tienda':', incluidos empates'):'Hace falta precio equivalente en varias tiendas'),this._stat(Number.isFinite(result.oldest)?new Date(result.oldest*1000).toLocaleDateString('es-ES'):'—','Precio más antiguo del análisis'));
    container.append(stats);
    if(data.observations_truncated)container.append(node('p','comparison-note','El análisis usa las 20.000 observaciones de precio más recientes disponibles.'));
    if(!result.rows.length){container.append(this._empty('No hay productos con precio guardado en al menos dos tiendas que coincidan con estos filtros.'));return;}
    container.append(node('p','comparison-note','Comparamos precios por kg, litro o unidad, independientemente de la marca y del EAN. En cada tienda se elige la alternativa con menor precio por la misma unidad. Los productos con precios en varias tiendas también se muestran cuando falta contenido del envase; esos precios se indican por envase y no cuentan para decidir qué tienda es más barata.'));
    if(result.known){
      const chart=node('section','card');chart.append(node('h2','chart-title','Dónde están los precios más bajos'));
      const maximum=Math.max(1,...result.ranking.map(shop=>shop.wins));
      for(const shop of result.ranking){
        const row=node('div','rank-row');row.dataset.store=shop.store;row.append(this._shopLabel(shop.store));const track=node('div','rank-track'),bar=node('div','rank-bar');bar.style.width=shop.wins/maximum*100+'%';track.append(bar);track.setAttribute('role','img');track.setAttribute('aria-label',(names[shop.store]??shop.store)+': '+shop.wins+' productos al menor precio');
        const total=node('span','rank-total',shop.wins+(shop.wins===1?' mínimo':' mínimos'));total.append(node('small','',shop.known+' con precio'));row.append(track,total);chart.append(row);
      }
      chart.append(node('p','muted','Se cuentan los mínimos de productos con al menos dos precios equivalentes. Los empates cuentan para todas las tiendas correspondientes.'));container.append(chart);
    }else container.append(this._empty('No hay precios guardados para estos productos en estas tiendas.'));
    if(result.common){
      const card=node('section','card');card.append(node('h2','','La misma cesta de referencia · '+result.common+(result.common===1?' producto':' productos')));
      card.append(node('p','muted','Una unidad de referencia por producto: 1 unidad, 1 kg o 1 litro, según indica la tabla. Solo los productos con precio equivalente en todas estas tiendas. No es una lista de compra real.'));
      const shops=node('div','common-cards');for(const [index,shop] of result.totals.entries()){const block=node('div','common-shop');block.append(this._shopLabel(shop.store),node('strong',Math.abs(shop.total-result.totals[0].total)<.000001?'best':'',this._amount(shop.total,result.currency)));shops.append(block);}card.append(shops);container.append(card);
    }
    const card=node('section','card'),scroll=node('div','scroll'),table=node('table');table.append(node('caption','','Precios del catálogo · '+result.currency));const stores=result.ranking.map(s=>s.store);
    const head=node('tr');head.append(node('th','','Producto'));for(const store of stores){const th=node('th');th.append(this._shopLabel(store));head.append(th);}head.append(node('th','','Diferencia máxima'));const thead=node('thead');thead.append(head);table.append(thead);
    const body=node('tbody');
    for(const row of result.rows.slice(0,this._catalogLimit)){
      const tr=node('tr'),title=node('th'),product=node('div','table-product');tr.dataset.productId=row.product.id;
      if(row.product.image_url){const image=node('img');image.src=row.product.image_url;image.alt='';image.loading='lazy';product.append(image);}else{const icon=node('ha-icon');icon.setAttribute('icon',row.product.icon||'mdi:shopping');icon.setAttribute('aria-hidden','true');product.append(icon);}
      const name=node('span','',row.product.name);name.append(node('small','',row.comparable?'Por '+(row.unit==='uds'?'unidad':row.unit):'Falta contenido comparable'));product.append(name);title.append(product);tr.append(title);
      for(const store of stores){const offer=row.offers.find(o=>o.store===store),equivalent=offer&&row.basis&&offer.basis===row.basis;const td=node('td',row.bestStores.includes(store)?'best':'',offer?this._amount(equivalent?offer.rate:offer.price,result.currency):'Sin precio');
        if(offer){td.append(node('small','',equivalent?'Por '+(row.unit==='uds'?'unidad':row.unit):'Por envase · falta contenido comparable'),node('small','',new Date(offer.at*1000).toLocaleDateString('es-ES')));}tr.append(td);}
      const difference=node('td');difference.append(row.difference!==null?node('span','saving',this._amount(row.difference,result.currency)+'/'+(row.unit==='uds'?'ud':row.unit)):node('span','muted','Sin comparación'));tr.append(difference);body.append(tr);
    }
    table.append(body);scroll.append(table);card.append(scroll);container.append(card);
    if(result.rows.length>this._catalogLimit){const more=node('button','comparison-more','Mostrar más productos');more.type='button';more.addEventListener('click',()=>{this._catalogLimit+=30;this._renderComparison();});container.append(more);}
  }
  _renderNutrition() {
    if(!this._built || !this._data || !this._active || this._view !== 'nutrition')return;
    const root=this.shadowRoot, hass=this._data.hass;
    const key=JSON.stringify((this._data.products ?? []).map(product=>[product.id,product.name,product.barcode,product.barcodes]));
    if(!hass || (this._nutritionKey===key && this._nutritionConnection===hass.connection))return;
    this._nutritionKey=key;this._nutritionConnection=hass.connection;
    const token=this._nutritionToken={};
    const status=root.querySelector('#nutrition-status'),chart=root.querySelector('#nutrition-chart'),total=root.querySelector('#nutrition-total');
    status.hidden=false;status.textContent='Cargando Nutri-Score guardado…';chart.hidden=true;total.hidden=true;
    void hass.callWS({type:'improved_shopping_list/catalog/nutrition_distribution'}).then(data=>{
      if(token!==this._nutritionToken || !this.isConnected)return;
      const entries=Object.entries(data.counts),count=data.total;
      status.hidden=Boolean(count);
      status.textContent=count ? '' : 'Todavía no hay productos con Nutri-Score guardado en el catálogo.';
      chart.hidden=!count;total.hidden=!count;
      total.textContent=count+' productos con Nutri-Score';
      const colors={a:['#038141','#fff'],b:['#85bb2f','#182b22'],c:['#fecb02','#182b22'],d:['#ee8100','#182b22'],e:['#e63e11','#fff']};
      const labels=[];
      const expanded=new Set([...chart.querySelectorAll('details[open]')].map(group=>group.dataset.grade));
      const products=new Map((this._data.products ?? []).map(product=>[product.id,product]));
      chart.replaceChildren(...entries.map(([grade,value])=>{
        const percentage=count ? value/count*100 : 0;
        const label=grade.toUpperCase()+': '+value+' ('+percentage.toLocaleString('es',{maximumFractionDigits:1})+' %)';labels.push(label);
        const group=document.createElement('details');group.className='nutrition-group';group.dataset.grade=grade;group.open=expanded.has(grade);
        const row=document.createElement('summary');row.className='nutrition-row';row.dataset.grade=grade;row.setAttribute('aria-label','Nutri-Score '+label);
        const letter=document.createElement('span');letter.className='nutrition-grade';letter.textContent=grade.toUpperCase();
        letter.style.background=colors[grade][0];letter.style.color=colors[grade][1];
        const track=document.createElement('div');track.className='nutrition-track';
        const bar=document.createElement('div');bar.className='nutrition-bar';bar.style.width=percentage+'%';bar.style.background=colors[grade][0];track.append(bar);
        const text=document.createElement('span');text.className='nutrition-value';text.textContent=value+' ('+percentage.toLocaleString('es',{maximumFractionDigits:1})+' %)';
        const list=document.createElement('ul');list.className='nutrition-products';list.setAttribute('aria-label','Productos Nutri-Score '+grade.toUpperCase());
        const members=(data.product_ids?.[grade] ?? []).map(id=>products.get(id)).filter(Boolean).sort((a,b)=>a.name.localeCompare(b.name,'es',{sensitivity:'base'}));
        for(const product of members){const item=document.createElement('li');item.textContent=product.name;list.append(item);}
        if(!value){const item=document.createElement('li');item.textContent='No hay productos con esta calificación.';list.append(item);}
        row.append(letter,track,text);group.append(row,list);return group;
      }));
      chart.setAttribute('aria-label','Distribución Nutri-Score: '+labels.join('; '));
    }).catch(()=>{
      if(token!==this._nutritionToken || !this.isConnected)return;
      status.hidden=false;status.textContent='No se ha podido cargar el Nutri-Score guardado. Vuelve a abrir esta vista para reintentarlo.';
      this._nutritionKey=null;
    });
  }

}
if(!customElements.get('isl-analytics'))customElements.define('isl-analytics',ImprovedShoppingAnalytics);
