"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { CheckCircle2, ExternalLink, FileText, Music, Trash2, Upload } from "lucide-react";
import { api } from "@/lib/api";
import { ApiError } from "@/lib/http";
import { useAuth } from "@/context/AuthContext";
import {
  CEFR_LEVELS,
  MATERIAL_ASSET_ACCEPT,
  MATERIAL_CATEGORIES,
  slugify,
  type AdminMaterialDetail,
  type MaterialAssetKind,
  type MaterialInput,
} from "@/lib/adminContent";
import { InlineError } from "@/components/ui/ErrorState";
import { LessonHtmlEditor } from "@/components/admin/LessonHtmlEditor";

type Form = Pick<MaterialInput, "title" | "slug" | "category" | "cefr_level" | "description" | "content_html">;

const EMPTY: Form = { title: "", slug: "", category: "freetalk", cefr_level: "B1", description: "", content_html: "" };

function formFrom(m: AdminMaterialDetail): Form {
  return { title: m.title, slug: m.slug, category: m.category, cefr_level: m.cefr_level, description: m.description, content_html: m.content_html };
}

const inputClass =
  "min-h-11 w-full rounded-xl border border-divider bg-white px-3.5 py-2.5 text-base text-ink shadow-xs focus:border-cocoa focus:outline-none focus:ring-2 focus:ring-cocoa/30";

function Errors({ messages }: { messages?: string[] }) {
  return (
    <>
      {messages?.map((m) => (
        <p key={m} className="text-sm font-bold text-error-hover">
          {m}
        </p>
      ))}
    </>
  );
}

const ASSETS: { kind: MaterialAssetKind; label: string; hint: string; icon: typeof FileText }[] = [
  { kind: "pdf", label: "Worksheet (PDF)", hint: "PDF, up to 25 MB", icon: FileText },
  { kind: "audio", label: "Listening audio", hint: "MP3, OGG or WAV, up to 25 MB", icon: Music },
];

/** Create or edit one lesson material (Wave 2). Draft -> Published; the server cleans the lesson HTML on every save. */
export function MaterialEditor({ initial }: { initial: AdminMaterialDetail | null }) {
  const router = useRouter();
  const { user } = useAuth();
  const [current, setCurrent] = useState<AdminMaterialDetail | null>(initial);
  const [form, setForm] = useState<Form>(initial ? formFrom(initial) : EMPTY);
  const [slugTouched, setSlugTouched] = useState(Boolean(initial));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});
  const [notice, setNotice] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);
  const [uploading, setUploading] = useState<MaterialAssetKind | null>(null);
  const [assetError, setAssetError] = useState<{ kind: MaterialAssetKind; error: unknown } | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [revision, setRevision] = useState(0); // remounts the editor after a save so it shows the server-cleaned HTML

  // A new item is saved on /new and then opened on its own page: say so there, then tidy the address.
  useEffect(() => {
    if (!initial || !window.location.search.includes("created=1")) return;
    setNotice(initial.is_published ? "Published." : "Draft saved.");
    window.history.replaceState(null, "", window.location.pathname);
  }, [initial]);

  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  const set = <K extends keyof Form>(key: K, value: Form[K]) => {
    setForm((prev) => {
      const next = { ...prev, [key]: value };
      if (key === "title" && !slugTouched) next.slug = slugify(String(value), 255);
      return next;
    });
    setDirty(true);
    setNotice(null);
  };

  const published = current?.is_published ?? false;

  const save = async (changes: Partial<MaterialInput>, message: string) => {
    setSaving(true);
    setError(null);
    setFieldErrors({});
    setNotice(null);
    try {
      const saved = await api.saveAdminMaterial(current?.id ?? null, { ...form, title: form.title.trim(), ...changes });
      setCurrent(saved);
      setForm(formFrom(saved));
      setSlugTouched(true);
      setDirty(false);
      setNotice(message);
      setRevision((r) => r + 1);
      if (!current) router.replace(`/admin/materials/${saved.id}?created=1`);
    } catch (err) {
      if (err instanceof ApiError) setFieldErrors(err.fieldErrors);
      setError(err);
    } finally {
      setSaving(false);
    }
  };

  const upload = async (kind: MaterialAssetKind, file: File | undefined) => {
    if (!file || !current || !user) return;
    setUploading(kind);
    setAssetError(null);
    setNotice(null);
    try {
      await api.uploadMaterialAsset(current.id, kind, file, String(user.id));
      setCurrent(await api.getAdminMaterial(current.id));
      setNotice(kind === "pdf" ? "Worksheet attached." : "Audio attached.");
    } catch (err) {
      setAssetError({ kind, error: err });
    } finally {
      setUploading(null);
    }
  };

  const detach = async (kind: MaterialAssetKind) => {
    if (!current) return;
    setUploading(kind);
    setAssetError(null);
    try {
      setCurrent(await api.saveAdminMaterial(current.id, kind === "pdf" ? { remove_pdf: true } : { remove_audio: true }));
      setNotice(kind === "pdf" ? "Worksheet removed." : "Audio removed.");
    } catch (err) {
      setAssetError({ kind, error: err });
    } finally {
      setUploading(null);
    }
  };

  const remove = async () => {
    if (!current) return;
    setSaving(true);
    setError(null);
    try {
      await api.deleteAdminMaterial(current.id);
      setDirty(false);
      router.replace("/admin/materials");
    } catch (err) {
      setError(err);
      setSaving(false);
    }
  };

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span
          className={`rounded-full border px-2.5 py-0.5 text-xs font-bold ${
            published ? "border-success-border bg-success-surface text-success-hover" : "border-warning-border bg-warning-surface text-warning-hover"
          }`}
        >
          {published ? "Published" : current ? "Draft" : "New draft"}
        </span>
        {published && current && (
          <Link href={`/materials/${current.slug}`} target="_blank" className="min-h-11 inline-flex items-center gap-1 font-bold text-cocoa hover:underline">
            View on the website <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
          </Link>
        )}
      </div>

      {notice && (
        <div role="status" className="flex items-center gap-2.5 rounded-2xl border border-success-border bg-success-surface p-4 text-sm font-bold text-success-hover">
          <CheckCircle2 className="h-4 w-4 shrink-0" aria-hidden="true" /> {notice}
        </div>
      )}

      <section aria-label="Material details" className="space-y-4 rounded-3xl border border-divider bg-white p-5 shadow-card sm:p-7">
        <div className="space-y-1.5">
          <label htmlFor="m-title" className="block text-sm font-bold text-ink">
            Title
          </label>
          <input id="m-title" className={inputClass} value={form.title} maxLength={255} onChange={(e) => set("title", e.target.value)} />
          <Errors messages={fieldErrors.title} />
        </div>
        <div className="space-y-1.5">
          <label htmlFor="m-slug" className="block text-sm font-bold text-ink">
            Web address
          </label>
          <input
            id="m-slug"
            className={`${inputClass} font-mono text-sm`}
            value={form.slug}
            maxLength={255}
            onChange={(e) => {
              setSlugTouched(true);
              set("slug", e.target.value.toLowerCase().replace(/[^a-z0-9-]+/g, "-"));
            }}
          />
          {fieldErrors.slug?.length ? <Errors messages={fieldErrors.slug} /> : <p className="text-sm text-ink-muted">/materials/{form.slug || "…"}</p>}
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5">
            <label htmlFor="m-category" className="block text-sm font-bold text-ink">
              Category
            </label>
            <select id="m-category" className={inputClass} value={form.category} onChange={(e) => set("category", e.target.value)}>
              {MATERIAL_CATEGORIES.map((c) => (
                <option key={c.value} value={c.value}>
                  {c.label}
                </option>
              ))}
            </select>
            <Errors messages={fieldErrors.category} />
          </div>
          <div className="space-y-1.5">
            <label htmlFor="m-level" className="block text-sm font-bold text-ink">
              Level (CEFR)
            </label>
            <select id="m-level" className={inputClass} value={form.cefr_level} onChange={(e) => set("cefr_level", e.target.value)}>
              {CEFR_LEVELS.map((level) => (
                <option key={level} value={level}>
                  {level}
                </option>
              ))}
            </select>
            <Errors messages={fieldErrors.cefr_level} />
          </div>
        </div>
        <div className="space-y-1.5">
          <label htmlFor="m-description" className="block text-sm font-bold text-ink">
            Short description
          </label>
          <textarea id="m-description" rows={3} className={inputClass} value={form.description} maxLength={2000} onChange={(e) => set("description", e.target.value)} />
          <p className="text-sm text-ink-muted">Shown on the materials list.</p>
        </div>
      </section>

      <section aria-labelledby="m-content-label" className="space-y-2 rounded-3xl border border-divider bg-white p-5 shadow-card sm:p-7">
        <h2 id="m-content-label" className="text-sm font-bold text-ink">
          Lesson content
        </h2>
        <LessonHtmlEditor key={`${current?.id ?? "new"}-${revision}`} id="m-content" labelledBy="m-content-label" value={form.content_html} onChange={(html) => set("content_html", html)} />
        <p className="text-sm text-ink-muted">Scripts, styles, images and embedded frames are removed when you save.</p>
        <Errors messages={fieldErrors.content_html} />
      </section>

      <section aria-label="Files" className="space-y-3 rounded-3xl border border-divider bg-white p-5 shadow-card sm:p-7">
        <h2 className="text-sm font-bold text-ink">Files</h2>
        {!current ? (
          <p className="text-sm text-ink-muted">Save the draft first, then attach a worksheet or audio.</p>
        ) : (
          <ul className="divide-y divide-divider">
            {ASSETS.map(({ kind, label, hint, icon: Icon }) => {
              const url = kind === "pdf" ? current.pdf_url : current.audio_url;
              return (
                <li key={kind} className="flex flex-col gap-3 py-3 sm:flex-row sm:items-center sm:justify-between">
                  <div className="flex min-w-0 items-start gap-3">
                    <Icon className="mt-0.5 h-5 w-5 shrink-0 text-cocoa" aria-hidden="true" />
                    <div className="min-w-0">
                      <p className="text-sm font-bold text-ink">{label}</p>
                      {url ? (
                        <a href={url} target="_blank" rel="noreferrer" className="block truncate text-sm font-bold text-cocoa hover:underline">
                          {url.split("/").pop()?.split("?")[0] || "Open file"}
                        </a>
                      ) : (
                        <p className="text-sm text-ink-muted">{hint}</p>
                      )}
                      {assetError?.kind === kind && <InlineError error={assetError.error} />}
                    </div>
                  </div>
                  <div className="flex shrink-0 gap-2">
                    <label
                      className={`min-h-11 inline-flex cursor-pointer items-center gap-2 rounded-xl border border-divider bg-white px-4 text-sm font-bold text-ink shadow-xs hover:bg-cream-surface ${
                        uploading ? "pointer-events-none opacity-50" : ""
                      }`}
                    >
                      <Upload className="h-4 w-4 text-cocoa" aria-hidden="true" />
                      {uploading === kind ? "Uploading..." : url ? "Replace" : "Upload"}
                      <input
                        type="file"
                        className="sr-only"
                        accept={MATERIAL_ASSET_ACCEPT[kind]}
                        disabled={uploading !== null}
                        onChange={(e) => {
                          void upload(kind, e.target.files?.[0]);
                          e.target.value = "";
                        }}
                      />
                    </label>
                    {url && (
                      <button
                        type="button"
                        disabled={uploading !== null}
                        onClick={() => detach(kind)}
                        aria-label={`Remove ${label.toLowerCase()}`}
                        className="min-h-11 min-w-11 inline-flex items-center justify-center rounded-xl border border-divider bg-white text-ink-muted hover:text-error-hover disabled:opacity-50"
                      >
                        <Trash2 className="h-4 w-4" aria-hidden="true" />
                      </button>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <InlineError error={error} />

      {confirmDelete && current && (
        <div role="alertdialog" aria-labelledby="delete-title" className="space-y-3 rounded-3xl border border-error-border bg-error-surface p-5">
          <p id="delete-title" className="font-bold text-error-hover">
            Delete this draft for good? This cannot be undone.
          </p>
          <div className="flex flex-wrap gap-2">
            <button type="button" disabled={saving} onClick={remove} className="min-h-11 rounded-xl bg-error-hover px-5 text-sm font-bold text-white disabled:opacity-50">
              Delete draft
            </button>
            <button type="button" onClick={() => setConfirmDelete(false)} className="min-h-11 rounded-xl border border-divider bg-white px-5 text-sm font-bold text-ink">
              Cancel
            </button>
          </div>
        </div>
      )}

      <div className="flex flex-col-reverse gap-2 sm:flex-row sm:items-center sm:justify-end">
        {current && !published && !confirmDelete && (
          <button
            type="button"
            disabled={saving}
            onClick={() => setConfirmDelete(true)}
            className="min-h-11 inline-flex items-center justify-center gap-2 rounded-xl px-4 text-sm font-bold text-error-hover hover:bg-error-surface sm:mr-auto"
          >
            <Trash2 className="h-4 w-4" aria-hidden="true" /> Delete draft
          </button>
        )}
        {published ? (
          <>
            <button
              type="button"
              disabled={saving}
              onClick={() => save({ is_published: false }, "Unpublished. Students no longer see this material.")}
              className="min-h-11 rounded-xl border border-divider bg-white px-5 text-sm font-bold text-ink shadow-xs hover:bg-cream-surface disabled:opacity-50"
            >
              Unpublish
            </button>
            <button
              type="button"
              disabled={saving || !dirty}
              onClick={() => save({ is_published: true }, "Saved. The website shows the new version.")}
              className="min-h-11 rounded-xl bg-cocoa px-5 text-sm font-bold text-white hover:bg-cocoa-hover disabled:opacity-50"
            >
              {saving ? "Saving..." : "Save changes"}
            </button>
          </>
        ) : (
          <>
            <button
              type="button"
              disabled={saving || (!dirty && Boolean(current))}
              onClick={() => save({ is_published: false }, "Draft saved. Students cannot see it yet.")}
              className="min-h-11 rounded-xl border border-divider bg-white px-5 text-sm font-bold text-ink shadow-xs hover:bg-cream-surface disabled:opacity-50"
            >
              {saving ? "Saving..." : "Save draft"}
            </button>
            <button
              type="button"
              disabled={saving}
              onClick={() => save({ is_published: true }, "Published. Students can see this material now.")}
              className="min-h-11 rounded-xl bg-cocoa px-5 text-sm font-bold text-white hover:bg-cocoa-hover disabled:opacity-50"
            >
              Publish
            </button>
          </>
        )}
      </div>
    </div>
  );
}
