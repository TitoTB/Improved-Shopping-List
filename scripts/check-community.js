/** Validate reviewed repository files before they become downloadable suggestions. */
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { createHash } from "node:crypto";

const index = JSON.parse(await readFile("community/index.json", "utf8"));
assert.equal(index.schema_version, 1);
assert.ok(Array.isArray(index.icons) && index.icons.length <= 5000);
const ids = new Set();
for (const icon of index.icons) {
  assert.match(icon.id, /^[a-z0-9][a-z0-9-]{0,79}$/);
  assert.ok(!ids.has(icon.id)); ids.add(icon.id);
  for (const key of ["name_en", "author", "license"]) assert.ok(typeof icon[key] === "string" && icon[key].length > 0 && icon[key].length <= 300);
  assert.ok(Array.isArray(icon.terms) && icon.terms.length > 0 && icon.terms.length <= 30 && icon.terms.every(term => typeof term === "string" && term.length > 0 && term.length <= 100));
  const license = new URL(icon.license_url);
  assert.ok(license.protocol === "https:" && !license.username && !license.password && !license.search);
  assert.match(icon.file, /^images\/[a-f0-9]{64}\.(svg|png|jpg|webp)$/);
  assert.equal(icon.sha256, icon.file.split("/")[1].split(".")[0]);
  assert.ok(Number.isInteger(icon.contributions) && icon.contributions >= 0 && icon.contributions <= 1000000);
  const data = await readFile(`community/${icon.file}`);
  assert.ok(data.length > 0 && data.length <= 262144);
  assert.equal(createHash("sha256").update(data).digest("hex"), icon.sha256);
}
console.log(`Community dictionary OK (${index.icons.length} reviewed images).`);
