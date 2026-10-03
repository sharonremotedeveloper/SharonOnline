"use client";

import { useState } from "react";
import { CreditCard, Lock, ShieldCheck, ArrowRight } from "lucide-react";

interface PayPalButtonsWrapperProps {
  /** Formatted amount to display (from the platform price list, or the server's checkout/init response); null while unknown. */
  amountLabel: string | null;
  bookingReference: string;
  /** Initializes a server-authoritative checkout. Booking success still comes only from the webhook. */
  onSuccess: () => void | Promise<void>;
  disabled?: boolean;
}

export function PayPalButtonsWrapper({
  amountLabel,
  bookingReference,
  onSuccess,
  disabled = false,
}: PayPalButtonsWrapperProps) {
  const [processing, setProcessing] = useState(false);

  // Provider capture is confirmed asynchronously by the PayPal webhook; this action cannot confirm a booking itself.
  const handlePayPal = async (e: React.FormEvent) => {
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
          <div className="w-8 h-8 rounded-xl bg-gold/15 text-gold-bright flex items-center justify-center font-bold text-xs">
            🌐
          </div>
          <div>
            <div className="text-xs font-bold text-ink">PayPal & International Cards</div>
            <div className="text-[10px] text-ink-muted">USD, EUR, JPY Gateway</div>
          </div>
        </div>

        <span className="text-sm font-extrabold text-ink font-serif">
          {amountLabel ?? "Price unavailable"}
        </span>
      </div>

      <div className="p-3 bg-cream-surface rounded-xl border border-divider text-xs space-y-1.5">
        <div className="flex justify-between text-ink-muted">
          <span>Booking Reference:</span>
          <span className="font-bold text-ink">{bookingReference}</span>
        </div>
        <div className="flex justify-between text-ink-muted">
          <span>Supported Methods:</span>
          <span className="font-semibold text-ink">PayPal Balance, Visa, Mastercard, AMEX</span>
        </div>
      </div>

      <div className="p-3 bg-amber-50 border border-amber-200 rounded-xl text-[11px] text-amber-900">
        Your booking is confirmed only after PayPal reports a verified capture. This page never marks its own payment successful.
      </div>

      <form onSubmit={handlePayPal} className="space-y-3">
        <button
          type="submit"
          disabled={disabled || processing}
          className="w-full py-3.5 bg-accent hover:bg-gold-bright text-ink rounded-xl text-xs font-extrabold transition-all shadow-sm flex items-center justify-center gap-2 disabled:opacity-50"
        >
          {processing ? (
            "Starting checkout..."
          ) : (
            <>
              <Lock className="w-3.5 h-3.5" />
              <span>Checkout with PayPal{amountLabel ? ` (${amountLabel})` : ""}</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </>
          )}
        </button>

        <div className="text-[10px] text-center text-ink-muted flex items-center justify-center gap-1">
          <ShieldCheck className="w-3 h-3 text-success" />
          <span>PayPal Buyer Protection & 24-Hour Escrow Hold</span>
        </div>
      </form>
    </div>
  );
}
