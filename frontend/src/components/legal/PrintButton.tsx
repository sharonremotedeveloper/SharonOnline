"use client";

import { Printer } from "lucide-react";

export function PrintButton() {
  return (
    <button
      type="button"
      onClick={() => {
        if (typeof window !== "undefined") {
          window.print();
        }
      }}
      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-divider bg-cream-surface hover:bg-cream-deep text-sm font-bold text-ink transition-colors"
      aria-label="Print policy document"
    >
      <Printer className="w-3.5 h-3.5" />
      <span>Print / Save PDF</span>
    </button>
  );
}
