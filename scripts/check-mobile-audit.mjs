import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

export const KNOWN_HIGH_PACKAGES = ["@expo/cli", "expo", "zod"];
// Expo 58.0.22 removes the high-severity Zod chain. Do not permit it to return.
export const HIGH_BASELINE_CEILING = 0;
export const KNOWN_HIGH_ADVISORIES = ["ghsa-mrhx-c7xc-m3w5"];

// An unchanged vulnerable package name is not an unchanged vulnerability.
// Trace npm audit's transitive "via" edges to the actual GHSA advisories.
// Fail closed if npm changes the report shape or the chain cannot be resolved.
function advisoryIdsForPackage(name, vulnerabilities, trail = new Set()) {
  if (trail.has(name)) throw new Error(`Circular mobile audit advisory chain: ${name}`);
  const entry = vulnerabilities[name];
  if (!entry || !Array.isArray(entry.via) || entry.via.length === 0) {
    throw new Error(`Missing mobile audit advisory details for ${name}`);
  }
  const nextTrail = new Set([...trail, name]);
  const ids = new Set();
  for (const via of entry.via) {
    if (typeof via === "string") {
      const dependency = vulnerabilities[via];
      if (!dependency) throw new Error(`Missing mobile audit advisory details for ${via}`);
      if (dependency.severity !== "high" && dependency.severity !== "critical") continue;
      for (const id of advisoryIdsForPackage(via, vulnerabilities, nextTrail)) ids.add(id);
    } else if (via && typeof via === "object" && typeof via.url === "string") {
      if (typeof via.severity !== "string") {
        throw new Error(`Missing mobile audit advisory severity for ${name}`);
      }
      if (via.severity !== "high" && via.severity !== "critical") continue;
      const match = via.url.match(/(?:^|\/)(GHSA-[a-z0-9-]+)(?:[/?#]|$)/i);
      if (!match) throw new Error(`Unrecognized mobile audit advisory URL for ${name}`);
      ids.add(match[1].toLowerCase());
    } else {
      throw new Error(`Unrecognized mobile audit advisory for ${name}`);
    }
  }
  if (ids.size === 0) throw new Error(`No high/critical advisory resolved for ${name}`);
  return ids;
}

export function evaluateMobileAudit(report) {
  if (!report || typeof report !== "object" || report.error) {
    throw new Error("npm audit failed or returned an error; review the audit artifact");
  }
  const counts = report.metadata?.vulnerabilities;
  if (!counts || !Number.isInteger(counts.high) || !Number.isInteger(counts.critical)) {
    throw new Error("npm audit returned no valid severity counts");
  }
  if (!report.vulnerabilities || typeof report.vulnerabilities !== "object") {
    throw new Error("npm audit returned no package-level vulnerability details");
  }
  const severe = Object.entries(report.vulnerabilities)
    .filter(([, entry]) => entry?.severity === "high" || entry?.severity === "critical");
  const highPackages = severe.map(([name, entry]) => `${name} (${entry.severity})`).sort();
  const unexpected = severe
    .filter(([name, entry]) => entry.severity === "high" && !KNOWN_HIGH_PACKAGES.includes(name))
    .map(([name]) => name);
  const highCount = severe.filter(([, entry]) => entry.severity === "high").length;
  const criticalCount = severe.filter(([, entry]) => entry.severity === "critical").length;
  const advisoryIds = new Set();
  for (const [name] of severe) {
    for (const id of advisoryIdsForPackage(name, report.vulnerabilities)) advisoryIds.add(id);
  }
  const unexpectedAdvisories = [...advisoryIds]
    .filter((id) => !KNOWN_HIGH_ADVISORIES.includes(id))
    .sort();
  if (highCount !== counts.high || criticalCount !== counts.critical) {
    throw new Error("npm audit severity counts disagree with package-level findings");
  }
  return {
    counts,
    highPackages,
    unexpected,
    advisories: [...advisoryIds].sort(),
    unexpectedAdvisories,
    passed: counts.critical === 0 && counts.high <= HIGH_BASELINE_CEILING && unexpected.length === 0 && unexpectedAdvisories.length === 0,
  };
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    const report = JSON.parse(readFileSync(process.argv[2], "utf8"));
    const result = evaluateMobileAudit(report);
    console.log("Mobile npm audit:", JSON.stringify(result.counts));
    console.log("High/critical packages:", result.highPackages.join(", ") || "none");
    console.log("Resolved high/critical advisories:", result.advisories.join(", ") || "none");
    if (result.counts.high > 0) {
      console.warn(
        `Unresolved mobile high findings: ${result.counts.high}; ceiling ${HIGH_BASELINE_CEILING}. This is NOT a security clearance.`,
      );
    }
    if (!result.passed) {
      console.error("Mobile audit found a new high-severity package/advisory, exceeded baseline, or found a critical vulnerability:", { packages: result.unexpected, advisories: result.unexpectedAdvisories });
      process.exitCode = 1;
    }
  } catch (error) {
    console.error("Mobile dependency audit could not be verified:", error.message);
    process.exitCode = 1;
  }
}
