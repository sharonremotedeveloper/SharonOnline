import { afterEach, beforeEach, describe, it } from "node:test";
import assert from "node:assert/strict";
import { fetchVideoSessionToken, videoSessionProblem } from "./classroomSession";
import { ApiError } from "./http";

const realFetch = globalThis.fetch;
const g = globalThis as any;

beforeEach(() => {
  g.window = {
    localStorage: { getItem: () => null, setItem() {}, removeItem() {} },
    location: { pathname: "/", search: "", href: "" },
  };
});

afterEach(() => {
  globalThis.fetch = realFetch;
});

function answer(status: number, body: unknown) {
  globalThis.fetch = (async () =>
    new Response(JSON.stringify(body), {
      status,
      headers: { "content-type": "application/json" },
    })) as typeof fetch;
}

describe("fetchVideoSessionToken", () => {
  it("GETs the video-token endpoint with URL-encoded bookingId and returns valid token data", async () => {
    let capturedUrl = "";
    let capturedMethod = "";

    globalThis.fetch = (async (input: any, init?: RequestInit) => {
      capturedUrl = String(input);
      capturedMethod = init?.method ?? "GET";
      return new Response(
        JSON.stringify({
          token: "jwt-token-xyz-1234567890",
          session_name: "lesson-b-1",
          user_name: "Jane Tutor",
          expires_at: 1790000000,
        }),
        {
          status: 200,
          headers: { "content-type": "application/json" },
        }
      );
    }) as typeof fetch;

    const tokenData = await fetchVideoSessionToken("b-1");
    assert.match(capturedUrl, /\/bookings\/b-1\/video-token\/$/);
    assert.equal(capturedMethod, "GET");
    assert.equal(tokenData.token, "jwt-token-xyz-1234567890");
    assert.equal(tokenData.session_name, "lesson-b-1");
    assert.equal(tokenData.user_name, "Jane Tutor");
  });

  it("handles Daily.co token response carrying room_url and is_owner", async () => {
    globalThis.fetch = (async () => {
      return new Response(
        JSON.stringify({
          token: "daily-meeting-token-jwt",
          session_name: "sharon-lesson-room-1",
          user_name: "Teacher Sharon",
          expires_at: 1790005000,
          room_url: "https://sharon-online.daily.co/sharon-lesson-room-1",
          is_owner: true,
        }),
        { status: 200, headers: { "content-type": "application/json" } }
      );
    }) as typeof fetch;

    const data = await fetchVideoSessionToken("b-daily-1");
    assert.equal(data.room_url, "https://sharon-online.daily.co/sharon-lesson-room-1");
    assert.equal(data.is_owner, true);
    assert.equal(data.session_name, "sharon-lesson-room-1");
  });

  it("safely URL-encodes booking IDs containing special characters", async () => {
    let capturedUrl = "";
    globalThis.fetch = (async (input: any) => {
      capturedUrl = String(input);
      return new Response(
        JSON.stringify({
          token: "jwt-token",
          session_name: "lesson-test",
          user_name: "Student",
          expires_at: 1790000000,
        }),
        { status: 200, headers: { "content-type": "application/json" } }
      );
    }) as typeof fetch;

    await fetchVideoSessionToken("booking/with#symbols?1");
    assert.match(capturedUrl, /\/bookings\/booking%2Fwith%23symbols%3F1\/video-token\/$/);
  });

  it("throws 502 ApiError when token payload is missing or empty", async () => {
    answer(200, { token: "", session_name: "lesson-1" });
    await assert.rejects(
      fetchVideoSessionToken("b-empty"),
      (e: unknown) => e instanceof ApiError && e.status === 502
    );

    answer(200, { token: "abc", session_name: "" });
    await assert.rejects(
      fetchVideoSessionToken("b-no-session"),
      (e: unknown) => e instanceof ApiError && e.status === 502
    );
  });

  it("propagates 401 unauthenticated and 403 forbidden errors from the API", async () => {
    answer(401, { error: "Authentication credentials were not provided.", code: "not_authenticated" });
    await assert.rejects(
      fetchVideoSessionToken("b-unauth"),
      (e: unknown) => e instanceof ApiError && e.status === 401
    );

    answer(403, { error: "You are neither the tutor nor student.", code: "forbidden" });
    await assert.rejects(
      fetchVideoSessionToken("b-stranger"),
      (e: unknown) => e instanceof ApiError && e.status === 403
    );
  });
});

describe("videoSessionProblem", () => {
  const apiErr = (status: number, code?: string) => {
    return new ApiError(status, "API error", code ? { code } : null);
  };

  it("maps 409 outside_lesson_window to not_open with 15-minute guidance", () => {
    const p = videoSessionProblem(apiErr(409, "outside_lesson_window"));
    assert.equal(p.kind, "not_open");
    assert.match(p.message, /15 minutes/i);
  });

  it("maps 409 booking_cancelled to cancelled", () => {
    const p = videoSessionProblem(apiErr(409, "booking_cancelled"));
    assert.equal(p.kind, "cancelled");
    assert.match(p.message, /cancelled/i);
  });

  it("maps other 409 codes (e.g. classroom_unavailable) to ended", () => {
    const p = videoSessionProblem(apiErr(409, "classroom_unavailable"));
    assert.equal(p.kind, "ended");
    assert.match(p.message, /ended/i);
  });

  it("maps 403 forbidden to forbidden explaining permissions", () => {
    const p = videoSessionProblem(apiErr(403, "forbidden"));
    assert.equal(p.kind, "forbidden");
    assert.match(p.message, /assigned tutor or student/i);
  });

  it("maps 404 not found to other explaining booking not found", () => {
    const p = videoSessionProblem(apiErr(404, "not_found"));
    assert.equal(p.kind, "other");
    assert.match(p.message, /could not be found/i);
  });

  it("maps 503 service unavailable to unconfigured", () => {
    const p = videoSessionProblem(apiErr(503, "video_unconfigured"));
    assert.equal(p.kind, "unconfigured");
    assert.match(p.message, /video engine is currently being initialized/i);
  });

  it("maps network errors to retry", () => {
    const p = videoSessionProblem(apiErr(0));
    assert.equal(p.kind, "retry");
    assert.match(p.message, /network connection/i);
  });

  it("maps unexpected exceptions to other fallback", () => {
    const p = videoSessionProblem(new Error("Unexpected failure"));
    assert.equal(p.kind, "other");
    assert.match(p.message, /Could not join video session/i);
  });
});
