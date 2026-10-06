"use client";

import { useState } from "react";
import { FileText, Download } from "lucide-react";
import { api } from "@/lib/api";
import { InlineError } from "@/components/ui/ErrorState";
import { useApiData } from "@/hooks/useApiData";

/** The student's receipts (Task 10.8): number, what was bought, the exact amount paid, and the PDF. */
export function ReceiptsList() {
  const { data: receipts, error, loading } = useApiData(() => api.getReceipts(), []);
  const [downloadError, setDownloadError] = useState<unknown>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const download = async (receipt: { id: string; receipt_number: string }) => {
    setDownloadError(null);
    setBusyId(receipt.id);
    try {
      await api.downloadReceipt(receipt);
    } catch (err) {
      setDownloadError(err);
    } finally {
      setBusyId(null);
    }
  };

  return (
    <section aria-labelledby="receipts-heading" className="bg-white rounded-3xl p-6 sm:p-8 border border-divider shadow-card space-y-4">
      <div className="flex items-center gap-2.5">
        <FileText className="w-5 h-5 text-cocoa" />
        <h2 id="receipts-heading" className="text-lg font-black text-ink font-serif">
          Receipts
        </h2>
      </div>
      <InlineError error={error || downloadError} />
      {loading && <p className="text-sm text-ink-muted">Loading your receipts...</p>}
      {!loading && !error && receipts && receipts.length === 0 && (
        <p className="text-sm text-ink-muted">Receipts for your payments appear here as soon as a payment is confirmed.</p>
      )}
      {receipts && receipts.length > 0 && (
        <ul className="divide-y divide-divider text-sm">
          {receipts.map((receipt) => (
            <li key={receipt.id} className="py-3.5 flex items-center justify-between gap-4">
              <div className="min-w-0">
                <div className="font-bold text-ink font-mono">{receipt.receipt_number}</div>
                <div className="text-sm text-ink-muted truncate">
                  {receipt.description} · {new Date(receipt.issued_at).toLocaleDateString()}
                </div>
              </div>
              <div className="flex items-center gap-3 shrink-0">
                <span className="font-black text-sm font-serif text-ink">
                  {receipt.currency} {receipt.total_amount}
                </span>
                <button
                  type="button"
                  onClick={() => download(receipt)}
                  disabled={busyId === receipt.id}
                  aria-label={`Download receipt ${receipt.receipt_number}`}
                  className="p-2 rounded-xl bg-cream-surface hover:bg-cream-deep border border-divider text-cocoa disabled:opacity-60"
                >
                  <Download className="w-4 h-4" />
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
