const PURCHASE_POLL_DELAYS_MS = [2_000, 4_000, 8_000, 15_000, 30_000] as const;
const MAX_RETRY_AFTER_MS = 60_000;

/** Backoff for authoritative payment status checks; never creates a tight loop. */
export function purchasePollDelayMs(attempt: number, retryAfterMs?: number, remainingMs = Number.POSITIVE_INFINITY): number {
  const deadline = Math.max(0, Math.floor(remainingMs));
  if (Number.isFinite(retryAfterMs) && retryAfterMs !== undefined) {
    return Math.min(Math.max(0, Math.round(retryAfterMs)), MAX_RETRY_AFTER_MS, deadline);
  }
  const index = Math.min(Math.max(0, Math.floor(attempt)), PURCHASE_POLL_DELAYS_MS.length - 1);
  return Math.min(PURCHASE_POLL_DELAYS_MS[index], deadline);
}

/** Parse DRF/HTTP Retry-After without trusting unbounded server-provided delays. */
export function retryAfterMs(value: string | undefined, nowMs = Date.now()): number | undefined {
  if (!value) return undefined;
  const seconds = Number(value.trim());
  if (Number.isFinite(seconds) && seconds >= 0) return seconds * 1_000;
  const dateMs = Date.parse(value);
  if (!Number.isFinite(dateMs)) return undefined;
  return Math.max(0, dateMs - nowMs);
}

export const PURCHASE_POLL_MAX_ATTEMPTS = 8;
export const PURCHASE_POLL_MAX_DURATION_MS = 120_000;
export const PURCHASE_POLL_FETCH_TIMEOUT_MS = 10_000;

export function purchasePollRemainingMs(startedAtMs: number, nowMs = Date.now()): number {
  return Math.max(0, PURCHASE_POLL_MAX_DURATION_MS - (nowMs - startedAtMs));
}
