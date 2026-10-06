/** One-decimal rating that never rounds up to a perfect score: 4.98 is shown as 4.9, not 5.0. */
export function formatRating(value: number): string {
  if (!Number.isFinite(value)) return "0.0";
  return (Math.floor(value * 10 + 1e-9) / 10).toFixed(1);
}

/** "1 credit", "5 credits". */
export function creditsLabel(count: number): string {
  return `${count} ${count === 1 ? "credit" : "credits"}`;
}
