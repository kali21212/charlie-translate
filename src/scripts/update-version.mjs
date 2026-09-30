import { argv } from "zx";

/**
 * Cross-platform version updater.
 *
 * Usage:
 *   pnpm version:patch
 *   pnpm version:minor
 *   pnpm version:major
 *   pnpm version:set -- 2.3.0
 *
 * We intentionally avoid spawning `npm version` here. The previous zx shell
 * path could fail on Windows before selecting a quote function.
 */

const rootDir = path.resolve(__dirname, "../..");
const pkgPath = path.join(rootDir, "package.json");
const versionType = argv._[0] || argv.type || "patch";
const pkg = await fs.readJSON(pkgPath);
const oldVersion = String(pkg.version || "");
const match = oldVersion.match(/^(\d+)\.(\d+)\.(\d+)$/);

if (!match) {
  throw new Error(`Unsupported current version: ${oldVersion}`);
}

const current = match.slice(1).map(Number);
let newVersion;

if (versionType === "set") {
  newVersion = argv._.find(
    (value, index) => index > 0 && /^\d+\.\d+\.\d+$/.test(String(value))
  );
  if (!newVersion) {
    throw new Error(
      "Please provide a semantic version, e.g. pnpm version:set -- 2.3.0"
    );
  }
} else {
  const [major, minor, patch] = current;
  if (versionType === "major") newVersion = `${major + 1}.0.0`;
  else if (versionType === "minor") newVersion = `${major}.${minor + 1}.0`;
  else if (versionType === "patch")
    newVersion = `${major}.${minor}.${patch + 1}`;
  else throw new Error(`Unsupported version operation: ${versionType}`);
}

console.log(chalk.blue(`\n🚀 更新版本号 ${oldVersion} -> ${newVersion}\n`));

if (newVersion !== oldVersion) {
  await fs.writeJSON(pkgPath, { ...pkg, version: newVersion }, { spaces: 2 });
}

await import("./sync-version.mjs");

console.log(chalk.green.bold(`\n✨ 版本更新完成：${newVersion}\n`));
