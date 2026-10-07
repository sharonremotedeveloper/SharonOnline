"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { AlertTriangle, Lock, AlertCircle } from "lucide-react";
import { confirmPasswordReset } from "@/lib/account";
import { ApiError, errorMessage } from "@/lib/http";

function ResetForm() {
  const router = useRouter();
  const params = useSearchParams();
  // Keep the one-time credentials in memory only and take them out of the address bar / history straight away.
  const [link, setLink] = useState<{ uid: string; token: string } | null>(null);
  const [checked, setChecked] = useState(false);
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});
  const [error, setError] = useState("");
  const [linkDead, setLinkDead] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    const uid = params.get("uid");
    const token = params.get("token");
    if (uid && token) {
      setLink({ uid, token });
      window.history.replaceState(null, "", window.location.pathname);
    }
    setChecked(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!link) return;
    setError("");
    setFieldErrors({});
    if (password !== confirm) {
      setFieldErrors({ new_password_confirm: ["Passwords don't match."] });
      return;
    }
    setSubmitting(true);
    try {
      await confirmPasswordReset({ ...link, new_password: password, new_password_confirm: confirm });
      router.push("/login?reset=1");
    } catch (err) {
      if (err instanceof ApiError && err.status === 400 && err.fieldErrors.token) setLinkDead(true);
      else if (err instanceof ApiError && Object.keys(err.fieldErrors).length) setFieldErrors(err.fieldErrors);
      else setError(errorMessage(err));
      setSubmitting(false);
    }
  };

  const fieldError = (name: string) =>
    fieldErrors[name]?.length ? <p id={`rp-${name}-error`} role="alert" className="text-sm text-error font-medium">{fieldErrors[name].join(" ")}</p> : null;

  if (!checked) return <div className="text-sm text-ink-muted">Loading...</div>;

  if (!link || linkDead) {
    return (
      <div role="alert" className="bg-white rounded-3xl p-8 max-w-md w-full border border-divider shadow-card text-center space-y-3">
        <AlertTriangle className="w-10 h-10 text-primary mx-auto" aria-hidden="true" />
        <h1 className="text-lg font-extrabold text-ink font-serif">This reset link doesn&apos;t work</h1>
        <p className="text-sm text-ink-muted leading-relaxed">
          Reset links work once and expire after an hour. Request a fresh one and use the newest e-mail.
        </p>
        <Link href="/forgot-password" className="min-h-11 inline-flex items-center inline-block px-4 py-2 bg-cocoa hover:bg-cocoa-hover text-white rounded-xl text-sm font-bold">
          Request a new link
        </Link>
      </div>
    );
  }

  return (
    <form onSubmit={submit} className="bg-white rounded-3xl p-8 max-w-md w-full border border-divider shadow-card space-y-5">
      <div className="text-center space-y-1">
        <h1 className="text-2xl font-extrabold text-ink font-serif">Choose a new password</h1>
        <p className="text-sm text-ink-muted">You&apos;ll be signed out everywhere else.</p>
      </div>
      {error && (
        <div role="alert" className="flex items-start gap-2 p-3 bg-error-surface border border-error-border rounded-xl text-sm text-error font-medium">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <span>{error}</span>
        </div>
      )}
      {(
        [
          ["new_password", "New password", password, setPassword],
          ["new_password_confirm", "Confirm new password", confirm, setConfirm],
        ] as const
      ).map(([name, label, value, set]) => (
        <div key={name} className="space-y-1">
          <label htmlFor={name} className="text-sm font-bold text-ink">{label}</label>
          <div className="relative">
            <Lock className="w-4 h-4 absolute left-3.5 top-1/2 -translate-y-1/2 text-ink-faint" />
            <input
              id={name}
              aria-invalid={fieldErrors[name]?.length ? true : undefined}
              aria-describedby={fieldErrors[name]?.length ? `rp-${name}-error` : undefined}
              type="password"
              required
              minLength={8}
              autoComplete="new-password"
              value={value}
              onChange={(e) => set(e.target.value)}
              className="min-h-11 w-full pl-10 pr-4 py-2.5 rounded-xl border border-strong text-base sm:text-sm text-ink bg-cream-surface focus:outline-none focus:ring-2 focus:ring-cocoa"
            />
          </div>
          {fieldError(name)}
        </div>
      ))}
      <button
        type="submit"
        disabled={submitting}
        className="min-h-11 inline-flex items-center w-full py-3 bg-cocoa hover:bg-cocoa-hover text-white rounded-xl text-sm font-bold shadow-sm disabled:opacity-50"
      >
        {submitting ? "Saving..." : "Update password"}
      </button>
    </form>
  );
}

export default function ResetPasswordPage() {
  return (
    <div className="min-h-[80vh] flex items-center justify-center px-4 py-12">
      <Suspense fallback={<div className="text-sm text-ink-muted">Loading...</div>}>
        <ResetForm />
      </Suspense>
    </div>
  );
}
