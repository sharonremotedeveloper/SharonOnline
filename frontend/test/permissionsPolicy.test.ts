import { test } from "node:test";
import assert from "node:assert/strict";
import path from "node:path";
import { pathToFileURL } from "node:url";

// The Daily classroom is a cross-origin iframe: the page's Permissions-Policy must delegate camera/mic to Daily,
// or the browser silently denies the devices and the join never completes (2026-10-16 production incident).
test("Permissions-Policy delegates camera and microphone to the Daily iframe origin", async () => {
  // The test build is CommonJS, which would turn import() into require(); keep a real ESM import for the .mjs config.
  const esmImport = new Function("u", "return import(u)") as (u: string) => Promise<{ default: { headers: () => Promise<unknown> } }>;
  const mod = await esmImport(pathToFileURL(path.join(process.cwd(), "next.config.mjs")).href);
  const rules = (await mod.default.headers()) as Array<{ source: string; headers: Array<{ key: string; value: string }> }>;
  const page = rules.find((r) => r.source === "/:path*");
  const policy = page?.headers.find((h) => h.key === "Permissions-Policy")?.value ?? "";
  for (const feature of ["camera", "microphone"]) {
    const entry = policy.split(",").map((s) => s.trim()).find((s) => s.startsWith(`${feature}=`)) ?? "";
    assert.match(entry, /\bself\b/, `${feature} must still allow our own origin`);
    assert.ok(entry.includes('"https://topscholaracademy.daily.co"'), `${feature} must allow the Daily domain: ${entry}`);
  }
  assert.match(policy, /geolocation=\(\)/);
});
