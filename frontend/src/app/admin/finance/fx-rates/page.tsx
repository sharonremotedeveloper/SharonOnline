"use client";

import { useState } from "react";
import Link from "next/link";
import { AlertTriangle, ArrowLeft, CheckCircle2, Coins } from "lucide-react";
import { api } from "@/lib/api";
import { ErrorState, InlineError } from "@/components/ui/ErrorState";
import { useApiData } from "@/hooks/useApiData";
import {
  FX_CURRENCIES,
  fxStatus,
  isConfirmationRequired,
  validateRateInput,
  type FxCurrency,
  type FxRateRow,
} from "@/lib/fx";

function StatusBadge({ row }: { row: FxRateRow }) {
  const status = fxStatus(row);
  if (status === "ok") {
    return (
      <span className="inline-flex items-center gap-1 text-[10px] font-black text-emerald-800 bg-emerald-100 px-2 py-0.5 rounded-full">
        <CheckCircle2 className="w-3 h-3" aria-hidden="true" /> FRESH
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 text-[10px] font-black text-white bg-rose-600 px-2 py-0.5 rounded-full">
      <AlertTriangle className="w-3 h-3" aria-hidden="true" /> {status === "missing" ? "MISSING" : "STALE"}
    </span>
  );
}

function formatWhen(iso: string | null): string {
  if (!iso) return "-";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString();
}

export default function AdminFxRatesPage() {
  const { data, error, loading, reload } = useApiData(() => api.getFxRates(), []);
  const [currency, setCurrency] = useState<FxCurrency>("EUR");
  const [rate, setRate] = useState("");
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<unknown>(null);
  const [needsConfirm, setNeedsConfirm] = useState<string | null>(null);
  const [savedNote, setSavedNote] = useState<string | null>(null);

  async function submit(confirm: boolean) {
    const check = validateRateInput(rate);
    if (!check.ok) {
      setFieldError(check.message);
      return;
    }
    setFieldError(null);
    setSaveError(null);
    setSavedNote(null);
    setSaving(true);
    try {
      const saved = await api.addFxRate(currency, check.rate, confirm);
      setNeedsConfirm(null);
      setRate("");
      setSavedNote(`${saved.currency} rate saved: 1 ${saved.currency} = R${saved.rate_to_zar}.`);
      reload();
    } catch (err) {
      if (isConfirmationRequired(err)) {
        setNeedsConfirm(err.message);
      } else {
        setNeedsConfirm(null);
        setSaveError(err);
      }
    } finally {
      setSaving(false);
    }
  }

  if (error || (!loading && !data)) {
    return (
      <div className="py-20">
        <ErrorState error={error ?? "No FX rates returned."} title="We couldn't load the FX rates" onRetry={reload} />
      </div>
    );
  }
  if (loading || !data) {
    return (
      <div className="py-20 text-center space-y-4">
        <div className="w-12 h-12 border-4 border-cocoa border-t-transparent rounded-full animate-spin mx-auto" />
        <p className="text-sm font-bold text-ink-muted">Loading FX rates...</p>
      </div>
    );
  }

  const blocked = data.current.filter((r) => fxStatus(r) !== "ok");

  return (
    <div className="space-y-8 max-w-5xl mx-auto">
      <div className="flex items-center gap-3">
        <Link
          href="/admin/dashboard"
          className="p-2.5 rounded-xl bg-white border border-divider text-ink-muted hover:text-ink hover:bg-cream-surface transition-colors shadow-xs"
          aria-label="Back to dashboard"
        >
          <ArrowLeft className="w-4 h-4" />
        </Link>
        <div>
          <div className="flex items-center gap-2">
            <Coins className="w-4 h-4 text-cocoa" aria-hidden="true" />
            <span className="text-xs font-bold text-ink-muted">EUR / JPY to ZAR, maintained by hand</span>
          </div>
          <h1 className="text-2xl sm:text-3xl font-black text-ink font-serif">FX Rates</h1>
        </div>
      </div>

      {blocked.length > 0 && (
        <div role="alert" className="flex items-start gap-3 rounded-2xl border border-rose-300 bg-rose-50 p-4 text-sm text-rose-800">
          <AlertTriangle className="w-5 h-5 shrink-0 mt-0.5" aria-hidden="true" />
          <div>
            <strong>{blocked.map((r) => r.currency).join(" and ")} checkout is blocked while the rate is stale or missing.</strong>{" "}
            Add a fresh rate below. A rate older than {data.max_age_hours} hours counts as stale.
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {data.current.map((r) => (
          <div key={r.currency} className="bg-white p-6 rounded-3xl border border-divider shadow-card space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-ink-muted">{r.currency} to ZAR</span>
              <StatusBadge row={r} />
            </div>
            <div className="text-3xl font-black text-ink font-serif">
              {r.rate_to_zar === null ? "No rate set" : `R${r.rate_to_zar}`}
            </div>
            {r.rate_to_zar !== null && (
              <p className="text-[11px] text-ink-muted">
                Source: {r.source ?? "-"} &middot; set by {r.set_by ?? "unknown"} &middot; {r.age_hours ?? "?"}h old
              </p>
            )}
          </div>
        ))}
      </div>

      <form
        className="bg-white p-6 rounded-3xl border border-divider shadow-card space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          void submit(false);
        }}
        noValidate
      >
        <h2 className="text-base font-bold text-ink font-serif">Add a rate</h2>
        <div className="flex flex-col sm:flex-row gap-3 sm:items-end">
          <label className="text-xs font-bold text-ink-muted space-y-1">
            <span>Currency</span>
            <select
              value={currency}
              onChange={(e) => {
                setCurrency(e.target.value as FxCurrency);
                setNeedsConfirm(null);
              }}
              className="block w-full sm:w-32 rounded-xl border border-divider bg-white px-3 py-2 text-sm text-ink"
            >
              {FX_CURRENCIES.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </label>
          <label className="text-xs font-bold text-ink-muted space-y-1 flex-1">
            <span>Rate (ZAR per 1 {currency})</span>
            <input
              inputMode="decimal"
              value={rate}
              onChange={(e) => {
                setRate(e.target.value);
                setNeedsConfirm(null);
                setFieldError(null);
              }}
              placeholder={currency === "EUR" ? "e.g. 19.85" : "e.g. 0.12"}
              aria-invalid={fieldError ? true : undefined}
              className="block w-full rounded-xl border border-divider bg-white px-3 py-2 text-sm text-ink"
            />
          </label>
          <button
            type="submit"
            disabled={saving}
            className="px-5 py-2.5 rounded-xl bg-cocoa text-white text-xs font-bold disabled:opacity-50"
          >
            {saving && !needsConfirm ? "Saving..." : "Save rate"}
          </button>
        </div>
        {fieldError && <p className="text-xs font-medium text-error">{fieldError}</p>}
        <InlineError error={saveError} />
        {savedNote && <p className="text-xs font-bold text-emerald-800">{savedNote}</p>}

        {needsConfirm && (
          <div role="alert" className="rounded-2xl border border-amber-300 bg-amber-50 p-4 space-y-3 text-sm text-amber-900">
            <p>{needsConfirm}</p>
            <button
              type="button"
              disabled={saving}
              onClick={() => void submit(true)}
              className="px-4 py-2 rounded-xl bg-amber-600 text-white text-xs font-bold disabled:opacity-50"
            >
              {saving ? "Saving..." : "Confirm and save"}
            </button>
          </div>
        )}
      </form>

      <div className="bg-white rounded-3xl border border-divider shadow-card overflow-x-auto">
        <h2 className="text-base font-bold text-ink font-serif p-6 pb-3">History (last 20)</h2>
        {data.history.length === 0 ? (
          <p className="px-6 pb-6 text-xs text-ink-muted">No rates have been recorded yet.</p>
        ) : (
          <table className="w-full text-xs">
            <thead className="text-left text-ink-muted">
              <tr>
                <th className="px-6 py-2">Currency</th>
                <th className="px-3 py-2">Rate to ZAR</th>
                <th className="px-3 py-2">Source</th>
                <th className="px-3 py-2">Set by</th>
                <th className="px-6 py-2">Valid from</th>
              </tr>
            </thead>
            <tbody>
              {data.history.map((r) => (
                <tr key={r.id ?? `${r.currency}-${r.valid_from}`} className="border-t border-divider">
                  <td className="px-6 py-2 font-bold text-ink">{r.currency}</td>
                  <td className="px-3 py-2 font-mono">{r.rate_to_zar ?? "-"}</td>
                  <td className="px-3 py-2">{r.source ?? "-"}</td>
                  <td className="px-3 py-2">{r.set_by ?? "-"}</td>
                  <td className="px-6 py-2">{formatWhen(r.valid_from)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
