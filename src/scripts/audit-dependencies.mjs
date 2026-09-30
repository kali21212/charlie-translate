import { spawnSync } from "node:child_process";
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";

const { exceptions, reviewBy } = JSON.parse(
  readFileSync("docs/dependency-audit-exceptions.json", "utf8")
);
if (new Date().toISOString().slice(0, 10) > reviewBy) {
  throw new Error(`Dependency exceptions need review after ${reviewBy}`);
}
const allowed = new Map(exceptions.map((item) => [item.id, item]));
mkdirSync("tmp", { recursive: true });
for (const scope of ["all", "prod"]) {
  const result = spawnSync(
    process.platform === "win32" ? "corepack.cmd" : "corepack",
    [
      "pnpm@10.15.1",
      "audit",
      "--json",
      ...(scope === "prod" ? ["--prod"] : []),
    ],
    {
      encoding: "utf8",
      shell: process.platform === "win32",
      maxBuffer: 8 * 1024 * 1024,
    }
  );
  if (result.error || ![0, 1].includes(result.status)) {
    throw new Error(
      result.error?.message || result.stderr || "Audit invocation failed"
    );
  }
  const report = JSON.parse(result.stdout);
  if (report.error || !report.metadata?.vulnerabilities || !report.advisories) {
    throw new Error(
      "Invalid audit response; audit service errors cannot pass CI"
    );
  }
  writeFileSync(
    `tmp/dependency-audit-${scope}.json`,
    JSON.stringify(report, null, 2) + "\n"
  );
  if (
    scope === "prod" &&
    Object.values(report.metadata.vulnerabilities).some((count) => count > 0)
  ) {
    throw new Error(
      "Production dependency audit must have zero vulnerabilities"
    );
  }
  for (const advisory of Object.values(report.advisories)) {
    const exception = allowed.get(advisory.github_advisory_id);
    if (
      !exception ||
      exception.module !== advisory.module_name ||
      exception.severity !== advisory.severity ||
      (scope === "prod" && exception.scope !== "runtime") ||
      advisory.findings.some(
        (finding) =>
          !exception.versions.includes(finding.version) ||
          finding.paths.some((path) => !exception.paths.includes(path))
      )
    ) {
      throw new Error(
        `Unreviewed ${scope} vulnerability: ${advisory.github_advisory_id} (${advisory.module_name})`
      );
    }
  }
  console.log(
    `${scope}: ${JSON.stringify(report.metadata.vulnerabilities)}; remaining advisories match reviewed scope/version/path exceptions`
  );
}
