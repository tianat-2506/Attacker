import { readdirSync, statSync } from "node:fs";
import { join } from "node:path";

const assetsDir = join(process.cwd(), "dist", "assets");
const jsAssets = readdirSync(assetsDir)
  .filter((fileName) => fileName.endsWith(".js"))
  .map((fileName) => {
    const path = join(assetsDir, fileName);
    return { fileName, bytes: statSync(path).size };
  })
  .sort((left, right) => right.bytes - left.bytes);

const maxBytes = 500_000;
const oversized = jsAssets.filter((asset) => asset.bytes > maxBytes);

if (jsAssets.length < 2) {
  throw new Error(`Expected at least 2 JavaScript chunks, found ${jsAssets.length}.`);
}

if (oversized.length) {
  const details = oversized.map((asset) => `${asset.fileName}=${asset.bytes}`).join(", ");
  throw new Error(`JavaScript chunk budget exceeded: ${details}`);
}

console.log(`Bundle budget OK: ${jsAssets.length} JS chunks, largest ${jsAssets[0].bytes} bytes.`);
