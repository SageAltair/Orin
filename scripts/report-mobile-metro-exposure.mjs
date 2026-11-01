/**
 * Evidence-only check for audited npm packages in the exported Android Metro JS graph.
 * This does NOT inspect native APK libraries or establish that a dependency is safe.
 */
import { readdir, readFile, writeFile } from "node:fs/promises";
import { resolve, join, extname } from "node:path";
import { fileURLToPath } from "node:url";

const watched = ["zod", "@expo/cli", "deepmerge", "glob", "minimatch"];
const watchedSource = /(?:^|\/)node_modules\/(@expo\/cli|zod|deepmerge|glob|minimatch)(?:\/|$)/g;

export function summarizeSourceMaps(maps) {
  const counts = Object.fromEntries(watched.map(name => [name, 0]));
  const samples = Object.fromEntries(watched.map(name => [name, []]));
  let sourceCount = 0;
  function visit(map) {
    if (!map || typeof map !== "object") throw new Error("Invalid Metro source map");
    if (Array.isArray(map.sections)) {
      for (const section of map.sections) visit(section?.map);
      return;
    }
    if (!Array.isArray(map.sources)) throw new Error("Metro source map has no sources");
    for (const source of map.sources) {
      if (typeof source !== "string") throw new Error("Invalid Metro source path");
      sourceCount++;
      const normalized = source.replaceAll("\\", "/");
      for (const match of normalized.matchAll(watchedSource)) {
        const name = match[1];
        counts[name]++;
        // Keep only package-relative paths, never CI runner or developer paths.
        const start = normalized.indexOf(`node_modules/${name}`, match.index);
        const relative = normalized.slice(start + "node_modules/".length);
        if (samples[name].length < 5 && !samples[name].includes(relative)) samples[name].push(relative);
      }
    }
  }
  for (const map of maps) visit(map);
  if (sourceCount === 0) throw new Error("No Metro JavaScript modules found in source maps");
  return {
    evidence_scope: "Exported Android Metro JavaScript source maps only",
    source_map_count: maps.length,
    module_source_count: sourceCount,
    audited_packages: Object.fromEntries(watched.map(name => [name, {
      source_occurrences: counts[name],
      observed_in_js_graph: counts[name] > 0,
      sample_package_paths: samples[name],
    }])),
    limitation: "Absence from these maps is not proof that a package or vulnerability is absent from an APK, native libraries, build tooling, or other execution paths.",
  };
}

async function findMaps(root) {
  const result = [];
  async function visit(dir) {
    for (const entry of await readdir(dir, { withFileTypes: true })) {
      const path = join(dir, entry.name);
      if (entry.isDirectory()) await visit(path);
      else if (entry.isFile() && extname(entry.name) === ".map") result.push(path);
    }
  }
  await visit(root);
  return result.sort();
}

export async function scanMetroExport(root) {
  const paths = await findMaps(root);
  if (paths.length === 0) throw new Error("No Android Metro source maps found; export with --source-maps");
  const maps = [];
  for (const path of paths) {
    let map;
    try { map = JSON.parse(await readFile(path, "utf8")); }
    catch (error) { throw new Error("Could not parse Android Metro source map", { cause: error }); }
    maps.push(map);
  }
  return summarizeSourceMaps(maps);
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const root = resolve(process.argv[2] ?? "apps/mobile/dist");
  const output = resolve(process.argv[3] ?? "apps/mobile/mobile-runtime-js-exposure.json");
  try {
    const report = await scanMetroExport(root);
    await writeFile(output, JSON.stringify(report, null, 2) + "\n", "utf8");
    console.log(JSON.stringify(report, null, 2));
  } catch (error) {
    console.error(error instanceof Error ? error.message : String(error));
    process.exitCode = 1;
  }
}
