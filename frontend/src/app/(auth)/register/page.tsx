"use client";

import { useState, useEffect, Suspense } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Lock, Mail, User, Globe, ArrowRight, Zap, CheckCircle2, ShieldCheck, AlertCircle } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { UserRole } from "@/types/auth";

function RegisterForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const defaultRole = (searchParams.get("role") as UserRole) || "student";

  const { register, isLoading } = useAuth();
  const [role, setRole] = useState<UserRole>(defaultRole === "teacher" ? "teacher" : "student");
  const [formData, setFormData] = useState({
    username: "",
    email: "",
    first_name: "",
    last_name: "",
    password: "",
    password_confirm: "",
    country: "JP",
    timezone: "Asia/Tokyo",
    phone_number: "",
    has_power_backup: false,
    tefl_certified: false,
  });

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});

  const fieldError = (name: string) =>
    fieldErrors[name]?.length ? (
      <p id={`err-${name}`} role="alert" className="text-sm text-error font-medium">{fieldErrors[name].join(" ")}</p>
    ) : null;

  useEffect(() => {
    try {
      const detected = Intl.DateTimeFormat().resolvedOptions().timeZone;
      if (detected) {
        setFormData((prev) => ({
          ...prev,
          timezone: detected,
          country: detected.includes("Johannesburg")
            ? "ZA"
            : detected.includes("Tokyo")
            ? "JP"
            : detected.includes("Seoul")
            ? "KR"
            : detected.includes("Europe")
            ? "DE"
            : "US",
        }));
      }
    } catch (e) {
      // Timezone detection is best-effort; the visible defaults (and editable country) remain.
      console.warn("Timezone detection failed; using defaults.", e);
    }
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (formData.password !== formData.password_confirm) {
      setError("Passwords do not match");
      return;
    }

    setSubmitting(true);
    setError("");
    setFieldErrors({});

    let res: Awaited<ReturnType<typeof register>>;
    try {
      res = await register({
        ...formData,
        role,
      });
    } catch (err) {
      setError(err instanceof Error && err.message ? err.message : "Failed to create account");
      return;
    } finally {
      setSubmitting(false);
    }

    if (res.success) {
      if (role === "teacher") {
        router.push("/teacher/dashboard");
      } else {
        router.push("/student/dashboard");
      }
    } else {
      setFieldErrors(res.fieldErrors || {});
      setError(res.error || "Failed to create account");
    }
  };

  return (
    <div className="bg-white rounded-3xl p-8 max-w-xl w-full border border-divider shadow-card space-y-6">
      <div className="text-center space-y-2">
        <div className="w-12 h-12 rounded-2xl bg-cocoa text-gold-bright font-black text-2xl flex items-center justify-center mx-auto shadow-sm font-serif">
          S
        </div>
        <h1 className="text-2xl font-extrabold text-ink font-serif">Create Your Account</h1>
        <p className="text-sm text-ink-muted">Join Sharon Online for high-focus 25-minute synchronous lessons</p>
      </div>

      {/* Role Switcher Tabs */}
      <div className="grid grid-cols-2 p-1 bg-cream-surface rounded-2xl border border-divider">
        <button
          type="button"
          onClick={() => setRole("student")}
          className={`py-2.5 rounded-xl text-sm font-bold transition-all ${
            role === "student"
              ? "bg-cocoa text-white shadow-sm"
              : "text-ink-muted hover:text-ink"
          }`}
        >
          I Want to Learn (Student)
        </button>
        <button
          type="button"
          onClick={() => setRole("teacher")}
          className={`py-2.5 rounded-xl text-sm font-bold transition-all ${
            role === "teacher"
              ? "bg-cocoa text-white shadow-sm"
              : "text-ink-muted hover:text-ink"
          }`}
        >
          I Want to Teach (South Africa)
        </button>
      </div>

      {error && (
        <div role="alert" className="flex items-start gap-2 p-3 bg-error-surface border border-error-border rounded-xl text-sm text-error font-medium">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <span>{error}</span>
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1">
            <label htmlFor="f-first-name" className="text-sm font-bold text-ink">First Name</label>
            <input id="f-first-name" aria-invalid={fieldErrors.first_name?.length ? true : undefined} aria-describedby={fieldErrors.first_name?.length ? "err-first_name" : undefined}
              type="text"
              required
              value={formData.first_name}
              onChange={(e) => setFormData({ ...formData, first_name: e.target.value })}
              className="min-h-11 w-full px-4 py-2.5 rounded-xl border border-strong text-base sm:text-sm text-ink bg-cream-surface focus:outline-none focus:ring-2 focus:ring-cocoa"
            />
            {fieldError("first_name")}
          </div>
          <div className="space-y-1">
            <label htmlFor="f-last-name" className="text-sm font-bold text-ink">Last Name</label>
            <input id="f-last-name" aria-invalid={fieldErrors.last_name?.length ? true : undefined} aria-describedby={fieldErrors.last_name?.length ? "err-last_name" : undefined}
              type="text"
              required
              value={formData.last_name}
              onChange={(e) => setFormData({ ...formData, last_name: e.target.value })}
              className="min-h-11 w-full px-4 py-2.5 rounded-xl border border-strong text-base sm:text-sm text-ink bg-cream-surface focus:outline-none focus:ring-2 focus:ring-cocoa"
            />
            {fieldError("last_name")}
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1">
            <label htmlFor="f-username" className="text-sm font-bold text-ink">Username</label>
            <input id="f-username" aria-invalid={fieldErrors.username?.length ? true : undefined} aria-describedby={fieldErrors.username?.length ? "err-username" : undefined}
              type="text"
              required
              value={formData.username}
              onChange={(e) => setFormData({ ...formData, username: e.target.value })}
              placeholder="e.g. aiko_tanaka"
              className="min-h-11 w-full px-4 py-2.5 rounded-xl border border-strong text-base sm:text-sm text-ink bg-cream-surface focus:outline-none focus:ring-2 focus:ring-cocoa"
            />
            {fieldError("username")}
          </div>
          <div className="space-y-1">
            <label htmlFor="f-email-address" className="text-sm font-bold text-ink">Email Address</label>
            <input id="f-email-address" aria-invalid={fieldErrors.email?.length ? true : undefined} aria-describedby={fieldErrors.email?.length ? "err-email" : undefined}
              type="email"
              required
              value={formData.email}
              onChange={(e) => setFormData({ ...formData, email: e.target.value })}
              placeholder="name@example.com"
              className="min-h-11 w-full px-4 py-2.5 rounded-xl border border-strong text-base sm:text-sm text-ink bg-cream-surface focus:outline-none focus:ring-2 focus:ring-cocoa"
            />
            {fieldError("email")}
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1">
            <label htmlFor="f-timezone" className="text-sm font-bold text-ink">Timezone</label>
            <input id="f-timezone"
              type="text"
              readOnly
              value={formData.timezone}
              className="min-h-11 w-full px-4 py-2.5 rounded-xl border border-strong text-base sm:text-sm text-ink bg-cream-deep/50 cursor-not-allowed"
            />
          </div>
          <div className="space-y-1">
            <label htmlFor="f-country-code" className="text-sm font-bold text-ink">Country Code</label>
            <input id="f-country-code" aria-invalid={fieldErrors.country?.length ? true : undefined} aria-describedby={fieldErrors.country?.length ? "err-country" : undefined}
              type="text"
              required
              value={formData.country}
              onChange={(e) => setFormData({ ...formData, country: e.target.value.toUpperCase() })}
              placeholder="e.g. JP, ZA, KR, DE"
              className="min-h-11 w-full px-4 py-2.5 rounded-xl border border-strong text-base sm:text-sm text-ink bg-cream-surface focus:outline-none focus:ring-2 focus:ring-cocoa"
            />
            {fieldError("country")}
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1">
            <label htmlFor="f-password" className="text-sm font-bold text-ink">Password</label>
            <input id="f-password" aria-invalid={fieldErrors.password?.length ? true : undefined} aria-describedby={fieldErrors.password?.length ? "err-password" : undefined}
              type="password"
              required
              value={formData.password}
              onChange={(e) => setFormData({ ...formData, password: e.target.value })}
              placeholder="••••••••"
              className="min-h-11 w-full px-4 py-2.5 rounded-xl border border-strong text-base sm:text-sm text-ink bg-cream-surface focus:outline-none focus:ring-2 focus:ring-cocoa"
            />
            {fieldError("password")}
          </div>
          <div className="space-y-1">
            <label htmlFor="f-confirm-password" className="text-sm font-bold text-ink">Confirm Password</label>
            <input id="f-confirm-password" aria-invalid={fieldErrors.password_confirm?.length ? true : undefined} aria-describedby={fieldErrors.password_confirm?.length ? "err-password_confirm" : undefined}
              type="password"
              required
              value={formData.password_confirm}
              onChange={(e) => setFormData({ ...formData, password_confirm: e.target.value })}
              placeholder="••••••••"
              className="min-h-11 w-full px-4 py-2.5 rounded-xl border border-strong text-base sm:text-sm text-ink bg-cream-surface focus:outline-none focus:ring-2 focus:ring-cocoa"
            />
            {fieldError("password_confirm")}
          </div>
        </div>

        {/* Tutor specific declarations */}
        {role === "teacher" && (
          <div className="p-4 bg-cream-surface rounded-2xl border border-cream-deep space-y-3">
            <div className="text-sm font-bold uppercase tracking-wider text-primary flex items-center gap-1.5">
              <Zap className="w-3.5 h-3.5" /> South African Tutor Onboarding Protocol
            </div>

            <label className="flex items-start gap-2.5 text-sm font-semibold text-ink cursor-pointer">
              <input
                type="checkbox"
                checked={formData.has_power_backup}
                onChange={(e) => setFormData({ ...formData, has_power_backup: e.target.checked })}
                className="mt-0.5 accent-cocoa"
              />
              <span>I confirm I possess a verified Solar / Inverter / UPS power backup for loadshedding stages.</span>
            </label>

            <label className="flex items-start gap-2.5 text-sm font-semibold text-ink cursor-pointer">
              <input
                type="checkbox"
                checked={formData.tefl_certified}
                onChange={(e) => setFormData({ ...formData, tefl_certified: e.target.checked })}
                className="mt-0.5 accent-cocoa"
              />
              <span>I hold a recognized TEFL / TESOL / CELTA certification (or equivalent education degree).</span>
            </label>
          </div>
        )}

        <div className="pt-2">
          <button
            type="submit"
            disabled={submitting || isLoading}
            className="w-full py-3.5 bg-cocoa hover:bg-cocoa-hover text-white rounded-xl text-sm font-bold transition-all shadow-sm flex items-center justify-center gap-2 disabled:opacity-50"
          >
            {submitting ? "Creating Account..." : role === "teacher" ? "Submit Tutor Application" : "Create Student Account"} <ArrowRight className="w-4 h-4" />
          </button>
        </div>
      </form>

      <div className="pt-2 text-center text-sm text-ink-muted">
        Already have an account?{" "}
        <Link href="/login" className="text-cocoa font-bold hover:underline">
          Sign In
        </Link>
      </div>
    </div>
  );
}

export default function RegisterPage() {
  return (
    <div className="min-h-[85vh] flex items-center justify-center px-4 py-12">
      <Suspense fallback={<div className="text-sm text-ink-muted">Loading registration...</div>}>
        <RegisterForm />
      </Suspense>
    </div>
  );
}
