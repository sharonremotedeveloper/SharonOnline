"use client";

import { useCallback, useEffect, useState } from "react";
import { CheckCircle2, RefreshCw, RotateCcw } from "lucide-react";
import { api } from "@/lib/api";
import {
  adminRefundStatusLabel,
  failureHelp,
  gatewayName,
  REFUND_VIEWS,
  refundReasonLabel,
  retryErrorText,
  retryNeedsConfirmation,
  type AdminRefund,
  type AdminRefundPage,
} from "@/lib/adminRefunds";
import { PageHeader } from "@/components/ui/PageHeader";
import { ErrorState, InlineError } from "@/components/ui/ErrorState";

type ViewKey = (typeof REFUND_VIEWS)[number]["key"];

const STATUS_TONE: Record<string, string> = {
  failed: "bg-error-surface text-error-hover border-error-border",
  pending_gateway: "bg-warning-surface text-warning-hover border-warning-border",
  awaiting_clearance: "bg-warning-surface text-warning-hover border-warning-border",
  submitted: "bg-cocoa/10 text-cocoa border-divider",
  processed: "bg-success-surface text-success-hover border-success-border",
  converted: "bg-success-surface text-success-hover border-success-border",
  void: "bg-cream-surface text-ink-muted border-divider",
};

function ageText(hours: number): string {
  if (hours < 1) return "under an hour";
  if (hours < 48) return `${Math.round(hours)} h`;
  return `${Math.round(hours / 24)} days`;
}

/**
 * Staff refund queue (Task 10.7; replaces "use the API or Django admin" in docs/RUNBOOK_REFUNDS.md). Read and retry only:
 * marking a refund paid by hand stays in Django admin, which records the provider refund id and an audit row.
 */
export default function AdminRefundsPage() {
  const [view, setView] = useState<ViewKey>("failed");
  const [data, setData] = useState<AdminRefundPage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [reloadTick, setReloadTick] = useState(0);
  const [confirming, setConfirming] = useState<string | null>(null);
  const [checkedGateway, setCheckedGateway] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [rowError, setRowError] = useState<{ id: string; error: unknown } | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const reload = useCallback(() => setReloadTick((t) => t + 1), []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    const params = REFUND_VIEWS.find((v) => v.key === view)!.params;
    api
      .getAdminRefunds({ ...params, page_size: 50 })
      .then((res) => !cancelled && setData(res))
      .catch((err) => !cancelled && setError(err))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [view, reloadTick]);

  const startRetry = (id: string) => {
    setConfirming(id);
    setCheckedGateway(false);
    setRowError(null);
    setNotice(null);
  };

  const retry = async (refund: AdminRefund) => {
    setBusy(refund.id);
    setRowError(null);
    try {
      const updated = await api.retryAdminRefund(refund.id, retryNeedsConfirmation(refund.failure_kind) && checkedGateway);
      setConfirming(null);
      setNotice(`Refund for ${refund.student} sent back to the gateway (now: ${adminRefundStatusLabel(updated.status)}).`);
      reload();
    } catch (err) {
      setRowError({ id: refund.id, error: retryErrorText(err) });
    } finally {
      setBusy(null);
    }
  };

  const buckets = data?.buckets;
  const summary = buckets
    ? [
        { label: "Needs action", value: buckets.status.failed ?? 0, alert: (buckets.status.failed ?? 0) > 0 },
        { label: "Waiting for manual payment", value: buckets.waiting_manual, alert: buckets.waiting_manual > 0 },
        { label: "Waiting for gateway", value: buckets.status.pending_gateway ?? 0, alert: false },
        { label: "On its way", value: buckets.status.submitted ?? 0, alert: false },
      ]
    : [];

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <PageHeader
        backHref="/admin/dashboard"
        eyebrow="REFUND QUEUE"
        secondary="Oldest first"
        title="Student Refunds"
        actions={
          <button
            type="button"
            onClick={reload}
            className="min-h-11 inline-flex items-center gap-2 rounded-xl border border-divider bg-white px-4 py-2 text-xs font-bold text-ink shadow-xs hover:bg-cream-surface"
          >
            <RefreshCw className="h-3.5 w-3.5 text-cocoa" aria-hidden="true" /> Refresh
          </button>
        }
      />

      {buckets && (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          {summary.map((s) => (
            <div
              key={s.label}
              className={`rounded-3xl border p-4 shadow-card sm:p-5 ${s.alert ? "border-error-border bg-error-surface" : "border-divider bg-white"}`}
            >
              <p className="text-xs font-bold text-ink-muted">{s.label}</p>
              <p className={`mt-1 font-serif text-2xl font-black sm:text-3xl ${s.alert ? "text-error-hover" : "text-ink"}`}>{s.value}</p>
            </div>
          ))}
        </div>
      )}

      {notice && (
        <div role="status" className="flex items-center gap-2.5 rounded-2xl border border-success-border bg-success-surface p-4 text-sm font-bold text-success-hover">
          <CheckCircle2 className="h-4 w-4 shrink-0" aria-hidden="true" /> {notice}
        </div>
      )}

      <div role="tablist" aria-label="Refund views" className="-mx-4 overflow-x-auto px-4 sm:mx-0 sm:px-0">
        <div className="inline-flex rounded-2xl border border-divider bg-white p-1">
          {REFUND_VIEWS.map((v) => (
            <button
              key={v.key}
              type="button"
              role="tab"
              aria-selected={view === v.key}
              onClick={() => {
                setView(v.key);
                setConfirming(null);
                setNotice(null);
              }}
              className={`min-h-11 whitespace-nowrap rounded-xl px-4 text-sm font-bold transition-colors ${
                view === v.key ? "bg-cocoa text-white" : "text-ink-muted hover:text-ink"
              }`}
            >
              {v.label}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div className="h-40 animate-pulse rounded-3xl bg-white shadow-card" aria-busy="true" />
      ) : error != null ? (
        <ErrorState error={error} title="We couldn't load the refund queue" onRetry={reload} />
      ) : !data || data.results.length === 0 ? (
        <div className="rounded-3xl bg-white p-8 text-center text-sm text-ink-muted shadow-card sm:p-10">
          {view === "failed" ? "Nothing needs a person right now." : "No refunds in this view."}
        </div>
      ) : (
        <section aria-label="Refunds" className="space-y-3">
          <p className="text-sm text-ink-muted">
            {data.count} {data.count === 1 ? "refund" : "refunds"}
            {data.count > data.results.length ? ` (showing the oldest ${data.results.length})` : ""}
          </p>
          <ul className="space-y-3">
            {data.results.map((r) => {
              const help = r.status === "failed" ? failureHelp(r.failure_kind) : null;
              const needsCheck = retryNeedsConfirmation(r.failure_kind);
              return (
                <li key={r.id} className="rounded-3xl border border-divider bg-white p-4 shadow-card sm:p-6">
                  <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                    <div className="min-w-0 space-y-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <h2 className="text-sm font-extrabold text-ink">{r.student}</h2>
                        <span className={`whitespace-nowrap rounded-full border px-2.5 py-0.5 text-xs font-bold ${STATUS_TONE[r.status] ?? STATUS_TONE.void}`}>
                          {adminRefundStatusLabel(r.status)}
                        </span>
                      </div>
                      <p className="text-sm text-ink-muted">
                        {refundReasonLabel(r.reason)} · <span className="whitespace-nowrap">{gatewayName(r.gateway)}</span> ·{" "}
                        <span className="whitespace-nowrap">waiting {ageText(r.age_hours)}</span>
                      </p>
                    </div>
                    <div className="flex items-center gap-3 md:flex-col md:items-end">
                      <p className="font-serif text-xl font-black text-ink">
                        {r.amount} <span className="font-sans text-sm font-bold text-ink-muted">{r.currency}</span>
                      </p>
                      {r.status === "failed" && confirming !== r.id && (
                        <button
                          type="button"
                          onClick={() => startRetry(r.id)}
                          className="min-h-11 inline-flex items-center gap-2 rounded-xl bg-cocoa px-4 text-xs font-bold text-white hover:bg-cocoa-hover"
                        >
                          <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" /> Retry
                        </button>
                      )}
                    </div>
                  </div>

                  {(help || r.failure_detail || r.last_error_code) && (
                    <div className="mt-3 space-y-1 rounded-2xl bg-cream-surface p-3 text-sm">
                      {help && <p className="font-bold text-ink">{help}</p>}
                      {(r.failure_detail || r.last_error_code) && (
                        <p className="break-words text-ink-muted">
                          {r.last_error_code && <span className="font-mono text-xs">{r.last_error_code}</span>}
                          {r.last_error_code && r.failure_detail ? " · " : ""}
                          {r.failure_detail}
                        </p>
                      )}
                    </div>
                  )}

                  {confirming === r.id && (
                    <div className="mt-3 space-y-3 rounded-2xl border border-warning-border bg-warning-surface p-4">
                      <p className="text-sm font-bold text-ink">
                        Send {r.amount} {r.currency} back to {gatewayName(r.gateway)} for {r.student}?
                      </p>
                      {needsCheck && (
                        <label className="flex items-start gap-3 text-sm text-ink">
                          <input
                            type="checkbox"
                            checked={checkedGateway}
                            onChange={(e) => setCheckedGateway(e.target.checked)}
                            className="mt-0.5 h-5 w-5 shrink-0 accent-cocoa"
                          />
                          <span>I checked the gateway dashboard and this refund did NOT go out.</span>
                        </label>
                      )}
                      <InlineError error={rowError?.id === r.id ? rowError.error : null} />
                      <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
                        <button
                          type="button"
                          onClick={() => setConfirming(null)}
                          className="min-h-11 rounded-xl border border-divider bg-white px-4 text-sm font-bold text-ink"
                        >
                          Cancel
                        </button>
                        <button
                          type="button"
                          onClick={() => retry(r)}
                          disabled={busy === r.id || (needsCheck && !checkedGateway)}
                          className="min-h-11 rounded-xl bg-cocoa px-4 text-sm font-bold text-white hover:bg-cocoa-hover disabled:opacity-50"
                        >
                          {busy === r.id ? "Sending..." : "Send refund again"}
                        </button>
                      </div>
                    </div>
                  )}

                  <details className="group mt-3 text-sm">
                    <summary className="min-h-11 flex cursor-pointer list-none items-center font-bold text-cocoa [&::-webkit-details-marker]:hidden">
                      Details and history
                    </summary>
                    <div className="space-y-3 pb-1 text-ink-muted">
                      <dl className="grid gap-x-6 gap-y-1 sm:grid-cols-2">
                        <div className="flex gap-2">
                          <dt className="font-bold">Refund id</dt>
                          <dd className="break-all font-mono text-xs leading-5">{r.id}</dd>
                        </div>
                        <div className="flex gap-2">
                          <dt className="font-bold">Booking</dt>
                          <dd className="break-all font-mono text-xs leading-5">{r.booking_id}</dd>
                        </div>
                        <div className="flex gap-2">
                          <dt className="font-bold">Attempts</dt>
                          <dd>{r.attempts}</dd>
                        </div>
                        {r.next_attempt_at && (
                          <div className="flex gap-2">
                            <dt className="font-bold">Next try</dt>
                            <dd>{new Date(r.next_attempt_at).toLocaleString()}</dd>
                          </div>
                        )}
                      </dl>
                      {r.recent_attempts.length > 0 && (
                        <ol className="space-y-1 border-l-2 border-divider pl-3">
                          {r.recent_attempts.map((a) => (
                            <li key={a.seq}>
                              #{a.seq} {a.kind} → <span className="font-bold text-ink">{a.result_state}</span>
                              {a.http_status ? ` (HTTP ${a.http_status})` : ""}
                              {a.error_code ? ` · ${a.error_code}` : ""} · {new Date(a.created_at).toLocaleString()}
                              {a.actor ? ` · by ${a.actor}` : ""}
                            </li>
                          ))}
                        </ol>
                      )}
                      {r.status === "failed" && (
                        <p>
                          Paid it by hand in the gateway? Record it in Django admin: Refund requests, select this refund,
                          &quot;Mark as paid in the gateway&quot;, with the gateway&apos;s refund id. Never edit refund or ledger rows directly.
                        </p>
                      )}
                    </div>
                  </details>
                </li>
              );
            })}
          </ul>
        </section>
      )}
    </div>
  );
}
