import { beforeEach, describe, it } from "node:test";
import assert from "node:assert/strict";
import * as h from "./handlers";
import * as up from "./upstream";

const json = (status: number, body: unknown, headers: Record<string, string> = {}) =>
  new Response(body === null ? null : JSON.stringify(body), { status, headers: { "Content-Type": "application/json", ...headers } });

const jwt = (expSeconds: number) => `h.${Buffer.from(JSON.stringify({ exp: expSeconds })).toString("base64url")}.s`;
const now = () => Math.floor(Date.now() / 1000);
const FRESH = () => jwt(now() + 600);
const EXPIRED = () => jwt(now() - 10);

type Call = { url: string; method: string; headers: Headers; body?: any };
function fakeUpstream(handler: (c: Call) => Response | Promise<Response>) {
  const calls: Call[] = [];
  const fetchImpl = async (url: string, init: any = {}) => {
    const call: Call = { url, method: init.method || "GET", headers: init.headers as Headers, body: init.body };
    calls.push(call);
    return handler(call);
  };
  return { calls, fetchImpl: fetchImpl as unknown as up.FetchLike };
}
const authOf = (c: Call) => c.headers.get("Authorization");
const refreshCalls = (calls: Call[]) => calls.filter((c) => c.url.endsWith("/auth/token/refresh/"));

beforeEach(() => up._resetRefreshState());

describe("normalizeProxyPath", () => {
  it("builds a slash-terminated path", () => {
    assert.equal(h.normalizeProxyPath(["teachers", "abc-123"]), "teachers/abc-123/");
    assert.equal(h.normalizeProxyPath(["student", "flashcards", "9", "mastery"]), "student/flashcards/9/mastery/");
  });

  it("rejects traversal, encoded separators, empty and oversized paths", () => {
    for (const bad of [[], undefined, [".."], ["a", ".."], ["."], ["a/b"], ["a\\b"], ["a?x=1"], ["%2e%2e"], ["a b"], ["a", ""], Array(13).fill("a")]) {
      assert.equal(h.normalizeProxyPath(bad as any), null, JSON.stringify(bad));
    }
  });

  it("never exposes the token-issuing endpoints to browser JS", () => {
    assert.equal(h.normalizeProxyPath(["auth", "token"]), null);
    assert.equal(h.normalizeProxyPath(["auth", "token", "refresh"]), null);
    assert.equal(h.normalizeProxyPath(["auth", "logout"]), null);
    assert.equal(h.normalizeProxyPath(["auth", "me"]), "auth/me/"); // everything else is fine
    assert.equal(h.normalizeProxyPath(["auth", "register"]), "auth/register/");
  });
});

describe("isSameOriginRequest (CSRF)", () => {
  const hosts = ["app.example.com"];
  const H = (o: Record<string, string>) => new Headers(o);
  it("safe methods pass", () => assert.equal(h.isSameOriginRequest("GET", H({}), hosts), true));
  it("accepts a matching Origin", () => assert.equal(h.isSameOriginRequest("POST", H({ origin: "https://app.example.com" }), hosts), true));
  it("rejects a foreign Origin", () => assert.equal(h.isSameOriginRequest("POST", H({ origin: "https://evil.com" }), hosts), false));
  it("rejects a lookalike origin", () => assert.equal(h.isSameOriginRequest("DELETE", H({ origin: "https://app.example.com.evil.com" }), hosts), false));
  it("rejects a malformed Origin", () => assert.equal(h.isSameOriginRequest("POST", H({ origin: "null" }), hosts), false));
  it("without Origin, requires Sec-Fetch-Site: same-origin", () => {
    assert.equal(h.isSameOriginRequest("POST", H({ "sec-fetch-site": "same-origin" }), hosts), true);
    assert.equal(h.isSameOriginRequest("POST", H({ "sec-fetch-site": "cross-site" }), hosts), false);
    assert.equal(h.isSameOriginRequest("POST", H({}), hosts), false);
  });
  it("allowedHostsFrom reads Host and X-Forwarded-Host", () => {
    assert.deepEqual(h.allowedHostsFrom(H({ host: "localhost:3000", "x-forwarded-host": "app.example.com" })), ["localhost:3000", "app.example.com"]);
  });
});

describe("clientIp", () => {
  const H = (v: string) => new Headers({ "x-forwarded-for": v });
  it("is unknown when no trusted proxy is configured", () => assert.equal(up.clientIp(H("1.1.1.1"), 0), null));
  it("takes the entry added by our trusted proxy, ignoring spoofed left-hand values", () => {
    assert.equal(up.clientIp(H("6.6.6.6, 203.0.113.9"), 1), "203.0.113.9");
    assert.equal(up.clientIp(H("6.6.6.6, 203.0.113.9, 10.0.0.1"), 2), "203.0.113.9");
  });
  it("handles a short or missing chain", () => {
    assert.equal(up.clientIp(H("203.0.113.9"), 3), "203.0.113.9");
    assert.equal(up.clientIp(new Headers(), 1), null);
  });
});

describe("proxyRequest", () => {
  const base = (over: Partial<h.ProxyInput> = {}): h.ProxyInput => ({
    method: "GET", segments: ["student", "lessons"], search: "?page=2", headers: new Headers(), body: null, ...over,
  });

  it("attaches the token from the cookie, hits the right URL, and returns the body", async () => {
    const access = FRESH();
    const { calls, fetchImpl } = fakeUpstream(() => json(200, { results: [1] }));
    const out = await h.proxyRequest(base({ access, refresh: "R1" }), fetchImpl);
    assert.equal(out.status, 200);
    assert.deepEqual(JSON.parse(new TextDecoder().decode(out.body as ArrayBuffer)), { results: [1] });
    assert.equal(calls.length, 1);
    assert.ok(calls[0].url.endsWith("/student/lessons/?page=2"));
    assert.equal(authOf(calls[0]), `Bearer ${access}`);
    assert.equal(out.newTokens, undefined);
  });

  it("does NOT forward the browser's own Authorization, Cookie or Host headers", async () => {
    const { calls, fetchImpl } = fakeUpstream(() => json(200, {}));
    const headers = new Headers({ authorization: "Bearer attacker", cookie: "sharon_refresh=steal", host: "evil", "x-forwarded-for": "6.6.6.6" });
    await h.proxyRequest(base({ headers, access: FRESH(), refresh: "R1" }), fetchImpl);
    const sent = calls[0].headers;
    assert.notEqual(sent.get("authorization"), "Bearer attacker");
    assert.equal(sent.get("cookie"), null);
    assert.equal(sent.get("host"), null);
    assert.equal(sent.get("x-forwarded-for"), null); // only the server-derived value is ever sent
  });

  it("sends the server-derived client IP as the single X-Forwarded-For value", async () => {
    const { calls, fetchImpl } = fakeUpstream(() => json(200, {}));
    await h.proxyRequest(base({ access: FRESH(), refresh: "R1", ip: "203.0.113.9" }), fetchImpl);
    assert.equal(calls[0].headers.get("x-forwarded-for"), "203.0.113.9");
  });

  it("calls public endpoints without credentials when there is no session", async () => {
    const { calls, fetchImpl } = fakeUpstream(() => json(200, { results: [] }));
    const out = await h.proxyRequest(base({ segments: ["teachers"] }), fetchImpl);
    assert.equal(out.status, 200);
    assert.equal(authOf(calls[0]), null);
    assert.equal(refreshCalls(calls).length, 0);
  });

  it("refreshes BEFORE calling when the access token is expired, and reports the rotated tokens", async () => {
    const newAccess = FRESH();
    const { calls, fetchImpl } = fakeUpstream((c) =>
      c.url.endsWith("/auth/token/refresh/") ? json(200, { access: newAccess, refresh: "R2" }) : json(200, { ok: 1 })
    );
    const out = await h.proxyRequest(base({ access: EXPIRED(), refresh: "R1" }), fetchImpl);
    assert.equal(out.status, 200);
    assert.deepEqual(out.newTokens, { access: newAccess, refresh: "R2" });
    assert.equal(calls.length, 2);
    assert.equal(JSON.parse(calls[0].body).refresh, "R1");
    assert.equal(authOf(calls[1]), `Bearer ${newAccess}`);
  });

  it("refreshes when the access cookie has expired away entirely", async () => {
    const newAccess = FRESH();
    const { fetchImpl } = fakeUpstream((c) =>
      c.url.endsWith("/auth/token/refresh/") ? json(200, { access: newAccess, refresh: "R2" }) : json(200, {})
    );
    const out = await h.proxyRequest(base({ access: undefined, refresh: "R1" }), fetchImpl);
    assert.equal(out.status, 200);
    assert.equal(out.newTokens?.access, newAccess);
  });

  it("on a 401 with a seemingly-valid token, refreshes once and retries with the new token", async () => {
    const stale = FRESH();
    const newAccess = FRESH() + "x";
    const { calls, fetchImpl } = fakeUpstream((c) => {
      if (c.url.endsWith("/auth/token/refresh/")) return json(200, { access: newAccess, refresh: "R2" });
      return authOf(c) === `Bearer ${newAccess}` ? json(200, { ok: 1 }) : json(401, { detail: "revoked" });
    });
    const out = await h.proxyRequest(base({ access: stale, refresh: "R1" }), fetchImpl);
    assert.equal(out.status, 200);
    assert.equal(out.newTokens?.refresh, "R2");
    assert.equal(refreshCalls(calls).length, 1);
  });

  it("a dead refresh token ends the session: 401 and clear cookies", async () => {
    const { fetchImpl } = fakeUpstream((c) => (c.url.endsWith("/auth/token/refresh/") ? json(401, {}) : json(401, {})));
    const out = await h.proxyRequest(base({ access: EXPIRED(), refresh: "BAD" }), fetchImpl);
    assert.equal(out.status, 401);
    assert.equal(out.clear, true);
  });

  it("shares ONE refresh between concurrent requests, and late arrivals holding the OLD cookie get the NEW tokens", async () => {
    const newAccess = FRESH();
    const { calls, fetchImpl } = fakeUpstream(async (c) => {
      if (c.url.endsWith("/auth/token/refresh/")) {
        await new Promise((r) => setTimeout(r, 20));
        return json(200, { access: newAccess, refresh: "R2" });
      }
      return json(200, { ok: 1 });
    });
    const inputs = [1, 2, 3].map(() => base({ access: EXPIRED(), refresh: "R1" }));
    const outs = await Promise.all(inputs.map((i) => h.proxyRequest(i, fetchImpl)));
    const late = await h.proxyRequest(base({ access: EXPIRED(), refresh: "R1" }), fetchImpl); // still has the old cookie
    assert.ok([...outs, late].every((o) => o.status === 200 && o.newTokens?.refresh === "R2"));
    assert.equal(refreshCalls(calls).length, 1); // the old refresh token (blacklisted after rotation) was spent exactly once
  });

  it("blocked and malformed paths never reach Django", async () => {
    const { calls, fetchImpl } = fakeUpstream(() => json(200, {}));
    assert.equal((await h.proxyRequest(base({ segments: ["auth", "token"] }), fetchImpl)).status, 404);
    assert.equal((await h.proxyRequest(base({ segments: ["..", "admin"] }), fetchImpl)).status, 404);
    assert.equal(calls.length, 0);
  });

  it("rejects oversized bodies before forwarding", async () => {
    const { calls, fetchImpl } = fakeUpstream(() => json(200, {}));
    const out = await h.proxyRequest(base({ method: "POST", body: new ArrayBuffer(h.MAX_BODY_BYTES + 1) }), fetchImpl);
    assert.equal(out.status, 413);
    assert.equal(calls.length, 0);
  });

  it("forwards bodies for unsafe methods and never for safe ones", async () => {
    const { calls, fetchImpl } = fakeUpstream(() => json(201, {}));
    const body = new TextEncoder().encode('{"a":1}').buffer as ArrayBuffer;
    await h.proxyRequest(base({ method: "POST", body, headers: new Headers({ "content-type": "application/json" }), access: FRESH(), refresh: "R" }), fetchImpl);
    assert.ok(calls[0].body);
    assert.equal(calls[0].headers.get("content-type"), "application/json");
    await h.proxyRequest(base({ method: "GET", body, access: FRESH(), refresh: "R" }), fetchImpl);
    assert.equal(calls[1].body, undefined);
  });

  it("passes through upstream statuses and Retry-After (throttling)", async () => {
    const { fetchImpl } = fakeUpstream(() => json(429, { detail: "Throttled" }, { "Retry-After": "42" }));
    const out = await h.proxyRequest(base({ access: FRESH(), refresh: "R" }), fetchImpl);
    assert.equal(out.status, 429);
    assert.equal(out.retryAfter, "42");
    assert.equal(out.clear, false);
  });

  it("maps an unreachable Django to 502 and a timeout to 504, keeping rotated tokens", async () => {
    const down = await h.proxyRequest(base({ access: FRESH(), refresh: "R" }), (async () => { throw new TypeError("fetch failed"); }) as any);
    assert.equal(down.status, 502);
    const timeout = await h.proxyRequest(base({ access: FRESH(), refresh: "R" }), (async () => { const e = new Error("t"); e.name = "TimeoutError"; throw e; }) as any);
    assert.equal(timeout.status, 504);
  });
});

describe("loginRequest", () => {
  const USER = { id: "u1", role: "student", username: "aiko" };
  const ok = () =>
    fakeUpstream((c) => (c.url.endsWith("/auth/token/") ? json(200, { access: "A", refresh: "R" }) : json(200, USER)));

  it("returns the user and tokens on success, loading the profile with the new access token", async () => {
    const { calls, fetchImpl } = ok();
    const out = await h.loginRequest({ username: "aiko", password: "pw", ip: "203.0.113.9" }, fetchImpl);
    assert.deepEqual(out, { ok: true, user: USER, tokens: { access: "A", refresh: "R" } });
    assert.equal(authOf(calls[1]), "Bearer A");
    assert.equal(calls[0].headers.get("x-forwarded-for"), "203.0.113.9"); // so Django's login throttle keys on the user, not on us
  });

  it("passes a wrong-password 401 through without tokens", async () => {
    const { fetchImpl } = fakeUpstream(() => json(401, { detail: "No active account" }));
    const out = await h.loginRequest({ username: "a", password: "b" }, fetchImpl);
    assert.equal(out.ok, false);
    assert.equal((out as any).status, 401);
  });

  it("passes throttling through with Retry-After", async () => {
    const { fetchImpl } = fakeUpstream(() => json(429, { detail: "Throttled" }, { "Retry-After": "30" }));
    const out: any = await h.loginRequest({ username: "a", password: "b" }, fetchImpl);
    assert.equal(out.status, 429);
    assert.equal(out.retryAfter, "30");
  });

  it("validates input before touching Django", async () => {
    const { calls, fetchImpl } = ok();
    for (const bad of [{ username: 1, password: "x" }, { username: "x", password: ["y"] }, { username: "", password: "x" }, { username: "x".repeat(151), password: "x" }, { username: "x", password: "y".repeat(257) }]) {
      const out: any = await h.loginRequest(bad as any, fetchImpl);
      assert.equal(out.status, 400);
    }
    assert.equal(calls.length, 0);
  });

  it("fails closed if the profile has no valid role or cannot be loaded", async () => {
    const noRole = fakeUpstream((c) => (c.url.endsWith("/auth/token/") ? json(200, { access: "A", refresh: "R" }) : json(200, { id: "u", role: "superuser" })));
    assert.equal(((await h.loginRequest({ username: "a", password: "b" }, noRole.fetchImpl)) as any).status, 502);
    const meDown = fakeUpstream((c) => (c.url.endsWith("/auth/token/") ? json(200, { access: "A", refresh: "R" }) : json(500, {})));
    assert.equal(((await h.loginRequest({ username: "a", password: "b" }, meDown.fetchImpl)) as any).status, 502);
  });

  it("reports an unreachable Django as 502", async () => {
    const out: any = await h.loginRequest({ username: "a", password: "b" }, (async () => { throw new Error("down"); }) as any);
    assert.equal(out.status, 502);
  });
});

describe("renewSession / revokeRefreshToken", () => {
  it("re-reads the role from Django and returns rotated tokens", async () => {
    const { fetchImpl } = fakeUpstream((c) =>
      c.url.endsWith("/auth/token/refresh/") ? json(200, { access: "A2", refresh: "R2" }) : json(200, { id: "u1", role: "teacher" })
    );
    const out: any = await h.renewSession("R1", null, fetchImpl);
    assert.equal(out.user.role, "teacher");
    assert.deepEqual(out.tokens, { access: "A2", refresh: "R2" });
  });

  it("is invalid without a refresh token or with a dead one", async () => {
    const { fetchImpl } = fakeUpstream(() => json(401, {}));
    assert.deepEqual(await h.renewSession(undefined, null, fetchImpl), { error: "invalid" });
    assert.deepEqual(await h.renewSession("DEAD", null, fetchImpl), { error: "invalid" });
  });

  it("revokes the refresh token at Django", async () => {
    const { calls, fetchImpl } = fakeUpstream(() => json(205, null));
    assert.equal(await h.revokeRefreshToken("R1", null, fetchImpl), true);
    assert.ok(calls[0].url.endsWith("/auth/logout/"));
    assert.equal(JSON.parse(calls[0].body).refresh, "R1");
    assert.equal(await h.revokeRefreshToken(undefined, null, fetchImpl), false);
    assert.equal(await h.revokeRefreshToken("R1", null, (async () => { throw new Error("x"); }) as any), false);
  });
});
