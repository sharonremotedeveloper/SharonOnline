import { afterEach, describe, it } from "node:test";
import assert from "node:assert/strict";
import { bookingListQuery, listBookings } from "./bookings";

const realFetch = globalThis.fetch;
afterEach(() => {
  globalThis.fetch = realFetch;
});

describe("bookingListQuery", () => {
  it("is empty without filters", () => assert.equal(bookingListQuery(), ""));
  it("joins statuses and encodes values", () => {
    assert.equal(
      bookingListQuery({ status: ["completed", "cancelled"], when: "past", from: "2026-10-01T00:00:00+02:00", pageSize: 50 }),
      "?status=completed%2Ccancelled&when=past&from=2026-10-01T00%3A00%3A00%2B02%3A00&page_size=50"
    );
  });
  it("skips empty status lists", () => assert.equal(bookingListQuery({ status: [] }), ""));
});

describe("listBookings", () => {
  const g = globalThis as any;
  it("calls the proxy with the query and reports totals", async () => {
    let url = "";
    g.window = { localStorage: { getItem: () => null, setItem() {}, removeItem() {} }, location: { pathname: "/", search: "", href: "" } };
    globalThis.fetch = (async (u: any) => {
      url = String(u);
      return new Response(JSON.stringify({ count: 7, next: "x", results: [{ id: "a" }, { id: "b" }] }), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    }) as typeof fetch;
    const page = await listBookings({ when: "upcoming" });
    assert.match(url, /\/bookings\/\?when=upcoming$/);
    assert.deepEqual([page.items.length, page.count, page.hasMore], [2, 7, true]);
  });
});

import { cancelBooking, errorCode, getCancelPreview, rescheduleBooking } from "./bookings";
import { convertRefundToWallet, listRefunds } from "./refunds";

describe("cancel + reschedule + refunds client", () => {
  const g = globalThis as any;
  const calls: { url: string; init: any }[] = [];
  function reply(status: number, body: unknown) {
    calls.length = 0;
    g.window = { localStorage: { getItem: () => null, setItem() {}, removeItem() {} }, location: { pathname: "/", search: "", href: "" } };
    globalThis.fetch = (async (u: any, init: any) => {
      calls.push({ url: String(u), init });
      return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
    }) as typeof fetch;
  }

  it("reads the preview without writing", async () => {
    reply(200, { can_cancel: true, outcome: "full_refund" });
    const p = await getCancelPreview("b1");
    assert.equal(p.outcome, "full_refund");
    assert.match(calls[0].url, /\/bookings\/b1\/cancel-preview\/$/);
    assert.notEqual(calls[0].init?.method, "POST");
  });

  it("sends the forfeit acknowledgement only when asked", async () => {
    reply(200, { outcome: "fee_forfeited", status: "student_late_cancelled", message: "" });
    await cancelBooking("b1", { reason: "sick", acknowledgeForfeit: true });
    assert.deepEqual(JSON.parse(calls[0].init.body), { reason: "sick", acknowledge_forfeit: true });
    await cancelBooking("b1");
    assert.deepEqual(JSON.parse(calls[1].init.body), { reason: "", acknowledge_forfeit: false });
  });

  it("surfaces the machine-readable error code", async () => {
    reply(400, { error: "Confirm the forfeit", code: "acknowledgement_required" });
    await assert.rejects(cancelBooking("b1"), (err: unknown) => errorCode(err) === "acknowledgement_required");
    assert.equal(errorCode(new Error("x")), null);
  });

  it("reschedules by posting the new UTC start", async () => {
    reply(200, { id: "b1" });
    await rescheduleBooking("b1", "2026-10-09T08:00:00Z");
    assert.match(calls[0].url, /\/bookings\/b1\/reschedule\/$/);
    assert.deepEqual(JSON.parse(calls[0].init.body), { start_time_utc: "2026-10-09T08:00:00Z" });
  });

  it("lists and converts refunds", async () => {
    reply(200, { results: [{ id: "r1", status: "pending_gateway" }] });
    assert.equal((await listRefunds())[0].id, "r1");
    reply(200, { id: "r1", status: "converted" });
    assert.equal((await convertRefundToWallet("r1")).status, "converted");
    assert.match(calls[0].url, /\/refunds\/r1\/convert-to-wallet\/$/);
  });
});
