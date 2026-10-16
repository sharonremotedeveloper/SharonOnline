export const APPLICATION_MIN_DOWNLOAD_MBPS = 10;
export const APPLICATION_MIN_UPLOAD_MBPS = 5;

export type TutorApplicationOverview = {
  status?: unknown;
  editable?: unknown;
  submitted_at?: unknown;
};

export type TutorApplicationOutcome = {
  status: string;
  title: string;
  summary: string;
  submittedAt: string | null;
};

const APPLICATION_OUTCOME_COPY: Record<string, Pick<TutorApplicationOutcome, "title" | "summary">> = {
  submitted: {
    title: "Application submitted successfully",
    summary: "Your application is safely in the review queue. You do not need to submit it again.",
  },
  in_review: {
    title: "Your application is under review",
    summary: "Our review team is assessing your profile and uploaded documents.",
  },
  approved: {
    title: "Your tutor application is approved",
    summary: "Congratulations — you can continue with the tutor onboarding steps.",
  },
  rejected: {
    title: "A decision has been made",
    summary: "Check your notifications or email for the review decision and any available next steps.",
  },
  suspended: {
    title: "Your tutor access is paused",
    summary: "Check your notifications or email for details and contact support if you need help.",
  },
};

export function getTutorApplicationOutcome(application: TutorApplicationOverview | null | undefined): TutorApplicationOutcome | null {
  if (!application || application.editable === true || typeof application.status !== "string") return null;
  const copy = APPLICATION_OUTCOME_COPY[application.status];
  if (!copy) return null;
  return {
    status: application.status,
    ...copy,
    submittedAt: typeof application.submitted_at === "string" ? application.submitted_at : null,
  };
}

export async function recoverTutorApplicationOutcome(fetchOverview: () => Promise<TutorApplicationOverview>): Promise<TutorApplicationOutcome | null> {
  return getTutorApplicationOutcome(await fetchOverview());
}

const MB = 1024 * 1024;
const ASSET_FORMATS: Record<string, { types: string[]; extensions: Record<string, string>; hint: string; maxBytes: number }> = {
  avatar: { types: ["image/jpeg", "image/png", "image/webp"], extensions: { jpg: "image/jpeg", jpeg: "image/jpeg", png: "image/png", webp: "image/webp" }, hint: "JPG, PNG or WebP", maxBytes: 5 * MB },
  accent_audio: { types: ["audio/mpeg", "audio/mp4", "audio/wav", "audio/webm", "audio/ogg"], extensions: { mp3: "audio/mpeg", m4a: "audio/mp4", mp4: "audio/mp4", wav: "audio/wav", webm: "audio/webm", ogg: "audio/ogg" }, hint: "MP3, M4A, WAV, WebM or OGG", maxBytes: 10 * MB },
  intro_video: { types: ["video/mp4", "video/webm"], extensions: { mp4: "video/mp4", webm: "video/webm" }, hint: "MP4 or WebM", maxBytes: 50 * MB },
  tefl_certificate: { types: ["application/pdf", "image/jpeg", "image/png"], extensions: { pdf: "application/pdf", jpg: "image/jpeg", jpeg: "image/jpeg", png: "image/png" }, hint: "PDF, JPG or PNG", maxBytes: 10 * MB },
  identity_document: { types: ["application/pdf", "image/jpeg", "image/png"], extensions: { pdf: "application/pdf", jpg: "image/jpeg", jpeg: "image/jpeg", png: "image/png" }, hint: "PDF, JPG or PNG", maxBytes: 10 * MB },
};

export function resolveTutorAssetContentType(kind: string, file: { name: string; type: string; size: number }): string {
  const format = ASSET_FORMATS[kind];
  if (!format) throw new Error("Unknown tutor asset type.");
  if (file.size <= 0) throw new Error("The selected file is empty.");
  if (file.size > format.maxBytes) throw new Error(`The file must be ${format.maxBytes / MB} MB or smaller.`);
  const aliases: Record<string, string> = { "image/jpg": "image/jpeg", "audio/x-m4a": "audio/mp4", "audio/m4a": "audio/mp4", "audio/x-wav": "audio/wav", "audio/mp3": "audio/mpeg" };
  const reported = file.type.toLowerCase();
  const extension = file.name.split(".").pop()?.toLowerCase() || "";
  const contentType = !reported || reported === "application/octet-stream" ? format.extensions[extension] : (aliases[reported] || reported);
  if (!contentType || !format.types.includes(contentType)) throw new Error(`Unsupported ${kind.replaceAll("_", " ")} format. Use ${format.hint}.`);
  return contentType;
}

export function hydrateTutorAssetProgress(
  application: { requirements?: { upload_kinds?: unknown }; steps?: Array<{ key?: unknown; missing?: unknown }> } | null | undefined,
  fallbackKinds: string[],
): { requiredKinds: string[]; committedKinds: string[] } {
  const configuredKinds = application?.requirements?.upload_kinds;
  const requiredKinds = Array.isArray(configuredKinds) && configuredKinds.every((kind) => typeof kind === "string")
    ? configuredKinds
    : fallbackKinds;
  const uploadStep = Array.isArray(application?.steps) ? application.steps.find((step) => step?.key === "uploads") : undefined;
  if (!uploadStep || !Array.isArray(uploadStep.missing)) return { requiredKinds, committedKinds: [] };
  const missingKinds = new Set(uploadStep.missing.filter((kind): kind is string => typeof kind === "string"));
  return { requiredKinds, committedKinds: requiredKinds.filter((kind) => !missingKinds.has(kind)) };
}

export function isSpeedTestPassing(download: number, upload: number): boolean {
  return Number.isFinite(download) && Number.isFinite(upload) && download >= APPLICATION_MIN_DOWNLOAD_MBPS && upload >= APPLICATION_MIN_UPLOAD_MBPS;
}

export function validateApplicationStep(step: number, input: {
  headline?: string;
  bio?: string;
  specialties?: string[];
  committedKinds?: string[];
  requiredKinds?: string[];
  powerConfirmed?: boolean;
  download?: number;
  upload?: number;
  accepted?: boolean;
}): string[] {
  if (step === 1) return [
    ...(input.headline?.trim() ? [] : ["Add a profile headline."]),
    ...(input.bio?.trim() ? [] : ["Tell learners about your teaching experience."]),
    ...(input.specialties?.length ? [] : ["Choose at least one specialty."]),
  ];
  if (step === 2) return (input.requiredKinds || []).filter((kind) => !(input.committedKinds || []).includes(kind)).map((kind) => `Upload your ${kind.replaceAll("_", " ")}.`);
  if (step === 3) return input.powerConfirmed ? [] : ["Confirm that you have a power-backup plan."];
  if (step === 4) return isSpeedTestPassing(Number(input.download), Number(input.upload)) ? [] : ["Your connection must reach at least 10 Mbps download and 5 Mbps upload."];
  if (step === 5) return input.accepted ? [] : ["Accept the legal declarations to submit your application."];
  return [];
}

export function buildApplicationPayload(input: { download?: number; upload?: number; powerConfirmed?: boolean; accepted?: boolean }) {
  return {
    ...(input.download !== undefined && input.upload !== undefined ? { speed_test: { download_mbps: input.download.toFixed(1), upload_mbps: input.upload.toFixed(1) } } : {}),
    ...(input.powerConfirmed !== undefined ? { confirm_power_backup: input.powerConfirmed } : {}),
    ...(input.accepted !== undefined ? { accept_declaration: input.accepted } : {}),
  };
}
