export type CurrencyCode = "USD" | "ZAR" | "EUR" | "JPY";

export interface CurrencyConfig {
  code: CurrencyCode;
  symbol: string;
  label: string;
  flag: string;
  format: (amount: number) => string;
}

export const CURRENCIES: Record<CurrencyCode, CurrencyConfig> = {
  USD: {
    code: "USD",
    symbol: "$",
    label: "USD ($)",
    flag: "🇺🇸",
    format: (val) => `$${val.toFixed(2)}`,
  },
  ZAR: {
    code: "ZAR",
    symbol: "R",
    label: "ZAR (R)",
    flag: "🇿🇦",
    format: (val) => `R${Math.round(val)}`,
  },
  EUR: {
    code: "EUR",
    symbol: "€",
    label: "EUR (€)",
    flag: "🇪🇺",
    format: (val) => `€${val.toFixed(2)}`,
  },
  JPY: {
    code: "JPY",
    symbol: "¥",
    label: "JPY (¥)",
    flag: "🇯🇵",
    format: (val) => `¥${Math.round(val).toLocaleString()}`,
  },
};

export const DEFAULT_BUNDLES = [
  {
    id: "bundle_1",
    credits: 1,
    name: "Single Lesson",
    tagline: "Try out a 25-minute class",
    discount: null,
    popular: false,
    prices: {
      USD: 8.0,
      ZAR: 150,
      EUR: 7.5,
      JPY: 1200,
    },
  },
  {
    id: "bundle_5",
    credits: 5,
    name: "Starter Pack",
    tagline: "5 x 25-min private lessons",
    discount: "5% OFF",
    popular: false,
    prices: {
      USD: 38.0,
      ZAR: 700,
      EUR: 35.5,
      JPY: 5700,
    },
  },
  {
    id: "bundle_10",
    credits: 10,
    name: "Fluency Builder",
    tagline: "10 x 25-min private lessons",
    discount: "10% OFF",
    popular: true,
    prices: {
      USD: 72.0,
      ZAR: 1300,
      EUR: 67.0,
      JPY: 10800,
    },
  },
  {
    id: "bundle_20",
    credits: 20,
    name: "Mastery Intensive",
    tagline: "20 x 25-min private lessons",
    discount: "15% OFF",
    popular: false,
    prices: {
      USD: 136.0,
      ZAR: 2400,
      EUR: 127.0,
      JPY: 20400,
    },
  },
];

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
