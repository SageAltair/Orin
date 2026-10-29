import assert from "node:assert/strict";
import test from "node:test";
import {
  evaluateMobileAudit,
  HIGH_BASELINE_CEILING,
  KNOWN_HIGH_ADVISORIES,
  KNOWN_HIGH_PACKAGES,
} from "./check-mobile-audit.mjs";

const knownAdvisory = { url: "https://github.com/advisories/GHSA-mrhx-c7xc-m3w5", severity: "high" };
const newAdvisory = { url: "https://github.com/advisories/GHSA-new-advisory-0000", severity: "high" };

function report(highNames = KNOWN_HIGH_PACKAGES, criticalNames = []) {
  const viaFor = (name) => {
    if (name === "expo") return ["@expo/cli", "@expo/config", "@expo/local-build-cache-provider", "@expo/metro-config"];
    if (name === "@expo/cli") return ["@expo/config", "@expo/metro-config", "@expo/prebuild-config", "zod"];
    if (name === "zod") return [knownAdvisory];
    return [newAdvisory];
  };
  const vulnerabilities = Object.fromEntries([
    ...highNames.map((name) => [name, { severity: "high", via: viaFor(name) }]),
    ...criticalNames.map((name) => [name, { severity: "critical", via: viaFor(name) }]),
    ["@expo/config", { severity: "low", via: ["deepmerge"] }],
    ["@expo/metro-config", { severity: "low", via: ["@expo/config"] }],
    ["@expo/prebuild-config", { severity: "low", via: ["@expo/config"] }],
    ["@expo/local-build-cache-provider", { severity: "low", via: ["@expo/config"] }],
    ["deepmerge", { severity: "low", via: [{ url: "https://github.com/advisories/GHSA-gcqx-w48m-w2h4", severity: "low" }] }],
  ]);
  return {
    metadata: {
      vulnerabilities: {
        low: 5, moderate: 0, high: highNames.length, critical: criticalNames.length,
      },
    },
    vulnerabilities,
  };
}

test("accepts only the reviewed high packages and their exact transitive advisory", () => {
  const result = evaluateMobileAudit(report());
  assert.equal(result.passed, true);
  assert.equal(result.counts.high, HIGH_BASELINE_CEILING);
  assert.deepEqual(result.unexpected, []);
  assert.deepEqual(result.advisories, KNOWN_HIGH_ADVISORIES.map((id) => id.toLowerCase()));
  assert.deepEqual(result.unexpectedAdvisories, []);
});

test("rejects a replacement high package even if the count stays unchanged", () => {
  const replacement = report(["@expo/cli", "expo", "unreviewed-package"]);
  // The old root dependency is replaced by another high-severity dependency.
  replacement.vulnerabilities["@expo/cli"].via = ["@expo/config", "unreviewed-package"];
  const result = evaluateMobileAudit(replacement);
  assert.equal(result.counts.high, HIGH_BASELINE_CEILING);
  assert.deepEqual(result.unexpected, ["unreviewed-package"]);
  assert.equal(result.passed, false);
});

test("ignores low-severity advisories reachable through a high package", () => {
  const mixed = report();
  mixed.vulnerabilities.expo.via.push("deepmerge");
  mixed.vulnerabilities.zod.via.push({
    url: "https://github.com/advisories/GHSA-gcqx-w48m-w2h4",
    severity: "low",
  });
  const result = evaluateMobileAudit(mixed);
  assert.equal(result.passed, true);
  assert.deepEqual(result.unexpectedAdvisories, []);
});

test("rejects a new high advisory in an existing known package", () => {
  const changed = report();
  changed.vulnerabilities.zod.via.push(newAdvisory);
  const result = evaluateMobileAudit(changed);
  assert.equal(result.counts.high, HIGH_BASELINE_CEILING);
  assert.deepEqual(result.unexpected, []);
  assert.deepEqual(result.unexpectedAdvisories, ["ghsa-new-advisory-0000"]);
  assert.equal(result.passed, false);
});

test("rejects critical findings and new high counts", () => {
  assert.equal(evaluateMobileAudit(report(KNOWN_HIGH_PACKAGES, ["critical-package"])).passed, false);
  assert.equal(evaluateMobileAudit(report([...KNOWN_HIGH_PACKAGES, "new-package"])).passed, false);
});

test("fails closed for missing, circular or unknown advisory chains", () => {
  const missing = report();
  delete missing.vulnerabilities.zod.via;
  assert.throws(() => evaluateMobileAudit(missing), /Missing mobile audit advisory/);

  const circular = report();
  circular.vulnerabilities.zod.via = ["expo"];
  assert.throws(() => evaluateMobileAudit(circular), /Circular mobile audit advisory chain/);

  const unresolvable = report();
  unresolvable.vulnerabilities.zod.via = ["not-in-report"];
  assert.throws(() => evaluateMobileAudit(unresolvable), /Missing mobile audit advisory/);

  const unknownUrl = report();
  unknownUrl.vulnerabilities.zod.via = [{ url: "https://example.invalid/unknown", severity: "high" }];
  assert.throws(() => evaluateMobileAudit(unknownUrl), /Unrecognized mobile audit advisory URL/);
});

test("rejects malformed, failed or inconsistent audit reports", () => {
  assert.throws(() => evaluateMobileAudit({ error: { code: "ENOAUDIT" } }));
  assert.throws(() => evaluateMobileAudit({}));
  assert.throws(() => evaluateMobileAudit(null));
  const inconsistent = report();
  inconsistent.metadata.vulnerabilities.high = 1;
  assert.throws(() => evaluateMobileAudit(inconsistent));
});
