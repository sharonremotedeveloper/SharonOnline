"use client";

import Link from "next/link";
import { Mail, ArrowLeft, Info } from "lucide-react";

export default function ForgotPasswordPage() {
  // The backend has no password-reset endpoint yet (production plan Task 8.5), so this page
  // must not pretend to send an email. It explains the current state instead.
  return (
    <div className="min-h-[80vh] flex items-center justify-center px-4 py-12">
      <div className="bg-white rounded-3xl p-8 max-w-md w-full border border-divider shadow-card space-y-6">
        <div className="text-center space-y-2">
          <div className="w-12 h-12 rounded-2xl bg-teal text-gold-bright font-black text-2xl flex items-center justify-center mx-auto shadow-sm font-serif">
            S
          </div>
          <h1 className="text-2xl font-extrabold text-ink font-serif">Reset Password</h1>
          <p className="text-xs text-ink-muted">Password recovery</p>
        </div>

        <div role="status" className="bg-cream-surface border border-divider rounded-2xl p-6 text-center space-y-3">
          <Info className="w-10 h-10 text-teal mx-auto" aria-hidden="true" />
          <div className="text-sm font-bold text-ink">Self-service reset isn&apos;t available yet</div>
          <p className="text-xs text-ink-muted leading-relaxed">
            We can&apos;t email you a reset link at the moment. If you&apos;ve lost access to your account, please
            contact our support team and we&apos;ll help you regain access.
          </p>
          <Link
            href="/support"
            className="inline-flex items-center gap-1.5 px-4 py-2 bg-primary hover:bg-primary-hover text-white rounded-xl text-xs font-bold transition-all shadow-sm"
          >
            <Mail className="w-3.5 h-3.5" /> Contact Support
          </Link>
          <div>
            <Link
              href="/login"
              className="inline-flex items-center gap-1.5 text-xs font-bold text-teal hover:underline pt-2"
            >
              <ArrowLeft className="w-3.5 h-3.5" /> Return to Login
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
