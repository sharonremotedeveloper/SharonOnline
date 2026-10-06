"use client";

import { useState, Suspense } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Lock, Mail, ArrowRight } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { UserRole } from "@/types/auth";

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const nextUrl = searchParams.get("next");
  const isRegistered = searchParams.get("registered");
  const isReset = searchParams.get("reset");

  const { login, isLoading } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  const handleLoginSuccess = (role: UserRole) => {
    // Only follow same-site relative paths ("/x"); "//evil.com", "/\evil.com" and absolute URLs would be an open redirect.
    if (nextUrl && /^\/(?![/\\])/.test(nextUrl)) {
      router.push(nextUrl);
      return;
    }

    if (role === "admin") {
      router.push("/admin/dashboard");
    } else if (role === "teacher") {
      router.push("/teacher/dashboard");
    } else {
      router.push("/student/dashboard");
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError("");

    const res = await login({ username, password });
    setSubmitting(false);

    if (res.success) {
      handleLoginSuccess(res.role);
    } else {
      setError(res.error || "Invalid username/e-mail or password");
    }
  };

  return (
    <div className="bg-white rounded-3xl p-8 max-w-md w-full border border-divider shadow-card space-y-6">
      <div className="text-center space-y-2">
        <div className="w-12 h-12 rounded-2xl bg-cocoa text-gold-bright font-black text-2xl flex items-center justify-center mx-auto shadow-sm font-serif">
          S
        </div>
        <h1 className="text-2xl font-extrabold text-ink font-serif">Sign In to Sharon Online</h1>
        <p className="text-sm text-ink-muted">Access your 25-minute lessons, notes, and schedule</p>
      </div>

      {isRegistered && (
        <div className="p-3 bg-success/15 border border-success/30 rounded-xl text-sm text-success font-medium text-center">
          Account created successfully! Please sign in.
        </div>
      )}

      {isReset && (
        <div role="status" className="p-3 bg-success/15 border border-success/30 rounded-xl text-sm text-success font-medium text-center">
          Password updated. Please sign in with your new password.
        </div>
      )}

      {error && (
        <div className="p-3 bg-primary/10 border border-primary/30 rounded-xl text-sm text-primary font-medium">
          {error}
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="space-y-1">
          <label className="text-sm font-bold text-ink">Username or Email</label>
          <div className="relative">
            <Mail className="w-4 h-4 absolute left-3.5 top-1/2 -translate-y-1/2 text-ink-faint" />
            <input
              type="text"
              required
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="you@example.com or username"
              className="w-full pl-10 pr-4 py-2.5 rounded-xl border border-divider text-sm text-ink bg-cream-surface focus:outline-none focus:ring-2 focus:ring-cocoa"
            />
          </div>
        </div>

        <div className="space-y-1">
          <div className="flex items-center justify-between">
            <label className="text-sm font-bold text-ink">Password</label>
            <Link href="/forgot-password" className="text-sm text-primary hover:underline">
              Forgot?
            </Link>
          </div>
          <div className="relative">
            <Lock className="w-4 h-4 absolute left-3.5 top-1/2 -translate-y-1/2 text-ink-faint" />
            <input
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              className="w-full pl-10 pr-4 py-2.5 rounded-xl border border-divider text-sm text-ink bg-cream-surface focus:outline-none focus:ring-2 focus:ring-cocoa"
            />
          </div>
        </div>

        <div className="pt-2">
          <button
            type="submit"
            disabled={submitting || isLoading}
            className="w-full py-3 bg-primary hover:bg-primary-hover text-white rounded-xl text-sm font-bold transition-all shadow-sm flex items-center justify-center gap-2 disabled:opacity-50"
          >
            {submitting ? "Signing in..." : "Sign In"} <ArrowRight className="w-4 h-4" />
          </button>
        </div>
      </form>

      <div className="pt-2 text-center text-sm text-ink-muted">
        Don't have an account?{" "}
        <Link href="/register" className="text-cocoa font-bold hover:underline">
          Create Account
        </Link>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <div className="min-h-[80vh] flex items-center justify-center px-4 py-12">
      <Suspense fallback={<div className="text-sm text-ink-muted">Loading authentication...</div>}>
        <LoginForm />
      </Suspense>
    </div>
  );
}
