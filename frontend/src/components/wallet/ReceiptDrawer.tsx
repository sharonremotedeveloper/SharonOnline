"use client";

import { useEffect, useState, useCallback } from "react";
import { FileText, Download, X, RefreshCw, AlertCircle, CheckCircle2 } from "lucide-react";
import { api } from "@/lib/api";
import type { ReceiptItem } from "@/types";

export interface ReceiptDrawerProps {
  isOpen: boolean;
  onClose: () => void;
}

export function ReceiptDrawer({ isOpen, onClose }: ReceiptDrawerProps) {
  const [receipts, setReceipts] = useState<ReceiptItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);
  const [actionNotice, setActionNotice] = useState<string | null>(null);

  const loadReceipts = useCallback(async () => {
    setLoading(true);
    setError(null);
    setActionNotice(null);
    try {
      const data = await api.getStudentReceipts();
      setReceipts(data);
    } catch (err) {
      console.error("Failed to load receipts:", err);
      setError("Unable to load receipts at this time. Please try again.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (isOpen) {
      loadReceipts();
      document.body.style.overflow = "hidden";
    }
    return () => {
      document.body.style.overflow = "unset";
    };
  }, [isOpen, loadReceipts]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isOpen) {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  const handleDownloadPdf = async (receipt: ReceiptItem) => {
    setDownloadingId(receipt.id);
    setActionNotice(null);
    try {
      const downloadEndpoint = `/api/proxy/payments/receipts/${encodeURIComponent(receipt.id)}/pdf/`;
      const res = await fetch(downloadEndpoint, { method: "GET" });
      if (!res.ok) {
        throw new Error(`Server returned HTTP ${res.status}`);
      }
      const blob = await res.blob();
      const objectUrl = window.URL.createObjectURL(blob);
      const downloadLink = document.createElement("a");
      downloadLink.href = objectUrl;
      downloadLink.download = `${receipt.receipt_number || "receipt"}.pdf`;
      document.body.appendChild(downloadLink);
      downloadLink.click();
      window.URL.revokeObjectURL(objectUrl);
      document.body.removeChild(downloadLink);
      setActionNotice(`Downloaded ${receipt.receipt_number}`);
    } catch (err) {
      console.error("Failed to download receipt PDF:", err);
      setActionNotice(`Could not download PDF (${err instanceof Error ? err.message : "Network error"}).`);
    } finally {
      setDownloadingId(null);
    }
  };

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-50 overflow-hidden"
      role="dialog"
      aria-modal="true"
      aria-labelledby="receipt-drawer-title"
    >
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-ink/50 backdrop-blur-sm transition-opacity duration-300"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Drawer Panel */}
      <div className="fixed inset-y-0 right-0 max-w-full flex pl-10">
        <div className="w-screen max-w-md bg-white shadow-2xl flex flex-col border-l border-divider animate-in slide-in-from-right duration-300">
          {/* Header */}
          <div className="p-6 border-b border-divider flex items-start justify-between bg-cream-surface/60">
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <div className="p-1.5 rounded-lg bg-teal/10 text-teal">
                  <FileText className="w-5 h-5" />
                </div>
                <h2 id="receipt-drawer-title" className="text-xl font-bold font-serif text-ink">
                  Invoices & Receipts
                </h2>
              </div>
              <p className="text-xs text-ink-muted">
                Official proof of purchase and tax invoices for lesson credit packages.
              </p>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="p-1.5 rounded-lg text-ink-muted hover:text-ink hover:bg-cream-deep transition-colors"
              aria-label="Close drawer"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Feedback Notices */}
          {actionNotice && (
            <div className="px-6 py-2.5 bg-accent-surface/40 border-b border-divider text-xs flex items-center justify-between text-ink">
              <span className="flex items-center gap-1.5">
                <CheckCircle2 className="w-3.5 h-3.5 text-teal" />
                {actionNotice}
              </span>
              <button
                type="button"
                onClick={() => setActionNotice(null)}
                className="text-ink-muted hover:text-ink text-[11px]"
              >
                Dismiss
              </button>
            </div>
          )}

          {/* Content Body */}
          <div className="flex-1 overflow-y-auto p-6 space-y-4">
            {loading ? (
              <div className="space-y-3 py-4">
                {[1, 2, 3].map((n) => (
                  <div key={n} className="p-4 rounded-2xl border border-divider bg-cream-surface animate-pulse space-y-2">
                    <div className="h-4 bg-divider rounded w-1/3" />
                    <div className="h-3 bg-divider rounded w-1/2" />
                    <div className="h-6 bg-divider rounded w-1/4 mt-2" />
                  </div>
                ))}
              </div>
            ) : error ? (
              <div className="p-6 rounded-2xl border border-amber-200 bg-amber-50 text-center space-y-3">
                <AlertCircle className="w-8 h-8 text-amber-600 mx-auto" />
                <p className="text-xs text-amber-900 font-medium">{error}</p>
                <button
                  type="button"
                  onClick={loadReceipts}
                  className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-ink text-white text-xs font-bold hover:bg-ink-light transition-colors"
                >
                  <RefreshCw className="w-3.5 h-3.5" />
                  <span>Retry</span>
                </button>
              </div>
            ) : receipts.length === 0 ? (
              <div className="py-16 text-center space-y-3">
                <div className="w-12 h-12 rounded-2xl bg-cream-deep/60 flex items-center justify-center mx-auto text-ink-muted">
                  <FileText className="w-6 h-6" />
                </div>
                <div className="space-y-1">
                  <h3 className="text-sm font-bold text-ink">No receipts issued yet</h3>
                  <p className="text-xs text-ink-muted max-w-xs mx-auto">
                    When you purchase lesson credit packages, your official tax invoices and receipts will appear here automatically.
                  </p>
                </div>
              </div>
            ) : (
              <div className="space-y-3">
                {receipts.map((rcpt) => {
                  const isDownloading = downloadingId === rcpt.id;
                  const dateStr = rcpt.created_at
                    ? new Date(rcpt.created_at).toLocaleDateString(undefined, {
                        year: "numeric",
                        month: "short",
                        day: "numeric",
                      })
                    : "Recent";

                  return (
                    <div
                      key={rcpt.id}
                      className="p-4 rounded-2xl border border-divider bg-white hover:border-accent/60 transition-all shadow-sm space-y-3"
                    >
                      <div className="flex items-start justify-between">
                        <div>
                          <div className="text-xs font-extrabold font-mono text-ink">
                            {rcpt.receipt_number}
                          </div>
                          <div className="text-[11px] text-ink-muted mt-0.5">
                            Issued on {dateStr}
                          </div>
                        </div>
                        <span className="text-sm font-black font-serif text-teal">
                          {rcpt.currency} {rcpt.total_amount}
                        </span>
                      </div>

                      {rcpt.description && (
                        <p className="text-xs text-ink-muted border-t border-divider/60 pt-2">
                          {rcpt.description}
                        </p>
                      )}

                      <div className="pt-2 border-t border-divider/60 flex items-center justify-between">
                        <span className="text-[11px] text-ink-muted">
                          {rcpt.tax_amount && Number(rcpt.tax_amount) > 0
                            ? `Includes ${rcpt.currency} ${rcpt.tax_amount} VAT`
                            : "Zero-rated VAT"}
                        </span>
                        <button
                          type="button"
                          disabled={isDownloading}
                          onClick={() => handleDownloadPdf(rcpt)}
                          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-cream-surface hover:bg-cream-deep border border-divider text-xs font-bold text-ink transition-colors disabled:opacity-50"
                        >
                          <Download className="w-3.5 h-3.5" />
                          <span>{isDownloading ? "Downloading..." : "Download PDF"}</span>
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Footer */}
          <div className="p-4 border-t border-divider bg-cream-surface/40 flex items-center justify-between text-xs">
            <span className="text-[11px] text-ink-muted">
              Sharon Online (Pty) Ltd. VAT registration
            </span>
            <button
              type="button"
              onClick={loadReceipts}
              disabled={loading}
              className="inline-flex items-center gap-1 text-ink-muted hover:text-ink font-semibold"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
              <span>Refresh</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
