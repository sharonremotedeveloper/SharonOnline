"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { ArrowDown, ArrowUp, Clock, GraduationCap, PlayCircle, Plus, Users } from "lucide-react";
import { api } from "@/lib/api";
import { moveId, trainingStatus, type AdminTrainingList } from "@/lib/adminContent";
import { PageHeader } from "@/components/ui/PageHeader";
import { ErrorState, InlineError } from "@/components/ui/ErrorState";

const TONE = {
  live: "border-success-border bg-success-surface text-success-hover",
  optional: "border-divider bg-cocoa/10 text-cocoa",
  draft: "border-warning-border bg-warning-surface text-warning-hover",
} as const;

/** Tutor training modules (Wave 2, ADM-07 training half): list, order, and open the editor. */
export default function AdminTrainingPage() {
  const [data, setData] = useState<AdminTrainingList | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [reloadTick, setReloadTick] = useState(0);
  const [moving, setMoving] = useState(false);
  const [moveError, setMoveError] = useState<unknown>(null);

  const reload = useCallback(() => setReloadTick((t) => t + 1), []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    api
      .getAdminTraining()
      .then((res) => !cancelled && setData(res))
      .catch((err) => !cancelled && setError(err))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [reloadTick]);

  const move = async (id: string, direction: -1 | 1) => {
    if (!data) return;
    const ids = moveId(
      data.modules.map((m) => m.id),
      id,
      direction,
    );
    setMoving(true);
    setMoveError(null);
    try {
      setData(await api.reorderAdminTraining(ids));
    } catch (err) {
      setMoveError(err);
    } finally {
      setMoving(false);
    }
  };

  const requiredLive = data?.modules.filter((m) => m.is_published && m.is_required).length ?? 0;

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <PageHeader
        backHref="/admin/dashboard"
        eyebrow="TUTOR TRAINING"
        title="Training modules"
        actions={
          <Link
            href="/admin/training/new"
            className="min-h-11 inline-flex items-center gap-2 rounded-xl bg-cocoa px-4 py-2 text-sm font-bold text-white shadow-xs hover:bg-cocoa-hover"
          >
            <Plus className="h-4 w-4" aria-hidden="true" /> New module
          </Link>
        }
      />

      {data && (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-3">
            <div className="rounded-3xl border border-divider bg-white p-4 shadow-card sm:p-5">
              <p className="text-xs font-bold text-ink-muted">Tutors fully trained</p>
              <p className="mt-1 font-serif text-2xl font-black text-ink sm:text-3xl">
                {data.trained_tutors}
                <span className="font-sans text-base font-bold text-ink-muted"> / {data.approved_tutors}</span>
              </p>
            </div>
            <div className="rounded-3xl border border-divider bg-white p-4 shadow-card sm:p-5">
              <p className="text-xs font-bold text-ink-muted">Required modules live</p>
              <p className="mt-1 font-serif text-2xl font-black text-ink sm:text-3xl">{requiredLive}</p>
            </div>
            <div className="col-span-2 rounded-3xl border border-divider bg-white p-4 shadow-card sm:p-5 lg:col-span-1">
              <p className="text-xs font-bold text-ink-muted">Training gate</p>
              <p className="mt-1 font-serif text-2xl font-black text-ink sm:text-3xl">{data.gate_enabled ? "On" : "Off"}</p>
              <p className="mt-1 text-sm text-ink-muted">
                {data.gate_enabled
                  ? "Only fully trained tutors can be booked."
                  : "Tutors can be booked whether or not they finished training."}
              </p>
            </div>
          </div>
          <p className="text-sm text-ink-muted">
            Publishing a new required module applies to every tutor: anyone who has not completed it cannot take new bookings until they do.
          </p>
        </>
      )}

      <InlineError error={moveError} />

      {loading && !data ? (
        <div className="h-40 animate-pulse rounded-3xl bg-white shadow-card" aria-busy="true" />
      ) : error != null ? (
        <ErrorState error={error} title="We couldn't load the training modules" onRetry={reload} />
      ) : !data || data.modules.length === 0 ? (
        <div className="rounded-3xl bg-white p-8 text-center shadow-card sm:p-10">
          <GraduationCap className="mx-auto h-8 w-8 text-cocoa" aria-hidden="true" />
          <p className="mt-3 font-bold text-ink">No training modules yet</p>
          <p className="mt-1 text-sm text-ink-muted">Create the first module tutors complete before they can be booked.</p>
        </div>
      ) : (
        <section aria-label="Modules">
          <ol className="space-y-3">
            {data.modules.map((m, index) => {
              const status = trainingStatus(m);
              return (
                <li key={m.id} className="flex items-stretch gap-2 rounded-3xl border border-divider bg-white p-3 shadow-card sm:gap-4 sm:p-4">
                  <div className="flex shrink-0 flex-col items-center justify-between">
                    <button
                      type="button"
                      aria-label={`Move ${m.title} up`}
                      disabled={moving || index === 0}
                      onClick={() => move(m.id, -1)}
                      className="min-h-11 min-w-11 inline-flex items-center justify-center rounded-xl text-ink-muted hover:bg-cream-surface hover:text-ink disabled:opacity-30"
                    >
                      <ArrowUp className="h-4 w-4" aria-hidden="true" />
                    </button>
                    <span className="font-serif text-lg font-black text-cocoa" aria-hidden="true">
                      {index + 1}
                    </span>
                    <button
                      type="button"
                      aria-label={`Move ${m.title} down`}
                      disabled={moving || index === data.modules.length - 1}
                      onClick={() => move(m.id, 1)}
                      className="min-h-11 min-w-11 inline-flex items-center justify-center rounded-xl text-ink-muted hover:bg-cream-surface hover:text-ink disabled:opacity-30"
                    >
                      <ArrowDown className="h-4 w-4" aria-hidden="true" />
                    </button>
                  </div>
                  <Link href={`/admin/training/${m.id}`} className="group min-w-0 flex-1 rounded-2xl p-2 hover:bg-cream-surface">
                    <div className="flex flex-wrap items-center gap-2">
                      <h2 className="text-base font-extrabold text-ink group-hover:underline">{m.title}</h2>
                      <span className={`whitespace-nowrap rounded-full border px-2.5 py-0.5 text-xs font-bold ${TONE[status.tone]}`}>{status.label}</span>
                    </div>
                    {m.summary && <p className="mt-1 line-clamp-2 text-sm text-ink-muted">{m.summary}</p>}
                    <p className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-sm text-ink-muted">
                      <span className="inline-flex items-center gap-1">
                        <Clock className="h-3.5 w-3.5" aria-hidden="true" /> {m.estimated_minutes} min
                      </span>
                      {m.video_youtube_id && (
                        <span className="inline-flex items-center gap-1">
                          <PlayCircle className="h-3.5 w-3.5" aria-hidden="true" /> Video
                        </span>
                      )}
                      <span className="inline-flex items-center gap-1">
                        <Users className="h-3.5 w-3.5" aria-hidden="true" /> {m.completed_count} completed
                      </span>
                    </p>
                  </Link>
                </li>
              );
            })}
          </ol>
        </section>
      )}
    </div>
  );
}
