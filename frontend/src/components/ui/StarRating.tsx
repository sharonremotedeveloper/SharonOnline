import React, { useId } from "react";
import { formatRating } from "@/lib/rating";

export interface StarRatingProps {
  rating: number; // e.g., 4.95
  totalReviews?: number;
  size?: "sm" | "md" | "lg";
  showNumber?: boolean;
  className?: string;
}

export function StarRating({
  rating,
  totalReviews,
  size = "md",
  showNumber = true,
  className = "",
}: StarRatingProps) {
  const uid = useId().replace(/:/g, "");
  const starSizes = {
    sm: "w-3.5 h-3.5",
    md: "w-4 h-4",
    lg: "w-5 h-5",
  }[size];

  return (
    <div className={`inline-flex items-center gap-1.5 ${className}`}>
      <div className="flex items-center text-star [--star-empty:theme(colors.cream.300)]" role="img" aria-label={`Rated ${formatRating(rating)} out of 5`}>
        {[1, 2, 3, 4, 5].map((star) => {
          const filled = star <= Math.floor(rating);
          const half = !filled && star - 0.5 <= rating;

          return (
            <svg
              key={star}
              className={`${starSizes} fill-current`}
              viewBox="0 0 20 20"
              xmlns="http://www.w3.org/2000/svg"
            >
              {half ? (
                <defs>
                  <linearGradient id={`${uid}-half-${star}`}>
                    <stop offset="50%" stopColor="currentColor" />
                    <stop offset="50%" stopColor="var(--star-empty)" />
                  </linearGradient>
                </defs>
              ) : null}
              <path
                fill={filled ? "currentColor" : half ? `url(#${uid}-half-${star})` : "var(--star-empty)"}
                d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z"
              />
            </svg>
          );
        })}
      </div>

      {showNumber && (
        <span className="text-xs font-semibold text-ink tabular-nums">
          {formatRating(rating)}
        </span>
      )}

      {totalReviews !== undefined && (
        <span className="text-xs text-ink-muted">({totalReviews})</span>
      )}
    </div>
  );
}
