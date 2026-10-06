"use client";

import { useEffect, useState } from "react";
import { Clock, AlertTriangle, RotateCcw } from "lucide-react";
import { Modal } from "@/components/ui/Modal";

interface ReservationTimerProps {
  initialSeconds?: number;
  onExpire?: () => void;
  onRestart?: () => void;
}

export function ReservationTimer({
  initialSeconds = 600,
  onExpire,
  onRestart,
}: ReservationTimerProps) {
  const [secondsLeft, setSecondsLeft] = useState(initialSeconds);
  const [showExpiredModal, setShowExpiredModal] = useState(false);

  useEffect(() => {
    if (secondsLeft <= 0) {
      setShowExpiredModal(true);
      if (onExpire) onExpire();
      return;
    }

    const interval = setInterval(() => {
      setSecondsLeft((prev) => {
        if (prev <= 1) {
          clearInterval(interval);
          setShowExpiredModal(true);
          if (onExpire) onExpire();
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => clearInterval(interval);
  }, [secondsLeft, onExpire]);

  const minutes = Math.floor(secondsLeft / 60);
  const remainingSeconds = secondsLeft % 60;
  const formattedTime = `${minutes.toString().padStart(2, "0")}:${remainingSeconds
    .toString()
    .padStart(2, "0")}`;

  const percentage = Math.max(0, Math.min(100, (secondsLeft / initialSeconds) * 100));
  const isUrgent = secondsLeft < 120; // less than 2 minutes

  return (
    <>
      <div
        className={`p-4 rounded-2xl border transition-all ${
          isUrgent
            ? "bg-primary/10 border-primary/40 text-primary"
            : "bg-cream-surface border-divider text-ink"
        }`}
      >
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <Clock className={`w-4 h-4 ${isUrgent ? "text-primary animate-pulse" : "text-cocoa"}`} />
            <span className="text-xs font-bold uppercase tracking-wider">
              {isUrgent ? "Slot Reservation Expiring Soon" : "10-Minute Slot Hold Active"}
            </span>
          </div>

          <div className="text-base font-extrabold font-serif">
            {formattedTime}
          </div>
        </div>

        {/* Progress bar */}
        <div className="w-full bg-cream-deep h-1.5 rounded-full overflow-hidden">
          <div
            className={`h-full transition-all duration-1000 ${
              isUrgent ? "bg-primary" : "bg-cocoa"
            }`}
            style={{ width: `${percentage}%` }}
          />
        </div>

        <div className="text-[11px] text-ink-muted mt-2">
          This 25-minute lesson is held exclusively for you in Redis. Complete checkout before the timer hits 00:00.
        </div>
      </div>

      {/* Expired Modal */}
      <Modal
        isOpen={showExpiredModal}
        onClose={() => {
          setShowExpiredModal(false);
          if (onRestart) onRestart();
        }}
        title="Reservation Expired"
      >
        <div className="text-center space-y-4 py-2">
          <div className="w-12 h-12 rounded-full bg-primary/10 text-primary flex items-center justify-center mx-auto">
            <AlertTriangle className="w-6 h-6" />
          </div>

          <div className="space-y-1">
            <h4 className="text-lg font-bold text-ink font-serif">Your 10-Minute Hold Has Ended</h4>
            <p className="text-xs text-ink-muted leading-relaxed">
              To keep slot scheduling fair for students across Japan, Korea, and Europe, held slots are automatically released back to the marketplace.
            </p>
          </div>

          <button
            onClick={() => {
              setShowExpiredModal(false);
              if (onRestart) onRestart();
            }}
            className="w-full py-3 bg-cocoa hover:bg-cocoa-hover text-white rounded-xl text-xs font-bold flex items-center justify-center gap-2 transition-all shadow-sm"
          >
            <RotateCcw className="w-4 h-4" /> Pick a New Slot
          </button>
        </div>
      </Modal>
    </>
  );
}
