import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, mkdir, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { scanMetroExport, summarizeSourceMaps } from "./report-mobile-metro-exposure.mjs";

test("reports watched packages without claiming a clean runtime", () => {
  const report = summarizeSourceMaps([{ sources: [
    "../../node_modules/zod/v3/index.js",
    "node_modules/@expo/cli/build/index.js",
    "node_modules/.pnpm/deepmerge@4.3.1/node_modules/deepmerge/index.js",
    "node_modules/glob/dist/commonjs/index.js",
    "node_modules/.pnpm/minimatch@10.2.6/node_modules/minimatch/dist/commonjs/index.js",
    "src/App.tsx",
  ] }]);
  assert.equal(report.source_map_count, 1);
  assert.equal(report.module_source_count, 6);
  for (const name of ["zod", "@expo/cli", "deepmerge", "glob", "minimatch"]) {
    assert.equal(report.audited_packages[name].observed_in_js_graph, true);
    assert.equal(report.audited_packages[name].source_occurrences, 1);
  }
  assert.deepEqual(report.audited_packages["@expo/cli"].sample_package_paths, ["@expo/cli/build/index.js"]);
  assert.deepEqual(report.audited_packages.deepmerge.sample_package_paths, ["deepmerge/index.js"]);
  assert.deepEqual(report.audited_packages.glob.sample_package_paths, ["glob/dist/commonjs/index.js"]);
  assert.deepEqual(report.audited_packages.minimatch.sample_package_paths, ["minimatch/dist/commonjs/index.js"]);
  assert.match(report.limitation, /not proof/);
});

test("handles indexed maps and Windows-style paths", () => {
  const report = summarizeSourceMaps([{ sections: [
    { map: { sources: ["C:\\repo\\node_modules\\zod\\v4\\index.ts"] } },
    { map: { sources: ["src/App.tsx"] } },
  ] }]);
  assert.equal(report.audited_packages.zod.source_occurrences, 1);
  assert.deepEqual(report.audited_packages.zod.sample_package_paths, ["zod/v4/index.ts"]);
  assert.equal(report.audited_packages.deepmerge.observed_in_js_graph, false);
  assert.equal(report.audited_packages.glob.observed_in_js_graph, false);
  assert.equal(report.audited_packages.minimatch.observed_in_js_graph, false);
});

test("rejects malformed or empty source maps instead of reporting false absence", () => {
  assert.throws(() => summarizeSourceMaps([{ sources: [] }]), /No Metro JavaScript modules/);
  assert.throws(() => summarizeSourceMaps([{ names: [] }]), /no sources/);
  assert.throws(() => summarizeSourceMaps([{ sources: [null] }]), /Invalid Metro source path/);
});

test("scans nested exported map files and fails when maps are missing", async () => {
  const dir = await mkdtemp(join(tmpdir(), "orin-metro-exposure-"));
  try {
    await assert.rejects(scanMetroExport(dir), /No Android Metro source maps/);
    const nested = join(dir, "_expo", "static", "js", "android");
    await mkdir(nested, { recursive: true });
    await writeFile(join(nested, "index.hbc.map"), JSON.stringify({
      sources: ["node_modules/react/index.js", "src/index.ts"],
    }));
    const report = await scanMetroExport(dir);
    assert.equal(report.module_source_count, 2);
    assert.equal(report.audited_packages.zod.observed_in_js_graph, false);
    await writeFile(join(nested, "bad.map"), "{");
    await assert.rejects(scanMetroExport(dir), /Could not parse Android Metro source map/);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});
