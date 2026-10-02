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
