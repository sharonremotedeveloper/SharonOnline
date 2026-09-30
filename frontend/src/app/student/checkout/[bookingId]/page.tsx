"use client";

import { useState, useEffect } from "react";
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
  CheckCircle2,
} from "lucide-react";
import { api } from "@/lib/api";
import { BookingDetail } from "@/types/booking";
import { useAuth } from "@/context/AuthContext";
import { Avatar } from "@/components/ui/Avatar";
import { ReservationTimer } from "@/components/booking/ReservationTimer";
import { PayFastForm } from "@/components/booking/PayFastForm";
import { PayPalButtonsWrapper } from "@/components/booking/PayPalButtonsWrapper";

export default function StudentCheckoutPage() {
  const params = useParams();
  const router = useRouter();
  const bookingId = (params?.bookingId as string) || "BK-0001";
  const { user } = useAuth();

  const [booking, setBooking] = useState<BookingDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeGateway, setActiveGateway] = useState<"credit" | "payfast" | "paypal">("credit");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  const userCredits = user?.credits ?? 5; // default to 5 for sandbox student

  useEffect(() => {
    async function loadBooking() {
      setLoading(true);
      try {
        const data = await api.getBooking(bookingId);
        setBooking(data);
        if (userCredits <= 0) {
          setActiveGateway("paypal");
        }
      } catch (err) {
        console.error("Failed to load booking details:", err);
      } finally {
        setLoading(false);
      }
    }
    loadBooking();
  }, [bookingId, userCredits]);

  const handleRedeemCredit = async () => {
    setSubmitting(true);
    setError("");

    try {
      const res = await api.redeemCredit(bookingId);
      if (res.success) {
        router.push(`/student/confirmed/${bookingId}`);
      }
    } catch (err: any) {
      setError(err.message || "Failed to redeem lesson credit.");
      setSubmitting(false);
    }
  };

  const handleGatewaySuccess = async (gatewayType: string) => {
    setSubmitting(true);
    try {
      await api.confirmPayment(bookingId, { gateway: gatewayType });
      router.push(`/student/confirmed/${bookingId}`);
    } catch (err: any) {
      setError("Payment received, but confirmation failed. Please contact support.");
      setSubmitting(false);
    }
  };

  if (loading || !booking) {
    return (
      <div className="max-w-4xl mx-auto px-4 py-16 text-center text-xs text-ink-muted">
        Loading checkout reservation...
      </div>
    );
  }

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-10 space-y-8">
      {/* Back button */}
      <div>
        <Link
          href={`/student/book/${booking.teacher.id}`}
          className="inline-flex items-center gap-1.5 text-xs font-bold text-ink-muted hover:text-ink transition-colors"
        >
          <ArrowLeft className="w-3.5 h-3.5" /> Change Slot
        </Link>
      </div>

      {/* 10-Minute Lock Timer Bar */}
      <ReservationTimer
        initialSeconds={600}
        onExpire={() => router.push(`/student/book/${booking.teacher.id}?expired=1`)}
        onRestart={() => router.push(`/student/book/${booking.teacher.id}`)}
      />

      {error && (
        <div className="p-4 bg-primary/10 border border-primary/30 rounded-2xl text-xs text-primary font-medium">
          {error}
        </div>
      )}

      {/* Checkout Grid: Left = Payment Method / Right = Order Summary */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 items-start">
        {/* Left Column: Payment Options */}
        <div className="lg:col-span-2 space-y-6">
          <div className="bg-white rounded-3xl p-6 sm:p-8 border border-divider shadow-card space-y-6">
            <div>
              <h2 className="text-xl font-extrabold text-ink font-serif">Select Checkout Method</h2>
              <p className="text-xs text-ink-muted mt-0.5">
                Redeem a pre-purchased lesson credit or pay directly with card / instant EFT
              </p>
            </div>

            {/* Gateway Selector Tabs */}
            <div className="grid grid-cols-3 gap-2 p-1.5 bg-cream-surface rounded-2xl border border-divider">
              <button
                type="button"
                onClick={() => setActiveGateway("credit")}
                className={`py-2.5 px-3 rounded-xl text-xs font-bold transition-all flex items-center justify-center gap-1.5 ${
                  activeGateway === "credit"
                    ? "bg-teal text-white shadow-sm"
                    : "text-ink-muted hover:text-ink"
                }`}
              >
                <Coins className="w-3.5 h-3.5 text-accent" />
                <span>1 Credit ({userCredits} left)</span>
              </button>

              <button
                type="button"
                onClick={() => setActiveGateway("paypal")}
                className={`py-2.5 px-3 rounded-xl text-xs font-bold transition-all flex items-center justify-center gap-1.5 ${
                  activeGateway === "paypal"
                    ? "bg-teal text-white shadow-sm"
                    : "text-ink-muted hover:text-ink"
                }`}
              >
                <CreditCard className="w-3.5 h-3.5" />
                <span>PayPal / Cards ($)</span>
              </button>

              <button
                type="button"
                onClick={() => setActiveGateway("payfast")}
                className={`py-2.5 px-3 rounded-xl text-xs font-bold transition-all flex items-center justify-center gap-1.5 ${
                  activeGateway === "payfast"
                    ? "bg-teal text-white shadow-sm"
                    : "text-ink-muted hover:text-ink"
                }`}
              >
                <span>🇿🇦 PayFast (ZAR)</span>
              </button>
            </div>

            {/* Path A: Credit Redemption */}
            {activeGateway === "credit" && (
              <div className="p-6 rounded-2xl bg-cream-surface border border-cream-deep space-y-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Coins className="w-5 h-5 text-accent" />
                    <span className="text-sm font-bold text-ink">Lesson Credit Wallet</span>
                  </div>
                  <span className="text-xs font-bold text-teal bg-white px-3 py-1 rounded-full border border-divider">
                    Balance: {userCredits} Credits
                  </span>
                </div>

                {userCredits > 0 ? (
                  <>
                    <p className="text-xs text-ink-muted leading-relaxed">
                      You have <strong>{userCredits} active lesson credits</strong> available. Confirming will deduct 1 credit and immediately verify your private 25-minute classroom slot with {booking.teacher.full_name}.
                    </p>

                    <button
                      onClick={handleRedeemCredit}
                      disabled={submitting}
                      className="w-full py-4 bg-primary hover:bg-primary-hover text-white rounded-xl text-xs font-bold transition-all shadow-sm flex items-center justify-center gap-2 disabled:opacity-50"
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
                    <p className="text-xs text-primary font-medium">
                      You have 0 lesson credits left in your wallet.
                    </p>
                    <Link
                      href="/pricing"
                      className="inline-flex items-center gap-2 px-4 py-2 bg-teal text-white rounded-xl text-xs font-bold"
                    >
                      Top Up Lesson Pack <ArrowRight className="w-3.5 h-3.5" />
                    </Link>
                  </div>
                )}
              </div>
            )}

            {/* Path B1: PayPal International */}
            {activeGateway === "paypal" && (
              <PayPalButtonsWrapper
                amountUsd={booking.price_usd}
                bookingReference={booking.booking_reference}
                onSuccess={(orderId) => handleGatewaySuccess("paypal")}
                disabled={submitting}
              />
            )}

            {/* Path B2: PayFast ZAR */}
            {activeGateway === "payfast" && (
              <PayFastForm
                amountZar={booking.price_zar}
                bookingReference={booking.booking_reference}
                itemDescription={`25-min lesson with ${booking.teacher.full_name}`}
                onSuccess={() => handleGatewaySuccess("payfast")}
                disabled={submitting}
              />
            )}
          </div>
        </div>

        {/* Right Column: Order Summary Card */}
        <div className="bg-white rounded-3xl p-6 border border-divider shadow-card space-y-6">
          <div className="space-y-1">
            <span className="text-[11px] font-bold uppercase tracking-wider text-primary">Order Summary</span>
            <h3 className="text-lg font-bold text-ink font-serif">Lesson Reservation</h3>
          </div>

          <div className="flex items-center gap-3.5 border-b border-divider pb-4">
            <Avatar src={booking.teacher.avatar_url} name={booking.teacher.full_name} size="md" />
            <div>
              <div className="text-sm font-bold text-ink">{booking.teacher.full_name}</div>
              <div className="text-xs text-ink-muted">{booking.teacher.accent}</div>
            </div>
          </div>

          {/* Time & Date Breakdown */}
          <div className="space-y-2 text-xs">
            <div className="flex items-center justify-between text-ink-muted">
              <span className="flex items-center gap-1.5">
                <Calendar className="w-3.5 h-3.5 text-teal" /> Date:
              </span>
              <span className="font-bold text-ink">{booking.local_date}</span>
            </div>

            <div className="flex items-center justify-between text-ink-muted">
              <span className="flex items-center gap-1.5">
                <Clock className="w-3.5 h-3.5 text-teal" /> Time:
              </span>
              <span className="font-bold text-ink">
                {booking.local_start_time} - {booking.local_end_time}
              </span>
            </div>

            <div className="flex items-center justify-between text-ink-muted">
              <span>Timezone:</span>
              <span className="font-semibold text-ink">{booking.viewer_timezone}</span>
            </div>

            <div className="flex items-center justify-between text-ink-muted">
              <span>Duration:</span>
              <span className="font-semibold text-ink">Strict 25 Minutes</span>
            </div>
          </div>

          {/* Price Breakdown */}
          <div className="pt-4 border-t border-divider space-y-2 text-xs">
            <div className="flex justify-between text-ink-muted">
              <span>Standard Lesson Fee:</span>
              <span>${booking.price_usd.toFixed(2)} USD</span>
            </div>
            <div className="flex justify-between text-ink-muted">
              <span>Platform Service Fee:</span>
              <span className="text-success font-semibold">$0.00 (Included)</span>
            </div>
            <div className="flex justify-between text-base font-extrabold text-ink font-serif pt-2 border-t border-divider">
              <span>Total Due:</span>
              <span className="text-teal">${booking.price_usd.toFixed(2)} USD</span>
            </div>
            <div className="text-[10px] text-right text-ink-muted">
              (~R{Math.round(booking.price_zar)} ZAR)
            </div>
          </div>

          {/* Escrow Guarantee */}
          <div className="bg-cream-surface rounded-2xl p-4 border border-cream-deep flex items-start gap-2.5 text-[11px] text-ink-muted">
            <ShieldCheck className="w-4 h-4 text-success shrink-0 mt-0.5" />
            <span>
              <strong>24-Hour Escrow Hold:</strong> Payment is held safely in escrow until the lesson completes and attendance is confirmed.
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
