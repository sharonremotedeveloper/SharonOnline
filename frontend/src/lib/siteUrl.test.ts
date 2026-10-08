import assert from "node:assert/strict";
import { test } from "node:test";
import { resolveSiteUrl } from "./siteUrl";

test("prefers NEXT_PUBLIC_SITE_URL, then APP_URL, then Vercel hosts", () => {
  assert.equal(resolveSiteUrl({ NEXT_PUBLIC_SITE_URL: "https://a.example/", NEXT_PUBLIC_APP_URL: "https://b.example" }), "https://a.example");
  assert.equal(resolveSiteUrl({ NEXT_PUBLIC_APP_URL: "https://b.example/path" }), "https://b.example");
  assert.equal(resolveSiteUrl({ VERCEL_PROJECT_PRODUCTION_URL: "p.vercel.app", VERCEL_URL: "d.vercel.app" }), "https://p.vercel.app");
  assert.equal(resolveSiteUrl({ VERCEL_URL: "d.vercel.app" }), "https://d.vercel.app");
});

test("falls back to localhost only when nothing is set or values are invalid", () => {
  assert.equal(resolveSiteUrl({}), "http://localhost:3000");
  assert.equal(resolveSiteUrl({ NEXT_PUBLIC_SITE_URL: "not a url", NEXT_PUBLIC_APP_URL: " " }), "http://localhost:3000");
});
