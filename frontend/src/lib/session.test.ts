import { afterEach, beforeEach, describe, it } from "node:test";
import assert from "node:assert/strict";
import * as s from "./session";

const SECRET = "unit-test-secret-unit-test-secret-1234567890";
const NOW = 1_800_000_000;

beforeEach(() => {
  process.env.SESSION_SECRET = SECRET;
});
afterEach(() => {
  delete process.env.SESSION_SECRET;
  delete process.env.SESSION_COOKIE_SECURE;
  (process.env as any).NODE_ENV = "test";
});

const claims = (over: Partial<s.SessionClaims> = {}): s.SessionClaims => ({ uid: "u1", role: "student", exp: NOW + 600, ...over });

describe("signed session cookie", () => {
  it("round-trips valid claims", async () => {
    const token = await s.signSession(claims());
    assert.deepEqual(await s.verifySession(token, NOW), claims());
  });

  it("rejects an expired session", async () => {
    const token = await s.signSession(claims({ exp: NOW - 1 }));
    assert.equal(await s.verifySession(token, NOW), null);
  });

  it("rejects a tampered payload (role escalation by editing the cookie)", async () => {
    const token = await s.signSession(claims({ role: "student" }));
    const forgedPayload = Buffer.from(JSON.stringify(claims({ role: "admin" }))).toString("base64url");
    assert.equal(await s.verifySession(`${forgedPayload}.${token.split(".")[1]}`, NOW), null);
  });

  it("rejects a forged cookie with an invented signature", async () => {
    const payload = Buffer.from(JSON.stringify(claims({ role: "admin" }))).toString("base64url");
    assert.equal(await s.verifySession(`${payload}.AAAA`, NOW), null);
    assert.equal(await s.verifySession(`${payload}.`, NOW), null);
    assert.equal(await s.verifySession(payload, NOW), null);
  });

  it("rejects a cookie signed with a different secret", async () => {
    const token = await s.signSession(claims());
    process.env.SESSION_SECRET = "another-secret-another-secret-another-secret";
    assert.equal(await s.verifySession(token, NOW), null);
  });

  it("rejects validly-signed claims with an unknown role or wrong shape", async () => {
    assert.equal(await s.verifySession(await s.signSession(claims({ role: "superuser" as any })), NOW), null);
    assert.equal(await s.verifySession(await s.signSession({ uid: 5, role: "student", exp: NOW + 5 } as any), NOW), null);
  });

  it("rejects empty, oversized and garbage input without throwing", async () => {
    for (const bad of [undefined, null, "", "x".repeat(5000), "a.b.c", "not a token", "%%%.%%%"]) {
      assert.equal(await s.verifySession(bad as any, NOW), null);
    }
  });

  it("refuses to run in production without a strong SESSION_SECRET (and never falls back to the dev key)", async () => {
    delete process.env.SESSION_SECRET;
    (process.env as any).NODE_ENV = "production";
    await assert.rejects(() => s.signSession(claims()), /SESSION_SECRET/);
    process.env.SESSION_SECRET = "short";
    await assert.rejects(() => s.signSession(claims()), /SESSION_SECRET/);
  });

  it("falls back to a dev secret only outside production", async () => {
    delete process.env.SESSION_SECRET;
    const token = await s.signSession(claims());
    assert.ok(await s.verifySession(token, NOW));
  });
});

describe("cookie attributes", () => {
  const spec = () => s.buildCookies({ access: "A", refresh: "R", session: "S" });

  it("every auth cookie is HttpOnly + SameSite=Lax", () => {
    for (const c of spec()) {
      assert.equal(c.httpOnly, true);
      assert.equal(c.sameSite, "lax");
    }
  });

  it("tokens are only sent to /api; the session cookie is needed by page navigations", () => {
    const byName = Object.fromEntries(spec().map((c) => [c.name, c]));
    assert.equal(byName[s.ACCESS_COOKIE].path, "/api");
    assert.equal(byName[s.REFRESH_COOKIE].path, "/api");
    assert.equal(byName[s.SESSION_COOKIE].path, "/");
    assert.equal(byName[s.REFRESH_COOKIE].maxAge, s.REFRESH_TTL_SECONDS);
  });

  it("Secure in production, overridable only explicitly for plain-http staging", () => {
    (process.env as any).NODE_ENV = "production";
    assert.ok(spec().every((c) => c.secure));
    process.env.SESSION_COOKIE_SECURE = "false";
    assert.ok(spec().every((c) => !c.secure));
  });

  it("expiredCookies clears all three", () => {
    const names = s.expiredCookies().map((c) => `${c.name}:${c.maxAge}:${c.value}`);
    assert.deepEqual(names.sort(), [`${s.ACCESS_COOKIE}:0:`, `${s.REFRESH_COOKIE}:0:`, `${s.SESSION_COOKIE}:0:`].sort());
  });
});

describe("serializeCookie", () => {
  const spec = (over: Partial<s.CookieSpec> = {}): s.CookieSpec => ({ name: "n", value: "v.1-2_3", httpOnly: true, sameSite: "lax", secure: false, path: "/api", maxAge: 60, ...over });

  it("emits HttpOnly + SameSite=Lax, path and max-age", () => {
    assert.equal(s.serializeCookie(spec()), "n=v.1-2_3; Path=/api; Max-Age=60; HttpOnly; SameSite=Lax");
  });
  it("adds Secure when asked", () => assert.match(s.serializeCookie(spec({ secure: true })), /; Secure$/));
  it("expired cookies carry an epoch Expires for old browsers", () => {
    assert.match(s.serializeCookie(spec({ value: "", maxAge: 0 })), /Max-Age=0; Expires=Thu, 01 Jan 1970/);
  });
  it("refuses values that could inject attributes or headers", () => {
    for (const bad of ["a;b", "a b", "a\r\nSet-Cookie: x=1", "a,b", 'a"b']) {
      assert.throws(() => s.serializeCookie(spec({ value: bad })), /unexpected characters/);
    }
  });
  it("accepts real JWT and session shapes", () => {
    const jwt = "eyJhbGciOiJIUzI1NiJ9.eyJleHAiOjF9.abc-_123";
    assert.doesNotThrow(() => s.serializeCookie(spec({ value: jwt })));
  });
});

describe("safeNext (open-redirect guard)", () => {
  it("allows same-site relative paths", () => {
    assert.equal(s.safeNext("/student/wallet?tab=1"), "/student/wallet?tab=1");
    assert.equal(s.safeNext("/"), "/");
  });

  it("rejects anything that could leave the site or smuggle headers", () => {
    for (const bad of ["//evil.com", "/\\evil.com", "https://evil.com", "http://x", "javascript:alert(1)", "evil.com", "/ok\r\nSet-Cookie: x=1", "/api/proxy/admin/", "x".repeat(600), "", null, undefined]) {
      assert.equal(s.safeNext(bad as any, "/fallback"), "/fallback", String(bad));
    }
  });
});

describe("decodeJwtExp", () => {
  const jwt = (payload: object) => `h.${Buffer.from(JSON.stringify(payload)).toString("base64url")}.s`;
  it("reads exp without verifying", () => assert.equal(s.decodeJwtExp(jwt({ exp: 123 })), 123));
  it("returns null for junk", () => {
    assert.equal(s.decodeJwtExp("nope"), null);
    assert.equal(s.decodeJwtExp(jwt({})), null);
    assert.equal(s.decodeJwtExp(undefined), null);
  });
});
