"use client";

import { useState, useEffect, useCallback } from "react";
import { dayLabel, zoneCityName } from "@/lib/scheduling";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import {
  ShieldCheck,
  Zap,
  Coins,
  CreditCard,
  Lock,
  ArrowRight,
  ArrowLeft,
  Calendar,
  Clock,
  CheckCircle2, AlertTriangle } from "lucide-react";
import { api } from "@/lib/api";
import { BookingDetail } from "@/types/booking";
import { useAuth } from "@/context/AuthContext";
import { Avatar } from "@/components/ui/Avatar";
import { ErrorState, InlineError } from "@/components/ui/ErrorState";
import { errorMessage } from "@/lib/http";
import { currencyDecimals, formatLessonPrice, formatMoney, lessonPriceFor } from "@/lib/prices";
import { detectDefaultCurrency, type CurrencyCode } from "@/lib/currency";
import { checkoutFailureMessage, paypalCheckoutCurrency } from "@/lib/fx";
import { useLessonPrices } from "@/hooks/useLessonPrices";
import { ReservationTimer } from "@/components/booking/ReservationTimer";
import { PayFastForm } from "@/components/booking/PayFastForm";
import { PayPalButtonsWrapper } from "@/components/booking/PayPalButtonsWrapper";
import { PAYMENTS_ENABLED } from "@/lib/paymentsEnabled";
import type { OutcomeView } from "@/lib/paypalOutcome";
import { rememberPendingPayFast } from "@/lib/pendingPayment";
import { creditsLabel } from "@/lib/rating";

export default function StudentCheckoutPage() {
  const params = useParams();
  const router = useRouter();
  const bookingId = params?.bookingId as string;
  const { user } = useAuth();

  const [booking, setBooking] = useState<BookingDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeGateway, setActiveGateway] = useState<"credit" | "payfast" | "paypal">("credit");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [loadError, setLoadError] = useState<unknown>(null);
  const [reloadTick, setReloadTick] = useState(0);
  // Seconds left on the server-side slot hold, computed once when the booking loads (source of truth: lock_expires_at).
  const [holdSeconds, setHoldSeconds] = useState<number | null>(null);
  // Set while PayPal has accepted the order but not finished verifying it ("Payment under review"): we poll the booking.
  const [underReview, setUnderReview] = useState<string | null>(null);
  // The hold expired or the slot was taken while the student was paying (capture answered 409).
  const [slotLost, setSlotLost] = useState(false);
  // Server truth: the amount and currency checkout/init returned for this booking (null until the student starts paying).
  const [quote, setQuote] = useState<{ gateway: string; amount: string; currency: string } | null>(null);
  // Before checkout/init there is no quote yet, so show the platform lesson price for the chosen gateway's currency.
  const { data: lessonPrices } = useLessonPrices();

  // The student's chosen display currency (localStorage 'sharon_currency' / timezone). Read after mount to avoid a
  // server/client hydration mismatch. Only EUR and JPY change what PayPal is asked to charge.
  const [displayCurrency, setDisplayCurrency] = useState<CurrencyCode>("USD");
  useEffect(() => {
    setDisplayCurrency(detectDefaultCurrency());
  }, []);
  const paypalCurrency = paypalCheckoutCurrency(displayCurrency);

  // Real credit balance only; never assume a default. `/auth/me/` may not provide it yet.
  const userCredits = user?.credits ?? 0;
  const hasCredits = userCredits > 0;

  useEffect(() => {
    if (!bookingId) return;
    let cancelled = false;
    async function loadBooking() {
      setLoading(true);
      setLoadError(null);
      try {
        const data = await api.getBooking(bookingId);
        if (cancelled) return;
        setBooking(data);
        const expiresMs = data.lock_expires_at ? new Date(data.lock_expires_at).getTime() : NaN;
        setHoldSeconds(Number.isFinite(expiresMs) ? Math.max(0, Math.floor((expiresMs - Date.now()) / 1000)) : null);
      } catch (err) {
        console.error("Failed to load booking details:", err);
        if (cancelled) return;
        setBooking(null);
        setLoadError(err);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    loadBooking();
    return () => {
      cancelled = true;
    };
  }, [bookingId, reloadTick]);

  // Default to the card gateway when the student has no credits to redeem.
  useEffect(() => {
    if (!hasCredits && PAYMENTS_ENABLED) setActiveGateway((g) => (g === "credit" ? "paypal" : g));
  }, [hasCredits]);

  const handleHoldExpired = useCallback(() => {
    if (booking) router.push(`/student/book/${booking.teacher.id}?expired=1`);
  }, [booking, router]);

  const handleRedeemCredit = async () => {
    setSubmitting(true);
    setError(null);

    try {
      await api.redeemCredit(bookingId);
      router.push(`/student/confirmed/${bookingId}`);
    } catch (err) {
      console.error("Failed to redeem credit:", err);
      setError(err);
      setSubmitting(false);
    }
  };

  useEffect(() => {
    if (!underReview || !bookingId) return;
    const timer = window.setInterval(async () => {
      try {
        const fresh = await api.getBooking(bookingId);
        setBooking(fresh);
        if (fresh.status === "confirmed") {
          window.clearInterval(timer);
          router.push(`/student/confirmed/${bookingId}`);
        } else if (fresh.status !== "pending_payment") {
          window.clearInterval(timer);
          setUnderReview(null);
          setError(`Payment was not applied because the booking is now ${fresh.status}. Support has been notified.`);
        }
      } catch (err) {
        console.error("Payment status poll failed:", err);
      }
    }, 3000);
    return () => window.clearInterval(timer);
  }, [underReview, bookingId, router]);

  // PayFast is a signed server redirect. Whether it was paid is decided only by PayFast's verified ITN on the server.
  const handlePayFastStart = async () => {
    setSubmitting(true);
    setError(null);
    try {
      const checkout = await api.initializeCheckout({ booking_id: bookingId, gateway: "payfast" });
      setQuote({ gateway: "payfast", amount: String(checkout.amount), currency: String(checkout.currency) });
      if (!checkout?.action_url || !checkout?.fields) {
        throw new Error("The server did not return a PayFast redirect.");
      }
      rememberPendingPayFast({ kind: "booking", id: bookingId });
      const form = document.createElement("form");
      form.method = "POST";
      form.action = checkout.action_url;
      for (const [name, value] of Object.entries(checkout.fields)) {
        const input = document.createElement("input");
        input.type = "hidden";
        input.name = name;
        input.value = String(value);
        form.appendChild(input);
      }
      document.body.appendChild(form);
      form.submit();
    } catch (err) {
      console.error("Failed to initialize payment:", err);
      setError(checkoutFailureMessage(err, `We could not start checkout. ${errorMessage(err)}`));
    } finally {
      setSubmitting(false);
    }
  };

  // The PayPal component reports the server's verdict; this page only routes on it.
  const handlePayPalOutcome = async (view: OutcomeView) => {
    const action = view.nextAction;
    if (action.type === "go_confirmed") {
      router.push(`/student/confirmed/${action.bookingId}${action.pendingNotice ? "?payment=pending" : ""}`);
    } else if (action.type === "poll") {
      setUnderReview(action.id);
    } else if (action.type === "back_to_tutor") {
      setSlotLost(true);
    } else if (action.type === "check_then_retry") {
      // Only the response may have been lost: look once at the booking before the student retries.
      try {
        const fresh = await api.getBooking(bookingId);
        if (fresh.status === "confirmed") {
          router.push(`/student/confirmed/${bookingId}`);
          return;
        }
      } catch (err) {
        console.error("Post-capture booking check failed:", err);
      }
      setError("Your booking is not confirmed yet. If you were charged we will e-mail you; otherwise you can try the payment again.");
    }
  };

  const gatewayCurrency: CurrencyCode = activeGateway === "payfast" ? "ZAR" : (paypalCurrency ?? "USD");
  const listPrice = lessonPriceFor(lessonPrices, gatewayCurrency);
  // The server's quote is only shown while it matches the gateway and currency currently selected.
  const activeQuote =
    quote && quote.gateway === activeGateway && quote.currency === gatewayCurrency ? quote : null;
  const amountLabel = activeQuote
    ? formatMoney(activeQuote.amount, activeQuote.currency, currencyDecimals(activeQuote.currency))
    : listPrice
      ? formatLessonPrice(listPrice)
      : null;
  const amountCurrency = activeQuote ? activeQuote.currency : listPrice ? listPrice.currency : null;

  if (loading) {
    return (
      <div className="max-w-4xl mx-auto px-4 py-16 text-center text-sm text-ink-muted">
        Loading checkout reservation...
      </div>
    );
  }

  if (loadError || !booking) {
    return (
      <div className="max-w-4xl mx-auto px-4 py-16">
        <ErrorState
          error={loadError ?? "We could not find this reservation."}
          title="We could not load your reservation"
          onRetry={() => setReloadTick((t) => t + 1)}
        />
      </div>
    );
  }

  if (booking.status !== "pending_payment") {
    const confirmed = booking.status === "confirmed";
    return (
      <div className="max-w-xl mx-auto px-4 py-16 text-center space-y-4">
        <h2 className="text-xl font-extrabold text-ink font-serif">
          {confirmed ? "This lesson is already confirmed" : "This reservation is no longer awaiting payment"}
        </h2>
        <p className="text-sm text-ink-muted">
          {confirmed
            ? "No further payment is needed."
            : "The slot hold may have expired or been released. Please pick a new time."}
        </p>
        <Link
          href={confirmed ? `/student/confirmed/${booking.id}` : `/student/book/${booking.teacher.id}`}
          className="min-h-11 inline-flex items-center gap-2 px-5 py-2.5 bg-cocoa text-white rounded-xl text-sm font-bold"
        >
          {confirmed ? "View confirmation" : "Choose a new slot"} <ArrowRight className="w-3.5 h-3.5" />
        </Link>
      </div>
    );
  }

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-10 space-y-8">
      {/* Back button */}
      <div>
        <Link
          href={`/student/book/${booking.teacher.id}`}
          className="inline-flex items-center gap-1.5 text-sm font-bold text-ink-muted hover:text-ink transition-colors"
        >
          <ArrowLeft className="w-3.5 h-3.5" /> Change Slot
        </Link>
      </div>

      {/* 10-Minute Lock Timer Bar */}
      {holdSeconds !== null && !underReview && (
        <ReservationTimer
          initialSeconds={holdSeconds}
          onExpire={handleHoldExpired}
          onRestart={() => router.push(`/student/book/${booking.teacher.id}`)}
        />
      )}

      <InlineError error={error} />

      {slotLost && (
        <div role="alert" className="p-4 rounded-2xl bg-warning-surface border border-warning-border text-sm text-warning-hover space-y-2"><AlertTriangle className="mr-2 inline h-4 w-4 shrink-0 align-text-bottom" aria-hidden="true" /><span className="sr-only">Warning: </span>
          <p>
            This time slot is no longer available (the reservation expired or the slot was taken). If PayPal took a
            payment we will refund it automatically and e-mail you.
          </p>
          <Link href={`/student/book/${booking.teacher.id}`} className="inline-flex items-center gap-1.5 font-bold text-cocoa">
            Choose a new time <ArrowRight className="w-3.5 h-3.5" />
          </Link>
        </div>
      )}

      {/* Checkout Grid: Left = Payment Method / Right = Order Summary */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 items-start">
        {/* Left Column: Payment Options */}
        <div className="lg:col-span-2 space-y-6">
          <div className="bg-white rounded-3xl p-6 sm:p-8 border border-divider shadow-card space-y-6">
            <div>
              <h2 className="text-xl font-extrabold text-ink font-serif">Select Checkout Method</h2>
              <p className="text-sm text-ink-muted mt-0.5">
                Redeem a pre-purchased lesson credit or pay directly with card / instant EFT
              </p>
            </div>

            {/* Gateway Selector Tabs */}
            {PAYMENTS_ENABLED && (
            <div className={`grid ${hasCredits ? "grid-cols-3" : "grid-cols-2"} gap-2 p-1.5 bg-cream-surface rounded-2xl border border-divider`}>
              {hasCredits && (
              <button
                type="button"
                onClick={() => setActiveGateway("credit")}
                className={`min-h-11 py-2.5 px-3 rounded-xl text-sm font-bold transition-all flex items-center justify-center gap-1.5 ${
                  activeGateway === "credit"
                    ? "bg-cocoa text-white shadow-sm"
                    : "text-ink-muted hover:text-ink"
                }`}
              >
                <Coins className="w-3.5 h-3.5" />
                <span>1 Credit ({userCredits} left)</span>
              </button>
              )}

              <button
                type="button"
                onClick={() => setActiveGateway("paypal")}
                className={`min-h-11 py-2.5 px-3 rounded-xl text-sm font-bold transition-all flex items-center justify-center gap-1.5 ${
                  activeGateway === "paypal"
                    ? "bg-cocoa text-white shadow-sm"
                    : "text-ink-muted hover:text-ink"
                }`}
              >
                <CreditCard className="w-3.5 h-3.5" />
                <span>PayPal / Cards</span>
              </button>

              <button
                type="button"
                onClick={() => setActiveGateway("payfast")}
                className={`min-h-11 py-2.5 px-3 rounded-xl text-sm font-bold transition-all flex items-center justify-center gap-1.5 ${
                  activeGateway === "payfast"
                    ? "bg-cocoa text-white shadow-sm"
                    : "text-ink-muted hover:text-ink"
                }`}
              >
                <span>🇿🇦 PayFast (ZAR)</span>
              </button>
            </div>
            )}
            {!PAYMENTS_ENABLED && (<p className="text-sm text-ink-muted bg-cream-surface border border-divider rounded-xl px-4 py-3">
            Payments are switched off in this test environment. Lessons are booked with lesson credits.
            </p>)}

            {/* Path A: Credit Redemption */}
            {hasCredits && activeGateway === "credit" && (
              <div className="p-6 rounded-2xl bg-cream-surface border border-cream-deep space-y-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Coins className="w-5 h-5 text-cocoa" />
                    <span className="text-sm font-bold text-ink">Lesson Credit Wallet</span>
                  </div>
                  <span className="text-sm font-bold text-cocoa bg-white px-3 py-1 rounded-full border border-divider">
                    Balance: {creditsLabel(userCredits)}
                  </span>
                </div>

                {userCredits > 0 ? (
                  <>
                    <p className="text-sm text-ink-muted leading-relaxed">
                      You have <strong>{userCredits} active lesson credits</strong> available. Confirming will deduct 1 credit and immediately verify your private 25-minute classroom slot with {booking.teacher.full_name}.
                    </p>

                    <button
                      onClick={handleRedeemCredit}
                      disabled={submitting}
                      className="min-h-11 w-full py-4 bg-cocoa hover:bg-cocoa-hover text-white rounded-xl text-sm font-bold transition-all shadow-sm flex items-center justify-center gap-2 disabled:opacity-50"
                    >
                      {submitting ? (
                        "Redeeming Credit..."
                      ) : (
                        <>
                          <CheckCircle2 className="w-4 h-4" />
                          <span>Confirm Booking with 1 Credit</span>
                          <ArrowRight className="w-4 h-4" />
                        </>
                      )}
                    </button>
                  </>
                ) : (
                  <div className="space-y-3">
                    <p className="text-sm text-primary font-medium">
                      You have 0 lesson credits left in your wallet.
                    </p>
                    <Link
                      href="/pricing"
                      className="min-h-11 inline-flex items-center gap-2 px-4 py-2 bg-cocoa text-white rounded-xl text-sm font-bold"
                    >
                      Top Up Lesson Pack <ArrowRight className="w-3.5 h-3.5" />
                    </Link>
                  </div>
                )}
              </div>
            )}

            {/* Payment under review: PayPal has not finished verifying; we poll the booking and e-mail the result. */}
            {underReview && (
              <div role="status" className="p-6 rounded-2xl bg-cream-surface border border-cream-deep space-y-2">
                <h3 className="text-sm font-extrabold text-ink font-serif">Payment under review</h3>
                <p className="text-sm text-ink-muted leading-relaxed">
                  PayPal is still checking your payment. Please keep this page open: your lesson will be confirmed
                  here as soon as PayPal finishes. We will also e-mail you the result, so you can safely leave.
                </p>
              </div>
            )}

            {/* Path B1: PayPal International */}
            {PAYMENTS_ENABLED && activeGateway === "paypal" && !underReview && !slotLost && (
              <PayPalButtonsWrapper
                target={{ kind: "booking", bookingId }}
                currency={paypalCurrency ?? "USD"}
                amountLabel={amountLabel}
                reference={booking.booking_reference}
                onQuote={(q) => setQuote({ gateway: "paypal", amount: q.amount, currency: q.currency })}
                onOutcome={handlePayPalOutcome}
                disabled={submitting}
              />
            )}

            {/* Path B2: PayFast ZAR */}
            {PAYMENTS_ENABLED && activeGateway === "payfast" && (
              <PayFastForm
                amountLabel={activeGateway === "payfast" ? amountLabel : null}
                bookingReference={booking.booking_reference}
                itemDescription={`25-min lesson with ${booking.teacher.full_name}`}
                onSuccess={handlePayFastStart}
                disabled={submitting}
              />
            )}
          </div>
        </div>

        {/* Right Column: Order Summary Card */}
        <div className="bg-white rounded-3xl p-6 border border-divider shadow-card space-y-6">
          <div className="space-y-1">
            <span className="text-sm font-bold uppercase tracking-wider text-primary">Order Summary</span>
            <h3 className="text-lg font-bold text-ink font-serif">Lesson Reservation</h3>
          </div>

          <div className="flex items-center gap-3.5 border-b border-divider pb-4">
            <Avatar src={booking.teacher.avatar_url} name={booking.teacher.full_name} size="md" />
            <div>
              <div className="text-sm font-bold text-ink">{booking.teacher.full_name}</div>
              <div className="text-sm text-ink-muted">{booking.teacher.accent}</div>
            </div>
          </div>

          {/* Time & Date Breakdown */}
          <div className="space-y-2 text-sm">
            <div className="flex items-center justify-between text-ink-muted">
              <span className="flex items-center gap-1.5">
                <Calendar className="w-3.5 h-3.5 text-cocoa" /> Date:
              </span>
              <span className="font-bold text-ink">{dayLabel(booking.local_date).long}</span>
            </div>

            <div className="flex items-center justify-between text-ink-muted">
              <span className="flex items-center gap-1.5">
                <Clock className="w-3.5 h-3.5 text-cocoa" /> Time:
              </span>
              <span className="font-bold text-ink">
                {booking.local_start_time} - {booking.local_end_time}
              </span>
            </div>

            <div className="flex items-center justify-between text-ink-muted">
              <span>Timezone:</span>
              <span className="font-semibold text-ink">{zoneCityName(booking.viewer_timezone)}</span>
            </div>

            <div className="flex items-center justify-between text-ink-muted">
              <span>Duration:</span>
              <span className="font-semibold text-ink">25 minutes</span>
            </div>
          </div>

          {/* Price Breakdown */}
          <div className="pt-4 border-t border-divider space-y-2 text-sm">
            <div className="flex justify-between text-base font-extrabold text-ink font-serif">
              <span>Total Due:</span>
              <span className="text-cocoa">
                {amountLabel ? `${amountLabel} ${amountCurrency}` : "Shown at payment"}
              </span>
            </div>
            <div className="text-sm text-right text-ink-muted">
              {activeQuote
                ? "Amount confirmed by our payment server."
                : "Lesson price for the selected payment method. The final amount is confirmed when you start payment."}
            </div>
          </div>

          {/* Escrow Guarantee */}
          <div className="bg-cream-surface rounded-2xl p-4 border border-cream-deep flex items-start gap-2.5 text-sm text-ink-muted">
            <ShieldCheck className="w-4 h-4 text-success shrink-0 mt-0.5" />
            <span>
              <strong>Your payment is protected:</strong> we hold it safely until your lesson has taken place and attendance is confirmed.
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
