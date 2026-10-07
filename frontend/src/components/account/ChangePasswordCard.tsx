"use client";

import { useState } from "react";
import { KeyRound } from "lucide-react";
import { changePassword } from "@/lib/account";
import { ApiError, errorMessage } from "@/lib/http";
import { useAuth } from "@/context/AuthContext";

const FIELDS = [
  ["old_password", "Current password", "current-password"],
  ["new_password", "New password", "new-password"],
  ["new_password_confirm", "Confirm new password", "new-password"],
] as const;

export function ChangePasswordCard() {
  const { logout } = useAuth();
  const [values, setValues] = useState({ old_password: "", new_password: "", new_password_confirm: "" });
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setFieldErrors({});
    if (values.new_password !== values.new_password_confirm) {
      setFieldErrors({ new_password_confirm: ["Passwords don't match."] });
      return;
    }
    setSubmitting(true);
    try {
      await changePassword(values);
      // The server ended every session, including this one, so sign out cleanly and send them to the login page.
      setDone(true);
      setTimeout(logout, 1800);
    } catch (err) {
      if (err instanceof ApiError && Object.keys(err.fieldErrors).length) setFieldErrors(err.fieldErrors);
      else setError(errorMessage(err));
      setSubmitting(false);
    }
  };

  return (
    <form onSubmit={submit} className="bg-white rounded-2xl border border-divider shadow-card p-6 space-y-4">
      <div className="flex items-center gap-2">
        <KeyRound className="w-4 h-4 text-cocoa" aria-hidden="true" />
        <h2 className="text-sm font-extrabold text-ink">Change password</h2>
      </div>
      {done ? (
        <p role="status" className="text-sm text-success font-medium">
          Password changed. For your safety you&apos;re being signed out everywhere - please sign in again.
        </p>
      ) : (
        <>
          {error && (
            <div role="alert" className="p-3 bg-primary/10 border border-primary/30 rounded-xl text-sm text-primary font-medium">
              {error}
            </div>
          )}
          {FIELDS.map(([name, label, autoComplete]) => (
            <div key={name} className="space-y-1">
              <label htmlFor={`cp-${name}`} className="text-sm font-bold text-ink">{label}</label>
              <input
                id={`cp-${name}`}
                aria-invalid={fieldErrors[name]?.length ? true : undefined}
                aria-describedby={fieldErrors[name]?.length ? `cp-${name}-error` : undefined}
                type="password"
                required
                autoComplete={autoComplete}
                value={values[name]}
                onChange={(e) => setValues({ ...values, [name]: e.target.value })}
                className="min-h-11 w-full p-2.5 rounded-xl border border-strong text-base sm:text-sm text-ink bg-cream-surface focus:outline-none focus:ring-2 focus:ring-cocoa"
              />
              {fieldErrors[name]?.length ? <p id={`cp-${name}-error`} role="alert" className="text-sm text-error font-medium">{fieldErrors[name].join(" ")}</p> : null}
            </div>
          ))}
          <button
            type="submit"
            disabled={submitting}
            className="min-h-11 inline-flex items-center px-5 py-2.5 bg-cocoa text-white text-sm font-bold rounded-xl shadow-sm disabled:opacity-50"
          >
            {submitting ? "Updating..." : "Update password"}
          </button>
        </>
      )}
    </form>
  );
}
