"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  UserCheck,
  CheckCircle2,
  XCircle,
  Video,
  FileText,
  BatteryCharging,
  AlertTriangle,
  ExternalLink,
  ShieldCheck,
  Sparkles,
  MapPin,
} from "lucide-react";
import { api } from "@/lib/api";
import { PendingTeacherApplication } from "@/types/admin";
import { ErrorState, InlineError } from "@/components/ui/ErrorState";

export default function AdminVettingPage() {
  const [applications, setApplications] = useState<PendingTeacherApplication[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedApp, setSelectedApp] = useState<PendingTeacherApplication | null>(null);
  const [processingId, setProcessingId] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<unknown>(null);
  const [actionError, setActionError] = useState<unknown>(null);
  const [reloadTick, setReloadTick] = useState(0);
  const [pendingDecision, setPendingDecision] = useState<{ id: string; approve: boolean } | null>(null);
  const [rejectionReason, setRejectionReason] = useState("");

  useEffect(() => {
    let cancelled = false;
    async function loadApplications() {
      setLoading(true);
      setLoadError(null);
      try {
        const list = await api.getPendingTeachers();
        if (cancelled) return;
        setApplications(list);
        setSelectedApp(list.length > 0 ? list[0] : null);
      } catch (e) {
        console.error("Failed to load vetting applications:", e);
        if (!cancelled) {
          setApplications([]);
          setSelectedApp(null);
          setLoadError(e);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    loadApplications();
    return () => {
      cancelled = true;
    };
  }, [reloadTick]);

  // Publishing/declining a tutor is a consequential action: it only runs after an explicit confirm, and the
  // application is only removed from the queue once the server accepted the decision.
  const handleVerify = async (id: string, isApproved: boolean) => {
    const target = applications.find((a) => a.id === id);
    if (!isApproved && !rejectionReason.trim()) {
      setActionError("Please give the applicant a short reason for the rejection.");
      return;
    }
    setProcessingId(id);
    setSuccessMessage(null);
    setActionError(null);
    try {
      await api.verifyTeacher(id, isApproved, isApproved ? undefined : rejectionReason.trim());
      setSuccessMessage(
        isApproved
          ? `Tutor ${target?.full_name} has been approved and published to public search.`
          : `Application for ${target?.full_name} has been declined.`
      );

      const remaining = applications.filter((a) => a.id !== id);
      setApplications(remaining);
      setSelectedApp(remaining.length > 0 ? remaining[0] : null);
      setPendingDecision(null);
      setRejectionReason("");
    } catch (e) {
      console.error("Failed to verify teacher:", e);
      setActionError(e);
    } finally {
      setProcessingId(null);
    }
  };

  if (loading) {
    return (
      <div className="py-20 text-center space-y-4">
        <div className="w-12 h-12 border-4 border-amber-500 border-t-transparent rounded-full animate-spin mx-auto" />
        <p className="text-sm font-bold text-ink-muted">Loading pending tutor audition reels...</p>
      </div>
    );
  }

  if (loadError) {
    return (
      <div className="py-20">
        <ErrorState
          error={loadError}
          title="We could not load the pending applications"
          onRetry={() => setReloadTick((t) => t + 1)}
        />
      </div>
    );
  }

  return (
    <div className="space-y-8 max-w-7xl mx-auto">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <Link
            href="/admin/dashboard"
            className="p-2.5 rounded-xl bg-white border border-divider text-ink-muted hover:text-ink hover:bg-cream-surface transition-colors shadow-xs"
          >
            <ArrowLeft className="w-4 h-4" />
          </Link>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-mono font-bold text-amber-700 bg-amber-100 px-2 py-0.5 rounded-md">
                APPLICANT AUDITION RADAR
              </span>
              <span className="text-xs font-bold text-ink-muted">{applications.length} Pending Review</span>
            </div>
            <h1 className="text-2xl sm:text-3xl font-black text-ink font-serif">
              Tutor Video Audition &amp; Vetting Studio
            </h1>
          </div>
        </div>
      </div>

      <InlineError error={actionError} />

      {successMessage && (
        <div className="p-4 rounded-2xl bg-emerald-50 border border-emerald-300 text-xs font-bold text-emerald-950 flex items-center gap-2.5">
          <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
          <span>{successMessage}</span>
        </div>
      )}

      {applications.length === 0 ? (
        <div className="bg-white rounded-3xl p-12 border border-divider shadow-card text-center space-y-4">
          <div className="w-16 h-16 rounded-full bg-emerald-100 text-emerald-700 flex items-center justify-center mx-auto">
            <CheckCircle2 className="w-8 h-8" />
          </div>
          <h2 className="text-xl font-black text-ink font-serif">All Tutor Applications Processed</h2>
          <p className="text-xs text-ink-muted max-w-sm mx-auto">
            The applicant queue is clear. New auditions will appear here as South African educators complete registration.
          </p>
          <Link
            href="/admin/teachers"
            className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-teal text-white text-xs font-bold"
          >
            <span>View Active Tutor Roster</span>
          </Link>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
          {/* Left Column: Applications List (4 cols) */}
          <div className="lg:col-span-4 bg-white rounded-3xl p-4 sm:p-5 border border-divider shadow-card space-y-3">
            <span className="text-xs font-bold text-ink-muted uppercase tracking-wider block px-2">
              Pending Candidates ({applications.length})
            </span>

            <div className="space-y-2">
              {applications.map((app) => {
                const isSelected = selectedApp?.id === app.id;
                return (
                  <button
                    key={app.id}
                    type="button"
                    onClick={() => {
                      setSelectedApp(app);
                      setPendingDecision(null);
                      setActionError(null);
                    }}
                    className={`w-full text-left p-3.5 rounded-2xl border transition-all space-y-1.5 ${
                      isSelected
                        ? "bg-teal/10 border-teal text-ink shadow-xs"
                        : "bg-cream-surface border-divider hover:bg-cream-deep text-ink-muted"
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-extrabold text-ink">{app.full_name}</span>
                      <span className="text-[10px] font-bold text-amber-700 bg-amber-100 px-2 py-0.5 rounded-full">
                        Pending
                      </span>
                    </div>
                    <p className="text-[11px] text-ink-muted">{app.accent}</p>
                    <div className="flex items-center gap-2 text-[10px] text-ink-muted pt-1">
                      <MapPin className="w-3 h-3 text-teal" />
                      <span className="truncate">{app.country}</span>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Right Column: Detailed Vetting Studio (8 cols) */}
          {selectedApp && (
            <div className="lg:col-span-8 bg-white rounded-3xl p-6 sm:p-8 border border-divider shadow-card space-y-6">
              {/* Candidate Bio Bar */}
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-divider pb-6">
                <div>
                  <h3 className="text-2xl font-black text-ink font-serif">{selectedApp.full_name}</h3>
                  <p className="text-xs text-ink-muted">
                    {selectedApp.email} &middot; Applied on {new Date(selectedApp.applied_at).toLocaleDateString()}
                  </p>
                </div>

                <div className="flex items-center gap-2">
                  <span className="px-3 py-1 rounded-xl bg-teal/10 text-teal text-xs font-bold border border-teal/20">
                    {selectedApp.accent}
                  </span>
                </div>
              </div>

              {/* 60s Video Audition Player */}
              <div className="space-y-2">
                <div className="flex items-center justify-between text-xs font-bold text-ink">
                  <span className="flex items-center gap-2">
                    <Video className="w-4 h-4 text-teal" />
                    <span>60-Second Pronunciation &amp; Natural Accent Reel</span>
                  </span>
                  <span className="text-[11px] text-ink-muted font-normal">HD Cloudflare Stream</span>
                </div>

                <div className="aspect-video rounded-2xl bg-ink overflow-hidden border border-divider">
                  <video
                    src={selectedApp.video_url}
                    controls
                    playsInline
                    className="w-full h-full object-cover"
                  />
                </div>
              </div>

              {/* Credentials & Eskom Declaration Grid */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs">
                {/* TEFL Verification */}
                <div className="p-4 rounded-2xl bg-cream-surface border border-divider space-y-2">
                  <span className="font-bold text-ink flex items-center gap-1.5">
                    <FileText className="w-4 h-4 text-teal" /> TEFL / CELTA Certification
                  </span>
                  <p className="text-[11px] text-ink-muted">120-Hour Accredited ESL Teaching Certificate</p>
                  {selectedApp.tefl_certificate_url && (
                    <a
                      href={selectedApp.tefl_certificate_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1.5 text-xs font-bold text-teal hover:underline pt-1"
                    >
                      <span>Preview Certificate PDF</span>
                      <ExternalLink className="w-3 h-3" />
                    </a>
                  )}
                </div>

                {/* Power Guard Check */}
                <div className="p-4 rounded-2xl bg-cream-surface border border-divider space-y-2">
                  <span className="font-bold text-ink flex items-center gap-1.5">
                    <BatteryCharging className="w-4 h-4 text-amber-600" /> Municipal Power Declaration
                  </span>
                  <p className="text-[11px] text-ink-muted">Area: {selectedApp.eskom_area || "Not provided"}</p>
                  <div className="pt-1">
                    {selectedApp.has_inverter ? (
                      <span className="text-emerald-800 font-bold flex items-center gap-1 text-[11px]">
                        <ShieldCheck className="w-3.5 h-3.5 text-emerald-600" /> 4+ Hour Inverter Backup Confirmed
                      </span>
                    ) : (
                      <span className="text-amber-800 font-bold flex items-center gap-1 text-[11px]">
                        <AlertTriangle className="w-3.5 h-3.5 text-amber-600" /> No Inverter Backup Declared
                      </span>
                    )}
                  </div>
                </div>
              </div>

              {/* Bio & Specialties */}
              <div className="space-y-3">
                <span className="text-xs font-bold uppercase tracking-wider text-ink-muted block">
                  Educator Statement &amp; Experience
                </span>
                <p className="text-xs text-ink leading-relaxed font-sans bg-cream-surface p-4 rounded-2xl border border-divider">
                  {selectedApp.bio}
                </p>

                <div className="flex flex-wrap gap-2 pt-1">
                  {selectedApp.specialties.map((spec, i) => (
                    <span
                      key={i}
                      className="px-2.5 py-1 rounded-xl bg-white border border-divider text-[11px] font-bold text-ink"
                    >
                      {spec}
                    </span>
                  ))}
                </div>
              </div>

              {/* Action Buttons */}
              {pendingDecision?.id === selectedApp.id ? (
                <div className="pt-6 border-t border-divider space-y-3">
                  <p className="text-xs font-bold text-ink">
                    {pendingDecision.approve
                      ? `Approve ${selectedApp.full_name} and publish their profile to public search?`
                      : `Reject ${selectedApp.full_name}'s application?`}
                  </p>
                  {!pendingDecision.approve && (
                    <textarea
                      rows={3}
                      value={rejectionReason}
                      onChange={(e) => setRejectionReason(e.target.value)}
                      placeholder="Feedback for the applicant (required)..."
                      className="w-full p-3 bg-cream-surface rounded-xl border border-divider text-xs text-ink focus:outline-none focus:ring-2 focus:ring-teal/30"
                    />
                  )}
                  <div className="flex items-center justify-end gap-3">
                    <button
                      type="button"
                      disabled={processingId === selectedApp.id}
                      onClick={() => {
                        setPendingDecision(null);
                        setActionError(null);
                      }}
                      className="px-5 py-2.5 rounded-2xl bg-white border border-divider text-xs font-bold text-ink disabled:opacity-50"
                    >
                      Cancel
                    </button>
                    <button
                      type="button"
                      disabled={processingId === selectedApp.id}
                      onClick={() => handleVerify(selectedApp.id, pendingDecision.approve)}
                      className={`px-6 py-2.5 rounded-2xl text-white text-xs font-black disabled:opacity-50 ${
                        pendingDecision.approve ? "bg-teal hover:bg-teal-hover" : "bg-rose-600 hover:bg-rose-700"
                      }`}
                    >
                      {processingId === selectedApp.id
                        ? "Submitting..."
                        : pendingDecision.approve
                        ? "Confirm approval"
                        : "Confirm rejection"}
                    </button>
                  </div>
                </div>
              ) : (
                <div className="pt-6 border-t border-divider flex items-center justify-end gap-3">
                  <button
                    type="button"
                    onClick={() => {
                      setPendingDecision({ id: selectedApp.id, approve: false });
                      setActionError(null);
                    }}
                    className="px-6 py-3 rounded-2xl border border-rose-300 text-rose-700 hover:bg-rose-50 text-xs font-bold flex items-center gap-2 transition-colors"
                  >
                    <XCircle className="w-4 h-4" />
                    <span>Reject with Feedback</span>
                  </button>

                  <button
                    type="button"
                    onClick={() => {
                      setPendingDecision({ id: selectedApp.id, approve: true });
                      setActionError(null);
                    }}
                    className="px-8 py-3.5 rounded-2xl bg-teal hover:bg-teal-hover text-white text-xs font-black flex items-center gap-2 shadow-md transition-all hover:scale-[1.01]"
                  >
                    <CheckCircle2 className="w-4 h-4" />
                    <span>Approve &amp; Publish Live</span>
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
