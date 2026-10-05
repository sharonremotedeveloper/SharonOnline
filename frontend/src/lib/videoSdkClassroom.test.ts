import { afterEach, beforeEach, describe, it } from "node:test";
import assert from "node:assert/strict";
import React from "react";
import { renderToString } from "react-dom/server";
import { VideoSdkClassroom } from "../components/classroom/VideoSdkClassroom";
import { videoSessionProblem } from "./videoSdk";
import { ApiError } from "./http";

const realFetch = globalThis.fetch;
const g = globalThis as any;

beforeEach(() => {
  g.window = {
    localStorage: { getItem: () => null, setItem() {}, removeItem() {} },
    location: { pathname: "/", search: "", href: "", origin: "http://localhost:3000" },
  };
});

afterEach(() => {
  globalThis.fetch = realFetch;
});

describe("VideoSdkClassroom component", () => {
  it("renders student pre-join staging with Enter Classroom button and partner name", () => {
    const html = renderToString(
      React.createElement(VideoSdkClassroom, {
        bookingId: "booking-student-1",
        isHost: false,
        partnerName: "Jane Tutor",
      })
    );

    assert.ok(html.includes("Live Synchronous Classroom"));
    assert.ok(html.includes("Jane Tutor"));
    assert.ok(html.includes("Enter Classroom"));
    assert.ok(html.includes("In-Browser Classroom"));
    assert.ok(html.includes("Device Settings"));
    // Legacy Zoom app launcher should NOT appear when legacyJoinUrl is omitted
    assert.ok(!html.includes("Launch in Zoom App"));
  });

  it("renders tutor pre-join staging with Open Classroom as Host button", () => {
    const html = renderToString(
      React.createElement(VideoSdkClassroom, {
        bookingId: "booking-tutor-1",
        isHost: true,
        partnerName: "Sam Student",
      })
    );

    assert.ok(html.includes("Sam Student"));
    assert.ok(html.includes("Open Classroom as Host"));
    assert.ok(!html.includes("Enter Classroom"));
    assert.ok(html.includes("Device Settings"));
  });

  it("renders legacy Zoom app button when legacyJoinUrl is provided", () => {
    const legacyUrl = "https://zoom.us/j/9876543210?pwd=testpassword";
    const html = renderToString(
      React.createElement(VideoSdkClassroom, {
        bookingId: "booking-legacy-1",
        isHost: false,
        partnerName: "Jane Tutor",
        legacyJoinUrl: legacyUrl,
      })
    );

    assert.ok(html.includes("Launch in Zoom App"));
    assert.ok(html.includes(legacyUrl));
  });

  it("formats the 'too early' outside-lesson-window error with 15-minute guidance", () => {
    const err = new ApiError(409, "Lesson window not open", { code: "outside_lesson_window" });
    const problem = videoSessionProblem(err);

    assert.equal(problem.kind, "not_open");
    assert.ok(problem.message.includes("15 minutes"));
  });

  it("formats the cancelled booking error clearly", () => {
    const err = new ApiError(409, "Lesson cancelled", { code: "booking_cancelled" });
    const problem = videoSessionProblem(err);

    assert.equal(problem.kind, "cancelled");
    assert.ok(problem.message.toLowerCase().includes("cancelled"));
  });

  it("formats the forbidden error for non-party users", () => {
    const err = new ApiError(403, "Forbidden", { code: "forbidden" });
    const problem = videoSessionProblem(err);

    assert.equal(problem.kind, "forbidden");
    assert.ok(problem.message.includes("assigned tutor or student"));
  });

  it("includes responsive styling classes for mobile and desktop screens", () => {
    const html = renderToString(
      React.createElement(VideoSdkClassroom, {
        bookingId: "booking-responsive-1",
        isHost: false,
        partnerName: "Teacher Maria",
      })
    );

    // Responsive padding and layout classes
    assert.ok(html.includes("sm:p-8"));
    assert.ok(html.includes("sm:w-auto"));
    assert.ok(html.includes("sm:flex-row"));
  });
});
