import { afterEach, beforeEach, describe, it } from "node:test";
import assert from "node:assert/strict";
import { fetchHostLink, hostLinkProblem, isSafeZoomUrl } from "./hostLink";
import { ApiError } from "./http";

const realFetch = globalThis.fetch;
const g = globalThis as any;

beforeEach(() => {
  g.window = { localStorage: { getItem: () => null, setItem() {}, removeItem() {} }, location: { pathname: "/", search: "", href: "" } };
});
afterEach(() => {
  globalThis.fetch = realFetch;
});

function answer(status: number, body: unknown) {
  globalThis.fetch = (async () =>
    new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } })) as typeof fetch;
}

describe("fetchHostLink", () => {
  it("GETs the host-link endpoint of the booking and returns the fresh link", async () => {
    let url = "";
    let method = "";
    globalThis.fetch = (async (u: any, init?: RequestInit) => {
      url = String(u);
      method = init?.method ?? "GET";
      return new Response(JSON.stringify({ meeting_id: "123", start_url: "https://zoom.us/s/123?zak=abc" }), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    }) as typeof fetch;
    const link = await fetchHostLink("b-1");
    assert.match(url, /\/bookings\/b-1\/host-link\/$/);
    assert.equal(method, "GET");
    assert.deepEqual(link, { meeting_id: "123", start_url: "https://zoom.us/s/123?zak=abc" });
  });

  it("throws a typed ApiError carrying the server code on a 409", async () => {
    answer(409, { error: "x", code: "too_early" });
    await assert.rejects(fetchHostLink("b-1"), (e: unknown) => e instanceof ApiError && e.status === 409 && hostLinkProblem(e).kind === "not_open");
  });

  it("refuses a response whose start_url is not a Zoom https link", async () => {
    answer(200, { meeting_id: "1", start_url: "javascript:alert(1)" });
    await assert.rejects(fetchHostLink("b-1"));
    answer(200, { meeting_id: "1", start_url: "https://evil.example/s/1" });
    await assert.rejects(fetchHostLink("b-1"));
  });
});

describe("hostLinkProblem", () => {
  const api = (status: number, code?: string) => new ApiError(status, "m", code ? { code } : null);
  it("maps the 409 codes to what the tutor can do", () => {
    assert.equal(hostLinkProblem(api(409, "too_early")).kind, "not_open");
    assert.equal(hostLinkProblem(api(409, "lesson_ended")).kind, "ended");
    assert.equal(hostLinkProblem(api(409, "not_live")).kind, "ended");
    assert.equal(hostLinkProblem(api(409, "no_meeting")).kind, "no_room");
    assert.equal(hostLinkProblem(api(409, "meeting_missing")).kind, "no_room");
  });
  it("asks to try again on a 502 and on a network failure", () => {
    assert.equal(hostLinkProblem(api(502, "zoom_unavailable")).kind, "retry");
    assert.equal(hostLinkProblem(new ApiError(0, "Network error")).kind, "retry");
  });
  it("explains a 403 and falls back for anything else", () => {
    assert.equal(hostLinkProblem(api(403, "host_only")).kind, "forbidden");
    assert.equal(hostLinkProblem(new Error("boom")).kind, "other");
    assert.equal(hostLinkProblem(api(500)).kind, "other");
  });
  it("gives every kind a message that never contains the raw server text", () => {
    for (const e of [api(409, "too_early"), api(409, "lesson_ended"), api(409, "no_meeting"), api(502), api(403), new Error("SECRET")]) {
      const p = hostLinkProblem(e);
      assert.ok(p.message.length > 10);
      assert.ok(!p.message.includes("SECRET"));
    }
  });
});

describe("isSafeZoomUrl", () => {
  it("accepts https Zoom hosts only", () => {
    assert.equal(isSafeZoomUrl("https://zoom.us/s/1?zak=a"), true);
    assert.equal(isSafeZoomUrl("https://us02web.zoom.us/s/1"), true);
    assert.equal(isSafeZoomUrl("http://zoom.us/s/1"), false);
    assert.equal(isSafeZoomUrl("https://zoom.us.evil.example/s/1"), false);
    assert.equal(isSafeZoomUrl("https://evilzoom.us/s/1"), false);
    assert.equal(isSafeZoomUrl("javascript:alert(1)"), false);
    assert.equal(isSafeZoomUrl(""), false);
    assert.equal(isSafeZoomUrl("zoommtg://zoom.us/start?confno=1"), false);
  });
});
