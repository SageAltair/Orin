import assert from "node:assert/strict";
import test from "node:test";
import { evaluateMobileAudit, HIGH_BASELINE_CEILING, KNOWN_HIGH_PACKAGES } from "./check-mobile-audit.mjs";

const report = (highNames = KNOWN_HIGH_PACKAGES, criticalNames = []) => {
  const vulnerabilities = Object.fromEntries([
    ...highNames.map((name) => [name, { severity: "high" }]),
    ...criticalNames.map((name) => [name, { severity: "critical" }]),
    ["deepmerge", { severity: "low" }],
  ]);
  return {
    metadata: {
      vulnerabilities: {
        low: 1, moderate: 0, high: highNames.length, critical: criticalNames.length,
      },
    },
    vulnerabilities,
  };
};

test("accepts only the recorded high package names and reports them", () => {
  const result = evaluateMobileAudit(report());
  assert.equal(result.passed, true);
  assert.equal(result.counts.high, HIGH_BASELINE_CEILING);
  assert.deepEqual(result.unexpected, []);
});

test("rejects a replacement high finding even when the count stays at baseline", () => {
  const replacement = report(["@expo/cli", "expo", "unreviewed-package"]);
  const result = evaluateMobileAudit(replacement);
  assert.equal(result.counts.high, HIGH_BASELINE_CEILING);
  assert.deepEqual(result.unexpected, ["unreviewed-package"]);
  assert.equal(result.passed, false);
});

test("rejects any critical finding or a high count increase", () => {
  assert.equal(evaluateMobileAudit(report(KNOWN_HIGH_PACKAGES, ["critical-package"])).passed, false);
  assert.equal(evaluateMobileAudit(report([...KNOWN_HIGH_PACKAGES, "new-package"])).passed, false);
});

test("rejects malformed, failed, or inconsistent audits", () => {
  assert.throws(() => evaluateMobileAudit({ error: { code: "ENOAUDIT" } }));
  assert.throws(() => evaluateMobileAudit({}));
  assert.throws(() => evaluateMobileAudit(null));
  const inconsistent = report();
  inconsistent.metadata.vulnerabilities.high = 1;
  assert.throws(() => evaluateMobileAudit(inconsistent));
});
