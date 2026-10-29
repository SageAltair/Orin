import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

export const HIGH_BASELINE_CEILING = 3;

export function evaluateMobileAudit(report) {
  if (!report || typeof report !== "object" || report.error) {
    throw new Error("npm audit failed or returned an error; review the audit artifact");
  }
  const counts = report.metadata?.vulnerabilities;
  if (!counts || !Number.isInteger(counts.high) || !Number.isInteger(counts.critical)) {
    throw new Error("npm audit returned no valid severity counts");
  }
  const highPackages = Object.entries(report.vulnerabilities ?? {})
    .filter(([, entry]) => entry?.severity === "high" || entry?.severity === "critical")
    .map(([name, entry]) => `${name} (${entry.severity})`)
    .sort();
  return {
    counts,
    highPackages,
    passed: counts.critical === 0 && counts.high <= HIGH_BASELINE_CEILING,
  };
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    const report = JSON.parse(readFileSync(process.argv[2], "utf8"));
    const result = evaluateMobileAudit(report);
    console.log("Mobile npm audit:", JSON.stringify(result.counts));
    console.log("High/critical packages:", result.highPackages.join(", ") || "none");
    if (result.counts.high > 0) {
      console.warn(
        `Unresolved mobile high findings: ${result.counts.high}; ceiling ${HIGH_BASELINE_CEILING}. This is NOT a security clearance.`,
      );
    }
    if (!result.passed) {
      console.error("Mobile dependency audit exceeded the recorded high baseline or found a critical vulnerability.");
      process.exitCode = 1;
    }
  } catch (error) {
    console.error("Mobile dependency audit could not be verified:", error.message);
    process.exitCode = 1;
  }
}
