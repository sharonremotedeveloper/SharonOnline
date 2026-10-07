"use client";

import { useEffect, useRef } from "react";
import Link from "next/link";
import { Portal } from "../ui/Portal";
import { useDialog } from "../../hooks/useDialog";
import {
  Bell,
  Calendar,
  AlertTriangle,
  Shield,
  Coins,
  FileText,
  CheckCheck,
  Settings,
  X,
  ExternalLink,
  ChevronRight,
  Loader2,
} from "lucide-react";
import {
  formatRelativeTime,
  getNotificationActionUrl,
  getNotificationCategoryInfo,
  type NotificationItem,
} from "../../lib/notifications";

interface NotificationDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  notifications: NotificationItem[];
  unreadCount: number;
  isLoading: boolean;
  isLoadingMore: boolean;
  hasMore: boolean;
  onFetchMore: () => void;
  onMarkRead: (id: string) => void;
  onMarkAllRead: () => void;
  onOpenPreferences: () => void;
}

export function NotificationDrawer({
  isOpen,
  onClose,
  notifications,
  unreadCount,
  isLoading,
  isLoadingMore,
  hasMore,
  onFetchMore,
  onMarkRead,
  onMarkAllRead,
  onOpenPreferences,
}: NotificationDrawerProps) {
  const panelRef = useRef<HTMLDivElement>(null);

  useDialog(panelRef, isOpen, onClose);

  if (!isOpen) return null;

  const renderCategoryIcon = (iconName: string) => {
    switch (iconName) {
      case "bell":
        return <Bell className="w-4 h-4" />;
      case "calendar":
        return <Calendar className="w-4 h-4" />;
      case "coins":
        return <Coins className="w-4 h-4" />;
      case "alert":
        return <AlertTriangle className="w-4 h-4" />;
      case "fileText":
        return <FileText className="w-4 h-4" />;
      default:
        return <Shield className="w-4 h-4" />;
    }
  };

  return (
    <Portal>
    <div className="fixed inset-0 z-50 overflow-hidden" role="dialog" aria-modal="true" aria-label="Notifications panel">
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/40 backdrop-blur-xs transition-opacity duration-200"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Drawer Panel */}
      <div className="fixed inset-y-0 right-0 max-w-full flex pl-10">
        <div
          ref={panelRef}
          tabIndex={-1} className="w-screen max-w-md bg-surface border-l border-ink/10 shadow-2xl flex flex-col text-ink animate-in slide-in-from-right duration-200"
        >
          {/* Header */}
          <div className="p-4 sm:px-6 border-b border-ink/10 flex items-center justify-between bg-cocoa-50/70">
            <div className="flex items-center space-x-2.5">
              <div className="p-2 bg-cocoa/10 rounded-xl text-cocoa">
                <Bell className="w-5 h-5" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h2 className="text-base font-bold text-ink">Notifications</h2>
                  {unreadCount > 0 && (
                    <span className="px-2 py-0.5 text-xs font-bold rounded-full bg-cocoa text-white">
                      {unreadCount} new
                    </span>
                  )}
                </div>
                <p className="text-sm text-ink-muted">Stay updated on lessons and alerts</p>
              </div>
            </div>

            <div className="flex items-center space-x-1">
              {unreadCount > 0 && (
                <button
                  type="button"
                  onClick={onMarkAllRead}
                  className="min-w-11 justify-center min-h-11 p-2 text-ink-muted hover:text-cocoa hover:bg-cocoa-100 rounded-lg transition-colors flex items-center gap-1 text-xs font-medium"
                  title="Mark all as read"
                  aria-label="Mark all as read"
                >
                  <CheckCheck className="w-4 h-4" />
                  <span className="hidden sm:inline">Mark all</span>
                </button>
              )}

              <button
                type="button"
                onClick={onOpenPreferences}
                className="min-w-11 justify-center min-h-11 inline-flex items-center p-2 text-ink-muted hover:text-ink hover:bg-cocoa-100 rounded-lg transition-colors"
                title="Notification preferences"
                aria-label="Notification preferences"
              >
                <Settings className="w-4.5 h-4.5" />
              </button>

              <button
                type="button"
                onClick={onClose}
                className="min-w-11 justify-center min-h-11 inline-flex items-center p-2 text-ink-muted hover:text-ink hover:bg-cocoa-100 rounded-lg transition-colors"
                aria-label="Close notification panel"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
          </div>

          {/* Body List */}
          <div className="flex-1 overflow-y-auto divide-y divide-ink/10">
            {isLoading ? (
              <div className="p-12 text-center space-y-3">
                <Loader2 className="w-8 h-8 text-cocoa animate-spin mx-auto" />
                <p className="text-sm font-medium text-ink-muted">Loading notifications...</p>
              </div>
            ) : notifications.length === 0 ? (
              <div className="py-20 px-6 text-center space-y-3">
                <div className="w-14 h-14 bg-cocoa/10 rounded-2xl flex items-center justify-center mx-auto text-cocoa">
                  <Bell className="w-7 h-7 opacity-75" />
                </div>
                <h3 className="text-sm font-bold text-ink">All caught up!</h3>
                <p className="text-sm text-ink-muted max-w-xs mx-auto">
                  You don&apos;t have any notifications right now. Lesson reminders and account updates will appear here.
                </p>
              </div>
            ) : (
              notifications.map((item) => {
                const isUnread = !item.read_at;
                const cat = getNotificationCategoryInfo(item.kind);
                const actionUrl = getNotificationActionUrl(item);

                return (
                  <div
                    key={item.id}
                    onClick={() => {
                      if (isUnread) onMarkRead(item.id);
                    }}
                    className={`p-4 transition-colors relative flex items-start gap-3.5 group cursor-pointer ${
                      isUnread
                        ? "bg-cocoa-50/25 hover:bg-cocoa-50/50"
                        : "bg-surface hover:bg-cocoa-50"
                    }`}
                  >
                    {/* Category Icon */}
                    <div
                      className={`w-9 h-9 rounded-xl flex items-center justify-center shrink-0 border ${cat.bgClass}`}
                    >
                      {renderCategoryIcon(cat.iconName)}
                    </div>

                    {/* Content Details */}
                    <div className="flex-1 min-w-0 pr-4">
                      <div className="flex items-center justify-between gap-2 mb-1">
                        <span
                          className={`text-xs font-bold uppercase tracking-wider ${cat.colorClass}`}
                        >
                          {cat.label}
                        </span>
                        <span className="text-xs text-ink-muted shrink-0">
                          {formatRelativeTime(item.created_at)}
                        </span>
                      </div>

                      <h4
                        className={`text-sm leading-snug break-words ${
                          isUnread ? "font-bold text-ink" : "font-medium text-ink/80"
                        }`}
                      >
                        {item.title}
                      </h4>

                      {item.body && (
                        <p className="text-sm text-ink-muted mt-1 leading-relaxed break-words line-clamp-3">
                          {item.body}
                        </p>
                      )}

                      {/* Action Link if available */}
                      {actionUrl && (
                        <div className="mt-2.5">
                          <Link
                            href={actionUrl}
                            onClick={(e) => {
                              e.stopPropagation();
                              if (isUnread) onMarkRead(item.id);
                              onClose();
                            }}
                            className="inline-flex items-center gap-1.5 text-xs font-bold text-cocoa hover:underline"
                          >
                            <span>Open</span>
                            <ExternalLink className="w-3 h-3" />
                          </Link>
                        </div>
                      )}
                    </div>

                    {/* Unread dot */}
                    {isUnread && (
                      <div
                        className="w-2.5 h-2.5 rounded-full bg-cocoa shrink-0 mt-2 shadow-xs"
                        aria-label="Unread notification"
                      />
                    )}
                  </div>
                );
              })
            )}

            {/* Load More Button */}
            {hasMore && !isLoading && (
              <div className="p-4 text-center bg-cocoa-50">
                <button
                  type="button"
                  onClick={onFetchMore}
                  disabled={isLoadingMore}
                  className="min-h-11 w-full py-2 px-4 rounded-xl text-xs font-bold text-cocoa bg-white border border-cocoa/20 hover:bg-cocoa-50 transition-colors flex items-center justify-center gap-2"
                >
                  {isLoadingMore ? (
                    <>
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      <span>Loading more...</span>
                    </>
                  ) : (
                    <>
                      <span>View earlier notifications</span>
                      <ChevronRight className="w-3.5 h-3.5" />
                    </>
                  )}
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
    </Portal>
  );
}
