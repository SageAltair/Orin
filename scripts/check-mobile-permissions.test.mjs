import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const config = JSON.parse(readFileSync(new URL("../apps/mobile/app.json", import.meta.url), "utf8"));

test("Android prebuild explicitly blocks unused overlay permission", () => {
  const blocked = config.expo?.android?.blockedPermissions;
  assert.ok(Array.isArray(blocked), "android.blockedPermissions must be configured");
  assert.equal(
    blocked.filter((permission) => permission === "android.permission.SYSTEM_ALERT_WINDOW").length,
    1,
    "overlay permission must be blocked exactly once",
  );
});
