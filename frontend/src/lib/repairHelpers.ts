import { ApiError } from "./http";
import { fxStatus, type FxCurrency, type FxRateRow } from "./fx";

// -----------------------------------------------------------------------------
// F-01 & F-02: Materials Canonical Links
// -----------------------------------------------------------------------------

/**
 * Returns the canonical router path for a curriculum material, or null if
 * the lesson was FreeTalk/unassigned or uses the placeholder 'freetalk-discussion' slug.
 */
export function canonicalMaterialLink(slug?: string | null): string | null {
  if (!slug || typeof slug !== "string") return null;
  const trimmed = slug.trim();
  if (!trimmed || trimmed === "freetalk-discussion") return null;
  return `/materials/${encodeURIComponent(trimmed)}`;
}

// -----------------------------------------------------------------------------
// F-03: Power Guard Problem Classification
// -----------------------------------------------------------------------------

export interface EskomProblem {
  kind: "area_not_configured" | "provider_unavailable" | "unauthorized" | "unknown";
  areaId?: string;
  message: string;
  guidance: string;
  actionable: boolean;
  retryable: boolean;
}

export function classifyEskomProblem(err: unknown): EskomProblem {
  if (err instanceof ApiError) {
    if (err.status === 409) {
      return {
        kind: "area_not_configured",
        message: "Your Eskom load-shedding area is not configured.",
        guidance: "Please set your suburb or block in your profile settings to enable automated outage monitoring.",
        actionable: true,
        retryable: false,
      };
    }
    if (err.status === 503) {
      const body = err.body as { code?: string; area_id?: string; provider_status?: string } | null;
      const areaId = body?.area_id;
      return {
        kind: "provider_unavailable",
        areaId,
        message: "Eskom load-shedding telemetry is currently unavailable.",
        guidance: areaId
          ? `Outage data provider is unreachable for area ${areaId}. Manual retry is available.`
          : "The grid status provider is unreachable. Please retry shortly.",
        actionable: false,
        retryable: true,
      };
    }
    if (err.status === 401 || err.status === 403) {
      return {
        kind: "unauthorized",
        message: "You must be signed in as a tutor to view Power Guard.",
        guidance: "Tutor authentication required.",
        actionable: false,
        retryable: false,
      };
    }
  }

  return {
    kind: "unknown",
    message: err instanceof Error ? err.message : "Unable to retrieve Eskom status.",
    guidance: "An unexpected error occurred while loading power status.",
    actionable: false,
    retryable: true,
  };
}

// -----------------------------------------------------------------------------
// F-04: Student Schedule & History Authority
// -----------------------------------------------------------------------------

const UNFINISHED_STATUSES = new Set(["pending_payment", "in_progress"]);

/**
 * Returns true if the lesson represents an archived/past event that belongs
 * in student history (completed, cancelled, power interrupted, disputed, or no-show).
 * Excludes pending payment and in-progress live sessions.
 */
export function isHistoricalLesson(lesson: { status: string }): boolean {
  return !UNFINISHED_STATUSES.has(lesson.status);
}

/**
 * Returns true if the booking is awaiting student checkout/payment.
 */
export function isPendingPayment(lesson: { status: string }): boolean {
  return lesson.status === "pending_payment";
}

// -----------------------------------------------------------------------------
// F-05: Attendance Duration Bounds in Live Radar
// -----------------------------------------------------------------------------

export interface RadarTelemetry {
  displayElapsed: number;
  displayMinutes: string;
  progressPercent: number;
  isAnomaly: boolean;
  isOverdue: boolean;
  badgeText: string | null;
  statusLabel: string;
}

export function formatRadarTelemetry(
  session: { elapsed_minutes: number; status?: string },
  lessonDurationMinutes: number = 25
): RadarTelemetry {
  const rawElapsed = session.elapsed_minutes || 0;
  const isOverdue = rawElapsed > lessonDurationMinutes;
  const isAnomaly = rawElapsed > lessonDurationMinutes + 5; // e.g. >30 minutes for a 25-minute lesson
  const displayMinutes = `${Math.min(lessonDurationMinutes, rawElapsed)} / ${lessonDurationMinutes} mins`;

  const badgeText = isAnomaly
    ? "Overdue Telemetry · Anomaly Review Required"
    : isOverdue
    ? "Overdue Telemetry · Review Required"
    : null;

  if (isAnomaly) {
    return {
      displayElapsed: rawElapsed,
      displayMinutes,
      progressPercent: 100,
      isAnomaly: true,
      isOverdue: true,
      badgeText,
      statusLabel: `Overdue Telemetry (${rawElapsed}m / ${lessonDurationMinutes}m) · Review Required`,
    };
  }

  const isWrapUp = session.status === "wrap_up" || rawElapsed >= 20;
  const isStaging = session.status === "staging";

  const statusLabel = isOverdue
    ? `Overdue (${rawElapsed}m)`
    : isWrapUp
    ? `Wrapping Up (${rawElapsed}m/${lessonDurationMinutes}m)`
    : isStaging
    ? "Staging Room"
    : `Active Class (${rawElapsed}m/${lessonDurationMinutes}m)`;

  return {
    displayElapsed: rawElapsed,
    displayMinutes,
    progressPercent: Math.min(100, (rawElapsed / lessonDurationMinutes) * 100),
    isAnomaly: false,
    isOverdue,
    badgeText,
    statusLabel,
  };
}

// -----------------------------------------------------------------------------
// F-06: FX Freshness and Checkout Blocking
// -----------------------------------------------------------------------------

export interface CheckoutCurrencyCheck {
  allowed: boolean;
  reason?: string;
}

export function canCheckoutCurrency(
  currency: string,
  rates?: readonly FxRateRow[] | null
): CheckoutCurrencyCheck {
  if (currency === "USD") {
    return { allowed: true };
  }

  if (currency === "EUR" || currency === "JPY") {
    const row = rates?.find((r) => r.currency === (currency as FxCurrency));
    if (!row) {
      return {
        allowed: false,
        reason: `Checkout in ${currency} is currently unavailable because the exchange rate has not been configured.`,
      };
    }
    const status = fxStatus(row);
    if (status === "missing") {
      return {
        allowed: false,
        reason: `Checkout in ${currency} is currently unavailable because exchange rates are missing.`,
      };
    }
    if (status === "stale") {
      return {
        allowed: false,
        reason: `Checkout in ${currency} is temporarily disabled because the exchange rate is stale and awaiting update.`,
      };
    }
    return { allowed: true };
  }

  // Other currencies not directly supported for PayPal capture
  return {
    allowed: false,
    reason: `Checkout in ${currency} is not supported. Please pay in USD or ZAR.`,
  };
}
