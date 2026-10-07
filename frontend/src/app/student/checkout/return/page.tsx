"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowRight, AlertTriangle } from "lucide-react";
import { api } from "@/lib/api";
import { clearPendingPayFast, readPendingPayFast, type PendingPayFast } from "@/lib/pendingPayment";

const POLL_MS = 3000;
// Stop after about two minutes: PayFast's server-to-server notification normally lands within seconds.
const MAX_POLLS = 40;

type View =
  | { state: "checking" }
  | { state: "confirmed-booking"; id: string }
  | { state: "credited" }
  | { state: "failed"; text: string }
  | { state: "waiting" } // still not confirmed after polling, or nothing to look up
  | { state: "error"; text: string };

/**
 * PayFast sends the buyer back here after the hosted payment page. A visit to this page proves nothing about payment
 * (the buyer controls the URL), so it only looks up the real booking / credit purchase status and displays it. Money
 * and booking state change only through PayFast's verified server-to-server notification.
 */
function PayFastReturn() {
  const router = useRouter();
  const ref = useSearchParams()?.get("ref") ?? null;
  const [view, setView] = useState<View>({ state: "checking" });

  useEffect(() => {
    const hint: PendingPayFast | null = readPendingPayFast();
    if (!hint) {
      setView({ state: "waiting" });
      return;
    }
    let cancelled = false;
    let polls = 0;
    let timer: number | undefined;

    const finish = (next: View, clear: boolean) => {
      if (cancelled) return;
      if (clear) clearPendingPayFast();
      setView(next);
    };

    const check = async () => {
      polls += 1;
      try {
        if (hint.kind === "booking") {
          const booking = await api.getBooking(hint.id);
          if (booking.status === "confirmed" || booking.status === "in_progress" || booking.status === "completed") {
            finish({ state: "confirmed-booking", id: booking.id }, true);
            router.replace(`/student/confirmed/${booking.id}`);
            return;
          }
          if (booking.status !== "pending_payment") {
            finish({ state: "failed", text: "This reservation is no longer awaiting payment. If you were charged we will e-mail you." }, true);
            return;
          }
        } else {
          const purchase = await api.getCreditPurchase(hint.id);
          if (purchase.status === "success") {
            finish({ state: "credited" }, true);
            return;
          }
          if (purchase.status === "failed" || purchase.status === "refunded") {
            finish({ state: "failed", text: "This purchase was not completed and no credits were added." }, true);
            return;
          }
        }
      } catch (err) {
        console.error("PayFast return status check failed:", err);
        if (polls >= 3) {
          finish({ state: "error", text: "We could not check your payment status right now." }, false);
          return;
        }
      }
      if (polls >= MAX_POLLS) {
        finish({ state: "waiting" }, false);
        return;
      }
      timer = window.setTimeout(check, POLL_MS);
    };

    check();
    return () => {
      cancelled = true;
      if (timer) window.clearTimeout(timer);
    };
  }, [router]);

  return (
    <div className="max-w-xl mx-auto px-4 py-16 text-center space-y-4">
      <h1 className="text-xl font-extrabold text-ink font-serif">
        {view.state === "credited" ? "Credits added" : "Thanks - confirming your payment"}
      </h1>

      {view.state === "checking" && (
        <p role="status" className="text-sm text-ink-muted">
          We are waiting for PayFast to confirm your payment with our server. This usually takes a few seconds.
        </p>
      )}
      {view.state === "confirmed-booking" && (
        <p role="status" className="text-sm text-ink-muted">Payment confirmed. Taking you to your lesson...</p>
      )}
      {view.state === "credited" && (
        <p role="status" className="text-sm text-ink-muted">Your payment was confirmed and the credits are now in your wallet.</p>
      )}
      {(view.state === "failed" || view.state === "error") && (
        <p role="alert" className="text-sm text-warning-hover bg-warning-surface border border-warning-border rounded-xl p-3"><AlertTriangle className="mr-2 inline h-4 w-4 shrink-0 align-text-bottom" aria-hidden="true" /><span className="sr-only">Warning: </span>{view.text}</p>
      )}
      {view.state === "waiting" && (
        <p role="status" className="text-sm text-ink-muted">
          We have not received PayFast&apos;s confirmation yet. There is nothing more you need to do: your lesson or
          credits appear in your account as soon as it arrives, and we will e-mail you. You can check your bookings
          and wallet below.
        </p>
      )}

      {ref && <p className="text-sm text-ink-muted">Payment reference: {ref}</p>}

      <div className="flex flex-col sm:flex-row gap-3 justify-center pt-2">
        <Link href="/student/dashboard" className="min-h-11 inline-flex items-center justify-center gap-2 px-5 py-2.5 bg-cocoa text-white rounded-xl text-sm font-bold">
          My bookings <ArrowRight className="w-3.5 h-3.5" />
        </Link>
        <Link href="/student/wallet" className="min-h-11 inline-flex items-center justify-center gap-2 px-5 py-2.5 border border-divider rounded-xl text-sm font-bold text-ink">
          My wallet
        </Link>
      </div>
    </div>
  );
}

export default function PayFastReturnPage() {
  return (
    <Suspense fallback={<div className="max-w-xl mx-auto px-4 py-16 text-center text-sm text-ink-muted">Loading...</div>}>
      <PayFastReturn />
    </Suspense>
  );
}
