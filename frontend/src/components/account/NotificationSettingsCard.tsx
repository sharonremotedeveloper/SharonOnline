"use client";

import { useEffect, useState } from "react";
import { Bell, Check, Lock, Mail } from "lucide-react";
import { fetchNotificationPreferences, updateNotificationPreferences } from "@/lib/notifications";
import { groupsFor, isGroupOn, setGroup, type KindMap, type PrefGroup, type PrefRole } from "@/lib/notificationPrefs";
import { ErrorState, InlineError } from "@/components/ui/ErrorState";

function Switch({ on, disabled, label, onClick }: { on: boolean; disabled?: boolean; label: string; onClick: () => void }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      aria-label={label}
      disabled={disabled}
      onClick={onClick}
      className={`min-h-11 min-w-11 inline-flex items-center justify-center rounded-lg transition-colors ${
        disabled ? "cursor-not-allowed opacity-60" : "hover:bg-cocoa/10"
      }`}
    >
      <span className={`flex h-5 w-9 items-center rounded-full p-0.5 transition-colors ${on ? "bg-cocoa" : "bg-cocoa-300"}`}>
        <span className={`h-4 w-4 rounded-full bg-white shadow-xs transition-transform ${on ? "translate-x-4" : "translate-x-0"}`} />
      </span>
    </button>
  );
}

/** Notification settings inline on a settings page (same rules as the bell's dialog: lib/notificationPrefs.ts). */
export function NotificationSettingsCard({ role }: { role: PrefRole }) {
  const groups = groupsFor(role);
  const [email, setEmail] = useState<KindMap>({});
  const [inApp, setInApp] = useState<KindMap>({});
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<unknown>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<unknown>(null);
  const [saved, setSaved] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [reloadTick, setReloadTick] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setLoadError(null);
    fetchNotificationPreferences()
      .then((p) => {
        if (cancelled) return;
        setEmail(p.email_by_kind || {});
        setInApp(p.in_app_by_kind || {});
      })
      .catch((err) => !cancelled && setLoadError(err))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [reloadTick]);

  const toggle = (channel: "email" | "in_app", group: PrefGroup) => {
    if (group.mandatory) return;
    const set = channel === "email" ? setEmail : setInApp;
    set((prev) => setGroup(prev, group, !isGroupOn(prev, group)));
    setDirty(true);
    setSaved(false);
  };

  const save = async () => {
    setSaving(true);
    setSaveError(null);
    try {
      const p = await updateNotificationPreferences({ email_by_kind: email, in_app_by_kind: inApp });
      setEmail(p.email_by_kind || {});
      setInApp(p.in_app_by_kind || {});
      setDirty(false);
      setSaved(true);
    } catch (err) {
      setSaveError(err);
    } finally {
      setSaving(false);
    }
  };

  return (
    <section aria-labelledby="notif-settings-title" className="rounded-3xl border border-divider bg-white p-5 shadow-card sm:p-7">
      <div className="flex flex-wrap items-end justify-between gap-2 border-b border-divider pb-4">
        <div>
          <h2 id="notif-settings-title" className="font-serif text-xl font-black text-ink">
            Notifications
          </h2>
          <p className="mt-1 text-sm text-ink-muted">Choose what reaches you in the app and by e-mail.</p>
        </div>
        <div className="ml-auto flex gap-1 text-xs font-bold uppercase tracking-wider text-ink-muted" aria-hidden="true">
          <span className="inline-flex w-11 flex-col items-center gap-0.5">
            <Bell className="h-3.5 w-3.5" /> App
          </span>
          <span className="inline-flex w-11 flex-col items-center gap-0.5">
            <Mail className="h-3.5 w-3.5" /> Email
          </span>
        </div>
      </div>

      {loading ? (
        <div className="mt-4 h-40 animate-pulse rounded-2xl bg-cream-surface" />
      ) : loadError != null ? (
        <div className="mt-4">
          <ErrorState error={loadError} title="We couldn't load your notification settings" onRetry={() => setReloadTick((t) => t + 1)} />
        </div>
      ) : (
        <>
          <ul className="divide-y divide-divider">
            {groups.map((g) => (
              <li key={g.key} className="flex items-center justify-between gap-3 py-3">
                <div className="min-w-0">
                  <p className="flex flex-wrap items-center gap-2 text-sm font-bold text-ink">
                    {g.title}
                    {g.mandatory && (
                      <span className="inline-flex items-center gap-1 rounded-md bg-cocoa/10 px-2 py-0.5 text-xs font-bold text-cocoa">
                        <Lock className="h-3 w-3" aria-hidden="true" /> Always on
                      </span>
                    )}
                  </p>
                  <p className="mt-0.5 text-sm text-ink-muted">{g.description}</p>
                </div>
                <div className="flex shrink-0 gap-1">
                  <Switch on={isGroupOn(inApp, g)} disabled={g.mandatory} label={`${g.title} in the app`} onClick={() => toggle("in_app", g)} />
                  <Switch on={isGroupOn(email, g)} disabled={g.mandatory} label={`${g.title} by e-mail`} onClick={() => toggle("email", g)} />
                </div>
              </li>
            ))}
          </ul>
          <InlineError error={saveError} />
          <div className="flex flex-wrap items-center justify-end gap-3 border-t border-divider pt-4">
            {saved && !dirty && (
              <span role="status" className="inline-flex items-center gap-1 text-sm font-bold text-success-hover">
                <Check className="h-4 w-4" aria-hidden="true" /> Saved
              </span>
            )}
            <button
              type="button"
              onClick={save}
              disabled={saving || !dirty}
              className="min-h-11 rounded-xl bg-cocoa px-5 text-sm font-bold text-white hover:bg-cocoa-hover disabled:opacity-50"
            >
              {saving ? "Saving..." : "Save notification settings"}
            </button>
          </div>
        </>
      )}
    </section>
  );
}
