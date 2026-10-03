/**
 * Remembers WHAT the student was paying for before the browser leaves for PayFast, so the return page can look the
 * booking / credit purchase up and show its real (server) status. The PayFast return URL carries only an opaque
 * transaction reference and no API resolves it, and a "return" visit proves nothing about payment: this is a lookup
 * hint only, never evidence of payment. Storage may be unavailable (private mode): everything degrades to null.
 */
export type PendingPayFast = { kind: "booking" | "credit_purchase"; id: string };

const KEY = "sharon_pending_payfast";

export function parsePendingPayFast(raw: string | null): PendingPayFast | null {
  if (!raw) return null;
  try {
    const v = JSON.parse(raw) as Partial<PendingPayFast> | null;
    if (v && (v.kind === "booking" || v.kind === "credit_purchase") && typeof v.id === "string" && v.id.length > 0) {
      return { kind: v.kind, id: v.id };
    }
  } catch {
    // fall through
  }
  return null;
}

export function rememberPendingPayFast(value: PendingPayFast): void {
  try {
    window.sessionStorage.setItem(KEY, JSON.stringify(value));
  } catch {
    // Storage blocked: the return page falls back to a generic message.
  }
}

export function readPendingPayFast(): PendingPayFast | null {
  try {
    return parsePendingPayFast(window.sessionStorage.getItem(KEY));
  } catch {
    return null;
  }
}

export function clearPendingPayFast(): void {
  try {
    window.sessionStorage.removeItem(KEY);
  } catch {
    // ignore
  }
}
