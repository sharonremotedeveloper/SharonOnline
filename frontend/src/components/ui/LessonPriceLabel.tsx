"use client";

import { useLessonPrices } from "@/hooks/useLessonPrices";
import type { CurrencyCode } from "@/lib/currency";
import { formatLessonPrice, lessonPriceFor } from "@/lib/prices";

interface LessonPriceLabelProps {
  currency?: CurrencyCode;
  className?: string;
}

/**
 * The platform price of one 25-minute lesson. Tutors do not set their own price, so every tutor surface shows this.
 * Loading and failure are shown as such; a price is never guessed.
 */
export function LessonPriceLabel({ currency = "USD", className }: LessonPriceLabelProps) {
  const { data, error, loading } = useLessonPrices();
  // A fixed-width placeholder keeps the layout from jumping when the price arrives.
  if (loading) {
    return (
      <span className={className} role="status" aria-label="Loading price">
        <span className="inline-block h-[1em] w-[3.5em] animate-pulse rounded bg-current opacity-15 align-middle" />
      </span>
    );
  }
  if (error) return <span className={className}>Price unavailable</span>;
  const price = lessonPriceFor(data, currency);
  return <span className={className}>{price ? formatLessonPrice(price) : "Price unavailable"}</span>;
}
