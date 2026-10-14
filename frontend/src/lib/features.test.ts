import test from "node:test";
import assert from "node:assert/strict";
import { POWER_GUARD_UI_ENABLED } from "./features";

test("Power Guard UI is disabled during the temporary Eskom shutdown", () => {
  assert.equal(POWER_GUARD_UI_ENABLED, false);
});
