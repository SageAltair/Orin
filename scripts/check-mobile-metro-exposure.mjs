/**
 * Fail on expansion of audited packages into the exported Android Metro JS graph.
 * This is a conservative source-map regression gate, NOT an APK security scan.
 * @see report-mobile-metro-exposure.mjs
 */
import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

// These audited roots must remain absent from the exported Android JS graph.
// @expo/cli is reported for evidence but intentionally not blocked by this gate.
const SCOPED_PACKAGES = ['zod', 'deepmerge', 'glob', 'minimatch'];
const EXPECTED_SCOPE = 'Exported Android Metro JavaScript source maps only';

export function enforceMetroExposureBaseline(report) {
  if (!report || typeof report !== 'object' || report.evidence_scope !== EXPECTED_SCOPE ||
      !Number.isInteger(report.source_map_count) || report.source_map_count < 1 ||
      !Number.isInteger(report.module_source_count) || report.module_source_count < 1 ||
      !report.audited_packages || typeof report.audited_packages !== 'object') {
    throw new Error('Invalid or incomplete Android Metro exposure report; cannot verify baseline');
  }
  for (const name of SCOPED_PACKAGES) {
    const entry = report.audited_packages[name];
    if (!entry || !Number.isInteger(entry.source_occurrences) || entry.source_occurrences < 0 ||
        typeof entry.observed_in_js_graph !== 'boolean' ||
        entry.observed_in_js_graph !== (entry.source_occurrences > 0)) {
      throw new Error(`Invalid Android Metro exposure evidence for ${name}`);
    }
    if (entry.source_occurrences > 0) {
      throw new Error(`${name} appeared in the Android Metro JS graph (${entry.source_occurrences} source entries); review before release`);
    }
  }
  return true;
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const path = resolve(process.argv[2] ?? 'apps/mobile/mobile-runtime-js-exposure.json');
  try {
    enforceMetroExposureBaseline(JSON.parse(await readFile(path, 'utf8')));
    console.log('Android Metro JS exposure baseline verified (zod, deepmerge, glob and minimatch absent from exported source maps only).');
  } catch (error) {
    console.error(error instanceof Error ? error.message : String(error));
    process.exitCode = 1;
  }
}
