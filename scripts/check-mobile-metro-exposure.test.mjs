import test from 'node:test';
import assert from 'node:assert/strict';
import { enforceMetroExposureBaseline } from './check-mobile-metro-exposure.mjs';

function report() {
  return {
    evidence_scope: 'Exported Android Metro JavaScript source maps only',
    source_map_count: 1,
    module_source_count: 803,
    audited_packages: {
      zod: { source_occurrences: 0, observed_in_js_graph: false },
      deepmerge: { source_occurrences: 0, observed_in_js_graph: false },
      '@expo/cli': { source_occurrences: 1, observed_in_js_graph: true },
    },
  };
}

test('permits the observed baseline even when Expo CLI is listed', () => {
  assert.equal(enforceMetroExposureBaseline(report()), true);
});

test('fails on newly bundled zod or deepmerge code', () => {
  for (const name of ['zod', 'deepmerge']) {
    const changed = report();
    changed.audited_packages[name] = { source_occurrences: 1, observed_in_js_graph: true };
    assert.throws(() => enforceMetroExposureBaseline(changed), new RegExp(`${name} appeared`));
  }
});

test('rejects missing, stale or inconsistent evidence instead of declaring safety', () => {
  for (const mutate of [
    (r) => { r.evidence_scope = 'APK scan'; },
    (r) => { r.source_map_count = 0; },
    (r) => { r.module_source_count = 0; },
    (r) => { delete r.audited_packages.zod; },
    (r) => { r.audited_packages.deepmerge.observed_in_js_graph = true; },
    (r) => { r.audited_packages.zod.source_occurrences = -1; },
  ]) {
    const changed = report();
    mutate(changed);
    assert.throws(() => enforceMetroExposureBaseline(changed), /Invalid/);
  }
  assert.throws(() => enforceMetroExposureBaseline(null), /Invalid/);
});
