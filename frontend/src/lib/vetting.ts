import { API_BASE, MOCK, liveRequest } from "./http";
import type { components } from "../types/api.generated";

export type ReviewPacket = components["schemas"]["ReviewPacket"];
export type PacketAsset = components["schemas"]["PacketAsset"];
export type PacketHistory = components["schemas"]["PacketHistory"];
export type PacketApplication = components["schemas"]["PacketApplication"];

export type RubricScores = Record<string, number>;
export type ReviewedAssetsMap = Record<string, string>;

export interface RubricValidationResult {
  passing: boolean;
  total: number;
  minTotalRequired: number;
  criteriaDeficiencies: string[];
}

export const DEFAULT_RUBRIC_CRITERIA = [
  "english_proficiency",
  "teaching_methodology",
  "tech_environment",
  "curriculum_alignment",
] as const;

export const CRITERIA_METADATA: Record<
  string,
  { label: string; description: string; guide1: string; guide5: string }
> = {
  english_proficiency: {
    label: "English Proficiency & Accent",
    description: "Neutrality, clarity, pacing, grammar accuracy, and vocal projection.",
    guide1: "Heavily accented, frequent grammar errors",
    guide5: "Flawless neutral accent, exceptional clarity",
  },
  teaching_methodology: {
    label: "Methodology & Student Engagement",
    description: "Student Talk Time (STT) ratio, elicitation, error correction, rapport.",
    guide1: "Monologue lecture, no elicitation",
    guide5: "Dynamic interaction, high STT, active correction",
  },
  tech_environment: {
    label: "Tech, Audio & Environment",
    description: "Microphone cleanliness, lighting, camera angle, speed test and backup.",
    guide1: "Muffled audio, poor lighting, echo",
    guide5: "Studio-grade audio/lighting, clean frame",
  },
  curriculum_alignment: {
    label: "Curriculum & CEFR Alignment",
    description: "Familiarity with CEFR A1-C1 stages, lesson objectives, pacing control.",
    guide1: "Disregards CEFR level, no plan",
    guide5: "Expert CEFR staging, perfect time control",
  },
};

export function formatCriterionLabel(criterion: string): string {
  if (CRITERIA_METADATA[criterion]) {
    return CRITERIA_METADATA[criterion].label;
  }
  return criterion
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

/**
 * Calculates total rubric score across all criteria.
 */
export function calculateRubricTotal(scores: RubricScores, criteria: string[]): number {
  return criteria.reduce((sum, crit) => sum + (scores[crit] || 0), 0);
}

/**
 * Validates rubric against passing thresholds:
 * - Every criterion must score >= minScore (default 3)
 * - Total score must be >= criteria.length * minScore (default 12 for 4 criteria)
 */
export function validateRubric(
  scores: RubricScores,
  criteria: string[] = DEFAULT_RUBRIC_CRITERIA as unknown as string[],
  minScorePerCriterion: number = 3
): RubricValidationResult {
  const deficiencies: string[] = [];
  let total = 0;

  for (const crit of criteria) {
    const score = scores[crit] ?? 0;
    total += score;
    if (score < minScorePerCriterion) {
      deficiencies.push(crit);
    }
  }

  const minTotalRequired = criteria.length * minScorePerCriterion;
  const passing = deficiencies.length === 0 && total >= minTotalRequired;

  return {
    passing,
    total,
    minTotalRequired,
    criteriaDeficiencies: deficiencies,
  };
}

/**
 * Builds the { [kind]: etag } map from the reviewer packet assets for approval verification.
 */
export function buildReviewedAssetsMap(assets: PacketAsset[] = []): ReviewedAssetsMap {
  const map: ReviewedAssetsMap = {};
  for (const asset of assets) {
    if (asset.kind && asset.etag) {
      map[asset.kind] = asset.etag;
    }
  }
  return map;
}

// ==========================================
// API Operations
// ==========================================

export async function fetchTeacherReviewPacket(teacherId: string): Promise<ReviewPacket> {
  const live = await liveRequest(`${API_BASE}/admin/teachers/${encodeURIComponent(teacherId)}/review-packet/`);
  if (live !== MOCK) return live as ReviewPacket;

  return {
    teacher_id: teacherId,
    full_name: "Applicant Tutor",
    status: "submitted",
    headline: "Certified ESL Educator",
    bio: "Experienced online English instructor.",
    accent: "Neutral RP",
    specialties: ["Conversational", "IELTS"],
    sla_strikes: 0,
    criteria: [...DEFAULT_RUBRIC_CRITERIA],
    min_score: 3,
    required_asset_kinds: ["avatar", "video_reel", "audio_snippet", "cv_tefl"],
    assets: [],
    history: [],
    application: {
      speed_test_download_mbps: "25.4",
      speed_test_upload_mbps: "12.8",
      speed_test_at: new Date().toISOString(),
      power_backup_confirmed: true,
      declaration_accepted_at: new Date().toISOString(),
      submitted_at: new Date().toISOString(),
    },
  };
}

export async function startTeacherReview(teacherId: string): Promise<{ success: boolean }> {
  const live = await liveRequest(`${API_BASE}/admin/teachers/${encodeURIComponent(teacherId)}/start-review/`, {
    method: "POST",
  });
  if (live !== MOCK) return { success: true };
  return { success: true };
}

export async function approveTeacherApplication(
  teacherId: string,
  rubric: RubricScores,
  reviewedAssets: ReviewedAssetsMap,
  reason: string = ""
): Promise<any> {
  const body = {
    rubric,
    reviewed_assets: reviewedAssets,
    reason: reason.trim(),
  };

  const live = await liveRequest(`${API_BASE}/admin/teachers/${encodeURIComponent(teacherId)}/approve/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (live !== MOCK) return live;

  return {
    teacher_id: teacherId,
    action: "approve",
    previous_status: "in_review",
    status: "approved",
    changed: true,
    change_ids: [],
    affected_booking_ids: [],
  };
}

export async function requestTeacherApplicationChanges(
  teacherId: string,
  reason: string,
  requestedChanges: string[]
): Promise<any> {
  if (!reason.trim()) {
    throw new Error("A clear explanation is required when requesting changes.");
  }
  if (!requestedChanges || requestedChanges.length === 0) {
    throw new Error("Please select at least one asset or item that needs to be redone.");
  }

  const body = {
    reason: reason.trim(),
    requested_changes: requestedChanges,
  };

  const live = await liveRequest(`${API_BASE}/admin/teachers/${encodeURIComponent(teacherId)}/request-changes/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (live !== MOCK) return live;

  return {
    teacher_id: teacherId,
    action: "request-changes",
    previous_status: "in_review",
    status: "changes_requested",
    changed: true,
    change_ids: [],
    affected_booking_ids: [],
  };
}

export async function rejectTeacherApplication(
  teacherId: string,
  reason: string
): Promise<any> {
  if (!reason.trim()) {
    throw new Error("A formal reason is required for rejection.");
  }

  const body = {
    reason: reason.trim(),
  };

  const live = await liveRequest(`${API_BASE}/admin/teachers/${encodeURIComponent(teacherId)}/reject/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (live !== MOCK) return live;

  return {
    teacher_id: teacherId,
    action: "reject",
    previous_status: "in_review",
    status: "rejected",
    changed: true,
    change_ids: [],
    affected_booking_ids: [],
  };
}
