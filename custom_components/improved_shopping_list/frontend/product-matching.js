/** Local name hints only; a candidate never authorises a code association. */
const normal = value => String(value ?? "").normalize("NFKD").replace(/\p{M}/gu, "").toLocaleLowerCase("es").replace(/[^\p{L}\p{N}]+/gu, " ").trim();
const ignored = new Set(["de", "del", "la", "el", "las", "los", "un", "una", "y", "con", "para", "en"]);
const tokens = value => new Set(normal(value).split(" ").filter(token => token.length > 1 && !ignored.has(token)));

export function matchCatalogProducts(hint, products) {
  if (hint?.status !== "found" || !hint.name) return [];
  const names = [hint.name, hint.product_name].filter(Boolean);
  return products.map(product => {
    const local = tokens(product.name);
    let score = 0;
    for (const name of names) {
      if (normal(product.name) === normal(name)) { score = 1; break; }
      const remote = tokens(name);
      const common = [...local].filter(token => remote.has(token)).length;
      if (common && local.size && remote.size) score = Math.max(score, .65 * common / local.size + .35 * common / remote.size);
    }
    return { product, score };
  }).filter(candidate => candidate.score >= .7)
    .sort((a, b) => b.score - a.score || a.product.name.localeCompare(b.product.name, "es"))
    .slice(0, 3).map(candidate => candidate.product);
}
