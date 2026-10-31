/** Lightweight product display helpers shared without importing any view. */
import { productNameKey } from "./product-names.js?v=0.73.1";
import { packageCost } from "./reference-formats.js?v=0.73.1";
export { productNameKey };
export const normalizedName = value => String(value ?? "").normalize("NFKC").trim().replace(/\s+/g, " ").toLocaleLowerCase("es");

export function storeFromProductUrl(value) {
  try {
    const url=new URL(value);
    if(url.protocol!=="https:"||url.username||url.password||url.port&&url.port!=="443")return "";
    return ({"www.elcorteingles.es":"elcorteingles","www.carrefour.es":"carrefour","carrefour.es":"carrefour","www.compraonline.alcampo.es":"alcampo","compraonline.alcampo.es":"alcampo",
      "tienda.masymas.com":"masymas","www.online.bmsupermercados.es":"bm","tienda.mercadona.es":"mercadona","tienda.consum.es":"consum","www.lasirena.es":"lasirena","supermercado.eroski.es":"eroski",
      "www.dia.es":"dia","dia.es":"dia","www.lidl.es":"lidl"})[url.hostname]??"";
  } catch { return ""; }
}

export function storeProductLink(store, value) {
  const program = {
    carrefour: {merchant:"25399",hosts:["www.carrefour.es","carrefour.es"],path:/^\/supermercado\/[^/]+\/R-[A-Za-z0-9-]+\/p\/?$/},
    elcorteingles: {merchant:"13075",hosts:["www.elcorteingles.es"],path:/^\/supermercado\/B[0-9]{1,20}-[^/]+\/?$/}
  }[store];
  if (!program) return value;
  try {
    const url = new URL(value);
    if (url.protocol !== "https:" || !program.hosts.includes(url.hostname) || url.username || url.password || url.port&&url.port!=="443" || !program.path.test(url.pathname)) return value;
    return `https://www.awin1.com/cread.php?awinmid=${program.merchant}&awinaffid=1535625&ued=${encodeURIComponent(value)}`;
  } catch { return value; }
}

export function cachedProductPrice(product, prices = [], favorite = "", desired = null) {
  if (!product) return null;
  const valid = offer => offer.price != null && offer.price !== "" && Number.isFinite(Number(offer.price)) &&
    Number(offer.price) >= 0 && /^[A-Z]{3}$/.test(offer.currency ?? "");
  const offers = prices.filter(offer => offer.catalog_product_id === product.id && valid(offer));
  const quantity=desired?.quantity??product.unit_quantity??1,unit=desired?.unit??product.purchase_unit??'uds';
  const cost=offer=>packageCost(offer,quantity,unit)?.price??Infinity;
  offers.sort((a,b) => Number(b.store === favorite) - Number(a.store === favorite) || cost(a)-cost(b) || (b.checked_at ?? 0) - (a.checked_at ?? 0));
  return offers[0] ?? (valid(product) ? {price:product.price,currency:product.currency} : null);
}

export function imageSource(value) {
  if (!value) return "";
  try {
    const url = new URL(value, location.origin);
    return ["http:", "https:"].includes(url.protocol) ? url.href : "";
  } catch { return ""; }
}

