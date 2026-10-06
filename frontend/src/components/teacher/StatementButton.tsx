"use client";

import { useState } from "react";
import { FileDown } from "lucide-react";
import { api } from "@/lib/api";
import { InlineError } from "@/components/ui/ErrorState";

/** Downloads the tutor's earnings and payout statement (slice P2): ZAR, one row per earning or payout, running balance. */
export function StatementButton() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const download = async () => {
    setError(null);
    setBusy(true);
    try {
      await api.downloadTutorStatement();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-2 self-start sm:self-auto">
      <button
        type="button"
        onClick={download}
        disabled={busy}
        className="px-5 py-2.5 bg-white hover:bg-cream-surface text-ink text-xs font-bold rounded-xl border border-divider shadow-xs flex items-center gap-2 transition-all disabled:opacity-60"
      >
        <FileDown className="w-4 h-4 text-cocoa" />
        <span>{busy ? "Preparing..." : "Download statement (CSV)"}</span>
      </button>
      <InlineError error={error} />
    </div>
  );
}
