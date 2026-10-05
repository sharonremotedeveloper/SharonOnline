/**
 * Zoom host link for the tutor's classroom (Slice Z1). The host start link embeds an expiring token, so the server never
 * stores or lists it: `GET /bookings/<id>/host-link/` fetches a FRESH one when the tutor presses "Start lesson". The link is
 * used at once (opened in a new tab) and never kept in state, storage or logs. Failures THROW an ApiError.
 */
import { ApiError, request } from "./http";
import { errorCode } from "./bookings";

export interface HostLink {
  meeting_id: string;
  start_url: string;
}

/** Only an https Zoom address may ever be opened as the host link. */
export function isSafeZoomUrl(url: string): boolean {
  try {
    const u = new URL(url);
    const host = u.hostname.toLowerCase();
    return u.protocol === "https:" && (host === "zoom.us" || host.endsWith(".zoom.us") || host === "zoomgov.com" || host.endsWith(".zoomgov.com"));
  } catch {
    return false;
  }
}

export async function fetchHostLink(bookingId: string): Promise<HostLink> {
  const link = await request<HostLink>(`/bookings/${encodeURIComponent(bookingId)}/host-link/`);
  if (!link || typeof link.start_url !== "string" || !isSafeZoomUrl(link.start_url)) {
    throw new ApiError(502, "The server returned an invalid host link", null);
  }
  return link;
}

export type HostLinkProblemKind = "not_open" | "ended" | "no_room" | "retry" | "forbidden" | "other";

export interface HostLinkProblem {
  kind: HostLinkProblemKind;
  /** Safe to show: never the raw server text. */
  message: string;
}

/** What went wrong and what the tutor can do about it. */
export function hostLinkProblem(err: unknown): HostLinkProblem {
  const status = err instanceof ApiError ? err.status : null;
  const code = errorCode(err);
  if (status === 409) {
    if (code === "too_early") {
      return { kind: "not_open", message: "The classroom is not open yet. You can start the lesson a few minutes before it begins." };
    }
    if (code === "lesson_ended" || code === "not_live") {
      return { kind: "ended", message: "This lesson is no longer open, so it cannot be started." };
    }
    return { kind: "no_room", message: "The Zoom room for this lesson is not available. Please contact support." };
  }
  if (status === 403 || status === 404) {
    return { kind: "forbidden", message: "Only the tutor of this lesson can start it as host." };
  }
  if (err instanceof ApiError && err.isNetworkError) {
    return { kind: "retry", message: "We could not reach Zoom just now. Please try again in a moment." };
  }
  return { kind: "other", message: "We could not start the lesson. Please try again, or contact support if it keeps happening." };
}
