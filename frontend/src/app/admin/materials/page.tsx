"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { BookOpen, FileText, Music, Plus, Search } from "lucide-react";
import { api } from "@/lib/api";
import { MATERIAL_VIEWS, type AdminMaterialList } from "@/lib/adminContent";
import { PageHeader } from "@/components/ui/PageHeader";
import { ErrorState } from "@/components/ui/ErrorState";

type ViewKey = (typeof MATERIAL_VIEWS)[number]["key"];

/** Lesson materials (Wave 2, ADM-07 materials half): drafts and published, search, open the editor. */
export default function AdminMaterialsPage() {
  const [view, setView] = useState<ViewKey>("all");
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const [data, setData] = useState<AdminMaterialList | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [reloadTick, setReloadTick] = useState(0);

  const reload = useCallback(() => setReloadTick((t) => t + 1), []);

  useEffect(() => {
    const timer = window.setTimeout(() => setSearch(query.trim()), 300);
    return () => window.clearTimeout(timer);
  }, [query]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    api
      .getAdminMaterials({ status: MATERIAL_VIEWS.find((v) => v.key === view)?.status, search })
      .then((res) => !cancelled && setData(res))
      .catch((err) => !cancelled && setError(err))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [view, search, reloadTick]);

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <PageHeader
        backHref="/admin/dashboard"
        eyebrow="CURRICULUM"
        title="Lesson materials"
        secondary={data ? `${data.published} published · ${data.drafts} ${data.drafts === 1 ? "draft" : "drafts"}` : undefined}
        actions={
          <Link
            href="/admin/materials/new"
            className="min-h-11 inline-flex items-center gap-2 rounded-xl bg-cocoa px-4 py-2 text-sm font-bold text-white shadow-xs hover:bg-cocoa-hover"
          >
            <Plus className="h-4 w-4" aria-hidden="true" /> New material
          </Link>
        }
      />

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div role="tablist" aria-label="Material views" className="inline-flex self-start rounded-2xl border border-divider bg-white p-1">
          {MATERIAL_VIEWS.map((v) => (
            <button
              key={v.key}
              type="button"
              role="tab"
              aria-selected={view === v.key}
              onClick={() => setView(v.key)}
              className={`min-h-11 whitespace-nowrap rounded-xl px-4 text-sm font-bold transition-colors ${
                view === v.key ? "bg-cocoa text-white" : "text-ink-muted hover:text-ink"
              }`}
            >
              {v.label}
            </button>
          ))}
        </div>
        <label className="relative block sm:w-72">
          <span className="sr-only">Search materials</span>
          <Search className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-muted" aria-hidden="true" />
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search title or description"
            className="min-h-11 w-full rounded-xl border border-divider bg-white py-2.5 pl-10 pr-3.5 text-base text-ink shadow-xs focus:border-cocoa focus:outline-none focus:ring-2 focus:ring-cocoa/30"
          />
        </label>
      </div>

      {loading && !data ? (
        <div className="h-40 animate-pulse rounded-3xl bg-white shadow-card" aria-busy="true" />
      ) : error != null ? (
        <ErrorState error={error} title="We couldn't load the materials" onRetry={reload} />
      ) : !data || data.materials.length === 0 ? (
        <div className="rounded-3xl bg-white p-8 text-center shadow-card sm:p-10">
          <BookOpen className="mx-auto h-8 w-8 text-cocoa" aria-hidden="true" />
          <p className="mt-3 font-bold text-ink">{search ? "No materials match your search" : "No materials in this view"}</p>
        </div>
      ) : (
        <section aria-label="Materials" aria-busy={loading}>
          <ul className="space-y-3">
            {data.materials.map((m) => (
              <li key={m.id}>
                <Link href={`/admin/materials/${m.id}`} className="group block rounded-3xl border border-divider bg-white p-4 shadow-card hover:bg-cream-surface sm:p-5">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="rounded-lg bg-cocoa px-2 py-0.5 font-mono text-xs font-bold text-white">{m.cefr_level}</span>
                    <h2 className="text-base font-extrabold text-ink group-hover:underline">{m.title}</h2>
                    <span
                      className={`whitespace-nowrap rounded-full border px-2.5 py-0.5 text-xs font-bold ${
                        m.is_published ? "border-success-border bg-success-surface text-success-hover" : "border-warning-border bg-warning-surface text-warning-hover"
                      }`}
                    >
                      {m.is_published ? "Published" : "Draft"}
                    </span>
                  </div>
                  <p className="mt-1 text-sm font-bold text-ink-muted">{m.category_display}</p>
                  {m.description && <p className="mt-1 line-clamp-2 text-sm text-ink-muted">{m.description}</p>}
                  {(m.pdf_url || m.audio_url) && (
                    <p className="mt-2 flex gap-4 text-sm text-ink-muted">
                      {m.pdf_url && (
                        <span className="inline-flex items-center gap-1">
                          <FileText className="h-3.5 w-3.5" aria-hidden="true" /> Worksheet
                        </span>
                      )}
                      {m.audio_url && (
                        <span className="inline-flex items-center gap-1">
                          <Music className="h-3.5 w-3.5" aria-hidden="true" /> Audio
                        </span>
                      )}
                    </p>
                  )}
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
