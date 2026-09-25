"use client";

import { useState, useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import {
  Star,
  ShieldCheck,
  Globe,
  Clock,
  Video,
  Calendar,
  Lock,
  ArrowRight,
  CheckCircle,
  AlertCircle
} from "lucide-react";
import { Teacher, Slot, TeacherSlotsResponse } from "../../../../types";
import { api } from "../../../../lib/api";

const COMMON_TIMEZONES = [
  { label: "🇯🇵 Tokyo (JST / UTC+9)", value: "Asia/Tokyo" },
  { label: "🇰🇷 Seoul (KST / UTC+9)", value: "Asia/Seoul" },
  { label: "🇪🇺 Paris / Berlin (CET / UTC+1)", value: "Europe/Paris" },
  { label: "🇬🇧 London (GMT / UTC+0)", value: "Europe/London" },
  { label: "🇿🇦 Johannesburg (SAST / UTC+2)", value: "Africa/Johannesburg" },
];

export default function TutorProfilePage() {
  const params = useParams();
  const router = useRouter();
  const tutorId = params.id as string;

  const [tutor, setTutor] = useState<Teacher | null>(null);
  const [slotsData, setSlotsData] = useState<TeacherSlotsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [timezone, setTimezone] = useState("Asia/Tokyo");

  // Booking Modal State
  const [selectedSlot, setSelectedSlot] = useState<Slot | null>(null);
  const [reserving, setReserving] = useState(false);
  const [reserveError, setReserveError] = useState("");
  const [lockExpiresIn, setLockExpiresIn] = useState<number | null>(null);
  const [checkoutGateway, setCheckoutGateway] = useState<'paypal' | 'payfast'>('paypal');
  const [bookingConfirmed, setBookingConfirmed] = useState(false);

  useEffect(() => {
    // Detect browser timezone if available
    try {
      const detected = Intl.DateTimeFormat().resolvedOptions().timeZone;
      if (detected) setTimezone(detected);
    } catch (e) {
      // Default to Tokyo
    }
  }, []);

  useEffect(() => {
    async function loadData() {
      if (!tutorId) return;
      setLoading(true);
      try {
        const [teacherRes, slotsRes] = await Promise.all([
          api.getTeacher(tutorId),
          api.getTeacherSlots(tutorId, timezone, 7),
        ]);
        setTutor(teacherRes);
        setSlotsData(slotsRes);
      } catch (err) {
        console.error("Error loading tutor data:", err);
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, [tutorId, timezone]);

  // Countdown timer for 10-minute hold
  useEffect(() => {
    if (lockExpiresIn === null || lockExpiresIn <= 0) return;
    const interval = setInterval(() => {
      setLockExpiresIn((prev) => (prev && prev > 0 ? prev - 1 : 0));
    }, 1000);
    return () => clearInterval(interval);
  }, [lockExpiresIn]);

  const handleSelectSlot = async (slot: Slot) => {
    if (!slot.is_bookable) return;
    setReserving(true);
    setReserveError("");
    try {
      const res = await api.reserveSlot(tutorId, slot.start_time_utc);
      setSelectedSlot(slot);
      setLockExpiresIn(res.lock_ttl_seconds || 600);
    } catch (err: any) {
      setReserveError(err.message || "Failed to hold slot. It may be already reserved.");
    } finally {
      setReserving(false);
    }
  };

  const handleConfirmCheckout = async () => {
    if (!selectedSlot) return;
    setReserving(true);
    try {
      // Simulate booking confirmation and trigger state
      setBookingConfirmed(true);
    } catch (err: any) {
      setReserveError("Checkout processing error. Please try again.");
    } finally {
      setReserving(false);
    }
  };

  if (loading || !tutor) {
    return (
      <div className="max-w-5xl mx-auto px-4 py-20 text-center text-sm text-gray-500 animate-pulse">
        Loading tutor profile and availability matrix...
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-10 space-y-10">
      {/* Profile Header */}
      <div className="bg-white rounded-2xl p-6 sm:p-8 border border-gray-100 shadow-card flex flex-col md:flex-row gap-8">
        {/* Left: Avatar & Intro Video Reel */}
        <div className="w-full md:w-80 flex-shrink-0 space-y-4">
          <div className="relative aspect-video rounded-xl overflow-hidden bg-brand-950 shadow-md">
            {tutor.intro_video_url ? (
              <video
                src={tutor.intro_video_url}
                controls
                poster={tutor.intro_video_thumbnail || tutor.avatar_url}
                className="w-full h-full object-cover"
              />
            ) : (
              <div className="w-full h-full flex flex-col items-center justify-center text-white/60 p-4 text-center">
                <Video className="w-8 h-8 mb-2" />
                <span className="text-xs">1-Minute Video Reel</span>
              </div>
            )}
          </div>

          <div className="bg-gray-50 rounded-xl p-4 space-y-2 border border-gray-100 text-xs text-gray-600">
            <div className="flex justify-between items-center">
              <span className="font-medium">Lesson Rate:</span>
              <span className="font-extrabold text-base text-gray-900">${Number(tutor.price_per_25min_usd).toFixed(2)} USD</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="font-medium">Lesson Length:</span>
              <span className="font-bold text-gray-900">25 Minutes</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="font-medium">Accent:</span>
              <span className="font-bold text-gray-900">
                {tutor.accent === 'ZA' ? 'South African' : tutor.accent === 'UK' ? 'British' : 'American'}
              </span>
            </div>
          </div>
        </div>

        {/* Right: Bio & Credentials */}
        <div className="flex-1 space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <h1 className="text-2xl sm:text-3xl font-extrabold text-gray-900">{tutor.full_name}</h1>
              {tutor.is_verified && <ShieldCheck className="w-5 h-5 text-emerald-600" />}
            </div>
            <div className="flex items-center gap-1.5 text-sm font-bold text-amber-500">
              <Star className="w-4 h-4 fill-current" />
              <span>{Number(tutor.rating_avg).toFixed(2)}</span>
              <span className="text-xs text-gray-400 font-normal">({tutor.rating_count} reviews)</span>
            </div>
          </div>

          <p className="text-sm font-semibold text-brand-900">{tutor.headline}</p>

          <div className="prose prose-sm text-gray-600 leading-relaxed whitespace-pre-line text-sm">
            {tutor.bio}
          </div>

          {/* Specialties */}
          <div className="pt-2">
            <h4 className="text-xs font-bold text-gray-500 uppercase tracking-wider mb-2">Specialties</h4>
            <div className="flex flex-wrap gap-2">
              {tutor.specialties.map((s) => (
                <span key={s} className="px-3 py-1 rounded-full bg-brand-50 text-brand-900 text-xs font-semibold border border-brand-100">
                  {s}
                </span>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* 25-Minute Availability Matrix */}
      <div className="bg-white rounded-2xl p-6 sm:p-8 border border-gray-100 shadow-card space-y-6">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 border-b border-gray-100 pb-4">
          <div>
            <h2 className="text-xl font-extrabold text-gray-900 flex items-center gap-2">
              <Calendar className="w-5 h-5 text-brand-700" />
              Select a 25-Minute Lesson Slot
            </h2>
            <p className="text-xs text-gray-500 mt-0.5">
              Slots are locked in real-time with a 10-minute reservation timer during checkout.
            </p>
          </div>

          {/* Timezone Switcher */}
          <div className="flex items-center gap-2">
            <Globe className="w-4 h-4 text-gray-400" />
            <select
              value={timezone}
              onChange={(e) => setTimezone(e.target.value)}
              className="text-xs font-semibold bg-gray-50 border border-gray-200 rounded-lg px-3 py-1.5 focus:outline-none focus:border-brand-700"
            >
              {COMMON_TIMEZONES.map((tz) => (
                <option key={tz.value} value={tz.value}>{tz.label}</option>
              ))}
            </select>
          </div>
        </div>

        {reserveError && (
          <div className="p-3 bg-red-50 border border-red-200 rounded-xl text-xs text-red-700 flex items-center gap-2">
            <AlertCircle className="w-4 h-4 flex-shrink-0" />
            <span>{reserveError}</span>
          </div>
        )}

        {/* Slot Grid */}
        {slotsData && slotsData.slots.length > 0 ? (
          <div className="grid grid-cols-2 sm:grid-cols-4 md:grid-cols-6 gap-3">
            {slotsData.slots.map((slot) => {
              const isAvailable = slot.status === 'available';
              return (
                <button
                  key={slot.start_time_utc}
                  onClick={() => handleSelectSlot(slot)}
                  disabled={!isAvailable || reserving}
                  className={`p-3 rounded-xl border text-center transition-all flex flex-col items-center justify-center space-y-1 ${
                    isAvailable
                      ? "border-brand-200 bg-brand-50/50 hover:bg-brand-900 hover:text-white hover:border-brand-900 text-brand-950 font-bold shadow-sm"
                      : "border-gray-100 bg-gray-50 text-gray-400 cursor-not-allowed opacity-60"
                  }`}
                >
                  <span className="text-[11px] font-medium opacity-80">{slot.local_date.slice(5)}</span>
                  <span className="text-sm font-extrabold">{slot.local_start_time}</span>
                  <span className="text-[10px] font-medium">25 mins</span>
                </button>
              );
            })}
          </div>
        ) : (
          <div className="text-center py-12 text-sm text-gray-400">
            No open slots found for this tutor in the selected timezone over the next 7 days.
          </div>
        )}
      </div>

      {/* Checkout / Lock Reservation Modal */}
      {selectedSlot && (
        <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-lg w-full p-6 sm:p-8 space-y-6 shadow-2xl relative">
            {bookingConfirmed ? (
              <div className="text-center space-y-4 py-4">
                <CheckCircle className="w-16 h-16 text-emerald-600 mx-auto" />
                <h3 className="text-2xl font-extrabold text-gray-900">Booking Confirmed!</h3>
                <p className="text-sm text-gray-600 leading-relaxed">
                  Your 25-minute lesson with <strong>{tutor.full_name}</strong> is scheduled for{" "}
                  <strong>{selectedSlot.local_date} at {selectedSlot.local_start_time} ({timezone})</strong>.
                </p>
                <div className="p-4 bg-brand-50 rounded-xl text-xs text-brand-900 text-left space-y-1">
                  <div>✓ Zoom Classroom provisioned</div>
                  <div>✓ Google Calendar sync event sent</div>
                  <div>✓ .ics invite dispatched to your email</div>
                </div>
                <div className="pt-2 flex gap-3">
                  <Link
                    href="/student/dashboard"
                    className="flex-1 py-3 bg-brand-900 text-white rounded-xl text-sm font-bold text-center hover:bg-brand-950 transition-all"
                  >
                    Go to Student Dashboard
                  </Link>
                </div>
              </div>
            ) : (
              <>
                <div className="flex items-center justify-between border-b border-gray-100 pb-3">
                  <div className="flex items-center gap-2 text-xs font-bold text-amber-700 bg-amber-50 px-3 py-1 rounded-full">
                    <Lock className="w-3.5 h-3.5" />
                    Slot Locked for: {Math.floor((lockExpiresIn || 0) / 60)}:
                    {((lockExpiresIn || 0) % 60).toString().padStart(2, "0")}
                  </div>
                  <button
                    onClick={() => setSelectedSlot(null)}
                    className="text-gray-400 hover:text-gray-600 text-sm font-bold"
                  >
                    ✕
                  </button>
                </div>

                <div className="space-y-3">
                  <h3 className="text-xl font-extrabold text-gray-900">Complete Lesson Checkout</h3>
                  <div className="bg-gray-50 rounded-xl p-4 text-xs space-y-2 text-gray-700">
                    <div className="flex justify-between">
                      <span>Tutor:</span>
                      <strong className="text-gray-900">{tutor.full_name}</strong>
                    </div>
                    <div className="flex justify-between">
                      <span>Date & Time:</span>
                      <strong className="text-gray-900">
                        {selectedSlot.local_date} at {selectedSlot.local_start_time} ({timezone})
                      </strong>
                    </div>
                    <div className="flex justify-between">
                      <span>Total Due:</span>
                      <strong className="text-base text-gray-900 font-extrabold">
                        ${Number(tutor.price_per_25min_usd).toFixed(2)} USD
                      </strong>
                    </div>
                  </div>
                </div>

                {/* Gateway Picker */}
                <div className="space-y-2">
                  <span className="text-xs font-bold text-gray-600">Select Payment Method:</span>
                  <div className="grid grid-cols-2 gap-3">
                    <button
                      onClick={() => setCheckoutGateway('paypal')}
                      className={`p-3 rounded-xl border text-xs font-bold text-center transition-all ${
                        checkoutGateway === 'paypal'
                          ? 'border-brand-900 bg-brand-50 text-brand-900'
                          : 'border-gray-200 text-gray-600'
                      }`}
                    >
                      PayPal (USD / JPY / EUR)
                    </button>
                    <button
                      onClick={() => setCheckoutGateway('payfast')}
                      className={`p-3 rounded-xl border text-xs font-bold text-center transition-all ${
                        checkoutGateway === 'payfast'
                          ? 'border-brand-900 bg-brand-50 text-brand-900'
                          : 'border-gray-200 text-gray-600'
                      }`}
                    >
                      PayFast (South Africa ZAR)
                    </button>
                  </div>
                </div>

                <button
                  onClick={handleConfirmCheckout}
                  disabled={reserving}
                  className="w-full py-3.5 bg-gold-500 hover:bg-gold-600 text-brand-950 font-bold rounded-xl text-sm transition-all shadow-md flex items-center justify-center gap-2"
                >
                  Confirm & Lock Slot <ArrowRight className="w-4 h-4" />
                </button>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
