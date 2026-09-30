"use client";

import { BookingSlot } from "@/types/booking";
import { Sun, Sunset, Moon, Sunrise, Clock, Check } from "lucide-react";

interface SlotGridProps {
  slots: BookingSlot[];
  selectedSlotId: string | null;
  onSelectSlot: (slot: BookingSlot) => void;
  loading?: boolean;
}

export function SlotGrid({ slots, selectedSlotId, onSelectSlot, loading = false }: SlotGridProps) {
  if (loading) {
    return (
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3 animate-pulse">
        {[1, 2, 3, 4, 5, 6, 7, 8].map((i) => (
          <div key={i} className="h-16 bg-cream-surface rounded-2xl border border-divider" />
        ))}
      </div>
    );
  }

  if (slots.length === 0) {
    return (
      <div className="p-8 text-center bg-cream-surface/60 rounded-3xl border border-divider space-y-2">
        <Clock className="w-8 h-8 text-ink-faint mx-auto" />
        <div className="text-sm font-bold text-ink">No Open Slots on This Date</div>
        <p className="text-xs text-ink-muted">
          All 25-minute slots are currently booked. Please choose another date above.
        </p>
      </div>
    );
  }

  // Categorize slots by time of day
  const morningSlots = slots.filter((s) => {
    const hour = parseInt(s.local_start_time.split(":")[0]);
    return hour >= 6 && hour < 12;
  });

  const afternoonSlots = slots.filter((s) => {
    const hour = parseInt(s.local_start_time.split(":")[0]);
    return hour >= 12 && hour < 17;
  });

  const eveningSlots = slots.filter((s) => {
    const hour = parseInt(s.local_start_time.split(":")[0]);
    return hour >= 17;
  });

  const renderSection = (title: string, icon: any, sectionSlots: BookingSlot[]) => {
    if (sectionSlots.length === 0) return null;
    const Icon = icon;

    return (
      <div className="space-y-3">
        <div className="flex items-center gap-1.5 text-xs font-bold text-ink-muted uppercase tracking-wider">
          <Icon className="w-4 h-4 text-teal" />
          <span>{title}</span>
          <span className="text-[10px] text-ink-faint">({sectionSlots.length} slots)</span>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
          {sectionSlots.map((slot) => {
            const isSelected = selectedSlotId === slot.id;
            const isAvailable = slot.is_bookable && slot.status === "available";

            return (
              <button
                key={slot.id}
                disabled={!isAvailable}
                onClick={() => isAvailable && onSelectSlot(slot)}
                className={`p-3 rounded-2xl border text-center transition-all flex flex-col items-center justify-center space-y-1 relative ${
                  isSelected
                    ? "bg-teal text-white border-teal shadow-md ring-2 ring-teal/30 scale-[1.02]"
                    : isAvailable
                    ? "bg-white hover:bg-cream-surface hover:border-teal border-divider text-ink shadow-sm cursor-pointer"
                    : "bg-cream-deep/30 border-divider text-ink-faint opacity-50 cursor-not-allowed"
                }`}
              >
                {isSelected && (
                  <div className="absolute top-1.5 right-1.5 w-4 h-4 rounded-full bg-accent text-ink flex items-center justify-center">
                    <Check className="w-2.5 h-2.5" />
                  </div>
                )}

                <div className="text-sm font-extrabold font-serif">
                  {slot.local_start_time} - {slot.local_end_time}
                </div>

                <div className="text-[10px] font-bold">
                  {isSelected ? (
                    <span className="text-accent font-black">Selected</span>
                  ) : isAvailable ? (
                    <span className="text-success font-semibold">25 min · Available</span>
                  ) : (
                    <span className="text-ink-faint">Booked</span>
                  )}
                </div>
              </button>
            );
          })}
        </div>
      </div>
    );
  };

  return (
    <div className="space-y-6">
      {renderSection("Morning", Sunrise, morningSlots)}
      {renderSection("Afternoon", Sun, afternoonSlots)}
      {renderSection("Evening & Prime Time", Sunset, eveningSlots)}
    </div>
  );
}
