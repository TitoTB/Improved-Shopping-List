/** Locally bundled Leaflet; only visible tiles are requested from OpenStreetMap. */
import * as L from './vendor/leaflet/leaflet.js';
class ShopZoneMap extends HTMLElement {
  constructor(){
    super();this.attachShadow({mode:'open'});const css=document.createElement('link');css.rel='stylesheet';css.href=new URL('./vendor/leaflet/leaflet.css',import.meta.url).href;
    const style=document.createElement('style');style.textContent=':host{display:block;min-width:0}#map{height:280px;width:100%;border-radius:12px;background:#e2e8e4;color:#222;isolation:isolate}.leaflet-container{font:inherit}.leaflet-control-attribution{font-size:10px}';
    const container=document.createElement('div');container.id='map';container.setAttribute('aria-label','Mapa de zonas de la tienda');container.setAttribute('role','region');this.shadowRoot.append(css,style,container);
  }
  set data(value){this._data=value;this._render();}
  disconnectedCallback(){this._dispose();}
  _dispose(){this._observer?.disconnect();this._map?.remove();this._map=null;this._fitKey=null;}
  _render(){
    const data=this._data;if(!data?.active){this._dispose();return;}
    if(!this._map){
      this._map=L.map(this.shadowRoot.querySelector('#map'),{scrollWheelZoom:false}).setView(data.center??[0,0],data.center?14:2);
      this._tiles=L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,keepBuffer:0,updateWhenIdle:true,referrerPolicy:'strict-origin-when-cross-origin',attribution:'&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">OpenStreetMap contributors</a>'}).addTo(this._map);
      this._tiles.on('tileerror',()=>this.dispatchEvent(new CustomEvent('map-error',{detail:'No se ha podido cargar alguna parte del mapa. Puedes indicar las coordenadas manualmente.'})));
      this._layers=L.layerGroup().addTo(this._map);
      this._map.on('click',event=>{if(this._data?.creating)this.dispatchEvent(new CustomEvent('location-selected',{detail:{latitude:event.latlng.lat,longitude:event.latlng.lng}}));});
      this._observer=new ResizeObserver(()=>this._map?.invalidateSize({pan:false}));this._observer.observe(this);
    }
    this._layers.clearLayers();const bounds=L.latLngBounds([]);
    for(const zone of data.zones??[]){
      const circle=L.circle([zone.latitude,zone.longitude],{radius:zone.radius??100,color:data.color??'#267052',fillOpacity:.15}).addTo(this._layers);circle.bindTooltip(document.createTextNode(zone.name));bounds.extend(circle.getBounds());
      L.circleMarker([zone.latitude,zone.longitude],{radius:5,color:data.color??'#267052',fillOpacity:1}).addTo(this._layers);
    }
    if(data.draft){L.circle([data.draft.latitude,data.draft.longitude],{radius:data.draft.radius,color:'#168aec',dashArray:'6 4',fillOpacity:.2}).addTo(this._layers);}
    const key=JSON.stringify(data.zones);if(key!==this._fitKey){this._fitKey=key;if(bounds.isValid())this._map.fitBounds(bounds,{padding:[20,20],maxZoom:16,animate:false});}
    this._map.invalidateSize({pan:false});
  }
}
if(!customElements.get('isl-zone-map'))customElements.define('isl-zone-map',ShopZoneMap);
