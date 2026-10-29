/** Lightweight product display helpers shared without importing any view. */
import { productNameKey } from "./product-names.js?v=0.50.0";
import { packageCost } from "./reference-formats.js?v=0.50.0";
export { productNameKey };
export const normalizedName = value => String(value ?? "").normalize("NFKC").trim().replace(/\s+/g, " ").toLocaleLowerCase("es");

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

