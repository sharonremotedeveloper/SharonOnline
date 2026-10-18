"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { ArrowRight } from "lucide-react";
import { listBookings, type BookingListParams } from "@/lib/bookings";
import { formatLessonDate, initials, lessonStatus, TUTOR_LESSON_VIEWS, tutorLessonAction, type StatusTone } from "@/lib/lessonStatus";
import type { BookingDetail } from "@/types/booking";
import { PageHeader } from "@/components/ui/PageHeader";
import { ErrorState, InlineError } from "@/components/ui/ErrorState";

type ViewKey = (typeof TUTOR_LESSON_VIEWS)[number]["key"];

const TONES: Record<StatusTone, string> = {
  info: "bg-cocoa/10 text-cocoa",
  success: "bg-success-surface text-success-hover",
  warning: "bg-warning-surface text-warning-hover",
  error: "bg-error-surface text-error-hover",
  neutral: "bg-cream-surface text-ink-muted",
};

const EMPTY: Record<ViewKey, string> = {
  upcoming: "No upcoming lessons. Students book the open hours you set in My hours.",
  memo: "No memos due. Well done.",
  past: "No past lessons yet.",
};

/** TEA-06: every lesson the tutor teaches, filtered and paged by the server (docs/BOOKING_LIST.md). */
export default function TeacherLessonsPage() {
  const [view, setView] = useState<ViewKey>("upcoming");
  const [items, setItems] = useState<BookingDetail[]>([]);
  const [count, setCount] = useState(0);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [moreError, setMoreError] = useState<unknown>(null);
  const [now, setNow] = useState<number | null>(null);
  const [reloadTick, setReloadTick] = useState(0);

  const load = useCallback(async (key: ViewKey, nextPage: number) => {
    const query = TUTOR_LESSON_VIEWS.find((v) => v.key === key)!.query as BookingListParams;
    return listBookings({ ...query, status: query.status ? [...query.status] : undefined, page: nextPage, pageSize: 20 });
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setMoreError(null);
    setNow(Date.now());
    load(view, 1)
      .then((res) => {
        if (cancelled) return;
        setItems(res.items);
        setCount(res.count);
        setHasMore(res.hasMore);
        setPage(1);
      })
      .catch((err) => !cancelled && setError(err))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [view, load, reloadTick]);

  const loadMore = async () => {
    setMoreError(null);
    try {
      const res = await load(view, page + 1);
      setItems((prev) => [...prev, ...res.items.filter((b) => !prev.some((p) => p.id === b.id))]);
      setHasMore(res.hasMore);
      setPage(page + 1);
    } catch (err) {
      setMoreError(err);
    }
  };

  return (
    <div className="min-h-screen bg-cream py-8 sm:py-12">
      <div className="mx-auto max-w-5xl space-y-7 px-4 sm:px-6 lg:px-8">
        <PageHeader
          backHref="/teacher/dashboard"
          backLabel="Back to dashboard"
          eyebrow="MY LESSONS"
          title="Your lessons"
          actions={
            <Link
              href="/teacher/schedule"
              className="min-h-11 inline-flex items-center gap-2 rounded-xl border border-divider bg-white px-4 py-2 text-xs font-bold text-ink shadow-xs hover:bg-cream-surface"
            >
              My hours <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
            </Link>
          }
        />

        <div role="tablist" aria-label="Lessons" className="-mx-4 flex gap-1 overflow-x-auto px-4 sm:mx-0 sm:px-0">
          <div className="inline-flex shrink-0 rounded-2xl border border-divider bg-white p-1">
            {TUTOR_LESSON_VIEWS.map((v) => (
              <button
                key={v.key}
                type="button"
                role="tab"
                aria-selected={view === v.key}
                onClick={() => setView(v.key)}
                className={`min-h-11 whitespace-nowrap rounded-xl px-4 text-sm font-bold transition-colors sm:px-5 ${
                  view === v.key ? "bg-cocoa text-white" : "text-ink-muted hover:text-ink"
                }`}
              >
                {v.label}
              </button>
            ))}
          </div>
        </div>

        {loading ? (
          <div className="space-y-3" aria-busy="true">
            {[0, 1, 2].map((i) => (
              <div key={i} className="h-20 animate-pulse rounded-3xl bg-white shadow-card" />
            ))}
          </div>
        ) : error != null ? (
          <ErrorState error={error} title="We couldn't load your lessons" onRetry={() => setReloadTick((t) => t + 1)} />
        ) : items.length === 0 ? (
          <div className="rounded-3xl bg-white p-8 text-center text-sm text-ink-muted shadow-card sm:p-10">{EMPTY[view]}</div>
        ) : (
          <section aria-label={`${count} lessons`} className="space-y-3">
            <p className="text-sm text-ink-muted">
              {count} {count === 1 ? "lesson" : "lessons"}
              {items[0]?.viewer_timezone ? ` · times in ${items[0].viewer_timezone}` : ""}
            </p>
            <ul className="divide-y divide-divider overflow-hidden rounded-3xl border border-divider bg-white shadow-card">
              {items.map((b) => {
                const status = lessonStatus(b.status);
                const action = now === null ? null : tutorLessonAction(b, now);
                return (
                  <li key={b.id} className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between sm:px-6">
                    <div className="flex min-w-0 items-center gap-3.5">
                      <div
                        aria-hidden="true"
                        className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-cocoa/10 text-xs font-black text-cocoa"
                      >
                        {initials(b.student.full_name)}
                      </div>
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                          <h2 className="text-sm font-extrabold text-ink">{b.student.full_name}</h2>
                          <span className={`whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-bold ${TONES[status.tone]}`}>
                            {status.label}
                          </span>
                        </div>
                        <p className="mt-0.5 text-sm text-ink-muted">
                          <span className="whitespace-nowrap">{formatLessonDate(b.local_date)}</span>{" "}
                          <span className="whitespace-nowrap">
                            · {b.local_start_time} - {b.local_end_time}
                          </span>
                          {b.material_title ? <span className="block truncate sm:inline"> · {b.material_title}</span> : null}
                        </p>
                      </div>
                    </div>
                    {action && (
                      <Link
                        href={action.href}
                        className={`min-h-11 inline-flex shrink-0 items-center justify-center self-start rounded-xl px-4 py-2 text-xs font-bold transition-colors sm:self-auto ${
                          action.kind === "memo"
                            ? "bg-warning-surface text-warning-hover border border-warning-border hover:bg-warning-surface/80"
                            : "bg-cocoa text-white hover:bg-cocoa-hover"
                        }`}
                      >
                        {action.label}
                      </Link>
                    )}
                  </li>
                );
              })}
            </ul>
            {hasMore && (
              <div className="space-y-2 text-center">
                <button
                  type="button"
                  onClick={loadMore}
                  className="min-h-11 rounded-xl border border-divider bg-white px-5 text-sm font-bold text-ink shadow-xs hover:bg-cream-surface"
                >
                  Show more
                </button>
                <InlineError error={moreError} />
              </div>
            )}
          </section>
        )}
      </div>
    </div>
  );
}
