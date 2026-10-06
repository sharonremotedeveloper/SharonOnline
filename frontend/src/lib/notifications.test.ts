import { afterEach, beforeEach, describe, it } from "node:test";
import assert from "node:assert/strict";
import React from "react";
import { renderToString } from "react-dom/server";
import {
  formatBadgeCount,
  formatRelativeTime,
  getNotificationActionUrl,
  getNotificationCategoryInfo,
  type NotificationItem,
} from "./notifications";
import { NotificationDrawer } from "../components/notifications/NotificationDrawer";
import { NotificationPreferencesModal } from "../components/notifications/NotificationPreferencesModal";

const realFetch = globalThis.fetch;
const g = globalThis as any;

beforeEach(() => {
  g.window = {
    localStorage: { getItem: () => null, setItem() {}, removeItem() {} },
    location: { pathname: "/", search: "", href: "", origin: "http://localhost:3000" },
    addEventListener() {},
    removeEventListener() {},
  };
  g.document = {
    visibilityState: "visible",
    addEventListener() {},
    removeEventListener() {},
  };
});

afterEach(() => {
  globalThis.fetch = realFetch;
});

describe("notifications helpers", () => {
  it("formats relative time correctly", () => {
    const now = new Date("2026-10-06T12:00:00Z");

    assert.equal(formatRelativeTime("2026-10-06T11:59:30Z", now), "Just now");
    assert.equal(formatRelativeTime("2026-10-06T11:55:00Z", now), "5m ago");
    assert.equal(formatRelativeTime("2026-10-06T09:00:00Z", now), "3h ago");
    assert.equal(formatRelativeTime("2026-10-04T12:00:00Z", now), "2d ago");
    assert.equal(formatRelativeTime("2026-09-22T12:00:00Z", now), "2w ago");
    assert.equal(formatRelativeTime("", now), "");
    assert.equal(formatRelativeTime("invalid-date", now), "");
  });

  it("formats unread badge count with 99+ cap", () => {
    assert.equal(formatBadgeCount(0), null);
    assert.equal(formatBadgeCount(-1), null);
    assert.equal(formatBadgeCount(1), "1");
    assert.equal(formatBadgeCount(42), "42");
    assert.equal(formatBadgeCount(99), "99");
    assert.equal(formatBadgeCount(100), "99+");
    assert.equal(formatBadgeCount(250), "99+");
  });

  it("categorizes notifications by kind", () => {
    const reminder = getNotificationCategoryInfo("lesson_reminder_t10m");
    assert.equal(reminder.label, "Lesson Reminder");
    assert.equal(reminder.iconName, "bell");

    const booking = getNotificationCategoryInfo("booking_confirmed");
    assert.equal(booking.label, "Booking");
    assert.equal(booking.iconName, "calendar");

    const credit = getNotificationCategoryInfo("credit_granted");
    assert.equal(credit.label, "Billing & Credits");
    assert.equal(credit.iconName, "coins");

    const alert = getNotificationCategoryInfo("tutor_strike_warning");
    assert.equal(alert.label, "Account Alert");
    assert.equal(alert.iconName, "alert");

    const memo = getNotificationCategoryInfo("memo_reminder");
    assert.equal(memo.label, "Lesson Memo");
    assert.equal(memo.iconName, "fileText");

    const unknown = getNotificationCategoryInfo("custom_system_ping");
    assert.equal(unknown.label, "Notification");
    assert.equal(unknown.iconName, "shield");
  });

  it("resolves action URLs from payload or booking id", () => {
    const notifWithClassroom: NotificationItem = {
      id: "n-1",
      kind: "lesson_reminder",
      title: "Lesson starting soon",
      body: "Click to enter",
      payload: { classroom_url: "/student/classroom/b-123" },
      booking_id: "b-123",
      created_at: "2026-10-06T10:00:00Z",
      read_at: null,
      email_state: "sent",
      email_last_error: null,
    };
    assert.equal(getNotificationActionUrl(notifWithClassroom), "/student/classroom/b-123");

    const notifStudentBooking: NotificationItem = {
      id: "n-2",
      kind: "booking_confirmed",
      title: "Confirmed",
      body: "Your lesson is set",
      payload: null,
      booking_id: "b-456",
      created_at: "2026-10-06T10:00:00Z",
      read_at: null,
      email_state: "sent",
      email_last_error: null,
    };
    assert.equal(getNotificationActionUrl(notifStudentBooking), "/student/classroom/b-456");

    const notifTeacherBooking: NotificationItem = {
      id: "n-3",
      kind: "teacher_new_booking",
      title: "New student",
      body: "You have a new booking",
      payload: null,
      booking_id: "b-789",
      created_at: "2026-10-06T10:00:00Z",
      read_at: null,
      email_state: "sent",
      email_last_error: null,
    };
    assert.equal(getNotificationActionUrl(notifTeacherBooking), "/teacher/classroom/b-789");

    const notifNoLink: NotificationItem = {
      id: "n-4",
      kind: "general_announcement",
      title: "Update",
      body: "Maintenance notice",
      payload: null,
      booking_id: null,
      created_at: "2026-10-06T10:00:00Z",
      read_at: null,
      email_state: "sent",
      email_last_error: null,
    };
    assert.equal(getNotificationActionUrl(notifNoLink), null);
  });
});

describe("Notification components", () => {
  it("renders NotificationDrawer in closed and open states", () => {
    // Closed state renders null
    const closedHtml = renderToString(
      React.createElement(NotificationDrawer, {
        isOpen: false,
        onClose: () => {},
        notifications: [],
        unreadCount: 0,
        isLoading: false,
        isLoadingMore: false,
        hasMore: false,
        onFetchMore: () => {},
        onMarkRead: () => {},
        onMarkAllRead: () => {},
        onOpenPreferences: () => {},
      })
    );
    assert.equal(closedHtml, "");

    // Open state with empty list
    const openEmptyHtml = renderToString(
      React.createElement(NotificationDrawer, {
        isOpen: true,
        onClose: () => {},
        notifications: [],
        unreadCount: 0,
        isLoading: false,
        isLoadingMore: false,
        hasMore: false,
        onFetchMore: () => {},
        onMarkRead: () => {},
        onMarkAllRead: () => {},
        onOpenPreferences: () => {},
      })
    );
    assert.ok(openEmptyHtml.includes("Notifications"));
    assert.ok(openEmptyHtml.includes("All caught up!"));

    // Open state with unread notification
    const testItem: NotificationItem = {
      id: "n-test-1",
      kind: "lesson_reminder_t10m",
      title: "Lesson starts in 10 minutes",
      body: "Please enter your classroom now to test equipment.",
      payload: { classroom_url: "/student/classroom/b-999" },
      booking_id: "b-999",
      created_at: new Date().toISOString(),
      read_at: null,
      email_state: "sent",
      email_last_error: null,
    };

    const openWithItemHtml = renderToString(
      React.createElement(NotificationDrawer, {
        isOpen: true,
        onClose: () => {},
        notifications: [testItem],
        unreadCount: 1,
        isLoading: false,
        isLoadingMore: false,
        hasMore: false,
        onFetchMore: () => {},
        onMarkRead: () => {},
        onMarkAllRead: () => {},
        onOpenPreferences: () => {},
      })
    );
    assert.ok(openWithItemHtml.includes("Lesson starts in 10 minutes"));
    assert.ok(openWithItemHtml.includes("Lesson Reminder"));
    assert.ok(openWithItemHtml.includes("Mark all"));
    assert.ok(openWithItemHtml.includes("Open"));
  });

  it("renders NotificationPreferencesModal with category toggles and mandatory locks", () => {
    const modalHtml = renderToString(
      React.createElement(NotificationPreferencesModal, {
        isOpen: true,
        onClose: () => {},
        preferences: {
          email_by_kind: { lesson_reminders: true },
          in_app_by_kind: { lesson_reminders: true },
          updated_at: new Date().toISOString(),
        },
        onSave: async () => {},
        isSaving: false,
      })
    );

    assert.ok(modalHtml.includes("Notification Preferences"));
    assert.ok(modalHtml.includes("Lesson Reminders"));
    assert.ok(modalHtml.includes("Booking Confirmations"));
    assert.ok(modalHtml.includes("Mandatory"));
    assert.ok(modalHtml.includes("Save Preferences"));
  });
});
