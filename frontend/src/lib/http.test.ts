/**
 * Tests for the HTTP core (token refresh, DRF error parsing, mock gating).
 * Runs on Node's built-in test runner after a plain `tsc` compile - no native binaries or extra dependencies:
 *   npm test
 */
import { afterEach, beforeEach, describe, it } from "node:test";
import assert from "node:assert/strict";

// ---- minimal browser shims (the client reads localStorage / document.cookie / window.location) ----
const store = new Map<string, string>();
let locationHref = "";
const g = globalThis as any;

function installBrowser() {
  store.clear();
  locationHref = "";
  const cookies = new Map<string, string>();
  g.window = {
    localStorage: {
      getItem: (k: string) => (store.has(k) ? store.get(k)! : null),
      setItem: (k: string, v: string) => void store.set(k, String(v)),
      removeItem: (k: string) => void store.delete(k),
    },
    location: {
      pathname: "/student/wallet",
      search: "",
      get href() {
        return locationHref;
      },
      set href(v: string) {
        locationHref = v;
      },
    },
  };
  g.localStorage = g.window.localStorage;
  Object.defineProperty(g, "document", {
    configurable: true,
    value: {
      get cookie() {
        return Array.from(cookies.entries()).map(([k, v]) => `${k}=${v}`).join("; ");
      },
      set cookie(v: string) {
        const [pair] = v.split(";");
        const [name, ...rest] = pair.split("=");
        if (/expires=Thu, 01 Jan 1970/i.test(v)) cookies.delete(name.trim());
        else cookies.set(name.trim(), rest.join("="));
      },
    },
  });
}

function json(status: number, body: unknown): Response {
  return new Response(body === null ? null : JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

/** Fresh module instances so module state (in-flight refresh, USE_MOCKS) never leaks between tests. */
function load(env: Record<string, string> = {}) {
  for (const key of Object.keys(require.cache)) {
    if (/[\\/]lib[\\/](http|auth)\.js$/.test(key)) delete require.cache[key];
  }
  delete process.env.NEXT_PUBLIC_USE_MOCKS;
  Object.assign(process.env, env);
  return { http: require("./http") as typeof import("./http"), auth: require("./auth") as typeof import("./auth") };
}

const realFetch = globalThis.fetch;
beforeEach(installBrowser);
afterEach(() => {
  globalThis.fetch = realFetch;
  delete process.env.NEXT_PUBLIC_USE_MOCKS;
});

describe("parseDrfError", () => {
  it("collects field errors and detail messages", () => {
    const { http } = load();
    const r = http.parseDrfError(400, { email: ["A user with this email already exists."], detail: "Bad." });
    assert.deepEqual(r.fieldErrors, { email: ["A user with this email already exists."] });
    assert.match(r.message, /already exists/);
    assert.match(r.message, /Bad\./);
  });

  it("handles non_field_errors, plain strings and HTML error pages", () => {
    const { http } = load();
    assert.equal(http.parseDrfError(400, { non_field_errors: ["Nope"] }).message, "Nope");
    assert.equal(http.parseDrfError(500, "boom").message, "boom");
    assert.equal(http.parseDrfError(500, "<html>Traceback</html>").message, "Request failed (500)");
  });
});

describe("request", () => {
  it("attaches the access token and returns parsed JSON", async () => {
    const { http, auth } = load();
    auth.updateStoredTokens({ access: "A1", refresh: "R1" });
    const seen: string[] = [];
    globalThis.fetch = (async (_u: any, init: any) => {
      seen.push((init.headers as Headers).get("Authorization") || "");
      return json(200, { ok: true });
    }) as any;
    assert.deepEqual(await http.request("/auth/me/"), { ok: true });
    assert.deepEqual(seen, ["Bearer A1"]);
  });

  it("throws a typed ApiError with field errors on a 400", async () => {
    const { http } = load();
    globalThis.fetch = (async () => json(400, { username: ["Taken."] })) as any;
    const err: any = await http.request("/auth/register/", { method: "POST", body: "{}" }).catch((e) => e);
    assert.ok(err instanceof http.ApiError);
    assert.equal(err.status, 400);
    assert.deepEqual(err.fieldErrors.username, ["Taken."]);
  });

  it("reports an unreachable backend as a network error (status 0), never as data", async () => {
    const { http } = load();
    globalThis.fetch = (async () => {
      throw new TypeError("fetch failed");
    }) as any;
    const err: any = await http.request("/teachers/").catch((e) => e);
    assert.ok(err instanceof http.ApiError);
    assert.equal(err.isNetworkError, true);
    assert.match(http.errorMessage(err), /couldn't reach the server/i);
  });

  it("refreshes once on 401, stores the ROTATED refresh token and retries with the new access token", async () => {
    const { http, auth } = load();
    auth.updateStoredTokens({ access: "OLD", refresh: "R1" });
    let refreshCalls = 0;
    globalThis.fetch = (async (url: string, init: any) => {
      if (String(url).endsWith("/auth/token/refresh/")) {
        refreshCalls++;
        assert.equal(JSON.parse(init.body).refresh, "R1");
        return json(200, { access: "NEW", refresh: "R2" });
      }
      return (init.headers as Headers).get("Authorization") === "Bearer NEW" ? json(200, { data: 1 }) : json(401, { detail: "expired" });
    }) as any;

    assert.deepEqual(await http.request("/student/lessons/"), { data: 1 });
    assert.deepEqual(auth.getStoredTokens(), { access: "NEW", refresh: "R2" });
    assert.equal(refreshCalls, 1);
  });

  it("shares ONE refresh between concurrent 401s (the old refresh token is blacklisted after rotation)", async () => {
    const { http, auth } = load();
    auth.updateStoredTokens({ access: "OLD", refresh: "R1" });
    let refreshCalls = 0;
    globalThis.fetch = (async (url: string, init: any) => {
      if (String(url).endsWith("/auth/token/refresh/")) {
        refreshCalls++;
        await new Promise((r) => setTimeout(r, 20));
        return json(200, { access: "NEW", refresh: "R2" });
      }
      return (init.headers as Headers).get("Authorization") === "Bearer NEW" ? json(200, { ok: 1 }) : json(401, {});
    }) as any;
    const results = await Promise.all([http.request("/a/"), http.request("/b/"), http.request("/c/")]);
    assert.deepEqual(results, [{ ok: 1 }, { ok: 1 }, { ok: 1 }]);
    assert.equal(refreshCalls, 1);
  });

  it("ends the session and sends the user to /login?next=... when refresh fails", async () => {
    const { http, auth } = load();
    auth.updateStoredTokens({ access: "OLD", refresh: "BAD" });
    globalThis.fetch = (async () => json(401, {})) as any;
    const err: any = await http.request("/student/lessons/").catch((e) => e);
    assert.ok(err instanceof http.ApiError);
    assert.equal(err.status, 401);
    assert.equal(auth.getStoredTokens(), null);
    assert.equal(locationHref, "/login?next=%2Fstudent%2Fwallet");
  });

  it("does not try to refresh on a failed login (a wrong password is just a 401)", async () => {
    const { http, auth } = load();
    auth.updateStoredTokens({ access: "A", refresh: "R" });
    let calls = 0;
    globalThis.fetch = (async () => {
      calls++;
      return json(401, { detail: "No active account" });
    }) as any;
    const err: any = await http.request("/auth/token/", { method: "POST", body: "{}", skipAuth: true }).catch((e) => e);
    assert.equal(err.status, 401);
    assert.equal(calls, 1);
    assert.equal(locationHref, "");
  });

  it("returns null for 204/205 (logout)", async () => {
    const { http } = load();
    globalThis.fetch = (async () => new Response(null, { status: 205 })) as any;
    assert.equal(await http.request("/auth/logout/", { method: "POST", body: "{}", skipAuth: true }), null);
  });
});

describe("mock mode is explicit and off by default", () => {
  it("liveRequest throws on failure by default - it never substitutes data", async () => {
    const { http } = load();
    globalThis.fetch = (async () => json(500, { detail: "db down" })) as any;
    const err: any = await http.liveRequest("http://localhost:8000/api/v1/admin/telemetry/").catch((e) => e);
    assert.ok(err instanceof http.ApiError);
    assert.equal(err.status, 500);
  });

  it("liveRequest returns the MOCK sentinel only when NEXT_PUBLIC_USE_MOCKS=true", async () => {
    const { http } = load({ NEXT_PUBLIC_USE_MOCKS: "true" });
    const warn = console.warn;
    console.warn = () => {};
    try {
      globalThis.fetch = (async () => json(500, {})) as any;
      assert.equal(await http.liveRequest("http://localhost:8000/api/v1/admin/telemetry/"), http.MOCK);
    } finally {
      console.warn = warn;
    }
  });
});
