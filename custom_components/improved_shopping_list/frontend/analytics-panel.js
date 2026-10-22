const node=(tag,cls,text)=>{const el=document.createElement(tag);if(cls)el.className=cls;if(text!==undefined)el.textContent=text;return el;};
const names={mercadona:'Mercadona',carrefour:'Carrefour',alcampo:'Alcampo',consum:'Consum',lasirena:'La Sirena',eroski:'Eroski',dia:'DIA'};
const money=(cents,currency)=>new Intl.NumberFormat('es-ES',{style:'currency',currency}).format(cents/100);
export function compareBaskets(receipts) {
  const currencies=[...new Set(receipts.flatMap(shop=>shop.lines.filter(line=>line.offer).map(line=>line.offer.currency)))].sort();
  return currencies.map(currency=>{
    const shops=receipts.map(shop=>({...shop,lines:shop.lines.map(line=>({...line,offer:line.offer?.currency===currency?line.offer:null}))})).filter(shop=>shop.lines.some(line=>line.offer));
    const indices=shops[0]?.lines.map((_,index)=>index)??[];
    const covered=indices.filter(index=>shops.some(shop=>shop.lines[index].offer));
    const common=indices.filter(index=>shops.every(shop=>shop.lines[index].offer));
    const cents=offer=>Math.round(Number(offer.price)*100);
    const totals=shops.map(shop=>({...shop,coverage:shop.lines.filter(line=>line.offer).length,total:shop.lines.reduce((sum,line)=>sum+(line.offer?cents(line.offer):0),0),commonTotal:common.reduce((sum,index)=>sum+cents(shop.lines[index].offer),0)}));
    const complete=totals.filter(shop=>shop.coverage===indices.length).sort((a,b)=>a.total-b.total);
    const commonRank=[...totals].sort((a,b)=>a.commonTotal-b.commonTotal);
    const rows=indices.map(index=>{const offers=shops.map(shop=>shop.lines[index].offer);const known=offers.filter(Boolean);return {name:shops[0].lines[index].name,quantity:shops[0].lines[index].quantity,offers,min:known.length?Math.min(...known.map(cents)):null};});
    const split=totals.map(shop=>({store:shop.store,lines:[],total:0}));
    rows.forEach(row=>{if(row.min===null)return;const index=row.offers.findIndex(offer=>offer&&cents(offer)===row.min);split[index].lines.push(row.name);split[index].total+=row.min;});
    const splitTotal=split.reduce((sum,shop)=>sum+shop.total,0);
    const coveredSingle=totals.filter(shop=>shop.coverage===covered.length).sort((a,b)=>a.total-b.total)[0];
    return {currency,shops:totals,rows,common,commonRank,complete,split:split.filter(shop=>shop.lines.length),splitTotal,covered:covered.length,savings:coveredSingle?coveredSingle.total-splitTotal:null};
  });
}
class ImprovedShoppingAnalytics extends HTMLElement {
  constructor(){super();this.attachShadow({mode:'open'});}
  set data(value){const entering=value.active&&value.view==='nutrition'&&(!this._active||this._view!=='nutrition');this._data=value;this._active=value.active;this._view=value.view;if(entering)this._nutritionKey=null;if(!this._built)this._build();this._render();}
  disconnectedCallback(){this._nutritionToken=null;this._nutritionKey=null;}
  _build(){this._built=true;this.shadowRoot.innerHTML=`<style>
    :host{display:block;color:inherit;font:inherit}*{box-sizing:border-box}[hidden]{display:none!important}
    .card{padding:22px;border:1px solid var(--divider-color,#dfe7e1);border-radius:18px;background:var(--card-background-color,#fff);margin-bottom:18px;min-width:0}
    h2{font-size:18px;margin:0 0 14px}h3{font-size:16px}p{line-height:1.5}.muted{color:var(--secondary-text-color,#63766b);font-size:12px}
    .list-select{display:flex;align-items:center;gap:12px;margin-bottom:18px}select{font:inherit;color:inherit;background:var(--card-background-color,#fff);border:1px solid var(--divider-color,#dfe7e1);border-radius:10px;padding:10px;min-width:0;max-width:100%}
    .shops{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,180px),1fr));gap:10px}.shop{padding:14px;border-radius:12px;background:var(--secondary-background-color,#edf4ee)}.shop img{width:32px;height:32px;object-fit:contain;background:#fff;padding:3px;border-radius:50%;vertical-align:middle;margin-right:8px}.shop strong,.shop small{display:block;margin-top:8px}
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
    </style><section id="comparison"><div class="list-select"><label for="comparison-list">Lista de la compra</label><select id="comparison-list" aria-label="Lista para comparar"></select></div><div id="comparison-data"></div></section>
    <section id="analytics-nutrition" class="card" hidden><h2>Nutri-Score del catálogo</h2><p>Distribución de los productos con Nutri-Score guardado. Cada producto cuenta una vez; los productos sin Nutri-Score no se incluyen.</p><p id="nutrition-status" role="status"></p><div id="nutrition-chart" role="group" hidden></div><p id="nutrition-total" hidden></p></section>`;
    this.shadowRoot.querySelector('select').addEventListener('change',event=>this.onSelectList?.(event.target.value));
  }
  _render(){
    const root=this.shadowRoot,d=this._data;
    root.querySelector('#comparison').hidden=this._view!=='comparison';root.querySelector('#analytics-nutrition').hidden=this._view!=='nutrition';
    if(!this._active)return;
    if(this._view==='nutrition'){this._renderNutrition();return;}if(this._view!=='comparison')return;
    const select=root.querySelector('select');select.replaceChildren(...(d.entities??[]).map(id=>{const option=node('option','',d.hass.states[id]?.attributes.friendly_name??id);option.value=id;return option;}));select.value=d.entityId??'';select.disabled=d.loading;
    const container=root.querySelector('#comparison-data');container.replaceChildren();
    if(d.loading||d.error){container.append(node('p','',d.error||'Cargando lista…'));return;}
    if(!d.enabled){container.append(node('p','','Los precios están desactivados en Ajustes → Tiendas.'));return;}
    if(!d.count){container.append(node('p','','No hay productos pendientes en esta lista.'));return;}
    const groups=compareBaskets(d.receipts??[]);
    if(!groups.length){container.append(node('p','','No hay precios guardados para los productos de esta lista en las tiendas activas.'));return;}
    container.append(node('p','muted','Precios guardados para las cantidades de la lista. Los precios desconocidos se excluyen de las comparaciones. Las vinculaciones pueden corresponder a formatos o marcas distintos; revisa que sean equivalentes.'));
    for(const group of groups){
      const card=node('section','card');card.append(node('h2','','Compra por tienda · '+group.currency));const shops=node('div','shops');
      for(const shop of group.shops){const block=node('div','shop');block.dataset.store=shop.store;if(d.logos?.[shop.store]){const img=node('img');img.src=d.logos[shop.store];img.alt='';block.append(img);}block.append(node('b','',names[shop.store]),node('strong','',money(shop.total,group.currency)),node('small','',shop.coverage+'/'+d.count+' productos con precio · '+(shop.coverage===d.count?'Cesta completa':'Total parcial')));if(group.complete[0]?.store===shop.store)block.append(node('small','best','Cesta completa más barata'));shops.append(block);}card.append(shops);
      if(!group.complete.length)card.append(node('p','muted','Ninguna tienda tiene precio para toda la lista; no se puede determinar la compra completa más barata.'));
      if(group.common.length&&group.shops.length>1){const common=node('div','common-ranking');common.append(node('h3','','Comparación sobre '+group.common.length+(group.common.length===1?' producto común':' productos comunes')));for(const shop of group.commonRank)common.append(node('p',shop.store===group.commonRank[0].store?'best':'',names[shop.store]+': '+money(shop.commonTotal,group.currency)));card.append(common);}else if(group.shops.length>1)card.append(node('p','muted','No hay productos con precio en todas las tiendas para comparar una misma cesta.'));
      const scroll=node('div','scroll'),table=node('table');table.append(node('caption','','Precio por producto'));const header=node('tr');header.append(node('th','','Producto'));for(const shop of group.shops){const th=node('th','',names[shop.store]);th.scope='col';header.append(th);}const thead=node('thead');thead.append(header);table.append(thead);const body=node('tbody');
      for(const row of group.rows){const tr=node('tr'),title=node('th','',row.name);title.scope='row';if(row.quantity)title.append(node('small','',new Intl.NumberFormat('es-ES',{maximumFractionDigits:3}).format(row.quantity.quantity)+' '+row.quantity.unit));tr.append(title);for(const offer of row.offers){const td=node('td',offer&&Math.round(Number(offer.price)*100)===row.min?'best':'',offer?money(Math.round(Number(offer.price)*100),group.currency):'Sin precio');if(offer?.checked_at){const date=new Date(Number(offer.checked_at)*1000);if(!Number.isNaN(date.getTime()))td.append(node('small','','Guardado: '+date.toLocaleDateString('es-ES')));}tr.append(td);}body.append(tr);}table.append(body);scroll.append(table);card.append(scroll);
      const split=node('details','split');split.append(node('summary','','Compra repartida · '+money(group.splitTotal,group.currency)+' · '+group.covered+'/'+d.count+' productos'));for(const shop of group.split){split.append(node('h3','',names[shop.store]+' · '+money(shop.total,group.currency)));const list=node('ul');for(const name of shop.lines)list.append(node('li','',name));split.append(list);}if(group.savings!==null)split.append(node('p','','Ahorro frente a la tienda más barata con estos mismos productos: '+money(group.savings,group.currency)));if(group.covered<d.count)split.append(node('p','muted','Faltan precios de '+(d.count-group.covered)+' productos.'));split.append(node('p','muted','Sin gastos de envío, desplazamiento ni descuentos adicionales.'));card.append(split);container.append(card);
    }
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
