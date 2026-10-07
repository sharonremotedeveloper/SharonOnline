"use client";

import { ChangePasswordCard } from "@/components/account/ChangePasswordCard";
import { useEffect, useState } from "react";
import Link from "next/link";
import {
  User,
  Globe,
  Clock,
  Target,
  Sparkles,
  Save,
  CheckCircle2,
  ChevronLeft,
  BookOpen,
  Shield,
  CreditCard,
} from "lucide-react";
import { studentApi } from "@/lib/api";
import { StudentProfileData } from "@/types/student";
import { ErrorState, InlineError } from "@/components/ui/ErrorState";

const TIMEZONES = [
  { value: "Asia/Tokyo", label: "Asia/Tokyo (JST - UTC+9)" },
  { value: "Asia/Seoul", label: "Asia/Seoul (KST - UTC+9)" },
  { value: "Asia/Shanghai", label: "Asia/Shanghai (CST - UTC+8)" },
  { value: "Europe/London", label: "Europe/London (BST/GMT - UTC+0/+1)" },
  { value: "Europe/Paris", label: "Europe/Paris (CET - UTC+1/+2)" },
  { value: "Europe/Rome", label: "Europe/Rome (CET - UTC+1/+2)" },
  { value: "America/New_York", label: "America/New_York (EDT - UTC-4)" },
  { value: "America/Los_Angeles", label: "America/Los_Angeles (PDT - UTC-7)" },
  { value: "Africa/Johannesburg", label: "Africa/Johannesburg (SAST - UTC+2)" },
  { value: "Australia/Sydney", label: "Australia/Sydney (AEST - UTC+10)" },
];

const CEFR_LEVELS = [
  { value: "A1 - Beginner", label: "A1 - Beginner (Basic survival phrases)" },
  { value: "A2 - Elementary", label: "A2 - Elementary (Simple routine exchanges)" },
  { value: "B1 - Intermediate", label: "B1 - Intermediate (Conversational flow & travel)" },
  { value: "B2 - Upper-Intermediate", label: "B2 - Upper-Intermediate (Professional discussion)" },
  { value: "C1 - Advanced Fluency", label: "C1 - Advanced Fluency (Executive negotiation)" },
  { value: "C2 - Mastery", label: "C2 - Mastery (Near-native nuance & idiom mastery)" },
];

export default function StudentProfilePage() {
  const [profile, setProfile] = useState<StudentProfileData | null>(null);
  const [formData, setFormData] = useState({
    full_name: "",
    email: "",
    country: "",
    timezone: "Asia/Tokyo",
    target_level: "C1 - Advanced Fluency",
    learning_goals: "",
  });
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [savedSuccess, setSavedSuccess] = useState(false);
  const [loadError, setLoadError] = useState<unknown>(null);
  const [saveError, setSaveError] = useState<unknown>(null);
  const [reloadTick, setReloadTick] = useState(0);

  useEffect(() => {
    async function loadProfile() {
      setIsLoading(true);
      setLoadError(null);
      try {
        const data = await studentApi.getStudentProfile();
        setProfile(data);
        setFormData({
          full_name: data.full_name,
          email: data.email,
          country: data.country,
          timezone: data.timezone,
          target_level: data.target_level,
          learning_goals: data.learning_goals,
        });
      } catch (err) {
        console.error("Failed to load profile:", err);
        setProfile(null);
        setLoadError(err);
      } finally {
        setIsLoading(false);
      }
    }
    loadProfile();
  }, [reloadTick]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSaving(true);
    setSavedSuccess(false);
    setSaveError(null);

    try {
      const res = await studentApi.updateStudentProfile(formData);
      if (!res?.success) throw new Error("The server did not confirm that your profile was saved.");
      setProfile(res.profile);
      setSavedSuccess(true);
      setTimeout(() => setSavedSuccess(false), 3000);
    } catch (err) {
      console.error("Failed to save profile:", err);
      setSaveError(err);
    } finally {
      setIsSaving(false);
    }
  };

  if (isLoading) {
    return (
      <div className="max-w-2xl mx-auto py-20 text-center space-y-3">
        <div className="w-8 h-8 border-2 border-cocoa-600 border-t-transparent rounded-full animate-spin mx-auto" />
        <p className="text-sm text-ink-500">Loading student profile...</p>
      </div>
    );
  }

  if (loadError || !profile) {
    return (
      <div className="max-w-2xl mx-auto px-4 py-16">
        <ErrorState
          error={loadError ?? "We could not find your profile."}
          title="We could not load your profile"
          onRetry={() => setReloadTick((t) => t + 1)}
        />
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto px-4 py-10 space-y-8 animate-fade-in">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <Link
              href="/student/dashboard"
              className="min-w-11 justify-center min-h-11 inline-flex items-center p-1.5 text-ink-400 hover:text-ink-900 hover:bg-cream-100 rounded-xl transition-colors"
            >
              <ChevronLeft className="w-5 h-5" />
            </Link>
            <h1 className="text-2xl sm:text-3xl font-extrabold text-ink-900 tracking-tight">
              Learning Profile & Timezone
            </h1>
          </div>
          <p className="text-sm sm:text-sm text-ink-600 mt-1 pl-8">
            Manage your local timezone for seamless scheduling and customize your target CEFR language goals.
          </p>
        </div>
      </div>

      {savedSuccess && (
        <div className="bg-success-surface border border-success-border text-success-hover p-4 rounded-2xl flex items-center gap-3 text-sm font-semibold animate-scale-up">
          <CheckCircle2 className="w-5 h-5 text-success shrink-0" />
          <span>Profile updated! Your scheduled lessons and memos will reflect your new preferences.</span>
        </div>
      )}

      <InlineError id="profile-error" error={saveError} />

      {/* Profile Form */}
      <form onSubmit={handleSubmit} className="bg-white rounded-3xl border border-cream-200 shadow-sm overflow-hidden">
        <div className="p-6 sm:p-8 space-y-6">
          <h2 className="text-base font-bold text-ink-900 border-b border-cream-100 pb-3 flex items-center gap-2">
            <User className="w-4 h-4 text-cocoa-600" />
            <span>Personal Information</span>
          </h2>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label htmlFor="f-full-name" className="text-sm font-bold text-ink-500 uppercase tracking-wider block mb-1.5">
                Full Name
              </label>
              <input aria-invalid={saveError ? true : undefined} aria-describedby={saveError ? "profile-error" : undefined} id="f-full-name"
                type="text"
                value={formData.full_name}
                onChange={(e) => setFormData({ ...formData, full_name: e.target.value })}
                className="min-h-11 w-full text-base sm:text-sm rounded-xl border border-strong p-3 text-ink-900 bg-cream-50/30 focus:outline-none focus:ring-2 focus:ring-cocoa-500"
                required
              />
            </div>

            <div>
              <label htmlFor="f-email-address" className="text-sm font-bold text-ink-500 uppercase tracking-wider block mb-1.5">
                Email Address
              </label>
              <input aria-invalid={saveError ? true : undefined} aria-describedby={saveError ? "profile-error" : undefined} id="f-email-address"
                type="email"
                value={formData.email}
                onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                className="min-h-11 w-full text-base sm:text-sm rounded-xl border border-strong p-3 text-ink-900 bg-cream-50/30 focus:outline-none focus:ring-2 focus:ring-cocoa-500"
                required
              />
            </div>

            <div>
              <label htmlFor="f-country-of-residence" className="text-sm font-bold text-ink-500 uppercase tracking-wider block mb-1.5">
                Country of Residence
              </label>
              <input aria-invalid={saveError ? true : undefined} aria-describedby={saveError ? "profile-error" : undefined} id="f-country-of-residence"
                type="text"
                value={formData.country}
                onChange={(e) => setFormData({ ...formData, country: e.target.value })}
                className="min-h-11 w-full text-base sm:text-sm rounded-xl border border-strong p-3 text-ink-900 bg-cream-50/30 focus:outline-none focus:ring-2 focus:ring-cocoa-500"
                required
              />
            </div>

            <div>
              <label htmlFor="f-local-timezone-iana" className="text-sm font-bold text-ink-500 uppercase tracking-wider block mb-1.5">
                Local Timezone (IANA)
              </label>
              <select aria-invalid={saveError ? true : undefined} aria-describedby={saveError ? "profile-error" : undefined} id="f-local-timezone-iana"
                value={formData.timezone}
                onChange={(e) => setFormData({ ...formData, timezone: e.target.value })}
                className="min-h-11 w-full text-base sm:text-sm rounded-xl border border-strong p-3 text-ink-900 bg-cream-50/30 focus:outline-none focus:ring-2 focus:ring-cocoa-500"
              >
                {TIMEZONES.map((tz) => (
                  <option key={tz.value} value={tz.value}>
                    {tz.label}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <h2 className="text-base font-bold text-ink-900 border-b border-cream-100 pb-3 pt-4 flex items-center gap-2">
            <Target className="w-4 h-4 text-star" />
            <span>Curriculum & Learning Goals</span>
          </h2>

          <div className="space-y-4">
            <div>
              <label htmlFor="f-target-cefr-proficiency" className="text-sm font-bold text-ink-500 uppercase tracking-wider block mb-1.5">
                Target CEFR Proficiency
              </label>
              <select aria-invalid={saveError ? true : undefined} aria-describedby={saveError ? "profile-error" : undefined} id="f-target-cefr-proficiency"
                value={formData.target_level}
                onChange={(e) => setFormData({ ...formData, target_level: e.target.value })}
                className="min-h-11 w-full text-base sm:text-sm rounded-xl border border-strong p-3 text-ink-900 bg-cream-50/30 focus:outline-none focus:ring-2 focus:ring-cocoa-500"
              >
                {CEFR_LEVELS.map((lvl) => (
                  <option key={lvl.value} value={lvl.value}>
                    {lvl.label}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label htmlFor="f-primary-learning-objecti" className="text-sm font-bold text-ink-500 uppercase tracking-wider block mb-1.5">
                Primary Learning Objectives & Pedagogical Notes
              </label>
              <textarea aria-invalid={saveError ? true : undefined} aria-describedby={saveError ? "profile-error" : undefined} id="f-primary-learning-objecti"
                value={formData.learning_goals}
                onChange={(e) => setFormData({ ...formData, learning_goals: e.target.value })}
                rows={4}
                placeholder="Describe your current English challenges, professional speaking requirements, or specific areas you want tutors to emphasize..."
                className="w-full text-base sm:text-sm rounded-xl border border-strong p-3 text-ink-900 bg-cream-50/30 focus:outline-none focus:ring-2 focus:ring-cocoa-500"
              />
              <p className="text-sm text-ink-400 mt-1">
                Your booked tutors can view your target CEFR and learning objectives before each lesson to tailor material selection.
              </p>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="p-6 bg-cream-50 border-t border-cream-200 flex items-center justify-between">
          <span className="text-sm text-ink-500">
            Account ID: <strong className="font-mono text-ink-700">{profile.id}</strong>
          </span>

          <button
            type="submit"
            disabled={isSaving}
            className="min-h-11 inline-flex items-center gap-2 px-6 py-2.5 bg-cocoa-600 hover:bg-cocoa-700 disabled:opacity-50 text-white text-sm font-bold rounded-xl transition-colors shadow-sm"
          >
            {isSaving ? (
              <>Saving...</>
            ) : (
              <>
                <Save className="w-3.5 h-3.5" /> Save Changes
              </>
            )}
          </button>
        </div>
      </form>
      <ChangePasswordCard />
    </div>
  );
}
