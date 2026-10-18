/**
 * Admin content management (Wave 2, docs/ADMIN_CONTENT_MANAGEMENT_PENDING.md): tutor training modules and lesson materials.
 * Pure helpers and types only (no React, no `@/` imports) so the node test build can load them.
 */
import { ApiError } from "./http";

// ------------------------------------------------------------------ training
export type AdminTrainingModule = {
  id: string;
  slug: string;
  title: string;
  summary: string;
  video_youtube_id: string;
  position: number;
  estimated_minutes: number;
  is_required: boolean;
  is_published: boolean;
  completed_count: number;
  updated_at: string;
};

export type AdminTrainingModuleDetail = AdminTrainingModule & { body: string };

export type AdminTrainingList = {
  modules: AdminTrainingModule[];
  approved_tutors: number;
  trained_tutors: number;
  gate_enabled: boolean;
};

export type TrainingModuleInput = {
  slug: string;
  title: string;
  summary: string;
  body: string;
  video_url: string;
  estimated_minutes: number;
  is_required: boolean;
  is_published: boolean;
  confirm_regate?: boolean;
};

const YOUTUBE_ID = /^[A-Za-z0-9_-]{11}$/;
const YOUTUBE_HOSTS = new Set(["youtube.com", "www.youtube.com", "m.youtube.com", "youtube-nocookie.com", "www.youtube-nocookie.com"]);

/**
 * The video id of a YouTube link, for the editor's live preview. Mirrors teachers/training.py::parse_youtube_id; the
 * server's answer is the one that counts. Returns "" for an empty value and null for anything it does not accept.
 */
export function youtubeIdFromLink(link: string): string | null {
  const value = link.trim();
  if (!value) return "";
  if (YOUTUBE_ID.test(value)) return value;
  let url: URL;
  try {
    url = new URL(value.includes("://") ? value : `https://${value}`);
  } catch {
    return null;
  }
  if (url.protocol !== "https:" && url.protocol !== "http:") return null;
  const host = url.hostname.toLowerCase();
  let candidate = "";
  if (host === "youtu.be" || host === "www.youtu.be") {
    candidate = url.pathname.replace(/^\/+/, "").split("/")[0];
  } else if (YOUTUBE_HOSTS.has(host)) {
    const parts = url.pathname.split("/").filter(Boolean);
    if (parts[0] === "watch") candidate = url.searchParams.get("v") ?? "";
    else if (parts.length >= 2 && ["embed", "shorts", "live"].includes(parts[0])) candidate = parts[1];
  }
  return YOUTUBE_ID.test(candidate) ? candidate : null;
}

/** Privacy-enhanced embed address (no cookies until the viewer plays). Only ever built from a checked id. */
export function youtubeEmbedUrl(id: string): string | null {
  return YOUTUBE_ID.test(id) ? `https://www.youtube-nocookie.com/embed/${id}?rel=0` : null;
}

/** When a save would re-gate tutors the API answers 409 with how many; null for every other outcome. */
export function regateCount(err: unknown): number | null {
  if (!(err instanceof ApiError) || err.status !== 409) return null;
  const body = err.body as { code?: unknown; tutors_affected?: unknown } | null;
  if (!body || body.code !== "regate_confirmation_required" || typeof body.tutors_affected !== "number") return null;
  return body.tutors_affected;
}

/** "Lessons" -> "lessons"; spaces and punctuation become single hyphens (matches Django's SlugField). */
export function slugify(text: string, max = 80): string {
  return text
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, max)
    .replace(/-+$/g, "");
}

/** Move one id up (-1) or down (+1); returns a new array, or the same one when the move is not possible. */
export function moveId(ids: string[], id: string, direction: -1 | 1): string[] {
  const from = ids.indexOf(id);
  const to = from + direction;
  if (from < 0 || to < 0 || to >= ids.length) return ids;
  const next = [...ids];
  [next[from], next[to]] = [next[to], next[from]];
  return next;
}

export function trainingStatus(module: Pick<AdminTrainingModule, "is_published" | "is_required">): { label: string; tone: "live" | "draft" | "optional" } {
  if (!module.is_published) return { label: "Draft", tone: "draft" };
  return module.is_required ? { label: "Published · required", tone: "live" } : { label: "Published · optional", tone: "optional" };
}

/** The sentence the admin confirms before tutors lose bookability. */
export function regateWarning(count: number): string {
  const who = count === 1 ? "1 tutor" : `${count} tutors`;
  return `${who} will need to complete this module before students can book new lessons with them. Lessons already booked are not affected.`;
}

// ------------------------------------------------------------------ materials
export const MATERIAL_CATEGORIES = [
  { value: "daily_news", label: "Daily News & Discussion" },
  { value: "freetalk", label: "FreeTalk Conversation Prompts" },
  { value: "business", label: "Business English & Professional" },
  { value: "test_prep", label: "Job Interview & Test Prep" },
] as const;

export const CEFR_LEVELS = ["A1", "A2", "B1", "B2", "C1", "C2"] as const;

export type AdminMaterial = {
  id: string;
  title: string;
  slug: string;
  category: string;
  category_display: string;
  cefr_level: string;
  description: string;
  is_published: boolean;
  pdf_url: string;
  audio_url: string;
  updated_at: string;
};

export type AdminMaterialDetail = AdminMaterial & { content_html: string };

export type AdminMaterialList = { materials: AdminMaterial[]; published: number; drafts: number };

export type MaterialInput = {
  title: string;
  slug: string;
  category: string;
  cefr_level: string;
  description: string;
  content_html: string;
  is_published: boolean;
  remove_pdf?: boolean;
  remove_audio?: boolean;
};

export const MATERIAL_VIEWS = [
  { key: "all", label: "All", status: undefined },
  { key: "published", label: "Published", status: "published" },
  { key: "draft", label: "Drafts", status: "draft" },
] as const;

export type MaterialAssetKind = "pdf" | "audio";

/** What materials/assets.py accepts (type, 25 MB). Checked here first so the admin hears about it before uploading. */
const ASSET_TYPES: Record<MaterialAssetKind, Record<string, string>> = {
  pdf: { pdf: "application/pdf" },
  audio: { mp3: "audio/mpeg", ogg: "audio/ogg", wav: "audio/wav" },
};
export const MATERIAL_ASSET_MAX_BYTES = 25 * 1024 * 1024;
export const MATERIAL_ASSET_ACCEPT: Record<MaterialAssetKind, string> = {
  pdf: ".pdf,application/pdf",
  audio: ".mp3,.ogg,.wav,audio/mpeg,audio/ogg,audio/wav",
};

/** The content type to declare for an upload, or an error the admin can act on. */
export function materialAssetType(kind: MaterialAssetKind, file: { name: string; size: number; type: string }): { contentType: string } | { error: string } {
  if (file.size > MATERIAL_ASSET_MAX_BYTES) return { error: "Files must be 25 MB or smaller." };
  if (file.size === 0) return { error: "This file is empty." };
  const extension = file.name.toLowerCase().split(".").pop() ?? "";
  const contentType = ASSET_TYPES[kind][extension];
  if (!contentType) return { error: kind === "pdf" ? "Choose a PDF file." : "Choose an MP3, OGG or WAV audio file." };
  return { contentType };
}

/** A quarantine key for the presigned upload: `incoming/<admin id>/<random>-<safe name>` (the only prefix commit accepts). */
export function quarantineKey(userId: string, fileName: string, random: string): string {
  const safe = fileName.replace(/[^a-zA-Z0-9._-]/g, "-").replace(/\.{2,}/g, "-").slice(-80) || "upload";
  return `incoming/${userId}/${random}-${safe}`;
}
