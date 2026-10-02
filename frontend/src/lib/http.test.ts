/**
 * Tests for the browser HTTP client. Runs on Node's built-in test runner after a plain `tsc` compile
 * (no native binaries or extra dependencies):  npm test
 */
import { afterEach, beforeEach, describe, it } from "node:test";
import assert from "node:assert/strict";

// ---- minimal browser shims ----
const store = new Map<string, string>();
const cookieJar = new Map<string, string>();
let locationHref = "";
const g = globalThis as any;

function installBrowser() {
  store.clear();
  cookieJar.clear();
  locationHref = "";
  g.window = {
    localStorage: {
      getItem: (k: string) => (store.has(k) ? store.get(k)! : null),
      setItem: (k: string, v: string) => void store.set(k, String(v)),
      removeItem: (k: string) => void store.delete(k),
    },
    location: {
      pathname: "/student/wallet",
      search: "?tab=1",
      get href() {
        return locationHref;
      },
      set href(v: string) {
        locationHref = v;
      },
    },
  };
  Object.defineProperty(g, "document", {
    configurable: true,
    value: {
      get cookie() {
        return Array.from(cookieJar.entries()).map(([k, v]) => `${k}=${v}`).join("; ");
      },
      set cookie(v: string) {
        const [pair] = v.split(";");
        const [name, ...rest] = pair.split("=");
        if (/expires=Thu, 01 Jan 1970/i.test(v)) cookieJar.delete(name.trim());
        else cookieJar.set(name.trim(), rest.join("="));
      },
    },
  });
}

function json(status: number, body: unknown): Response {
  return new Response(body === null ? null : JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

/** Fresh module instance so module-level constants (USE_MOCKS, API_BASE) are re-evaluated per test. */
function load(env: Record<string, string> = {}) {
  for (const key of Object.keys(require.cache)) {
    if (/[\\/]lib[\\/](http|session)\.js$/.test(key)) delete require.cache[key];
  }
  delete process.env.NEXT_PUBLIC_USE_MOCKS;
  Object.assign(process.env, env);
  return require("./http") as typeof import("./http");
}

const realFetch = globalThis.fetch;
beforeEach(installBrowser);
afterEach(() => {
  globalThis.fetch = realFetch;
  delete process.env.NEXT_PUBLIC_USE_MOCKS;
});

describe("parseDrfError", () => {
  it("collects field errors and detail messages", () => {
    const http = load();
    const r = http.parseDrfError(400, { email: ["A user with this email already exists."], detail: "Bad." });
    assert.deepEqual(r.fieldErrors, { email: ["A user with this email already exists."] });
    assert.match(r.message, /already exists/);
    assert.match(r.message, /Bad\./);
  });

  it("handles non_field_errors, plain strings and HTML error pages", () => {
    const http = load();
    assert.equal(http.parseDrfError(400, { non_field_errors: ["Nope"] }).message, "Nope");
    assert.equal(http.parseDrfError(500, "boom").message, "boom");
    assert.equal(http.parseDrfError(500, "<html>Traceback</html>").message, "Request failed (500)");
  });
});

describe("request (browser)", () => {
  it("talks to our own origin through the proxy and sends no token of its own", async () => {
    const http = load();
    let seen: { url: string; init: any } | null = null;
    globalThis.fetch = (async (url: any, init: any) => {
      seen = { url: String(url), init };
      return json(200, { ok: true });
    }) as any;
    assert.deepEqual(await http.request("/teachers/"), { ok: true });
    assert.equal(seen!.url, "/api/proxy/teachers"); // no trailing slash: Next would 308 it; the proxy re-adds it for Django
    assert.equal(seen!.init.credentials, "same-origin");
    assert.equal((seen!.init.headers as Headers).get("Authorization"), null);
  });

  it("strips the trailing slash only for the proxy, keeping the query string", () => {
    const http = load();
    assert.equal(http.stripProxyTrailingSlash("/api/proxy/teachers/?page=2"), "/api/proxy/teachers?page=2");
    assert.equal(http.stripProxyTrailingSlash("/api/proxy/a/b/"), "/api/proxy/a/b");
    assert.equal(http.stripProxyTrailingSlash("/api/session/me/"), "/api/session/me/");
    assert.equal(http.stripProxyTrailingSlash("https://x.test/teachers/"), "https://x.test/teachers/");
  });

  it("leaves /api/* app routes and absolute URLs alone", async () => {
    const http = load();
    const urls: string[] = [];
    globalThis.fetch = (async (url: any) => {
      urls.push(String(url));
      return json(200, {});
    }) as any;
    await http.request("/api/session/me");
    await http.request("https://example.com/x");
    assert.deepEqual(urls, ["/api/session/me", "https://example.com/x"]);
  });

  it("throws a typed ApiError with field errors on a 400", async () => {
    const http = load();
    globalThis.fetch = (async () => json(400, { username: ["Taken."] })) as any;
    const err: any = await http.request("/auth/register/", { method: "POST", body: "{}" }).catch((e) => e);
    assert.ok(err instanceof http.ApiError);
    assert.equal(err.status, 400);
    assert.deepEqual(err.fieldErrors.username, ["Taken."]);
  });

  it("reports an unreachable server as a network error, never as data", async () => {
    const http = load();
    globalThis.fetch = (async () => {
      throw new TypeError("fetch failed");
    }) as any;
    const err: any = await http.request("/teachers/").catch((e) => e);
    assert.ok(err instanceof http.ApiError);
    assert.equal(err.isNetworkError, true);
    assert.match(http.errorMessage(err), /couldn't reach the server/i);
  });

  it("treats proxy 502/504 as network errors too", () => {
    const http = load();
    assert.equal(new http.ApiError(502, "x").isNetworkError, true);
    assert.equal(new http.ApiError(504, "x").isNetworkError, true);
    assert.equal(new http.ApiError(500, "x").isNetworkError, false);
  });

  it("a 401 ends the session: redirect to /login?next=... and throw", async () => {
    const http = load();
    globalThis.fetch = (async () => json(401, { detail: "Your session has expired." })) as any;
    const err: any = await http.request("/student/lessons/").catch((e) => e);
    assert.ok(err instanceof http.ApiError);
    assert.equal(err.status, 401);
    assert.equal(locationHref, "/login?next=%2Fstudent%2Fwallet%3Ftab%3D1");
  });

  it("skipAuth: a 401 (wrong password, 'not signed in') is just an answer - no redirect", async () => {
    const http = load();
    globalThis.fetch = (async () => json(401, { detail: "No active account" })) as any;
    const err: any = await http.request("/api/session/login", { method: "POST", body: "{}", skipAuth: true }).catch((e) => e);
    assert.equal(err.status, 401);
    assert.equal(locationHref, "");
  });

  it("returns null for 204/205", async () => {
    const http = load();
    globalThis.fetch = (async () => new Response(null, { status: 205 })) as any;
    assert.equal(await http.request("/api/session/logout", { method: "POST", skipAuth: true }), null);
  });
});

describe("purgeLegacyBrowserSession", () => {
  it("removes tokens the old implementation left in localStorage and JS-readable cookies", () => {
    const http = load();
    for (const k of ["access_token", "refresh_token", "user_role", "user_profile", "sharon_currency"]) store.set(k, "x");
    for (const c of ["sharon_access_token", "sharon_refresh_token", "sharon_user_role", "unrelated"]) cookieJar.set(c, "x");
    http.purgeLegacyBrowserSession();
    assert.deepEqual(Array.from(store.keys()), ["sharon_currency"]); // unrelated prefs survive
    assert.deepEqual(Array.from(cookieJar.keys()), ["unrelated"]);
  });
});

describe("mock mode is explicit and off by default", () => {
  it("liveRequest throws on failure by default - it never substitutes data", async () => {
    const http = load();
    globalThis.fetch = (async () => json(500, { detail: "db down" })) as any;
    const err: any = await http.liveRequest("/admin/telemetry/").catch((e) => e);
    assert.ok(err instanceof http.ApiError);
    assert.equal(err.status, 500);
  });

  it("liveRequest returns the MOCK sentinel only when NEXT_PUBLIC_USE_MOCKS=true", async () => {
    const http = load({ NEXT_PUBLIC_USE_MOCKS: "true" });
    const warn = console.warn;
    console.warn = () => {};
    try {
      globalThis.fetch = (async () => json(500, {})) as any;
      assert.equal(await http.liveRequest("/admin/telemetry/"), http.MOCK);
    } finally {
      console.warn = warn;
    }
  });
});
