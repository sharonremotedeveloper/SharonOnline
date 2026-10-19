import assert from "node:assert/strict";
import test from "node:test";
import { buildApplicationPayload, getTutorApplicationOutcome, hydrateTutorAssetProgress, isSpeedTestPassing, recoverTutorApplicationOutcome, resolveTutorAssetContentType, validateApplicationStep } from "../src/lib/tutorApplication";

test("T5b speed threshold requires 10/2 Mbps", () => {
  assert.equal(isSpeedTestPassing(10, 2), true);
  assert.equal(isSpeedTestPassing(9.99, 20), false);
  assert.equal(isSpeedTestPassing(20, 1.99), false);
});

test("T5b validates required uploads and declarations", () => {
  assert.deepEqual(validateApplicationStep(2, { requiredKinds: ["avatar", "intro_video"], committedKinds: ["avatar"] }), ["Upload your intro video."]);
  assert.deepEqual(validateApplicationStep(5, { accepted: false }), ["Accept the legal declarations to submit your application."]);
});

test("T5b emits speed results at the backend's one-decimal precision", () => {
  assert.deepEqual(buildApplicationPayload({ download: 12.56, upload: 6.04, powerConfirmed: true, accepted: true }), {
    speed_test: { download_mbps: "12.6", upload_mbps: "6.0" }, confirm_power_backup: true, accept_declaration: true,
  });
});

test("tutor uploads normalize supported browser MIME aliases without accepting unsupported media", () => {
  assert.equal(resolveTutorAssetContentType("accent_audio", { name: "sample.m4a", type: "audio/x-m4a", size: 1200 }), "audio/mp4");
  assert.equal(resolveTutorAssetContentType("accent_audio", { name: "sample.ogg", type: "", size: 1200 }), "audio/ogg");
  assert.equal(resolveTutorAssetContentType("intro_video", { name: "intro.mp4", type: "application/octet-stream", size: 1200 }), "video/mp4");
  assert.throws(() => resolveTutorAssetContentType("intro_video", { name: "intro.mov", type: "video/quicktime", size: 1200 }), /MP4 or WebM/);
  assert.throws(() => resolveTutorAssetContentType("accent_audio", { name: "sample.aac", type: "audio/aac", size: 1200 }), /MP3, M4A, WAV, WebM or OGG/);
  assert.throws(() => resolveTutorAssetContentType("avatar", { name: "photo.jpg", type: "image/jpeg", size: 0 }), /empty/);
  assert.throws(() => resolveTutorAssetContentType("avatar", { name: "photo.jpg", type: "image/jpeg", size: 6 * 1024 * 1024 }), /5 MB/);
  assert.throws(() => resolveTutorAssetContentType("accent_audio", { name: "sample.m4a", type: "audio/mp4", size: 11 * 1024 * 1024 }), /10 MB/);
  assert.throws(() => resolveTutorAssetContentType("intro_video", { name: "intro.mp4", type: "video/mp4", size: 51 * 1024 * 1024 }), /50 MB/);
});

test("tutor application resumes committed uploads from the API contract", () => {
  const kinds = ["avatar", "accent_audio", "intro_video", "tefl_certificate", "identity_document"];
  assert.deepEqual(hydrateTutorAssetProgress({
    requirements: { upload_kinds: kinds },
    steps: [{ key: "uploads", missing: ["accent_audio", "intro_video"] }],
  }, ["fallback"]), {
    requiredKinds: kinds,
    committedKinds: ["avatar", "tefl_certificate", "identity_document"],
  });
  assert.deepEqual(hydrateTutorAssetProgress({ requirements: { upload_kinds: "invalid" } }, ["avatar"]), {
    requiredKinds: ["avatar"],
    committedKinds: [],
  });
});

test("submitted tutor applications resolve to a durable success state", () => {
  assert.deepEqual(getTutorApplicationOutcome({
    status: "submitted",
    editable: false,
    submitted_at: "2026-10-16T01:21:31Z",
  }), {
    status: "submitted",
    title: "Application submitted successfully",
    summary: "Your application is safely in the review queue. You do not need to submit it again.",
    submittedAt: "2026-10-16T01:21:31Z",
  });
});

test("editable applications keep the form while later review states get honest outcomes", () => {
  assert.equal(getTutorApplicationOutcome({ status: "changes_requested", editable: true, submitted_at: null }), null);
  assert.equal(getTutorApplicationOutcome({ status: "in_review", editable: false, submitted_at: "2026-10-16T01:21:31Z" })?.title, "Your application is under review");
  assert.equal(getTutorApplicationOutcome({ status: "approved", editable: false, submitted_at: "2026-10-16T01:21:31Z" })?.title, "Your tutor application is approved");
  assert.equal(getTutorApplicationOutcome({ status: "rejected", editable: false, submitted_at: "2026-10-16T01:21:31Z" })?.title, "A decision has been made");
});

test("an ambiguous submit failure recovers an already-committed outcome from the server", async () => {
  let calls = 0;
  const outcome = await recoverTutorApplicationOutcome(async () => {
    calls += 1;
    return { status: "submitted", editable: false, submitted_at: "2026-10-16T01:21:31Z" };
  });
  assert.equal(calls, 1);
  assert.equal(outcome?.status, "submitted");
  assert.equal(outcome?.title, "Application submitted successfully");
});
