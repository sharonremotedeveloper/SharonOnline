import { afterEach, beforeEach, describe, it } from "node:test";
import assert from "node:assert/strict";

const g = globalThis as any;
let href = "";
const calls: { url: string; init: any }[] = [];
const realFetch = globalThis.fetch;

beforeEach(() => {
  href = "";
  calls.length = 0;
  g.window = { localStorage: { getItem: () => null, setItem() {}, removeItem() {} }, location: { pathname: "/student/profile", search: "", get href() { return href; }, set href(v: string) { href = v; } } };
});
afterEach(() => {
  globalThis.fetch = realFetch;
});

function respond(status: number, body: unknown) {
  globalThis.fetch = (async (url: any, init: any) => {
    calls.push({ url: String(url), init });
    return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
  }) as any;
}
const account = () => require("./account") as typeof import("./account");

describe("account API helpers", () => {
  it("send the documented bodies to the documented endpoints (slash-less for the proxy)", async () => {
    respond(202, {});
    await account().requestPasswordReset("a@b.co");
    respond(200, {});
    await account().confirmPasswordReset({ uid: "u", token: "t", new_password: "p", new_password_confirm: "p" });
    await account().confirmEmail("tok");
    assert.deepEqual(calls.map((c) => c.url), ["/api/proxy/auth/password-reset", "/api/proxy/auth/password-reset/confirm", "/api/proxy/auth/verify-email/confirm"]);
    assert.deepEqual(JSON.parse(calls[0].init.body), { email: "a@b.co" });
    assert.deepEqual(JSON.parse(calls[2].init.body), { token: "tok" });
  });

  it("anonymous calls treat a 401 as an answer: no redirect to /login", async () => {
    respond(401, { detail: "x" });
    await assert.rejects(() => account().confirmEmail("tok"));
    await assert.rejects(() => account().requestPasswordReset("a@b.co"));
    assert.equal(href, "");
  });

  it("signed-in calls (change password, resend) end the session on 401", async () => {
    respond(401, { detail: "expired" });
    await assert.rejects(() => account().changePassword({ old_password: "a", new_password: "b", new_password_confirm: "b" }));
    assert.match(href, /^\/login\?next=/);
  });

  it("surface DRF field errors so forms can show them", async () => {
    respond(400, { new_password: ["This password is too common."] });
    const err: any = await account().changePassword({ old_password: "a", new_password: "b", new_password_confirm: "b" }).catch((e) => e);
    assert.deepEqual(err.fieldErrors.new_password, ["This password is too common."]);
  });
});
