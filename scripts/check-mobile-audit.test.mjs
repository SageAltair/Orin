import assert from "node:assert/strict";
import test from "node:test";
import { evaluateMobileAudit, HIGH_BASELINE_CEILING } from "./check-mobile-audit.mjs";

const report = (high, critical = 0) => ({
  metadata: { vulnerabilities: { low: 5, moderate: 0, high, critical } },
  vulnerabilities: { deepmerge: { severity: high ? "high" : "low" } },
});

test("accepts but reports the unresolved high baseline", () => {
  const result = evaluateMobileAudit(report(HIGH_BASELINE_CEILING));
  assert.equal(result.passed, true);
  assert.deepEqual(result.highPackages, ["deepmerge (high)"]);
});

test("rejects any new high or critical vulnerability", () => {
  assert.equal(evaluateMobileAudit(report(HIGH_BASELINE_CEILING + 1)).passed, false);
  assert.equal(evaluateMobileAudit(report(0, 1)).passed, false);
});

test("rejects missing, malformed or failed audits", () => {
  assert.throws(() => evaluateMobileAudit({ error: { code: "ENOAUDIT" } }));
  assert.throws(() => evaluateMobileAudit({}));
  assert.throws(() => evaluateMobileAudit(null));
});
