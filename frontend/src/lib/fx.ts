/**
 * Admin FX rate table helpers (Task 10.1d). Rates are decimal STRINGS end to end (6 decimal places on the server);
 * nothing here ever parses a rate to a float.
 */
import { ApiError } from "./http";

export type FxCurrency = "EUR" | "JPY";
export const FX_CURRENCIES: readonly FxCurrency[] = ["EUR", "JPY"];

export interface FxRateRow {
  id: number | null;
  currency: FxCurrency;
  /** Decimal string ("19.850000") or null when no rate has ever been set. */
  rate_to_zar: string | null;
  source: string | null;
  valid_from: string | null;
  set_by: string | null;
  age_hours: number | null;
  stale: boolean;
}

export interface FxRatesResponse {
  max_age_hours: number;
  current: FxRateRow[];
  history: FxRateRow[];
}

const RATE_PLACES = 6;
const RATE_INT_DIGITS = 6; // NUMERIC(12, 6)
const POSITIVE_DECIMAL = /^(\d+)(?:\.(\d+))?$/;

export type RateValidation = { ok: true; rate: string } | { ok: false; message: string };

/** Validate admin input as a positive decimal string the server can store exactly. Returns it trimmed, unchanged. */
export function validateRateInput(input: string): RateValidation {
  const value = (input ?? "").trim();
  if (!value) return { ok: false, message: "Enter a rate." };
  const m = POSITIVE_DECIMAL.exec(value);
  if (!m) return { ok: false, message: "Enter a positive number such as 19.85 (digits and one decimal point only)." };
  if (!/[1-9]/.test(value)) return { ok: false, message: "The rate must be greater than zero." };
  if (m[1].replace(/^0+(?=\d)/, "").length > RATE_INT_DIGITS) {
    return { ok: false, message: `The rate is too large (at most ${RATE_INT_DIGITS} digits before the decimal point).` };
  }
  if ((m[2] ?? "").length > RATE_PLACES) {
    return { ok: false, message: `Use at most ${RATE_PLACES} decimal places.` };
  }
  return { ok: true, rate: value };
}

export type FxStatus = "ok" | "stale" | "missing";

export function fxStatus(row: Pick<FxRateRow, "rate_to_zar" | "stale">): FxStatus {
  if (row.rate_to_zar === null) return "missing";
  return row.stale ? "stale" : "ok";
}

/** Currencies whose current rate is stale or missing (checkout in these currencies is blocked). */
export function blockedCurrencies(rows: readonly FxRateRow[] | null | undefined): FxCurrency[] {
  return (rows ?? []).filter((r) => fxStatus(r) !== "ok").map((r) => r.currency);
}

/** True when the server asked the admin to confirm a large rate move (HTTP 409, code confirmation_required). */
export function isConfirmationRequired(err: unknown): err is ApiError {
  if (!(err instanceof ApiError) || err.status !== 409) return false;
  const body = err.body as { code?: unknown } | null;
  return !!body && typeof body === "object" && body.code === "confirmation_required";
}

/** The explicit `currency` a PayPal lesson checkout must send: only EUR/JPY (USD is the server default). */
export function paypalCheckoutCurrency(display: string): FxCurrency | undefined {
  return display === "EUR" || display === "JPY" ? display : undefined;
}

/**
 * Message for a failed checkout start. A 503 means the EUR/JPY rate is stale or missing: show the server's own
 * explanation and offer USD, instead of the generic "server hit a problem" text.
 */
export function checkoutFailureMessage(err: unknown, genericMessage: string): string {
  if (err instanceof ApiError && err.status === 503) {
    const detail =
      err.message && !err.message.startsWith("Request failed") ? err.message : "This currency is temporarily unavailable.";
    return `${detail} Please pay in USD instead, or try again later.`;
  }
  return genericMessage;
}
