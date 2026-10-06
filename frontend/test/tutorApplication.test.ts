import assert from "node:assert/strict";
import test from "node:test";
import { buildApplicationPayload, isSpeedTestPassing, validateApplicationStep } from "../src/lib/tutorApplication";

test("T5b speed threshold requires 10/5 Mbps", () => {
  assert.equal(isSpeedTestPassing(10, 5), true);
  assert.equal(isSpeedTestPassing(9.99, 20), false);
  assert.equal(isSpeedTestPassing(20, 4.99), false);
});

test("T5b validates required uploads and declarations", () => {
  assert.deepEqual(validateApplicationStep(2, { requiredKinds: ["avatar", "intro_video"], committedKinds: ["avatar"] }), ["Upload your intro video."]);
  assert.deepEqual(validateApplicationStep(5, { accepted: false }), ["Accept the legal declarations to submit your application."]);
});

test("T5b emits only the typed application PATCH fields", () => {
  assert.deepEqual(buildApplicationPayload({ download: 12.5, upload: 6, powerConfirmed: true, accepted: true }), {
    speed_test: { download_mbps: "12.50", upload_mbps: "6.00" }, confirm_power_backup: true, accept_declaration: true,
  });
});
