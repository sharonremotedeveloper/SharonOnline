import { afterEach, describe, it } from "node:test";
import assert from "node:assert/strict";
import { upstreamBase } from "./upstream";

const original = {
  INTERNAL_API_URL: process.env.INTERNAL_API_URL,
  NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL,
  NODE_ENV: process.env.NODE_ENV,
};

const testEnv = process.env as Record<string, string | undefined>;

afterEach(() => {
  for (const [key, value] of Object.entries(original)) {
    if (value === undefined) delete process.env[key];
    else process.env[key] = value;
  }
});

describe("upstreamBase", () => {
  it("uses only INTERNAL_API_URL when configured", () => {
    testEnv.NODE_ENV = "production";
    process.env.INTERNAL_API_URL = "https://api.dev.topteacheracademy.com/api/v1/";
    process.env.NEXT_PUBLIC_API_URL = "https://browser-visible.example/api/v1";
    assert.equal(upstreamBase(), "https://api.dev.topteacheracademy.com/api/v1");
  });

  it("refuses browser-visible and localhost fallbacks in production", () => {
    testEnv.NODE_ENV = "production";
    delete process.env.INTERNAL_API_URL;
    process.env.NEXT_PUBLIC_API_URL = "https://browser-visible.example/api/v1";
    assert.throws(() => upstreamBase(), /INTERNAL_API_URL.*NEXT_PUBLIC_API_URL/);

    process.env.INTERNAL_API_URL = "http://localhost:8000/api/v1";
    assert.throws(() => upstreamBase(), /must not point at localhost/);
  });

  it("rejects malformed and non-http configured upstream URLs", () => {
    testEnv.NODE_ENV = "production";
    for (const value of ["not a url", "ftp://backend/api/v1", "javascript:alert(1)"]) {
      process.env.INTERNAL_API_URL = value;
      assert.throws(() => upstreamBase(), /valid http\(s\) URL/);
    }
  });

  it("keeps the localhost default only for non-production local development", () => {
    testEnv.NODE_ENV = "development";
    delete process.env.INTERNAL_API_URL;
    delete process.env.NEXT_PUBLIC_API_URL;
    assert.equal(upstreamBase(), "http://localhost:8000/api/v1");
  });
});
