"use client";

import { useState } from "react";
import { ShieldCheck, CreditCard, Lock, ArrowRight, ExternalLink } from "lucide-react";

interface PayFastFormProps {
  /** Formatted amount to display (from the platform price list, or the server's checkout/init response); null while unknown. */
  amountLabel: string | null;
  bookingReference: string;
  itemDescription: string;
  /** Initializes the signed PayFast redirect. Booking success still comes only from the ITN webhook. */
  onSuccess: () => void | Promise<void>;
  disabled?: boolean;
}

export function PayFastForm({
  amountLabel,
  bookingReference,
  itemDescription,
  onSuccess,
  disabled = false,
}: PayFastFormProps) {
  const [processing, setProcessing] = useState(false);

  // The server returns signed redirect fields; only PayFast's verified ITN can confirm the booking.
  const handlePayFastPayment = async (e: React.FormEvent) => {
    e.preventDefault();
    setProcessing(true);
    try {
      await onSuccess();
    } finally {
      setProcessing(false);
    }
  };

  return (
    <div className="bg-white rounded-3xl p-6 border border-divider shadow-card space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-xl bg-cocoa/10 text-cocoa flex items-center justify-center font-bold text-sm">
            🇿🇦
          </div>
          <div>
            <div className="text-sm font-bold text-ink">PayFast Instant EFT / Card</div>
            <div className="text-sm text-ink-muted">South African ZAR Gateway</div>
          </div>
        </div>

        <span className="text-sm font-extrabold text-cocoa font-serif">
          {amountLabel ?? "Price unavailable"}
        </span>
      </div>

      <div className="p-3 bg-cream-surface rounded-xl border border-divider text-sm space-y-1.5">
        <div className="flex justify-between text-ink-muted">
          <span>Booking Reference:</span>
          <span className="font-bold text-ink">{bookingReference}</span>
        </div>
        <div className="flex justify-between text-ink-muted">
          <span>Supported Banks:</span>
          <span className="font-semibold text-ink">Capitec, FNB, Standard Bank, ABSA, Nedbank</span>
        </div>
      </div>

      <div className="p-3 bg-amber-50 border border-amber-200 rounded-xl text-sm text-amber-900">
        You will be redirected to PayFast. This page waits for the verified ITN before showing success.
      </div>

      <form onSubmit={handlePayFastPayment} className="space-y-3">
        <button
          type="submit"
          disabled={disabled || processing}
          className="w-full py-3.5 bg-cocoa hover:bg-cocoa-hover text-white rounded-xl text-sm font-bold transition-all shadow-sm flex items-center justify-center gap-2 disabled:opacity-50"
        >
          {processing ? (
            "Starting PayFast..."
          ) : (
            <>
              <Lock className="w-3.5 h-3.5" />
              <span>Pay{amountLabel ? ` ${amountLabel}` : ""} via PayFast</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </>
          )}
        </button>

        <div className="text-sm text-center text-ink-muted flex items-center justify-center gap-1">
          <ShieldCheck className="w-3 h-3 text-success" />
          <span>PCI-DSS Level 1 256-Bit Encrypted Payment Guarantee</span>
        </div>
      </form>
    </div>
  );
}
