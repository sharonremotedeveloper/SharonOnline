"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AlertTriangle, CheckCircle2, Eye, PencilLine, PlayCircle } from "lucide-react";
import { api } from "@/lib/api";
import { ApiError } from "@/lib/http";
import {
  regateCount,
  regateWarning,
  slugify,
  trainingStatus,
  youtubeIdFromLink,
  type AdminTrainingModuleDetail,
  type TrainingModuleInput,
} from "@/lib/adminContent";
import { InlineError } from "@/components/ui/ErrorState";
import { TrainingMarkdown, TrainingVideo } from "@/components/training/TrainingContent";

type Form = Omit<TrainingModuleInput, "confirm_regate" | "is_published">;

const EMPTY: Form = { slug: "", title: "", summary: "", body: "", video_url: "", estimated_minutes: 10, is_required: true };

function formFrom(m: AdminTrainingModuleDetail): Form {
  return {
    slug: m.slug,
    title: m.title,
    summary: m.summary,
    body: m.body,
    video_url: m.video_youtube_id ? `https://youtu.be/${m.video_youtube_id}` : "",
    estimated_minutes: m.estimated_minutes,
    is_required: m.is_required,
  };
}

const inputClass =
  "min-h-11 w-full rounded-xl border border-divider bg-white px-3.5 py-2.5 text-base text-ink shadow-xs focus:border-cocoa focus:outline-none focus:ring-2 focus:ring-cocoa/30";

function Field({ id, label, hint, error, children }: { id: string; label: string; hint?: string; error?: string[]; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <label htmlFor={id} className="block text-sm font-bold text-ink">
        {label}
      </label>
      {children}
      {hint && !error?.length && <p className="text-sm text-ink-muted">{hint}</p>}
      {error?.map((message) => (
        <p key={message} className="text-sm font-bold text-error-hover">
          {message}
        </p>
      ))}
    </div>
  );
}

/**
 * Create or edit one tutor training module (Wave 2). Publishing a required module asks first, because every tutor who has
 * not completed it stops being bookable for new lessons until they do (decision 4, no grace period).
 */
export function TrainingModuleEditor({ initial }: { initial: AdminTrainingModuleDetail | null }) {
  const router = useRouter();
  const [current, setCurrent] = useState<AdminTrainingModuleDetail | null>(initial);
  const [form, setForm] = useState<Form>(initial ? formFrom(initial) : EMPTY);
  const [slugTouched, setSlugTouched] = useState(Boolean(initial));
  const [tab, setTab] = useState<"write" | "preview">("write");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});
  const [notice, setNotice] = useState<string | null>(null);
  const [regate, setRegate] = useState<{ count: number; publish: boolean } | null>(null);
  const [dirty, setDirty] = useState(false);

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
      if (key === "title" && !slugTouched) next.slug = slugify(String(value));
      return next;
    });
    setDirty(true);
    setNotice(null);
  };

  const videoId = youtubeIdFromLink(form.video_url);
  const published = current?.is_published ?? false;

  const save = async (publish: boolean, confirmRegate = false) => {
    setSaving(true);
    setError(null);
    setFieldErrors({});
    setNotice(null);
    try {
      const saved = await api.saveAdminTrainingModule(current?.id ?? null, {
        ...form,
        title: form.title.trim(),
        is_published: publish,
        confirm_regate: confirmRegate,
      });
      setCurrent(saved);
      setForm(formFrom(saved));
      setSlugTouched(true);
      setDirty(false);
      setRegate(null);
      setNotice(publish && !published ? "Published. Tutors can see this module now." : !publish && published ? "Unpublished. Tutors no longer see this module." : "Saved.");
      if (!current) router.replace(`/admin/training/${saved.id}?created=1`);
    } catch (err) {
      const count = regateCount(err);
      if (count !== null) {
        setRegate({ count, publish });
      } else {
        if (err instanceof ApiError) setFieldErrors(err.fieldErrors);
        setError(err);
      }
    } finally {
      setSaving(false);
    }
  };

  const status = current ? trainingStatus(current) : { label: "New draft", tone: "draft" as const };
  const tone = status.tone === "live" ? "border-success-border bg-success-surface text-success-hover" : status.tone === "optional" ? "border-divider bg-cocoa/10 text-cocoa" : "border-warning-border bg-warning-surface text-warning-hover";

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className={`rounded-full border px-2.5 py-0.5 text-xs font-bold ${tone}`}>{status.label}</span>
        {current && (
          <span className="text-ink-muted">
            {current.completed_count} {current.completed_count === 1 ? "tutor has" : "tutors have"} completed it
          </span>
        )}
      </div>

      {notice && (
        <div role="status" className="flex items-center gap-2.5 rounded-2xl border border-success-border bg-success-surface p-4 text-sm font-bold text-success-hover">
          <CheckCircle2 className="h-4 w-4 shrink-0" aria-hidden="true" /> {notice}
        </div>
      )}

      <section aria-label="Module details" className="space-y-4 rounded-3xl border border-divider bg-white p-5 shadow-card sm:p-7">
        <Field id="t-title" label="Title" error={fieldErrors.title}>
          <input id="t-title" className={inputClass} value={form.title} maxLength={200} onChange={(e) => set("title", e.target.value)} />
        </Field>
        <Field id="t-slug" label="Web address" hint={`Shown in the tutor's address bar: /teacher/training/${form.slug || "…"}`} error={fieldErrors.slug}>
          <input
            id="t-slug"
            className={`${inputClass} font-mono text-sm`}
            value={form.slug}
            maxLength={80}
            onChange={(e) => {
              setSlugTouched(true);
              set("slug", e.target.value.toLowerCase().replace(/[^a-z0-9-]+/g, "-"));
            }}
          />
        </Field>
        <Field id="t-summary" label="Summary" hint="One or two sentences on the training list." error={fieldErrors.summary}>
          <textarea id="t-summary" rows={2} className={inputClass} value={form.summary} maxLength={500} onChange={(e) => set("summary", e.target.value)} />
        </Field>
        <div className="grid gap-4 sm:grid-cols-[10rem_minmax(0,1fr)]">
          <Field id="t-minutes" label="Minutes" error={fieldErrors.estimated_minutes}>
            <input
              id="t-minutes"
              type="number"
              inputMode="numeric"
              min={1}
              max={600}
              className={inputClass}
              value={form.estimated_minutes}
              onChange={(e) => set("estimated_minutes", Number(e.target.value))}
            />
          </Field>
          <Field
            id="t-video"
            label="YouTube video (optional)"
            hint={videoId === null ? undefined : "Paste the link from YouTube's Share button. Set the video to Unlisted on YouTube."}
            error={fieldErrors.video_url ?? (videoId === null ? ["This is not a YouTube link we can embed."] : undefined)}
          >
            <input
              id="t-video"
              inputMode="url"
              className={inputClass}
              placeholder="https://youtu.be/…"
              value={form.video_url}
              onChange={(e) => set("video_url", e.target.value)}
            />
          </Field>
        </div>
        <label className="flex min-h-11 cursor-pointer items-start gap-3 rounded-2xl bg-cream-surface p-4">
          <input type="checkbox" className="mt-1 h-4 w-4 accent-cocoa" checked={form.is_required} onChange={(e) => set("is_required", e.target.checked)} />
          <span>
            <span className="block text-sm font-bold text-ink">Required</span>
            <span className="block text-sm text-ink-muted">
              Tutors must complete every published required module before students can book them. Publishing a new required module applies to all tutors.
            </span>
          </span>
        </label>
      </section>

      <section aria-label="Module content" className="rounded-3xl border border-divider bg-white shadow-card">
        <div role="tablist" aria-label="Content view" className="flex gap-1 border-b border-divider p-2">
          {(
            [
              ["write", "Write", PencilLine],
              ["preview", "Preview", Eye],
            ] as const
          ).map(([key, label, Icon]) => (
            <button
              key={key}
              type="button"
              role="tab"
              aria-selected={tab === key}
              onClick={() => setTab(key)}
              className={`min-h-11 inline-flex items-center gap-2 rounded-xl px-4 text-sm font-bold ${tab === key ? "bg-cocoa text-white" : "text-ink-muted hover:text-ink"}`}
            >
              <Icon className="h-4 w-4" aria-hidden="true" /> {label}
            </button>
          ))}
        </div>
        <div className="p-5 sm:p-7">
          {tab === "write" ? (
            <Field id="t-body" label="Content" hint="Start a line with # for a heading and - for a bullet point. Leave a blank line between paragraphs." error={fieldErrors.body}>
              <textarea id="t-body" rows={16} className={`${inputClass} font-mono text-sm leading-relaxed`} value={form.body} onChange={(e) => set("body", e.target.value)} />
            </Field>
          ) : (
            <div className="space-y-6">
              <h2 className="font-serif text-3xl font-black text-ink">{form.title || "Untitled module"}</h2>
              {form.summary && <p className="text-lg text-ink-muted">{form.summary}</p>}
              {videoId ? (
                <TrainingVideo id={videoId} title={form.title} />
              ) : (
                form.video_url.trim() === "" && (
                  <p className="flex items-center gap-2 text-sm text-ink-muted">
                    <PlayCircle className="h-4 w-4" aria-hidden="true" /> No video
                  </p>
                )
              )}
              {form.body.trim() ? <TrainingMarkdown body={form.body} /> : <p className="text-ink-muted">No content yet.</p>}
            </div>
          )}
        </div>
      </section>

      {regate && (
        <div role="alertdialog" aria-labelledby="regate-title" className="space-y-3 rounded-3xl border border-warning-border bg-warning-surface p-5 sm:p-6">
          <p id="regate-title" className="flex items-start gap-2 font-bold text-warning-hover">
            <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0" aria-hidden="true" /> {regateWarning(regate.count)}
          </p>
          <p className="text-sm text-ink">They will get an e-mail and an in-app notice asking them to complete it.</p>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              disabled={saving}
              onClick={() => save(regate.publish, true)}
              className="min-h-11 rounded-xl bg-cocoa px-5 text-sm font-bold text-white hover:bg-cocoa-hover disabled:opacity-50"
            >
              {saving ? "Publishing..." : `Publish for all ${regate.count === 1 ? "" : `${regate.count} `}tutors`}
            </button>
            <button type="button" disabled={saving} onClick={() => setRegate(null)} className="min-h-11 rounded-xl border border-divider bg-white px-5 text-sm font-bold text-ink">
              Cancel
            </button>
          </div>
        </div>
      )}

      <InlineError error={error} />

      <div className={`flex flex-col-reverse gap-2 sm:flex-row sm:justify-end ${regate ? "hidden" : ""}`}>
        {published ? (
          <>
            <button
              type="button"
              disabled={saving}
              onClick={() => save(false)}
              className="min-h-11 rounded-xl border border-divider bg-white px-5 text-sm font-bold text-ink shadow-xs hover:bg-cream-surface disabled:opacity-50"
            >
              Unpublish
            </button>
            <button
              type="button"
              disabled={saving || !dirty || videoId === null}
              onClick={() => save(true)}
              className="min-h-11 rounded-xl bg-cocoa px-5 text-sm font-bold text-white hover:bg-cocoa-hover disabled:opacity-50"
            >
              {saving ? "Saving..." : "Save changes"}
            </button>
          </>
        ) : (
          <>
            <button
              type="button"
              disabled={saving || videoId === null || (!dirty && Boolean(current))}
              onClick={() => save(false)}
              className="min-h-11 rounded-xl border border-divider bg-white px-5 text-sm font-bold text-ink shadow-xs hover:bg-cream-surface disabled:opacity-50"
            >
              {saving ? "Saving..." : "Save draft"}
            </button>
            <button
              type="button"
              disabled={saving || videoId === null}
              onClick={() => save(true)}
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
