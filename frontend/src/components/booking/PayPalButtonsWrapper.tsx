"use client";

import { useRef, useState } from "react";
import { PayPalButtons, PayPalScriptProvider, usePayPalScriptReducer } from "@paypal/react-paypal-js";
import { Lock, ShieldCheck } from "lucide-react";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/http";
import { checkoutFailureMessage } from "@/lib/fx";
import {
  interpretCaptureError,
  interpretCaptureResponse,
  type CaptureTarget,
  type OutcomeView,
} from "@/lib/paypalOutcome";

export type PayPalCheckoutTarget =
  | { kind: "booking"; bookingId: string }
  | { kind: "credit_pack"; packId: number };

export type PayPalCurrency = "USD" | "EUR" | "JPY";

interface PayPalButtonsWrapperProps {
  target: PayPalCheckoutTarget;
  /** SDK currency AND the currency the order is created in. */
  currency: PayPalCurrency;
  /** Formatted amount to display (platform price list, or the server's checkout/init response); null while unknown. */
  amountLabel: string | null;
  /** Human reference shown to the student (booking reference or pack name). */
  reference: string;
  /** The server's authoritative quote from checkout/init (shown by the parent). */
  onQuote?: (quote: { amount: string; currency: string }) => void;
  /**
   * Called with the interpreted server result of a capture, or of a capture error. The parent performs navigation or
   * polling from `view.nextAction`. This component never marks anything paid.
   */
  onOutcome: (view: OutcomeView) => void | Promise<void>;
  disabled?: boolean;
}

const CLIENT_ID = process.env.NEXT_PUBLIC_PAYPAL_CLIENT_ID;

export function PayPalButtonsWrapper(props: PayPalButtonsWrapperProps) {
  const { amountLabel, reference } = props;

  return (
    <div className="bg-white rounded-3xl p-6 border border-divider shadow-card space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-xl bg-gold/15 text-gold-bright flex items-center justify-center font-bold text-xs">
            PP
          </div>
          <div>
            <div className="text-xs font-bold text-ink">PayPal & International Cards</div>
            <div className="text-[10px] text-ink-muted">USD, EUR, JPY Gateway</div>
          </div>
        </div>
        <span className="text-sm font-extrabold text-ink font-serif">{amountLabel ?? "Price unavailable"}</span>
      </div>

      <div className="p-3 bg-cream-surface rounded-xl border border-divider text-xs space-y-1.5">
        <div className="flex justify-between text-ink-muted">
          <span>Reference:</span>
          <span className="font-bold text-ink">{reference}</span>
        </div>
        <div className="flex justify-between text-ink-muted">
          <span>Supported Methods:</span>
          <span className="font-semibold text-ink">PayPal Balance, Visa, Mastercard, AMEX</span>
        </div>
      </div>

      <div className="p-3 bg-amber-50 border border-amber-200 rounded-xl text-[11px] text-amber-900">
        Your payment is confirmed by our server after PayPal reports the result. This page never marks its own payment
        successful.
      </div>

      {!CLIENT_ID ? (
        <div role="alert" className="p-3 bg-red-50 border border-red-200 rounded-xl text-xs text-red-800">
          PayPal is not configured. Card and PayPal payments are unavailable right now; please try again later or contact
          support.
        </div>
      ) : (
        // Remount the SDK when the currency changes: the PayPal script is loaded for exactly one currency.
        <PayPalScriptProvider
          key={props.currency}
          options={{ clientId: CLIENT_ID, currency: props.currency, intent: "capture", components: "buttons" }}
        >
          <PayPalButtonsInner {...props} />
        </PayPalScriptProvider>
      )}

      <div className="text-[10px] text-center text-ink-muted flex items-center justify-center gap-1">
        <ShieldCheck className="w-3 h-3 text-success" />
        <span>PayPal Buyer Protection & 24-Hour Escrow Hold</span>
      </div>
    </div>
  );
}

function PayPalButtonsInner({ target, currency, onQuote, onOutcome, disabled = false }: PayPalButtonsWrapperProps) {
  const [{ isPending, isRejected }] = usePayPalScriptReducer();
  const [message, setMessage] = useState<string | null>(null);
  const [finishing, setFinishing] = useState(false);
  // True once createOrder/capture already put a specific message on screen, so the generic onError does not overwrite it.
  const messageIsSpecific = useRef(false);
  const targetKind: CaptureTarget = target.kind;

  const show = (text: string | null, specific = false) => {
    messageIsSpecific.current = specific;
    setMessage(text);
  };

  if (isRejected) {
    return (
      <div role="alert" className="p-3 bg-red-50 border border-red-200 rounded-xl text-xs text-red-800">
        We could not load PayPal. Check your connection or ad-blocker and reload the page.
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {isPending && <div className="text-xs text-ink-muted text-center py-3">Loading PayPal...</div>}

      {finishing && (
        <div role="status" className="text-xs text-ink font-semibold text-center py-2 flex items-center justify-center gap-1.5">
          <Lock className="w-3.5 h-3.5" /> Finishing your payment securely. Please do not close this page...
        </div>
      )}

      <div className={disabled || finishing ? "pointer-events-none opacity-50" : undefined}>
        <PayPalButtons
          style={{ layout: "vertical", shape: "rect", label: "pay" }}
          disabled={disabled || finishing}
          forceReRender={[currency, target.kind === "booking" ? target.bookingId : target.packId]}
          createOrder={async () => {
            show(null);
            try {
              const checkout = await api.initializeCheckout({
                ...(target.kind === "booking" ? { booking_id: target.bookingId } : { credit_pack_id: target.packId }),
                gateway: "paypal",
                currency,
              });
              if (!checkout?.order_id) {
                throw new Error("The server did not return a PayPal order.");
              }
              onQuote?.({ amount: String(checkout.amount), currency: String(checkout.currency) });
              return String(checkout.order_id);
            } catch (err) {
              console.error("PayPal createOrder failed:", err);
              show(checkoutFailureMessage(err, `We could not start PayPal checkout. ${errorMessage(err)}`), true);
              throw err;
            }
          }}
          onApprove={async (data, actions) => {
            setFinishing(true);
            show(null);
            try {
              const resp = await api.capturePayPalOrder(data.orderID);
              const view = interpretCaptureResponse(resp, targetKind);
              if (view.nextAction.type === "restart") {
                show(view.message, true);
                // Let the buyer pick another funding source inside the same PayPal order.
                await actions.restart();
                return;
              }
              if (view.kind === "error" || view.kind === "retry") show(view.message, true);
              await onOutcome(view);
            } catch (err) {
              console.error("PayPal capture failed:", err);
              const view = interpretCaptureError(err);
              show(view.message, true);
              await onOutcome(view);
            } finally {
              setFinishing(false);
            }
          }}
          onCancel={() => {
            show("Payment cancelled. Nothing was charged. You can pay whenever you are ready.", true);
          }}
          onError={(err) => {
            console.error("PayPal button error:", err);
            if (!messageIsSpecific.current) {
              show("PayPal reported a problem. Nothing has been confirmed. Please try again.");
            }
          }}
        />
      </div>

      {message && (
        <div role="alert" className="p-3 bg-amber-50 border border-amber-200 rounded-xl text-xs text-amber-900">
          {message}
        </div>
      )}
    </div>
  );
}
