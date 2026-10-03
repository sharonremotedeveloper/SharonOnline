export type CurrencyCode = "USD" | "ZAR" | "EUR" | "JPY";

export interface CurrencyConfig {
  code: CurrencyCode;
  symbol: string;
  label: string;
  flag: string;
}

/** Presentation only (symbol, flag, label). Amounts come from the price API as strings; see lib/prices.ts. */
export const CURRENCIES: Record<CurrencyCode, CurrencyConfig> = {
  USD: {
    code: "USD",
    symbol: "$",
    label: "USD ($)",
    flag: "🇺🇸",
  },
  ZAR: {
    code: "ZAR",
    symbol: "R",
    label: "ZAR (R)",
    flag: "🇿🇦",
  },
  EUR: {
    code: "EUR",
    symbol: "€",
    label: "EUR (€)",
    flag: "🇪🇺",
  },
  JPY: {
    code: "JPY",
    symbol: "¥",
    label: "JPY (¥)",
    flag: "🇯🇵",
  },
};

export function detectDefaultCurrency(): CurrencyCode {
  if (typeof window === "undefined") return "USD";
  try {
    const saved = localStorage.getItem("sharon_currency") as CurrencyCode;
    if (saved && CURRENCIES[saved]) return saved;

    const tz = Intl.DateTimeFormat().resolvedOptions().timeZone || "";
    if (tz.includes("Asia/Tokyo") || tz.includes("Japan")) return "JPY";
    if (tz.includes("Europe/")) return "EUR";
    if (tz.includes("Africa/Johannesburg")) return "ZAR";
  } catch (e) {
    // Fallback
  }
  return "USD";
}
