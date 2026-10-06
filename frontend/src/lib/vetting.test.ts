import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  DEFAULT_RUBRIC_CRITERIA,
  buildReviewedAssetsMap,
  calculateRubricTotal,
  formatCriterionLabel,
  validateRubric,
  type PacketAsset,
} from "./vetting";

describe("vetting rubric helpers", () => {
  it("formats criterion labels cleanly", () => {
    assert.equal(formatCriterionLabel("english_proficiency"), "English Proficiency & Accent");
    assert.equal(formatCriterionLabel("teaching_methodology"), "Methodology & Student Engagement");
    assert.equal(formatCriterionLabel("tech_environment"), "Tech, Audio & Environment");
    assert.equal(formatCriterionLabel("curriculum_alignment"), "Curriculum & CEFR Alignment");
    assert.equal(formatCriterionLabel("custom_criterion_name"), "Custom Criterion Name");
  });

  it("calculates rubric total across criteria", () => {
    const criteria = [...DEFAULT_RUBRIC_CRITERIA];
    const scores = {
      english_proficiency: 4,
      teaching_methodology: 3,
      tech_environment: 5,
      curriculum_alignment: 4,
    };
    assert.equal(calculateRubricTotal(scores, criteria), 16);
  });

  it("validates passing rubric (all >= 3 and total >= 12)", () => {
    const criteria = [...DEFAULT_RUBRIC_CRITERIA];
    const passingScores = {
      english_proficiency: 3,
      teaching_methodology: 3,
      tech_environment: 3,
      curriculum_alignment: 3,
    };
    const result = validateRubric(passingScores, criteria, 3);
    assert.equal(result.passing, true);
    assert.equal(result.total, 12);
    assert.equal(result.criteriaDeficiencies.length, 0);
  });

  it("rejects rubric when any criterion is below minimum (e.g. score of 2)", () => {
    const criteria = [...DEFAULT_RUBRIC_CRITERIA];
    const deficientScores = {
      english_proficiency: 5,
      teaching_methodology: 5,
      tech_environment: 2, // Fails min 3 requirement
      curriculum_alignment: 5,
    };
    const result = validateRubric(deficientScores, criteria, 3);
    assert.equal(result.passing, false);
    assert.equal(result.total, 17); // Total is 17 (> 12) but has deficiency!
    assert.deepEqual(result.criteriaDeficiencies, ["tech_environment"]);
  });

  it("rejects rubric when criteria are missing or 0", () => {
    const criteria = [...DEFAULT_RUBRIC_CRITERIA];
    const incompleteScores = {
      english_proficiency: 4,
      teaching_methodology: 4,
    };
    const result = validateRubric(incompleteScores, criteria, 3);
    assert.equal(result.passing, false);
    assert.equal(result.criteriaDeficiencies.includes("tech_environment"), true);
    assert.equal(result.criteriaDeficiencies.includes("curriculum_alignment"), true);
  });

  it("builds reviewed assets map pinning live ETags", () => {
    const assets: PacketAsset[] = [
      {
        kind: "avatar",
        etag: '"etag-avatar-123"',
        content_type: "image/jpeg",
        size_bytes: 409600,
        uploaded_at: "2026-10-06T10:00:00Z",
      },
      {
        kind: "video_reel",
        etag: '"etag-video-456"',
        content_type: "video/mp4",
        size_bytes: 15000000,
        uploaded_at: "2026-10-06T10:05:00Z",
      },
      {
        kind: "audio_snippet",
        etag: '"etag-audio-789"',
        content_type: "audio/mp3",
        size_bytes: 1200000,
        uploaded_at: "2026-10-06T10:07:00Z",
      },
      {
        kind: "cv_tefl",
        etag: '"etag-tefl-999"',
        content_type: "application/pdf",
        size_bytes: 2500000,
        uploaded_at: "2026-10-06T10:10:00Z",
      },
    ];

    const map = buildReviewedAssetsMap(assets);
    assert.deepEqual(map, {
      avatar: '"etag-avatar-123"',
      video_reel: '"etag-video-456"',
      audio_snippet: '"etag-audio-789"',
      cv_tefl: '"etag-tefl-999"',
    });
  });
});
