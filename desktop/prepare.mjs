// Build-time downloads only. Every executable/model is pinned and checksum-verified.
import { readFile, writeFile, mkdir, copyFile } from "node:fs/promises";
import { createHash } from "node:crypto";
import { dirname, join } from "node:path";
import { createRequire } from "node:module";
import { spawnSync } from "node:child_process";
import "../src/scripts/prepare-desktop-models.mjs";
const hash = (bytes) => createHash("sha256").update(bytes).digest("hex");
async function verified(url, file, expected) {
  let bytes;
  try {
    bytes = await readFile(file);
  } catch (_) {
    /* prepare below */
  }
  if (!bytes || hash(bytes) !== expected) {
    const response = await fetch(url, { signal: AbortSignal.timeout(120000) });
    if (!response.ok) throw new Error("Resource download failed: " + url);
    bytes = Buffer.from(await response.arrayBuffer());
    if (hash(bytes) !== expected) throw new Error("Checksum mismatch: " + file);
    await mkdir(dirname(file), { recursive: true });
    await writeFile(file, bytes);
  }
  return bytes;
}
const runtime = JSON.parse(await readFile("desktop/node-runtime.json", "utf8"));
await verified(runtime.url, "tmp/desktop-node.exe", runtime.sha256);
const license = await fetch(runtime.license);
if (!license.ok) throw new Error("Node license download failed");
await writeFile("tmp/NODE-LICENSE.txt", await license.text());
await mkdir("tmp/desktop-translation", { recursive: true });
await copyFile(
  "desktop/mtran-package.json",
  "tmp/desktop-translation/package.json"
);
await copyFile(
  "desktop/mtran-lock.json",
  "tmp/desktop-translation/package-lock.json"
);
const npmCli = join(
  dirname(process.execPath),
  "node_modules/npm/bin/npm-cli.js"
);
const install = spawnSync(
  process.execPath,
  [
    npmCli,
    "ci",
    "--prefix",
    "tmp/desktop-translation",
    "--ignore-scripts",
    "--omit=dev",
    "--no-fund",
    "--no-audit",
  ],
  { stdio: "inherit" }
);
if (install.status !== 0)
  throw new Error("Pinned MTran dependency installation failed");
const require = createRequire(
  join(
    process.cwd(),
    "tmp/desktop-translation/node_modules/mtranserver/package.json"
  )
);
const { decompress } = require("fzstd");
const records = JSON.parse(
  await readFile("desktop/translation-records.json", "utf8")
);
for (const record of records.data) {
  const output = "tmp/mtran-models/en_zh-Hans/" + record.name;
  try {
    if (hash(await readFile(output)) === record.decompressedHash) continue;
  } catch (_) {
    /* download below */
  }
  const url =
    "https://firefox-settings-attachments.cdn.mozilla.net/" +
    record.attachment.location;
  const compressed = await verified(
    url,
    "tmp/translation-model-downloads/" + record.attachment.filename,
    record.attachment.hash
  );
  const bytes = decompress(compressed);
  if (hash(bytes) !== record.decompressedHash)
    throw new Error("Translation model checksum mismatch");
  await mkdir(dirname(output), { recursive: true });
  await writeFile(output, bytes);
}
console.log(
  "Pinned desktop resources prepared. Runtime performs no downloads."
);
