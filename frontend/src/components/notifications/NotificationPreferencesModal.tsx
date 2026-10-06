"use client";

import { useEffect, useState } from "react";
import { X, Lock, Check, Bell, Mail } from "lucide-react";
import { Button } from "../ui/Button";
import type { NotificationPreference, PatchedNotificationPreferenceRequest } from "../../lib/notifications";

interface NotificationPreferencesModalProps {
  isOpen: boolean;
  onClose: () => void;
  preferences: NotificationPreference | null;
  onSave: (payload: PatchedNotificationPreferenceRequest) => Promise<void>;
  isSaving: boolean;
}

interface CategoryConfig {
  key: string;
  title: string;
  description: string;
  isMandatory?: boolean;
}

const CATEGORIES: CategoryConfig[] = [
  {
    key: "lesson_reminders",
    title: "Lesson Reminders",
    description: "T-24h calendar check, T-1h equipment check, and T-10m classroom launch links.",
    isMandatory: false,
  },
  {
    key: "booking_lifecycle",
    title: "Booking Confirmations & Changes",
    description: "Instant booking confirmations with .ics calendar files, reschedules, and cancellations.",
    isMandatory: true,
  },
  {
    key: "account_alerts",
    title: "Account & Operational Alerts",
    description: "Security notifications, vetting status updates, tutor strikes, and banking changes.",
    isMandatory: true,
  },
  {
    key: "billing_credits",
    title: "Billing & Wallet Credits",
    description: "Receipts, refund confirmations, and expiring wallet credit reminders.",
    isMandatory: false,
  },
];

export function NotificationPreferencesModal({
  isOpen,
  onClose,
  preferences,
  onSave,
  isSaving,
}: NotificationPreferencesModalProps) {
  const [emailSettings, setEmailSettings] = useState<Record<string, boolean>>({});
  const [inAppSettings, setInAppSettings] = useState<Record<string, boolean>>({});
  const [savedSuccess, setSavedSuccess] = useState<boolean>(false);

  useEffect(() => {
    if (preferences) {
      setEmailSettings(preferences.email_by_kind || {});
      setInAppSettings(preferences.in_app_by_kind || {});
    }
  }, [preferences]);

  if (!isOpen) return null;

  const handleToggle = (type: "email" | "in_app", key: string, isMandatory?: boolean) => {
    if (isMandatory) return; // Locked by policy
    if (type === "email") {
      setEmailSettings((prev) => ({ ...prev, [key]: !prev[key] }));
    } else {
      setInAppSettings((prev) => ({ ...prev, [key]: !prev[key] }));
    }
    setSavedSuccess(false);
  };

  const handleSave = async () => {
    await onSave({
      email_by_kind: emailSettings,
      in_app_by_kind: inAppSettings,
    });
    setSavedSuccess(true);
    setTimeout(() => {
      setSavedSuccess(false);
      onClose();
    }, 800);
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="notification-prefs-title"
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs animate-in fade-in duration-200"
    >
      <div className="relative w-full max-w-lg bg-surface rounded-2xl shadow-2xl border border-ink/10 overflow-hidden text-ink">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-ink/10 bg-cocoa-50/50">
          <div>
            <h2 id="notification-prefs-title" className="text-base font-bold text-ink">
              Notification Preferences
            </h2>
            <p className="text-sm text-ink-muted">
              Choose how you want to be notified across channels
            </p>
          </div>
          <button
            onClick={onClose}
            className="min-w-11 justify-center min-h-11 inline-flex items-center p-1.5 text-ink-muted hover:text-ink rounded-lg hover:bg-cocoa-100 transition-colors"
            aria-label="Close preferences"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Channel Labels */}
        <div className="flex items-center justify-end px-6 pt-4 pb-1 space-x-6 text-xs font-bold text-ink-muted uppercase tracking-wider">
          <div className="flex items-center gap-1 w-16 justify-center">
            <Bell className="w-3.5 h-3.5" /> In-App
          </div>
          <div className="flex items-center gap-1 w-16 justify-center">
            <Mail className="w-3.5 h-3.5" /> Email
          </div>
        </div>

        {/* Category Rows */}
        <div className="px-6 py-2 divide-y divide-ink/10 max-h-[60vh] overflow-y-auto">
          {CATEGORIES.map((cat) => {
            const inAppEnabled = cat.isMandatory ? true : inAppSettings[cat.key] ?? true;
            const emailEnabled = cat.isMandatory ? true : emailSettings[cat.key] ?? true;

            return (
              <div key={cat.key} className="py-3.5 flex items-start justify-between gap-4">
                <div className="flex-1 pr-2">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold text-ink">{cat.title}</span>
                    {cat.isMandatory && (
                      <span className="inline-flex items-center gap-0.5 px-2 py-0.5 text-xs font-bold rounded-md bg-cocoa-100 text-cocoa-700 border border-cocoa-200">
                        <Lock className="w-2.5 h-2.5" /> Mandatory
                      </span>
                    )}
                  </div>
                  <p className="text-sm text-ink-muted mt-0.5 leading-relaxed">
                    {cat.description}
                  </p>
                </div>

                {/* Toggles */}
                <div className="flex items-center space-x-6 pt-1">
                  {/* In-App Toggle */}
                  <button
                    type="button"
                    role="switch"
                    aria-checked={inAppEnabled}
                    disabled={cat.isMandatory}
                    onClick={() => handleToggle("in_app", cat.key, cat.isMandatory)}
                    className={`min-h-11 items-center w-16 flex justify-center py-1 rounded-md transition-colors ${
                      cat.isMandatory
                        ? "opacity-60 cursor-not-allowed"
                        : "hover:bg-cocoa-100"
                    }`}
                    aria-label={`Toggle in-app for ${cat.title}`}
                  >
                    <span
                      className={`w-8 h-4.5 flex items-center rounded-full p-0.5 transition-colors ${
                        inAppEnabled ? "bg-cocoa" : "bg-cocoa-300"
                      }`}
                    >
                      <span
                        className={`w-3.5 h-3.5 rounded-full bg-white shadow-xs transform transition-transform ${
                          inAppEnabled ? "translate-x-3.5" : "translate-x-0"
                        }`}
                      />
                    </span>
                  </button>

                  {/* Email Toggle */}
                  <button
                    type="button"
                    role="switch"
                    aria-checked={emailEnabled}
                    disabled={cat.isMandatory}
                    onClick={() => handleToggle("email", cat.key, cat.isMandatory)}
                    className={`min-h-11 items-center w-16 flex justify-center py-1 rounded-md transition-colors ${
                      cat.isMandatory
                        ? "opacity-60 cursor-not-allowed"
                        : "hover:bg-cocoa-100"
                    }`}
                    aria-label={`Toggle email for ${cat.title}`}
                  >
                    <span
                      className={`w-8 h-4.5 flex items-center rounded-full p-0.5 transition-colors ${
                        emailEnabled ? "bg-cocoa" : "bg-cocoa-300"
                      }`}
                    >
                      <span
                        className={`w-3.5 h-3.5 rounded-full bg-white shadow-xs transform transition-transform ${
                          emailEnabled ? "translate-x-3.5" : "translate-x-0"
                        }`}
                      />
                    </span>
                  </button>
                </div>
              </div>
            );
          })}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-6 py-4 bg-cocoa-50 border-t border-ink/10">
          <span className="text-xs text-ink-muted">
            {savedSuccess ? (
              <span className="text-cocoa font-bold flex items-center gap-1">
                <Check className="w-3.5 h-3.5" /> Saved successfully
              </span>
            ) : (
              "Changes apply across all your active devices"
            )}
          </span>
          <div className="flex items-center space-x-2">
            <Button variant="secondary" size="sm" onClick={onClose} disabled={isSaving}>
              Cancel
            </Button>
            <Button
              variant="primary"
              size="sm"
              onClick={handleSave}
              disabled={isSaving}
              className="bg-cocoa hover:bg-cocoa/90 text-white"
            >
              {isSaving ? "Saving..." : "Save Preferences"}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
