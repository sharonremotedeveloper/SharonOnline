"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useAuth } from "../context/AuthContext";
import {
  fetchNotifications,
  fetchUnreadCount,
  fetchNotificationPreferences,
  markAllNotificationsRead,
  markNotificationRead,
  updateNotificationPreferences,
  type NotificationItem,
  type NotificationPreference,
  type PatchedNotificationPreferenceRequest,
} from "../lib/notifications";

const BASE_POLL_INTERVAL_MS = 45_000;
const JITTER_RANGE_MS = 20_000; // ±10s

function getJitteredInterval(): number {
  const jitter = (Math.random() - 0.5) * JITTER_RANGE_MS;
  return Math.max(20_000, BASE_POLL_INTERVAL_MS + jitter);
}

export function useNotifications() {
  const { isAuthenticated, user } = useAuth();
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [unreadCount, setUnreadCount] = useState<number>(0);
  const [page, setPage] = useState<number>(1);
  const [hasMore, setHasMore] = useState<boolean>(false);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [isLoadingMore, setIsLoadingMore] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const [isOpen, setIsOpen] = useState<boolean>(false);
  const [preferencesOpen, setPreferencesOpen] = useState<boolean>(false);
  const [preferences, setPreferences] = useState<NotificationPreference | null>(null);
  const [isSavingPreferences, setIsSavingPreferences] = useState<boolean>(false);

  const isOpenRef = useRef(isOpen);
  useEffect(() => {
    isOpenRef.current = isOpen;
  }, [isOpen]);

  const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isMountedRef = useRef<boolean>(true);

  // ----------------------------------------------------
  // Refresh Unread Count
  // ----------------------------------------------------
  const refreshUnreadCount = useCallback(async () => {
    if (!isAuthenticated || !user) return;
    try {
      const count = await fetchUnreadCount();
      if (isMountedRef.current) {
        setUnreadCount(count);
      }
    } catch (err) {
      // Background poll failure is non-fatal
      console.warn("Unread notifications poll failed:", err);
    }
  }, [isAuthenticated, user]);

  // ----------------------------------------------------
  // Load Notifications List (Page 1 or Refresh)
  // ----------------------------------------------------
  const loadNotifications = useCallback(async () => {
    if (!isAuthenticated || !user) return;
    setIsLoading(true);
    setError(null);
    try {
      const resp = await fetchNotifications(1, 20);
      if (isMountedRef.current) {
        setNotifications(resp.results || []);
        setHasMore(Boolean(resp.next));
        setPage(1);
      }
      // Keep unread count synchronized
      await refreshUnreadCount();
    } catch (err) {
      if (isMountedRef.current) {
        setError(err instanceof Error ? err.message : "Failed to load notifications");
      }
    } finally {
      if (isMountedRef.current) {
        setIsLoading(false);
      }
    }
  }, [isAuthenticated, user, refreshUnreadCount]);

  // ----------------------------------------------------
  // Pagination: Load Next Page
  // ----------------------------------------------------
  const fetchMore = useCallback(async () => {
    if (isLoadingMore || !hasMore || !isAuthenticated) return;
    setIsLoadingMore(true);
    const nextPage = page + 1;
    try {
      const resp = await fetchNotifications(nextPage, 20);
      if (isMountedRef.current) {
        setNotifications((prev) => [...prev, ...(resp.results || [])]);
        setHasMore(Boolean(resp.next));
        setPage(nextPage);
      }
    } catch (err) {
      console.error("Failed to load more notifications:", err);
    } finally {
      if (isMountedRef.current) {
        setIsLoadingMore(false);
      }
    }
  }, [isLoadingMore, hasMore, isAuthenticated, page]);

  // ----------------------------------------------------
  // Mark Single Notification as Read
  // ----------------------------------------------------
  const markRead = useCallback(async (id: string) => {
    // Optimistic UI update
    setNotifications((prev) =>
      prev.map((item) =>
        item.id === id && !item.read_at ? { ...item, read_at: new Date().toISOString() } : item
      )
    );
    setUnreadCount((prev) => Math.max(0, prev - 1));

    try {
      await markNotificationRead(id);
    } catch (err) {
      console.error("Failed to mark notification as read:", err);
    }
  }, []);

  // ----------------------------------------------------
  // Mark All Notifications as Read
  // ----------------------------------------------------
  const markAllRead = useCallback(async () => {
    const nowIso = new Date().toISOString();
    // Optimistic UI update
    setNotifications((prev) =>
      prev.map((item) => (item.read_at ? item : { ...item, read_at: nowIso }))
    );
    setUnreadCount(0);

    try {
      await markAllNotificationsRead();
    } catch (err) {
      console.error("Failed to mark all notifications as read:", err);
    }
  }, []);

  // ----------------------------------------------------
  // Notification Preferences
  // ----------------------------------------------------
  const loadPreferences = useCallback(async () => {
    if (!isAuthenticated) return;
    try {
      const data = await fetchNotificationPreferences();
      if (isMountedRef.current) {
        setPreferences(data);
      }
    } catch (err) {
      console.error("Failed to load notification preferences:", err);
    }
  }, [isAuthenticated]);

  const savePreferences = useCallback(
    async (payload: PatchedNotificationPreferenceRequest) => {
      setIsSavingPreferences(true);
      try {
        const updated = await updateNotificationPreferences(payload);
        if (isMountedRef.current) {
          setPreferences(updated);
          setPreferencesOpen(false);
        }
      } catch (err) {
        console.error("Failed to update notification preferences:", err);
        throw err;
      } finally {
        if (isMountedRef.current) {
          setIsSavingPreferences(false);
        }
      }
    },
    []
  );

  // ----------------------------------------------------
  // Drawer / UI Toggles
  // ----------------------------------------------------
  const toggleOpen = useCallback(() => {
    setIsOpen((prev) => {
      const next = !prev;
      if (next && notifications.length === 0) {
        loadNotifications();
      }
      return next;
    });
  }, [notifications.length, loadNotifications]);

  const close = useCallback(() => setIsOpen(false), []);
  const open = useCallback(() => {
    setIsOpen(true);
    if (notifications.length === 0) {
      loadNotifications();
    }
  }, [notifications.length, loadNotifications]);

  const togglePreferences = useCallback(() => {
    setPreferencesOpen((prev) => {
      const next = !prev;
      if (next && !preferences) {
        loadPreferences();
      }
      return next;
    });
  }, [preferences, loadPreferences]);

  const closePreferences = useCallback(() => setPreferencesOpen(false), []);

  // ----------------------------------------------------
  // Jittered Visibility-Aware Polling Loop
  // ----------------------------------------------------
  useEffect(() => {
    isMountedRef.current = true;
    if (!isAuthenticated || !user) {
      setNotifications([]);
      setUnreadCount(0);
      return;
    }

    // Initial load
    refreshUnreadCount();

    const scheduleNextPoll = () => {
      if (pollTimerRef.current) {
        clearTimeout(pollTimerRef.current);
      }

      // Do not schedule if tab is not visible
      if (typeof document !== "undefined" && document.visibilityState === "hidden") {
        return;
      }

      const nextInterval = getJitteredInterval();
      pollTimerRef.current = setTimeout(async () => {
        if (typeof document !== "undefined" && document.visibilityState === "visible") {
          await refreshUnreadCount();
          // If drawer is currently open, refresh notifications list as well
          if (isOpenRef.current) {
            await loadNotifications();
          }
        }
        scheduleNextPoll();
      }, nextInterval);
    };

    const handleVisibilityChange = () => {
      if (document.visibilityState === "visible") {
        refreshUnreadCount();
        if (isOpenRef.current) {
          loadNotifications();
        }
        scheduleNextPoll();
      } else if (pollTimerRef.current) {
        clearTimeout(pollTimerRef.current);
        pollTimerRef.current = null;
      }
    };

    const handleOnline = () => {
      refreshUnreadCount();
      scheduleNextPoll();
    };

    if (typeof document !== "undefined") {
      document.addEventListener("visibilitychange", handleVisibilityChange);
      window.addEventListener("online", handleOnline);
    }

    scheduleNextPoll();

    return () => {
      isMountedRef.current = false;
      if (pollTimerRef.current) {
        clearTimeout(pollTimerRef.current);
        pollTimerRef.current = null;
      }
      if (typeof document !== "undefined") {
        document.removeEventListener("visibilitychange", handleVisibilityChange);
        window.removeEventListener("online", handleOnline);
      }
    };
  }, [isAuthenticated, user, refreshUnreadCount, loadNotifications]);

  return {
    notifications,
    unreadCount,
    isLoading,
    isLoadingMore,
    hasMore,
    isOpen,
    error,
    preferencesOpen,
    preferences,
    isSavingPreferences,
    toggleOpen,
    close,
    open,
    togglePreferences,
    closePreferences,
    fetchMore,
    markRead,
    markAllRead,
    refresh: loadNotifications,
    loadPreferences,
    savePreferences,
  };
}
