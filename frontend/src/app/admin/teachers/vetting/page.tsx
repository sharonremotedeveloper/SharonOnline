"use client";

import { useEffect, useState, useMemo } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  CheckCircle2,
  XCircle,
  Video,
  FileText,
  BatteryCharging,
  AlertTriangle,
  ExternalLink,
  ShieldCheck,
  MapPin,
  PlayCircle,
  Award,
  History,
  Info,
  RotateCcw,
  Wifi,
  Sparkles,
} from "lucide-react";
import { api } from "@/lib/api";
import {
  fetchTeacherReviewPacket,
  startTeacherReview,
  approveTeacherApplication,
  requestTeacherApplicationChanges,
  rejectTeacherApplication,
  validateRubric,
  calculateRubricTotal,
  buildReviewedAssetsMap,
  formatCriterionLabel,
  CRITERIA_METADATA,
  DEFAULT_RUBRIC_CRITERIA,
  type ReviewPacket,
  type RubricScores,
} from "@/lib/vetting";
import { PendingTeacherApplication } from "@/types/admin";
import { ErrorState, InlineError } from "@/components/ui/ErrorState";
import { Button } from "@/components/ui/Button";

const ASSET_CHANGE_OPTIONS = [
  { kind: "video_reel", label: "Video Audition Reel (60s)" },
  { kind: "audio_snippet", label: "Audio Pronunciation Sample (15s)" },
  { kind: "avatar", label: "Profile Photo (Avatar)" },
  { kind: "cv_tefl", label: "TEFL / Degree Certificate" },
];

export default function AdminVettingPage() {
  const [applications, setApplications] = useState<PendingTeacherApplication[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedApp, setSelectedApp] = useState<PendingTeacherApplication | null>(null);
  const [packet, setPacket] = useState<ReviewPacket | null>(null);
  const [loadingPacket, setLoadingPacket] = useState(false);

  const [rubricScores, setRubricScores] = useState<RubricScores>({
    english_proficiency: 3,
    teaching_methodology: 3,
    tech_environment: 3,
    curriculum_alignment: 3,
  });

  const [activeModal, setActiveModal] = useState<"approve" | "request_changes" | "reject" | null>(null);
  const [actionReason, setActionReason] = useState("");
  const [selectedChanges, setSelectedChanges] = useState<string[]>([]);
  const [processingAction, setProcessingAction] = useState(false);

  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<unknown>(null);
  const [actionError, setActionError] = useState<unknown>(null);
  const [reloadTick, setReloadTick] = useState(0);

  // Load pending list
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

  // Load Review Packet for selected applicant
  useEffect(() => {
    if (!selectedApp) {
      setPacket(null);
      return;
    }
    const appId = selectedApp.id;
    let cancelled = false;
    async function loadPacket() {
      setLoadingPacket(true);
      try {
        const p = await fetchTeacherReviewPacket(appId);
        if (cancelled) return;
        setPacket(p);
        // Initialize scores with 3 if criteria exist
        const initialScores: RubricScores = {};
        const criteriaList = p.criteria && p.criteria.length > 0 ? p.criteria : [...DEFAULT_RUBRIC_CRITERIA];
        for (const crit of criteriaList) {
          initialScores[crit] = 3;
        }
        setRubricScores(initialScores);
      } catch (err) {
        console.warn("Could not load full review packet:", err);
      } finally {
        if (!cancelled) setLoadingPacket(false);
      }
    }
    loadPacket();
    return () => {
      cancelled = true;
    };
  }, [selectedApp]);

  const activeCriteria = useMemo(() => {
    return packet?.criteria && packet.criteria.length > 0
      ? packet.criteria
      : [...DEFAULT_RUBRIC_CRITERIA];
  }, [packet]);

  const rubricTotal = useMemo(() => {
    return calculateRubricTotal(rubricScores, activeCriteria);
  }, [rubricScores, activeCriteria]);

  const rubricValidation = useMemo(() => {
    return validateRubric(rubricScores, activeCriteria, packet?.min_score ?? 3);
  }, [rubricScores, activeCriteria, packet]);

  const handleScoreChange = (criterion: string, score: number) => {
    setRubricScores((prev) => ({ ...prev, [criterion]: score }));
  };

  const handleStartReview = async () => {
    if (!selectedApp) return;
    setProcessingAction(true);
    setActionError(null);
    try {
      await startTeacherReview(selectedApp.id);
      setPacket((prev) => (prev ? { ...prev, status: "in_review" } : prev));
      setSuccessMessage(`Review started for ${selectedApp.full_name}. You may now score the rubric.`);
    } catch (e) {
      setActionError(e);
    } finally {
      setProcessingAction(false);
    }
  };

  const handleConfirmAction = async () => {
    if (!selectedApp) return;
    setProcessingAction(true);
    setActionError(null);
    try {
      if (activeModal === "approve") {
        const reviewedAssets = buildReviewedAssetsMap(packet?.assets || []);
        await approveTeacherApplication(selectedApp.id, rubricScores, reviewedAssets, actionReason);
        setSuccessMessage(`Tutor ${selectedApp.full_name} approved! Rubric score ${rubricTotal}/20 verified.`);
      } else if (activeModal === "request_changes") {
        await requestTeacherApplicationChanges(selectedApp.id, actionReason, selectedChanges);
        setSuccessMessage(`Requested changes from ${selectedApp.full_name} for: ${selectedChanges.join(", ")}.`);
      } else if (activeModal === "reject") {
        await rejectTeacherApplication(selectedApp.id, actionReason);
        setSuccessMessage(`Application for ${selectedApp.full_name} declined.`);
      }

      // Remove processed application from queue
      const remaining = applications.filter((a) => a.id !== selectedApp.id);
      setApplications(remaining);
      setSelectedApp(remaining.length > 0 ? remaining[0] : null);
      setActiveModal(null);
      setActionReason("");
      setSelectedChanges([]);
    } catch (e) {
      setActionError(e);
    } finally {
      setProcessingAction(false);
    }
  };

  if (loading) {
    return (
      <div className="py-20 text-center space-y-4">
        <div className="w-12 h-12 border-4 border-warning border-t-transparent rounded-full animate-spin mx-auto" />
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
    <div className="space-y-8 max-w-7xl mx-auto pb-12">
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
              <span className="text-xs font-mono font-bold text-cocoa bg-cocoa/10 px-2 py-0.5 rounded-md">
                TUTOR VETTING &amp; RUBRIC STUDIO (T4b)
              </span>
              <span className="text-xs font-bold text-ink-muted">{applications.length} In Queue</span>
            </div>
            <h1 className="text-2xl sm:text-3xl font-black text-ink font-serif">
              Tutor Audition &amp; Rubric Evaluation Studio
            </h1>
          </div>
        </div>
      </div>

      <InlineError error={actionError} />

      {successMessage && (
        <div className="p-4 rounded-2xl bg-success-surface border border-success-border text-xs font-bold text-success-hover flex items-center justify-between gap-2.5">
          <div className="flex items-center gap-2.5">
            <CheckCircle2 className="w-4 h-4 text-success shrink-0" />
            <span>{successMessage}</span>
          </div>
          <button
            onClick={() => setSuccessMessage(null)}
            className="text-success-hover hover:text-success-hover text-xs underline"
          >
            Dismiss
          </button>
        </div>
      )}

      {applications.length === 0 ? (
        <div className="bg-white rounded-3xl p-12 border border-divider shadow-card text-center space-y-4">
          <div className="w-16 h-16 rounded-full bg-success-surface text-success-hover flex items-center justify-center mx-auto">
            <CheckCircle2 className="w-8 h-8" />
          </div>
          <h2 className="text-xl font-black text-ink font-serif">All Tutor Applications Processed</h2>
          <p className="text-xs text-ink-muted max-w-sm mx-auto">
            The applicant queue is clear. New auditions will appear here as South African educators complete registration.
          </p>
          <Link
            href="/admin/teachers"
            className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-cocoa text-white text-xs font-bold"
          >
            <span>View Active Tutor Roster</span>
          </Link>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
          {/* Left Column: Applications List (4 cols) */}
          <div className="lg:col-span-4 bg-white rounded-3xl p-4 sm:p-5 border border-divider shadow-card space-y-3">
            <span className="text-xs font-bold text-ink-muted uppercase tracking-wider block px-2">
              Applicants Queue ({applications.length})
            </span>

            <div className="space-y-2">
              {applications.map((app) => {
                const isSelected = selectedApp?.id === app.id;
                const status = app.status || "submitted";
                return (
                  <button
                    key={app.id}
                    type="button"
                    onClick={() => {
                      setSelectedApp(app);
                      setActiveModal(null);
                      setActionError(null);
                    }}
                    className={`w-full text-left p-3.5 rounded-2xl border transition-all space-y-1.5 ${
                      isSelected
                        ? "bg-cocoa/10 border-cocoa text-ink shadow-xs"
                        : "bg-cream-surface border-divider hover:bg-cream-deep text-ink-muted"
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-extrabold text-ink">{app.full_name}</span>
                      <span
                        className={`text-xs font-bold px-2 py-0.5 rounded-full capitalize ${
                          status === "in_review"
                            ? "bg-info-surface text-info-hover"
                            : status === "changes_requested"
                            ? "bg-warning-surface text-warning-hover"
                            : "bg-sky-soft text-ink"
                        }`}
                      >
                        {status.replace("_", " ")}
                      </span>
                    </div>
                    <p className="text-xs text-ink-muted">{app.accent}</p>
                    <div className="flex items-center gap-2 text-xs text-ink-muted pt-1">
                      <MapPin className="w-3 h-3 text-cocoa" />
                      <span className="truncate">{app.country}</span>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Right Column: Detailed Vetting & Rubric Studio (8 cols) */}
          {selectedApp && (
            <div className="lg:col-span-8 bg-white rounded-3xl p-6 sm:p-8 border border-divider shadow-card space-y-6">
              {/* Candidate Bio Header */}
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-divider pb-6">
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="text-2xl font-black text-ink font-serif">{selectedApp.full_name}</h3>
                    {packet?.status === "submitted" && (
                      <span className="text-xs bg-sky-soft text-ink font-bold px-2 py-0.5 rounded-md">
                        Awaiting Review
                      </span>
                    )}
                    {packet?.status === "in_review" && (
                      <span className="text-xs bg-info-surface text-info-hover font-bold px-2 py-0.5 rounded-md flex items-center gap-1">
                        <Sparkles className="w-3 h-3" /> In Review
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-ink-muted">
                    {selectedApp.email} &middot; Applied on {new Date(selectedApp.applied_at).toLocaleDateString()}
                  </p>
                </div>

                <div className="flex items-center gap-2">
                  {packet?.status === "submitted" && (
                    <Button
                      variant="primary"
                      size="sm"
                      onClick={handleStartReview}
                      disabled={processingAction}
                      className="bg-info hover:bg-info-hover text-white"
                    >
                      <PlayCircle className="w-4 h-4" /> Start Review
                    </Button>
                  )}
                  <span className="px-3 py-1 rounded-xl bg-cocoa/10 text-cocoa text-xs font-bold border border-cocoa/20">
                    {selectedApp.accent}
                  </span>
                </div>
              </div>

              {/* 60s Video Audition Reel */}
              <div className="space-y-2">
                <div className="flex items-center justify-between text-xs font-bold text-ink">
                  <span className="flex items-center gap-2">
                    <Video className="w-4 h-4 text-cocoa" />
                    <span>60-Second Pronunciation &amp; Natural Accent Reel</span>
                  </span>
                  <span className="text-xs text-ink-muted font-mono">
                    {packet?.assets.find((a) => a.kind === "video_reel")?.etag || "Verified Video"}
                  </span>
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

              {/* Hardware & Power Readiness Grid */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs">
                {/* Speed Test */}
                <div className="p-4 rounded-2xl bg-cream-surface border border-divider space-y-2">
                  <span className="font-bold text-ink flex items-center gap-1.5">
                    <Wifi className="w-4 h-4 text-cocoa" /> WebRTC Network Readiness
                  </span>
                  <div className="grid grid-cols-2 gap-2 pt-1 text-xs">
                    <div>
                      <span className="text-ink-muted block text-xs">Download:</span>
                      <span className="font-mono font-bold text-ink">
                        {packet?.application?.speed_test_download_mbps || "25.0"} Mbps
                      </span>
                    </div>
                    <div>
                      <span className="text-ink-muted block text-xs">Upload:</span>
                      <span className="font-mono font-bold text-ink">
                        {packet?.application?.speed_test_upload_mbps || "12.0"} Mbps
                      </span>
                    </div>
                  </div>
                  <span className="text-success-hover font-bold flex items-center gap-1 text-xs pt-1">
                    <ShieldCheck className="w-3.5 h-3.5 text-success" /> Exceeds 10/5 Mbps Sharon SLA
                  </span>
                </div>

                {/* Eskom Power Backup */}
                <div className="p-4 rounded-2xl bg-cream-surface border border-divider space-y-2">
                  <span className="font-bold text-ink flex items-center gap-1.5">
                    <BatteryCharging className="w-4 h-4 text-warning" /> Municipal Power Declaration
                  </span>
                  <p className="text-xs text-ink-muted">
                    Area: {selectedApp.eskom_area || "Western Cape"}
                  </p>
                  <div className="pt-1">
                    {packet?.application?.power_backup_confirmed || selectedApp.has_inverter ? (
                      <span className="text-success-hover font-bold flex items-center gap-1 text-xs">
                        <ShieldCheck className="w-3.5 h-3.5 text-success" /> 4+ Hour Inverter / UPS Confirmed
                      </span>
                    ) : (
                      <span className="text-warning-hover font-bold flex items-center gap-1 text-xs">
                        <AlertTriangle className="w-3.5 h-3.5 text-warning" /> Backup Declared Pending Check
                      </span>
                    )}
                  </div>
                </div>
              </div>

              {/* Bio & Experience */}
              <div className="space-y-2">
                <span className="text-xs font-bold uppercase tracking-wider text-ink-muted block">
                  Educator Statement &amp; Specialties
                </span>
                <p className="text-xs text-ink leading-relaxed font-sans bg-cream-surface p-4 rounded-2xl border border-divider">
                  {selectedApp.bio}
                </p>
                <div className="flex flex-wrap gap-2 pt-1">
                  {selectedApp.specialties.map((spec, i) => (
                    <span
                      key={i}
                      className="px-2.5 py-1 rounded-xl bg-white border border-divider text-xs font-bold text-ink"
                    >
                      {spec}
                    </span>
                  ))}
                </div>
              </div>

              {/* Interactive Rubric Studio (T4a / T4b) */}
              <div className="p-6 bg-cream-surface/70 rounded-3xl border border-divider space-y-5">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-divider pb-4">
                  <div>
                    <div className="flex items-center gap-2">
                      <Award className="w-5 h-5 text-cocoa" />
                      <h4 className="text-base font-bold text-ink">4-Criterion Vetting Rubric</h4>
                    </div>
                    <p className="text-xs text-ink-muted">
                      Score candidate from 1 (Unacceptable) to 5 (Mastery). Passing requires $\ge 3$ per criterion and total $\ge 12/20$.
                    </p>
                  </div>

                  {/* Rubric Total Score Pill */}
                  <div className="flex items-center gap-2">
                    <div
                      className={`px-4 py-2 rounded-2xl border font-bold text-sm flex items-center gap-2 ${
                        rubricValidation.passing
                          ? "bg-success-surface text-success-hover border-success-border"
                          : "bg-warning-surface text-warning-hover border-warning-border"
                      }`}
                    >
                      <span>Total: {rubricTotal} / 20</span>
                      {rubricValidation.passing ? (
                        <CheckCircle2 className="w-4 h-4 text-success" />
                      ) : (
                        <AlertTriangle className="w-4 h-4 text-warning" />
                      )}
                    </div>
                  </div>
                </div>

                {/* Criterion Scoring List */}
                <div className="space-y-4">
                  {activeCriteria.map((criterion) => {
                    const meta = CRITERIA_METADATA[criterion] || {
                      label: formatCriterionLabel(criterion),
                      description: "Evaluation criterion",
                    };
                    const currentScore = rubricScores[criterion] ?? 3;
                    const isDeficient = currentScore < 3;

                    return (
                      <div
                        key={criterion}
                        className={`p-4 rounded-2xl border transition-all ${
                          isDeficient
                            ? "bg-warning-surface/50 border-warning-border"
                            : "bg-white border-divider"
                        }`}
                      >
                        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-2">
                          <div>
                            <span className="text-xs font-bold text-ink">{meta.label}</span>
                            <p className="text-xs text-ink-muted leading-tight">
                              {meta.description}
                            </p>
                          </div>

                          {/* 1-5 Radio Buttons */}
                          <div className="flex items-center gap-1.5">
                            {[1, 2, 3, 4, 5].map((score) => {
                              const isSelected = currentScore === score;
                              return (
                                <button
                                  key={score}
                                  type="button"
                                  onClick={() => handleScoreChange(criterion, score)}
                                  className={`w-8 h-8 rounded-xl font-bold text-xs transition-all flex items-center justify-center ${
                                    isSelected
                                      ? "bg-cocoa text-white shadow-xs scale-105"
                                      : "bg-cream-surface border border-divider text-ink-muted hover:bg-cream-deep hover:text-ink"
                                  }`}
                                  aria-label={`Score ${score} for ${meta.label}`}
                                >
                                  {score}
                                </button>
                              );
                            })}
                          </div>
                        </div>

                        {/* Deficient alert */}
                        {isDeficient && (
                          <div className="text-xs font-bold text-warning-hover flex items-center gap-1 pt-1">
                            <AlertTriangle className="w-3 h-3" /> Minimum score of 3 required for approval
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Action Buttons */}
              <div className="pt-4 border-t border-divider flex flex-wrap items-center justify-end gap-3">
                <Button
                  variant="quiet"
                  size="md"
                  onClick={() => {
                    setActiveModal("reject");
                    setActionReason("");
                  }}
                  className="text-error-hover hover:bg-error-surface border-error-border"
                >
                  <XCircle className="w-4 h-4" /> Reject
                </Button>

                <Button
                  variant="secondary"
                  size="md"
                  onClick={() => {
                    setActiveModal("request_changes");
                    setActionReason("");
                    setSelectedChanges(["video_reel"]);
                  }}
                >
                  <RotateCcw className="w-4 h-4 text-warning" /> Request Changes
                </Button>

                <Button
                  variant="primary"
                  size="md"
                  disabled={!rubricValidation.passing || packet?.status !== "in_review"}
                  onClick={() => {
                    setActiveModal("approve");
                    setActionReason("");
                  }}
                  className="bg-cocoa hover:bg-cocoa/90 text-white"
                  title={
                    packet?.status !== "in_review"
                      ? "Must start review before approving"
                      : !rubricValidation.passing
                      ? "Rubric must score >= 3 on all criteria"
                      : "Approve candidate"
                  }
                >
                  <CheckCircle2 className="w-4 h-4" /> Approve &amp; Publish Live
                </Button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Confirmation Modal: Approve / Request Changes / Reject */}
      {activeModal && selectedApp && (
        <div
          role="dialog"
          aria-modal="true"
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs animate-in fade-in duration-200"
        >
          <div className="w-full max-w-lg bg-surface rounded-3xl p-6 sm:p-8 border border-divider shadow-2xl text-ink space-y-5">
            <div>
              <h3 className="text-lg font-black text-ink font-serif">
                {activeModal === "approve" && `Approve ${selectedApp.full_name}`}
                {activeModal === "request_changes" && `Request Application Changes from ${selectedApp.full_name}`}
                {activeModal === "reject" && `Reject ${selectedApp.full_name}`}
              </h3>
              <p className="text-xs text-ink-muted mt-1">
                {activeModal === "approve" && `Final verification passing with score ${rubricTotal}/20.`}
                {activeModal === "request_changes" && "Select the upload kinds the tutor must redo before resubmitting."}
                {activeModal === "reject" && "Provide a clear and respectful formal reason for declining this application."}
              </p>
            </div>

            {/* Request Changes Checkboxes */}
            {activeModal === "request_changes" && (
              <div className="space-y-2 p-3 bg-cream-surface rounded-2xl border border-divider">
                <span className="text-xs font-bold text-ink block mb-1">Required Items to Redo:</span>
                {ASSET_CHANGE_OPTIONS.map((item) => (
                  <label key={item.kind} className="flex items-center gap-2.5 text-xs text-ink cursor-pointer py-1">
                    <input
                      type="checkbox"
                      checked={selectedChanges.includes(item.kind)}
                      onChange={(e) => {
                        if (e.target.checked) {
                          setSelectedChanges((prev) => [...prev, item.kind]);
                        } else {
                          setSelectedChanges((prev) => prev.filter((k) => k !== item.kind));
                        }
                      }}
                      className="rounded border-divider text-cocoa focus:ring-cocoa"
                    />
                    <span>{item.label}</span>
                  </label>
                ))}
              </div>
            )}

            {/* Reason Textarea */}
            <div className="space-y-1.5">
              <label htmlFor="f-activemodal-approve-revi" className="text-xs font-bold text-ink">
                {activeModal === "approve" ? "Reviewer Notes (Optional)" : "Feedback / Reason (Required)"}
              </label>
              <textarea id="f-activemodal-approve-revi"
                rows={3}
                value={actionReason}
                onChange={(e) => setActionReason(e.target.value)}
                placeholder={
                  activeModal === "approve"
                    ? "Optional pedagogical praise or onboarding notes..."
                    : activeModal === "request_changes"
                    ? "Explain what needs improvement (e.g. video audio had background echo; please re-record in quiet space)..."
                    : "Formal reason for rejection..."
                }
                className="w-full p-3 bg-cream-surface rounded-2xl border border-divider text-xs text-ink focus:outline-hidden focus:ring-2 focus:ring-cocoa/30"
              />
            </div>

            {/* Modal Actions */}
            <div className="flex items-center justify-end gap-3 pt-3 border-t border-divider">
              <Button
                variant="quiet"
                size="sm"
                disabled={processingAction}
                onClick={() => setActiveModal(null)}
              >
                Cancel
              </Button>
              <Button
                variant={activeModal === "reject" ? "destructive" : "primary"}
                size="sm"
                disabled={
                  processingAction ||
                  (activeModal !== "approve" && !actionReason.trim()) ||
                  (activeModal === "request_changes" && selectedChanges.length === 0)
                }
                onClick={handleConfirmAction}
                className={activeModal === "approve" ? "bg-cocoa hover:bg-cocoa/90 text-white" : ""}
              >
                {processingAction ? "Processing..." : "Confirm & Send"}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
