"use client";

import { useState } from "react";
import { CreditCard, Lock, ShieldCheck, ArrowRight } from "lucide-react";

interface PayPalButtonsWrapperProps {
  amountUsd: number;
  currency?: string;
  bookingReference: string;
  onSuccess: (orderId: string) => void;
  disabled?: boolean;
}

export function PayPalButtonsWrapper({
  amountUsd,
  currency = "USD",
  bookingReference,
  onSuccess,
  disabled = false,
}: PayPalButtonsWrapperProps) {
  const [processing, setProcessing] = useState(false);

  const handleSimulatedPayPal = (e: React.FormEvent) => {
    e.preventDefault();
    setProcessing(true);

    setTimeout(() => {
      setProcessing(false);
      onSuccess(`PAYPAL_ORDER_${Date.now()}`);
    }, 1200);
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
          ${amountUsd.toFixed(2)} {currency}
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

      <form onSubmit={handleSimulatedPayPal} className="space-y-3">
        <button
          type="submit"
          disabled={disabled || processing}
          className="w-full py-3.5 bg-accent hover:bg-gold-bright text-ink rounded-xl text-xs font-extrabold transition-all shadow-sm flex items-center justify-center gap-2 disabled:opacity-50"
        >
          {processing ? (
            "Authorizing PayPal Order..."
          ) : (
            <>
              <Lock className="w-3.5 h-3.5" />
              <span>Checkout with PayPal (${amountUsd.toFixed(2)})</span>
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
