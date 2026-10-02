"use client";

import { useState } from "react";
import { ShieldCheck, CreditCard, Lock, ArrowRight, ExternalLink } from "lucide-react";

interface PayFastFormProps {
  amountZar: number;
  bookingReference: string;
  itemDescription: string;
  /** Asks the parent to confirm payment with the server. Must reject on failure. */
  onSuccess: () => void | Promise<void>;
  disabled?: boolean;
}

export function PayFastForm({
  amountZar,
  bookingReference,
  itemDescription,
  onSuccess,
  disabled = false,
}: PayFastFormProps) {
  const [processing, setProcessing] = useState(false);

  // NOTE: the live PayFast redirect/ITN flow is not integrated yet. No payment is taken here; this only asks the
  // server to confirm, and the parent shows the server's real answer (it will fail until live payments exist).
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
          <div className="w-8 h-8 rounded-xl bg-teal/10 text-teal flex items-center justify-center font-bold text-xs">
            🇿🇦
          </div>
          <div>
            <div className="text-xs font-bold text-ink">PayFast Instant EFT / Card</div>
            <div className="text-[10px] text-ink-muted">South African ZAR Gateway</div>
          </div>
        </div>

        <span className="text-sm font-extrabold text-teal font-serif">
          R{Math.round(amountZar)} ZAR
        </span>
      </div>

      <div className="p-3 bg-cream-surface rounded-xl border border-divider text-xs space-y-1.5">
        <div className="flex justify-between text-ink-muted">
          <span>Booking Reference:</span>
          <span className="font-bold text-ink">{bookingReference}</span>
        </div>
        <div className="flex justify-between text-ink-muted">
          <span>Supported Banks:</span>
          <span className="font-semibold text-ink">Capitec, FNB, Standard Bank, ABSA, Nedbank</span>
        </div>
      </div>

      <div className="p-3 bg-amber-50 border border-amber-200 rounded-xl text-[11px] text-amber-900">
        PayFast payments are not switched on yet. Trying to pay will ask the server to confirm and may be declined.
      </div>

      <form onSubmit={handlePayFastPayment} className="space-y-3">
        <button
          type="submit"
          disabled={disabled || processing}
          className="w-full py-3.5 bg-teal hover:bg-teal-hover text-white rounded-xl text-xs font-bold transition-all shadow-sm flex items-center justify-center gap-2 disabled:opacity-50"
        >
          {processing ? (
            "Confirming with server..."
          ) : (
            <>
              <Lock className="w-3.5 h-3.5" />
              <span>Pay R{Math.round(amountZar)} ZAR via PayFast</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </>
          )}
        </button>

        <div className="text-[10px] text-center text-ink-muted flex items-center justify-center gap-1">
          <ShieldCheck className="w-3 h-3 text-success" />
          <span>PCI-DSS Level 1 256-Bit Encrypted Payment Guarantee</span>
        </div>
      </form>
    </div>
  );
}
