"use client";

import { useEffect, useRef, useState } from "react";
import { CURRENCIES, CurrencyCode, detectDefaultCurrency } from "@/lib/currency";
import { api } from "@/lib/api";
import { useApiData } from "@/hooks/useApiData";
import type { LessonPrice } from "@/lib/prices";
import { Globe } from "lucide-react";

interface CurrencySwitcherProps {
  onCurrencyChange?: (code: CurrencyCode) => void;
  variant?: "badge" | "select" | "inline";
}

export function CurrencySwitcher({ onCurrencyChange, variant = "select" }: CurrencySwitcherProps) {
  const [selected, setSelected] = useState<CurrencyCode>("USD");
  const [mounted, setMounted] = useState(false);
  const initialCurrencyChange = useRef(onCurrencyChange);
  // Only currencies the platform actually prices are offered; the list is server truth, not a hardcoded set.
  const { data: prices, error, loading, reload } = useApiData<LessonPrice[]>(() => api.getLessonPrices(), []);
  const offered = (prices ?? []).map((p) => p.currency).filter((c) => CURRENCIES[c]);

  useEffect(() => {
    setMounted(true);
    const code = detectDefaultCurrency();
    setSelected(code);
    initialCurrencyChange.current?.(code);
  }, []);

  const handleChange = (code: CurrencyCode) => {
    setSelected(code);
    if (typeof window !== "undefined") {
      localStorage.setItem("sharon_currency", code);
      // Dispatch custom window event so sibling components (e.g. pricing table) update in real-time
      window.dispatchEvent(new CustomEvent("sharon_currency_changed", { detail: code }));
    }
    if (onCurrencyChange) onCurrencyChange(code);
  };

  const shell = "flex items-center gap-1.5 px-3 py-1 rounded-lg bg-cream-surface border border-divider text-sm text-ink-muted";

  if (!mounted || loading) {
    // Fixed size, so the header and pricing bar do not jump when the real control arrives.
    return (
      <div
        className="h-11 w-28 shrink-0 animate-pulse rounded-xl border border-divider bg-cream-surface"
        role="status"
        aria-label="Loading currencies"
      />
    );
  }

  if (error) {
    return (
      <div className={shell} role="alert">
        <Globe className="w-3.5 h-3.5" />
        <span>Currencies unavailable</span>
        <button type="button" onClick={reload} className="font-bold text-primary hover:underline">
          Retry
        </button>
      </div>
    );
  }

  if (offered.length === 0) {
    return (
      <div className={shell}>
        <Globe className="w-3.5 h-3.5" />
        <span>No currencies available</span>
      </div>
    );
  }

  const active: CurrencyCode = offered.includes(selected) ? selected : offered[0];

  // Flag emoji render as bare letters ("us", "eu") on Windows, so the currency is shown by its code and symbol only.
  if (variant === "inline") {
    return (
      <div role="group" aria-label="Display currency" className="inline-flex items-center gap-1 p-1 bg-cream-surface rounded-xl border border-divider">
        {offered.map((code) => {
          const curr = CURRENCIES[code];
          const isActive = active === code;
          return (
            <button
              key={code}
              type="button"
              onClick={() => handleChange(code)}
              aria-pressed={isActive}
              className={`min-h-[44px] min-w-[44px] px-3.5 rounded-lg text-sm font-bold transition-colors flex items-center justify-center gap-1.5 ${
                isActive
                  ? "bg-cocoa text-white shadow-sm"
                  : "text-ink-muted hover:text-ink hover:bg-cream-deep"
              }`}
            >
              <span aria-hidden="true">{curr.symbol}</span>
              <span>{curr.code}</span>
            </button>
          );
        })}
      </div>
    );
  }

  return (
    <div className="relative flex shrink-0 items-center">
      <Globe className="pointer-events-none absolute left-3 h-4 w-4 text-ink-muted" aria-hidden="true" />
      <select
        value={active}
        onChange={(e) => handleChange(e.target.value as CurrencyCode)}
        aria-label="Display currency"
        className="h-11 min-w-[7.5rem] cursor-pointer rounded-xl border border-strong bg-cream-surface pl-9 pr-3 text-base sm:text-sm font-bold text-ink focus:outline-none focus:ring-2 focus:ring-gold-bright"
      >
        {offered.map((code) => (
          <option key={code} value={code}>
            {CURRENCIES[code].label}
          </option>
        ))}
      </select>
    </div>
  );
}
