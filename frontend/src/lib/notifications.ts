import { API_BASE, MOCK, liveRequest } from "./http";
import type { components } from "../types/api.generated";

export type NotificationItem = components["schemas"]["Notification"];
export type NotificationPreference = components["schemas"]["NotificationPreference"];
export type PaginatedNotificationList = components["schemas"]["PaginatedNotificationList"];
export type PatchedNotificationPreferenceRequest = components["schemas"]["PatchedNotificationPreferenceRequest"];

export interface NotificationCategoryInfo {
  label: string;
  iconName: "bell" | "calendar" | "alert" | "shield" | "coins" | "fileText";
  colorClass: string;
  bgClass: string;
}

/**
 * Maps backend notification kind to human label, category icon and theme colors.
 */
export function getNotificationCategoryInfo(kind: string): NotificationCategoryInfo {
  const normalized = (kind || "").toLowerCase();

  if (normalized.includes("memo")) {
    return {
      label: "Lesson Memo",
      iconName: "fileText",
      colorClass: "text-info",
      bgClass: "bg-info-surface text-info-hover border-info-border",
    };
  }

  if (normalized.includes("reminder") || normalized.includes("late")) {
    return {
      label: "Lesson Reminder",
      iconName: "bell",
      colorClass: "text-warning",
      bgClass: "bg-warning-surface text-warning-hover border-warning-border",
    };
  }

  if (normalized.includes("booking") || normalized.includes("lesson") || normalized.includes("reschedule")) {
    return {
      label: "Booking",
      iconName: "calendar",
      colorClass: "text-cocoa",
      bgClass: "bg-cocoa-50 text-cocoa-800 border-cocoa-200",
    };
  }

  if (normalized.includes("pay") || normalized.includes("credit") || normalized.includes("refund")) {
    return {
      label: "Billing & Credits",
      iconName: "coins",
      colorClass: "text-success",
      bgClass: "bg-success-surface text-success-hover border-success-border",
    };
  }

  if (normalized.includes("strike") || normalized.includes("suspend") || normalized.includes("alert") || normalized.includes("vetting")) {
    return {
      label: "Account Alert",
      iconName: "alert",
      colorClass: "text-error",
      bgClass: "bg-error-surface text-error-hover border-error-border",
    };
  }


  return {
    label: "Notification",
    iconName: "shield",
    colorClass: "text-cocoa-600",
    bgClass: "bg-cocoa-50 text-cocoa-800 border-cocoa-200",
  };
}

/**
 * Returns clean relative time string (e.g. "Just now", "5m ago", "3h ago", "2d ago").
 */
export function formatRelativeTime(dateString: string, now: Date = new Date()): string {
  if (!dateString) return "";
  const date = new Date(dateString);
  if (Number.isNaN(date.getTime())) return "";

  const diffMs = now.getTime() - date.getTime();
  if (diffMs < 0) return "Just now"; // future clock skew tolerance

  const diffSec = Math.floor(diffMs / 1000);
  if (diffSec < 60) return "Just now";

  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m ago`;

  const diffHours = Math.floor(diffMin / 60);
  if (diffHours < 24) return `${diffHours}h ago`;

  const diffDays = Math.floor(diffHours / 24);
  if (diffDays < 7) return `${diffDays}d ago`;

  const diffWeeks = Math.floor(diffDays / 7);
  if (diffWeeks < 4) return `${diffWeeks}w ago`;

  return date.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

/**
 * Formats unread count badge value. Returns null when count is 0 or negative.
 */
export function formatBadgeCount(unreadCount: number): string | null {
  if (!unreadCount || unreadCount <= 0) return null;
  if (unreadCount > 99) return "99+";
  return String(unreadCount);
}

/**
 * Resolves optional navigation URL from notification payload or booking reference.
 */
export function getNotificationActionUrl(notification: NotificationItem): string | null {
  if (!notification) return null;

  if (notification.payload && typeof notification.payload === "object") {
    const p = notification.payload as Record<string, unknown>;
    if (typeof p.classroom_url === "string" && p.classroom_url.startsWith("/")) {
      return p.classroom_url;
    }
    if (typeof p.action_url === "string" && p.action_url.startsWith("/")) {
      return p.action_url;
    }
  }

  if (notification.booking_id) {
    if (notification.kind.includes("teacher")) {
      return `/teacher/classroom/${notification.booking_id}`;
    }
    return `/student/classroom/${notification.booking_id}`;
  }

  return null;
}

// ==========================================
// API Operations
// ==========================================

export async function fetchNotifications(
  page: number = 1,
  pageSize: number = 20
): Promise<PaginatedNotificationList> {
  const query = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  });
  const live = await liveRequest(`${API_BASE}/notifications/?${query.toString()}`);
  if (live !== MOCK) return live as PaginatedNotificationList;

  return {
    count: 0,
    results: [],
  };
}

export async function fetchUnreadCount(): Promise<number> {
  const live = await liveRequest(`${API_BASE}/notifications/unread-count/`);
  if (live !== MOCK) {
    return Number((live as { count?: number })?.count ?? 0);
  }
  return 0;
}

export async function markNotificationRead(id: string): Promise<NotificationItem> {
  const live = await liveRequest(`${API_BASE}/notifications/${encodeURIComponent(id)}/read/`, {
    method: "POST",
  });
  if (live !== MOCK) return live as NotificationItem;

  return {
    id,
    kind: "general",
    title: "Notification",
    body: "",
    payload: null,
    booking_id: null,
    created_at: new Date().toISOString(),
    read_at: new Date().toISOString(),
    email_state: "sent",
    email_last_error: null,
  };
}

export async function markAllNotificationsRead(): Promise<{ updated: number }> {
  const live = await liveRequest(`${API_BASE}/notifications/read-all/`, {
    method: "POST",
  });
  if (live !== MOCK) return live as { updated: number };

  return { updated: 0 };
}

export async function fetchNotificationPreferences(): Promise<NotificationPreference> {
  const live = await liveRequest(`${API_BASE}/notifications/preferences/`);
  if (live !== MOCK) return live as NotificationPreference;

  return {
    email_by_kind: {},
    in_app_by_kind: {},
    updated_at: new Date().toISOString(),
  };
}

export async function updateNotificationPreferences(
  payload: PatchedNotificationPreferenceRequest
): Promise<NotificationPreference> {
  const live = await liveRequest(`${API_BASE}/notifications/preferences/`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (live !== MOCK) return live as NotificationPreference;

  return {
    email_by_kind: payload.email_by_kind || {},
    in_app_by_kind: payload.in_app_by_kind || {},
    updated_at: new Date().toISOString(),
  };
}
