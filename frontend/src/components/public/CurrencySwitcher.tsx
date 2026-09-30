"use client";

import { useEffect, useState } from "react";
import { CURRENCIES, CurrencyCode, detectDefaultCurrency } from "@/lib/currency";
import { Globe } from "lucide-react";

interface CurrencySwitcherProps {
  onCurrencyChange?: (code: CurrencyCode) => void;
  variant?: "badge" | "select" | "inline";
}

export function CurrencySwitcher({ onCurrencyChange, variant = "select" }: CurrencySwitcherProps) {
  const [selected, setSelected] = useState<CurrencyCode>("USD");
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    const code = detectDefaultCurrency();
    setSelected(code);
    if (onCurrencyChange) onCurrencyChange(code);
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

  if (!mounted) {
    return (
      <div className="flex items-center gap-1.5 px-3 py-1 rounded-lg bg-cream-surface border border-divider text-xs text-ink-muted">
        <Globe className="w-3.5 h-3.5" />
        <span>USD ($)</span>
      </div>
    );
  }

  if (variant === "inline") {
    return (
      <div className="inline-flex items-center gap-1 p-1 bg-cream-surface rounded-xl border border-divider">
        {(Object.keys(CURRENCIES) as CurrencyCode[]).map((code) => {
          const curr = CURRENCIES[code];
          const isActive = selected === code;
          return (
            <button
              key={code}
              onClick={() => handleChange(code)}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all flex items-center gap-1.5 ${
                isActive
                  ? "bg-teal text-white shadow-sm"
                  : "text-ink-muted hover:text-ink hover:bg-cream-deep"
              }`}
            >
              <span>{curr.flag}</span>
              <span>{curr.code}</span>
            </button>
          );
        })}
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2">
      <Globe className="w-4 h-4 text-ink-muted" />
      <select
        value={selected}
        onChange={(e) => handleChange(e.target.value as CurrencyCode)}
        className="bg-cream-surface border border-divider rounded-xl px-3 py-1.5 text-xs font-bold text-ink focus:outline-none focus:ring-2 focus:ring-teal cursor-pointer"
      >
        {(Object.keys(CURRENCIES) as CurrencyCode[]).map((code) => (
          <option key={code} value={code}>
            {CURRENCIES[code].flag} {CURRENCIES[code].label}
          </option>
        ))}
      </select>
    </div>
  );
}
