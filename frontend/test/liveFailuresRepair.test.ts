import { describe, it } from "node:test";
import assert from "node:assert/strict";
import React from "react";
import { renderToString } from "react-dom/server";

// Import existing components & helpers to prove failure (RED)
import { VideoReelPlayer } from "../src/components/tutors/VideoReelPlayer";
import { AudioSnippetButton } from "../src/components/tutors/AudioSnippetButton";
import {
  classifyEskomProblem,
  isHistoricalLesson,
  formatRadarTelemetry,
  canCheckoutCurrency,
  canonicalMaterialLink,
  isPendingPayment,
} from "../src/lib/repairHelpers";
import { ApiError } from "../src/lib/http";
import { type FxRateRow } from "../src/lib/fx";
import type { StudentLessonItem } from "../src/types/student";
import type { LiveSessionRadarItem } from "../src/types/admin";

describe("Live Failures Repair Suite (F-01 through F-08)", () => {
  // ---------------------------------------------------------------------------
  // F-07: Tutor media pending/private/unavailable states (No fake URLs)
  // ---------------------------------------------------------------------------
  describe("F-07: Tutor Media States", () => {
    it("VideoReelPlayer does NOT inject mixkit.co demo video and shows truthful empty state when videoUrl is omitted", () => {
      const html = renderToString(
        React.createElement(VideoReelPlayer, {
          tutorName: "Charlotte Van Der Merwe",
          headline: "Warm, Encouraging Conversation Coach",
        })
      );

      // Must NOT contain external fabricated mixkit URL
      assert.ok(
        !html.includes("mixkit.co"),
        "VideoReelPlayer must not use fabricated mixkit.co fallback"
      );
      // Must show truthful unavailable/pending text
      assert.ok(
        html.includes("Video introduction unavailable") ||
          html.includes("Video introduction not available yet") ||
          html.includes("No video introduction"),
        "VideoReelPlayer must render a truthful unavailable message"
      );
    });

    it("AudioSnippetButton does NOT inject actions.google.com and renders disabled/unavailable state when audioUrl is missing", () => {
      const html = renderToString(
        React.createElement(AudioSnippetButton, {
          tutorName: "David Smith",
        })
      );

      // Must NOT contain external fabricated google actions sound URL
      assert.ok(
        !html.includes("actions.google.com"),
        "AudioSnippetButton must not use fabricated actions.google.com fallback"
      );
      // Must render unavailable state
      assert.ok(
        html.includes("Voice sample unavailable") ||
          html.includes("Voice unavailable") ||
          html.includes("disabled"),
        "AudioSnippetButton must render disabled/unavailable state when no audio URL provided"
      );
    });
  });

  // ---------------------------------------------------------------------------
  // F-01 & F-02: Materials canonical links (No broken freetalk-discussion links)
  // ---------------------------------------------------------------------------
  describe("F-01 & F-02: Materials Canonical Slugs", () => {
    it("canonicalMaterialLink returns null for placeholder freetalk-discussion slug or empty slugs", () => {
      assert.equal(canonicalMaterialLink("freetalk-discussion"), null);
      assert.equal(canonicalMaterialLink(""), null);
      assert.equal(canonicalMaterialLink(null as any), null);
      assert.equal(canonicalMaterialLink(undefined as any), null);
    });

    it("canonicalMaterialLink returns valid route for approved curriculum slugs", () => {
      assert.equal(
        canonicalMaterialLink("weekend-activities-and-hobbies"),
        "/materials/weekend-activities-and-hobbies"
      );
      assert.equal(
        canonicalMaterialLink("global-remote-work-trends-2026"),
        "/materials/global-remote-work-trends-2026"
      );
    });
  });

  // ---------------------------------------------------------------------------
  // F-03: Power Guard 409 & 503 classification
  // ---------------------------------------------------------------------------
  describe("F-03: Power Guard Status Handling", () => {
    it("classifyEskomProblem identifies 409 as area_not_configured with configuration guidance", () => {
      const err = new ApiError(409, "Area not configured", {
        code: "eskom_area_not_configured",
      });
      const problem = classifyEskomProblem(err);
      assert.equal(problem.kind, "area_not_configured");
      assert.ok(problem.actionable);
      assert.ok(problem.guidance.includes("profile"));
    });

    it("classifyEskomProblem identifies 503 as provider_unavailable without triggering fatal crash", () => {
      const err = new ApiError(503, "Eskom status unavailable", {
        code: "eskom_status_unavailable",
        area_id: "jhb-block-3",
        provider_status: "unavailable",
      });
      const problem = classifyEskomProblem(err);
      assert.equal(problem.kind, "provider_unavailable");
      assert.equal(problem.areaId, "jhb-block-3");
      assert.ok(problem.retryable);
    });
  });

  // ---------------------------------------------------------------------------
  // F-04: Student Schedule & History state authority
  // ---------------------------------------------------------------------------
  describe("F-04: Student Schedule & History Authority", () => {
    const baseLesson: StudentLessonItem = {
      id: "les-1",
      booking_reference: "BK-001",
      teacher: {
        id: "tut-1",
        name: "Naledi Molefe",
        avatar: "/avatar.jpg",
        accent: "South African",
      },
      start_time_utc: "2026-10-01T10:00:00Z",
      end_time_utc: "2026-10-01T10:25:00Z",
      local_date: "Oct 01, 2026",
      local_start_time: "10:00",
      local_end_time: "10:25",
      viewer_timezone: "Asia/Tokyo",
      material_title: "FreeTalk",
      material_cefr: "B2",
      material_slug: "freetalk-discussion",
      status: "pending_payment",
      zoom_url: "",
      memo: null,
      review: null,
    };

    it("isHistoricalLesson excludes pending_payment and in_progress lessons from history list", () => {
      assert.equal(
        isHistoricalLesson({ ...baseLesson, status: "pending_payment" }),
        false,
        "pending_payment is not a finished historical lesson"
      );
      assert.equal(
        isHistoricalLesson({ ...baseLesson, status: "in_progress" }),
        false,
        "in_progress is currently happening, not history"
      );
      assert.equal(
        isHistoricalLesson({ ...baseLesson, status: "completed" }),
        true
      );
      assert.equal(
        isHistoricalLesson({ ...baseLesson, status: "interrupted_power" }),
        true
      );
      assert.equal(
        isHistoricalLesson({ ...baseLesson, status: "cancelled_by_student" }),
        true
      );
      assert.equal(
        isHistoricalLesson({ ...baseLesson, status: "disputed" }),
        true
      );
    });

    it("isPendingPayment detects pending_payment bookings correctly", () => {
      assert.equal(
        isPendingPayment({ ...baseLesson, status: "pending_payment" }),
        true
      );
      assert.equal(
        isPendingPayment({ ...baseLesson, status: "confirmed" }),
        false
      );
    });

    it("StudentScheduleCard renders Cancelled for past cancelled lesson, not Completed", async () => {
      // Import StudentScheduleCard dynamically or directly once created
      const { StudentScheduleCard } = await import("../src/components/student/StudentScheduleCard");
      const pastCancelled: StudentLessonItem = {
        ...baseLesson,
        status: "cancelled_by_student",
        end_time_utc: "2026-10-01T10:25:00Z", // In the past
      };

      const html = renderToString(
        React.createElement(StudentScheduleCard, {
          lesson: pastCancelled,
          now: Date.parse("2026-10-05T12:00:00Z"), // well after end_time_utc
        })
      );

      assert.ok(!html.includes("Completed"), "Past cancelled lesson must NEVER be labelled Completed");
      assert.ok(html.includes("Cancelled"), "Must display Cancelled status badge");
      assert.ok(!html.includes("Add to Google Calendar"), "Cancelled lesson must not offer Google Calendar");
    });

    it("StudentScheduleCard renders Complete Checkout for pending_payment and NOT Add to Google Calendar", async () => {
      const { StudentScheduleCard } = await import("../src/components/student/StudentScheduleCard");
      const upcomingPending: StudentLessonItem = {
        ...baseLesson,
        status: "pending_payment",
        start_time_utc: "2026-10-20T10:00:00Z",
        end_time_utc: "2026-10-20T10:25:00Z",
      };

      const html = renderToString(
        React.createElement(StudentScheduleCard, {
          lesson: upcomingPending,
          now: Date.parse("2026-10-05T12:00:00Z"),
        })
      );

      assert.ok(html.includes("Complete Checkout") || html.includes("Pay to Confirm"), "Must provide checkout action");
      assert.ok(!html.includes("Add to Google Calendar"), "Unpaid pending lesson must not offer Google Calendar sync");
    });
  });

  // ---------------------------------------------------------------------------
  // F-05: Attendance duration integrity in live radar
  // ---------------------------------------------------------------------------
  describe("F-05: Live Session Radar Duration Bounds", () => {
    it("formatRadarTelemetry caps elapsed minutes and flags anomalies when dwell exceeds 25 minutes", () => {
      const normalSession: LiveSessionRadarItem = {
        id: "b1",
        booking_ref: "BK-001",
        teacher_name: "Naledi",
        student_name: "Aiko",
        zoom_meeting_id: "123456",
        material_title: "Daily News",
        elapsed_minutes: 15,
        start_time_utc: "2026-10-06T15:00:00Z",
        teacher_joined_at: "2026-10-06T15:00:00Z",
        student_joined_at: "2026-10-06T15:01:00Z",
        status: "active",
      };

      const normalTele = formatRadarTelemetry(normalSession);
      assert.equal(normalTele.displayElapsed, 15);
      assert.equal(normalTele.isAnomaly, false);
      assert.equal(normalTele.statusLabel, "Active Class (15m/25m)");

      const anomalySession: LiveSessionRadarItem = {
        ...normalSession,
        elapsed_minutes: 1136,
      };

      const anomalyTele = formatRadarTelemetry(anomalySession);
      // Elapsed must be capped or explicitly flagged
      assert.equal(anomalyTele.isAnomaly, true);
      assert.ok(
        anomalyTele.statusLabel.includes("Overdue") ||
          anomalyTele.statusLabel.includes("Anomaly") ||
          anomalyTele.statusLabel.includes("Review"),
        "Must flag >25min telemetry as anomaly rather than reporting normal Active Class"
      );
      assert.equal(anomalyTele.progressPercent, 100);
    });
  });

  // ---------------------------------------------------------------------------
  // F-06: FX freshness and checkout blocking
  // ---------------------------------------------------------------------------
  describe("F-06: FX Freshness and Checkout Guard", () => {
    it("canCheckoutCurrency blocks checkout when rate is missing or stale", () => {
      const staleRate: FxRateRow = {
        id: 1,
        currency: "EUR",
        rate_to_zar: "20.15",
        valid_from: new Date(Date.now() - 48 * 3600 * 1000).toISOString(),
        source: "admin",
        set_by: "admin",
        age_hours: 48,
        stale: true,
      };

      const rates = [staleRate];

      const eurCheck = canCheckoutCurrency("EUR", rates);
      assert.equal(eurCheck.allowed, false);
      assert.ok(eurCheck.reason?.includes("EUR"));
      assert.ok(
        eurCheck.reason?.includes("unavailable") ||
          eurCheck.reason?.includes("stale")
      );

      const jpyCheck = canCheckoutCurrency("JPY", rates);
      assert.equal(jpyCheck.allowed, false);
      assert.ok(jpyCheck.reason?.includes("JPY"));

      const usdCheck = canCheckoutCurrency("USD", rates);
      // USD is base platform currency and does not require FX conversion to ZAR for PayPal
      assert.equal(usdCheck.allowed, true);
    });
  });

  // ---------------------------------------------------------------------------
  // F-08: Availability Grid and Saved Windows Alignment
  // ---------------------------------------------------------------------------
  describe("F-08: Availability Grid Alignment", () => {
    it("wouldChangeSavedWindows detects alignment when windows match hourly blocks", async () => {
      const { wouldChangeSavedWindows } = await import("../src/lib/availability");
      type AvRow = import("../src/lib/availability").AvailabilityRow;

      // Canonical aligned windows (skipping 12:00-13:00 break)
      const alignedRows: AvRow[] = [
        { day_of_week: 0, start_time: "08:00:00", end_time: "12:00:00", is_active: true },
        { day_of_week: 0, start_time: "13:00:00", end_time: "18:00:00", is_active: true },
      ];
      assert.equal(wouldChangeSavedWindows(alignedRows), false, "Aligned windows must not trigger warning");

      // Spanning across 12:00-13:00 break or off-grid
      const unalignedRows: AvRow[] = [
        { day_of_week: 0, start_time: "08:00:00", end_time: "18:00:00", is_active: true },
      ];
      assert.equal(wouldChangeSavedWindows(unalignedRows), true, "Continuous 08:00-18:00 window across lunch gap must detect change");
    });
  });
});
