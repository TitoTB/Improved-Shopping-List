/** Comparison keys never replace the user's display spelling. */
export const productNameKey = value => String(value ?? "").normalize("NFKD")
  .replace(/\p{M}/gu, "").trim().replace(/\s+/g, " ").toLocaleLowerCase("es");
