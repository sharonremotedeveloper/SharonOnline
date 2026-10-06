"use client";

import { useState } from "react";
import Link from "next/link";
import { Mail, ArrowLeft, CheckCircle2 } from "lucide-react";
import { requestPasswordReset } from "@/lib/account";
import { ApiError, errorMessage } from "@/lib/http";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      await requestPasswordReset(email.trim());
      // The server answers identically whether or not the address has an account, so we say the same thing too.
      setSent(true);
    } catch (err) {
      setError(err instanceof ApiError && err.fieldErrors.email ? err.fieldErrors.email.join(" ") : errorMessage(err));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-[80vh] flex items-center justify-center px-4 py-12">
      <div className="bg-white rounded-3xl p-8 max-w-md w-full border border-divider shadow-card space-y-6">
        <div className="text-center space-y-2">
          <div className="w-12 h-12 rounded-2xl bg-cocoa text-gold-bright font-black text-2xl flex items-center justify-center mx-auto shadow-sm font-serif">
            S
          </div>
          <h1 className="text-2xl font-extrabold text-ink font-serif">Reset Password</h1>
          <p className="text-xs text-ink-muted">We&apos;ll e-mail you a link to choose a new one</p>
        </div>

        {sent ? (
          <div role="status" className="bg-cream-surface border border-divider rounded-2xl p-6 text-center space-y-3">
            <CheckCircle2 className="w-10 h-10 text-success mx-auto" aria-hidden="true" />
            <div className="text-sm font-bold text-ink">Check your inbox</div>
            <p className="text-xs text-ink-muted leading-relaxed">
              If an account exists for <span className="font-bold">{email}</span>, a reset link is on its way. It works once and expires
              in an hour. Nothing arrived? Check spam, or try again in a few minutes.
            </p>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">
            {error && (
              <div role="alert" className="p-3 bg-primary/10 border border-primary/30 rounded-xl text-xs text-primary font-medium">
                {error}
              </div>
            )}
            <div className="space-y-1">
              <label htmlFor="email" className="text-xs font-bold text-ink">E-mail address</label>
              <div className="relative">
                <Mail className="w-4 h-4 absolute left-3.5 top-1/2 -translate-y-1/2 text-ink-faint" />
                <input
                  id="email"
                  type="email"
                  required
                  autoComplete="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@example.com"
                  className="w-full pl-10 pr-4 py-2.5 rounded-xl border border-divider text-xs text-ink bg-cream-surface focus:outline-none focus:ring-2 focus:ring-cocoa"
                />
              </div>
            </div>
            <button
              type="submit"
              disabled={submitting}
              className="w-full py-3 bg-primary hover:bg-primary-hover text-white rounded-xl text-xs font-bold transition-all shadow-sm disabled:opacity-50"
            >
              {submitting ? "Sending..." : "Send reset link"}
            </button>
          </form>
        )}

        <div className="text-center">
          <Link href="/login" className="inline-flex items-center gap-1.5 text-xs font-bold text-cocoa hover:underline">
            <ArrowLeft className="w-3.5 h-3.5" /> Return to Login
          </Link>
        </div>
      </div>
    </div>
  );
}
