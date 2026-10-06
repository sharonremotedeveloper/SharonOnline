"use client";

import { Bell } from "lucide-react";
import { useNotifications } from "../../hooks/useNotifications";
import { formatBadgeCount } from "../../lib/notifications";
import { NotificationDrawer } from "./NotificationDrawer";
import { NotificationPreferencesModal } from "./NotificationPreferencesModal";

interface NotificationBellProps {
  className?: string;
}

export function NotificationBell({ className = "" }: NotificationBellProps) {
  const {
    notifications,
    unreadCount,
    isLoading,
    isLoadingMore,
    hasMore,
    isOpen,
    preferencesOpen,
    preferences,
    isSavingPreferences,
    toggleOpen,
    close,
    togglePreferences,
    closePreferences,
    fetchMore,
    markRead,
    markAllRead,
    savePreferences,
  } = useNotifications();

  const badgeText = formatBadgeCount(unreadCount);
  const ariaLabel =
    unreadCount > 0 ? `Notifications (${unreadCount} unread)` : "Notifications";

  return (
    <>
      <button
        type="button"
        onClick={toggleOpen}
        aria-label={ariaLabel}
        aria-expanded={isOpen}
        aria-haspopup="dialog"
        className={`relative p-2 rounded-xl text-white/90 hover:text-white hover:bg-white/10 transition-colors focus:outline-hidden focus:ring-2 focus:ring-gold ${className}`}
      >
        <Bell className="w-5 h-5" />

        {/* Unread count badge */}
        {badgeText && (
          <span
            aria-hidden="true"
            className="absolute top-1 right-1 flex items-center justify-center min-w-4.5 h-4.5 px-1 text-[10px] font-black leading-none text-cocoa bg-gold rounded-full ring-2 ring-cocoa shadow-xs animate-in zoom-in-75 duration-150"
          >
            {badgeText}
          </span>
        )}
      </button>

      {/* Flyout Drawer */}
      <NotificationDrawer
        isOpen={isOpen}
        onClose={close}
        notifications={notifications}
        unreadCount={unreadCount}
        isLoading={isLoading}
        isLoadingMore={isLoadingMore}
        hasMore={hasMore}
        onFetchMore={fetchMore}
        onMarkRead={markRead}
        onMarkAllRead={markAllRead}
        onOpenPreferences={togglePreferences}
      />

      {/* Preferences Modal */}
      <NotificationPreferencesModal
        isOpen={preferencesOpen}
        onClose={closePreferences}
        preferences={preferences}
        onSave={savePreferences}
        isSaving={isSavingPreferences}
      />
    </>
  );
}
