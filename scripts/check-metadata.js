import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const base = "custom_components/improved_shopping_list/";
const read = async (path) => JSON.parse(await readFile(path, "utf8"));
const manifest = await read(`${base}manifest.json`);
const pkg = await read("package.json");
const strings = await read(`${base}strings.json`);
const spanish = await read(`${base}translations/es.json`);
const english = await read(`${base}translations/en.json`);
const hacs = await read("hacs.json");
assert.equal(manifest.domain, "improved_shopping_list");
assert.equal(manifest.version, pkg.version);
assert.match(await readFile(`${base}const.py`, "utf8"), new RegExp(`VERSION = "${pkg.version.replaceAll(".", "\\.")}"`));
assert.match(await readFile(`${base}frontend/panel.js`, "utf8"), new RegExp(`todo-client.js\\?v=${pkg.version.replaceAll(".", "\\.")}`));
assert.equal(hacs.homeassistant, "2026.10.0");
const keys = (value, prefix = "") => Object.entries(value).flatMap(([key, entry]) =>
  typeof entry === "object" ? keys(entry, `${prefix}${key}.`) : [`${prefix}${key}`]).sort();
assert.deepEqual(keys(strings), keys(spanish));
assert.deepEqual(english, strings);
if (process.env.GITHUB_REF_TYPE === "tag") assert.equal(process.env.GITHUB_REF_NAME, `v${manifest.version}`);
console.log(`Metadata and translations OK (${manifest.version}).`);
