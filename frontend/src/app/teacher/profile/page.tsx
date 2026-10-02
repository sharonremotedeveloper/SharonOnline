"use client";

import Link from "next/link";
import {
  ArrowLeft,
  User,
  Video,
  Award,
  DollarSign,
  Save,
  Check,
  Sparkles,
  ExternalLink,
} from "lucide-react";
import { useAuth } from "@/context/AuthContext";

export default function TeacherProfilePage() {
  const { user } = useAuth();
  const fullName = user ? [user.first_name, user.last_name].filter(Boolean).join(" ") || user.username : "";
  const initials = fullName
    .split(" ")
    .map((w) => w[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();

  return (
    <div className="min-h-screen bg-cream py-8 sm:py-12">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 space-y-8">
        {/* Navigation */}
        <div className="flex items-center justify-between">
          <Link
            href="/teacher/dashboard"
            className="inline-flex items-center gap-2 text-xs font-bold text-ink-muted hover:text-ink transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
            <span>Return to Dashboard</span>
          </Link>
          <span className="text-xs font-bold text-teal bg-teal/10 px-3 py-1 rounded-full border border-teal/20">
            Public Educator Profile
          </span>
        </div>

        {/* Header */}
        <div className="bg-white rounded-3xl p-6 sm:p-8 border border-divider shadow-card flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex items-center gap-3.5">
            <div className="w-14 h-14 rounded-2xl bg-teal/10 text-teal flex items-center justify-center font-bold text-xl shrink-0">
              {initials || <User className="w-6 h-6" />}
            </div>
            <div>
              <h1 className="text-2xl font-black text-ink font-serif">{fullName || "Your profile"}</h1>
              <p className="text-xs text-ink-muted">{user?.email}</p>
            </div>
          </div>

          <Link
            href="/tutors"
            target="_blank"
            className="px-4 py-2 bg-cream-surface hover:bg-cream-deep text-ink text-xs font-bold rounded-xl border border-divider flex items-center gap-1.5 transition-colors self-start sm:self-auto"
          >
            <span>View Public Listing</span>
            <ExternalLink className="w-3.5 h-3.5 text-teal" />
          </Link>
        </div>

        {/* Profile Edit Form */}
        <form aria-disabled="true" onSubmit={(e) => e.preventDefault()} className="bg-white rounded-3xl p-6 sm:p-10 border border-divider shadow-card space-y-6">
          <div className="p-4 rounded-2xl bg-amber-50 border border-amber-200 text-xs text-amber-900 font-bold">
            Profile editing is coming soon. Your public listing can&apos;t be changed from here yet, so the fields below
            are not editable and nothing on this page is saved.
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <label className="text-xs font-bold uppercase tracking-wider text-ink block">Full Display Name</label>
              <input
                disabled
                type="text"
                value={fullName} readOnly
                className="w-full p-3 bg-cream-surface rounded-xl border border-divider text-xs font-bold text-ink focus:outline-none focus:ring-2 focus:ring-teal/30"
                required
              />
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-bold uppercase tracking-wider text-ink block">Accent &amp; Dialect</label>
              <input
                disabled
                type="text"
                value=""
                className="w-full p-3 bg-cream-surface rounded-xl border border-divider text-xs text-ink focus:outline-none focus:ring-2 focus:ring-teal/30"
                required
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <label className="text-xs font-bold uppercase tracking-wider text-ink block">Teacher Bio &amp; Pedagogy</label>
            <textarea
              disabled
              rows={4}
              value=""
              className="w-full p-4 bg-cream-surface rounded-2xl border border-divider text-xs sm:text-sm text-ink focus:outline-none focus:ring-2 focus:ring-teal/30 leading-relaxed font-sans"
              required
            />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <label className="text-xs font-bold uppercase tracking-wider text-ink block">
                60-Second Video Reel URL (MP4)
              </label>
              <input
                disabled
                type="url"
                value=""
                className="w-full p-3 bg-cream-surface rounded-xl border border-divider text-xs font-mono text-ink focus:outline-none focus:ring-2 focus:ring-teal/30"
                required
              />
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-bold uppercase tracking-wider text-ink block">
                Price per 25-Min Lesson (USD)
              </label>
              <div className="relative">
                <DollarSign className="w-4 h-4 text-ink-muted absolute left-3 top-1/2 -translate-y-1/2" />
                <input
                disabled
                  type="text"
                  value=""
                  className="w-full pl-9 pr-4 py-3 bg-cream-surface rounded-xl border border-divider text-xs font-bold text-ink focus:outline-none focus:ring-2 focus:ring-teal/30"
                  required
                />
              </div>
            </div>
          </div>

          <div className="space-y-1.5">
            <label className="text-xs font-bold uppercase tracking-wider text-ink block">
              Teaching Specialties (Comma Separated)
            </label>
            <input
                disabled
              type="text"
              value=""
              className="w-full p-3 bg-cream-surface rounded-xl border border-divider text-xs text-ink focus:outline-none focus:ring-2 focus:ring-teal/30"
            />
          </div>

          <div className="pt-4 border-t border-divider flex items-center justify-end">
            <button
              type="submit"
              disabled
              title="Profile editing is coming soon"
              className="px-8 py-3.5 bg-teal text-white text-xs font-black rounded-2xl flex items-center gap-2 shadow-md opacity-50 cursor-not-allowed"
            >
              <Save className="w-4 h-4" />
              <span>Save Profile Details (coming soon)</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
