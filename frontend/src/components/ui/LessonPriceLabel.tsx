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
  if (loading) return <span className={className}>...</span>;
  if (error) return <span className={className}>Price unavailable</span>;
  const price = lessonPriceFor(data, currency);
  return <span className={className}>{price ? formatLessonPrice(price) : "Price unavailable"}</span>;
}
