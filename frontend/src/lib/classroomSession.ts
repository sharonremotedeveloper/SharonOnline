/**
 * Classroom session helper: fetches the ephemeral Daily.co meeting token from GET /api/v1/bookings/<id>/video-token/
 * for the in-browser classroom.
 */
import { ApiError, request } from "./http";
import { errorCode } from "./bookings";

export interface VideoSessionToken {
  token: string;
  session_name: string;
  user_name: string;
  expires_at: number;
  room_url?: string;
  is_owner?: boolean;
}

export async function fetchVideoSessionToken(bookingId: string): Promise<VideoSessionToken> {
  const data = await request<VideoSessionToken>(`/bookings/${encodeURIComponent(bookingId)}/video-token/`);
  if (!data || !data.token || !data.session_name) {
    throw new ApiError(502, "The server returned an invalid video session token", null);
  }
  return data;
}

export type VideoSessionProblemKind =
  | "not_open"
  | "ended"
  | "cancelled"
  | "forbidden"
  | "unconfigured"
  | "retry"
  | "other";

export interface VideoSessionProblem {
  kind: VideoSessionProblemKind;
  message: string;
}

export function videoSessionProblem(err: unknown): VideoSessionProblem {
  const status = err instanceof ApiError ? err.status : null;
  const code = errorCode(err);

  if (status === 409) {
    if (code === "outside_trial_window") {
      return { kind: "not_open", message: "This video trial is not open. Check its scheduled time with the organizer." };
    }
    if (code === "outside_lesson_window") {
      return {
        kind: "not_open",
        message: "The classroom is not open yet. It opens 15 minutes before the lesson starts.",
      };
    }
    if (code === "booking_cancelled") {
      return { kind: "cancelled", message: "This lesson has been cancelled." };
    }
    return { kind: "ended", message: "This lesson's video session has ended." };
  }

  if (status === 403) {
    return { kind: "forbidden", message: "Only the assigned tutor or student can enter this live classroom." };
  }

  if (status === 404) {
    return { kind: "other", message: "This classroom could not be found, or your account was not invited." };
  }

  if (status === 503) {
    return {
      kind: "unconfigured",
      message: "The in-platform video engine is currently being initialized. Please contact support.",
    };
  }

  if (err instanceof ApiError && err.isNetworkError) {
    return { kind: "retry", message: "Network connection lost. Please check your internet connection." };
  }

  return { kind: "other", message: "Could not join video session. Please try again or refresh the page." };
}
