import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { serverConfigProblems } from "./config";

const GOOD = {
  SESSION_SECRET: "s".repeat(40),
  INTERNAL_API_URL: "http://backend:8000/api/v1",
  NEXT_PUBLIC_APP_URL: "https://sharonesl.com",
  TRUSTED_PROXY_COUNT: "1",
};

describe("serverConfigProblems", () => {
  it("accepts a complete production environment", () => {
    assert.deepEqual(serverConfigProblems(GOOD), []);
  });

  it("flags each missing or weak setting", () => {
    assert.match(serverConfigProblems({ ...GOOD, SESSION_SECRET: undefined }).join(), /SESSION_SECRET/);
    assert.match(serverConfigProblems({ ...GOOD, SESSION_SECRET: "short" }).join(), /SESSION_SECRET/);
    assert.match(serverConfigProblems({ ...GOOD, INTERNAL_API_URL: undefined }).join(), /INTERNAL_API_URL/);
    assert.match(serverConfigProblems({ ...GOOD, NEXT_PUBLIC_APP_URL: undefined }).join(), /NEXT_PUBLIC_APP_URL/);
  });

  it("falls back to NEXT_PUBLIC_API_URL for the upstream", () => {
    assert.deepEqual(serverConfigProblems({ ...GOOD, INTERNAL_API_URL: undefined, NEXT_PUBLIC_API_URL: "https://api.sharonesl.com/api/v1" }), []);
  });

  it("rejects malformed and non-http upstream URLs", () => {
    for (const bad of ["not a url", "ftp://backend/api", "javascript:alert(1)"]) {
      assert.match(serverConfigProblems({ ...GOOD, INTERNAL_API_URL: bad }).join(), /not a valid http/, bad);
    }
  });

  it("refuses a localhost upstream unless explicitly allowed", () => {
    const local = { ...GOOD, INTERNAL_API_URL: "http://localhost:8000/api/v1" };
    assert.match(serverConfigProblems(local).join(), /localhost/);
    assert.deepEqual(serverConfigProblems({ ...local, ALLOW_LOCAL_UPSTREAM: "1" }), []);
  });

  it("requires an https app URL unless plain-http staging is explicit", () => {
    const http = { ...GOOD, NEXT_PUBLIC_APP_URL: "http://staging.example.com" };
    assert.match(serverConfigProblems(http).join(), /https/);
    assert.deepEqual(serverConfigProblems({ ...http, SESSION_COOKIE_SECURE: "false" }), []);
  });

  it("validates TRUSTED_PROXY_COUNT and the mock flag", () => {
    for (const bad of ["abc", "-1", "1.5", "100"]) assert.match(serverConfigProblems({ ...GOOD, TRUSTED_PROXY_COUNT: bad }).join(), /TRUSTED_PROXY_COUNT/, bad);
    assert.deepEqual(serverConfigProblems({ ...GOOD, TRUSTED_PROXY_COUNT: "" }), []);
    assert.match(serverConfigProblems({ ...GOOD, NEXT_PUBLIC_USE_MOCKS: "true" }).join(), /MOCKS/);
  });

  it("reports every problem at once, not just the first", () => {
    const all = serverConfigProblems({}).join();
    assert.ok(/SESSION_SECRET/.test(all) && /INTERNAL_API_URL/.test(all) && /NEXT_PUBLIC_APP_URL/.test(all));
  });
});
