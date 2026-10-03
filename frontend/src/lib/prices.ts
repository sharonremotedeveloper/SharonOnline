/**
 * Money display helpers.
 *
 * The API serialises every amount as a decimal STRING ("9.00") together with the currency's decimal places. Amounts
 * stay strings end to end: they are validated, split on the decimal point and handed to Intl as BigInt integer
 * and fraction parts, so there is no Number(), no Math.round and no float arithmetic anywhere on a price.
 */
import type { CurrencyCode } from "./currency";

export interface LessonPrice {
  currency: CurrencyCode;
  /** Decimal string, e.g. "9.00" or "1350". */
  amount: string;
  /** Minor-unit digits for the currency (2 for USD/EUR/ZAR, 0 for JPY). */
  decimals: number;
}

export interface CreditPackPrice {
  id: number;
  code: string;
  name: string;
  credits: number;
  prices: Record<CurrencyCode, string>;
}

const DECIMAL = /^(\d+)(?:\.(\d+))?$/;

function split(amount: string, decimals: number): { whole: string; fraction: string } {
  if (typeof amount !== "string") throw new TypeError("Money amounts must be decimal strings, never numbers.");
  if (!Number.isInteger(decimals) || decimals < 0 || decimals > 6) {
    throw new RangeError(`Invalid number of decimals: ${decimals}`);
  }
  const m = DECIMAL.exec(amount);
  if (!m) throw new TypeError(`Not a decimal amount: ${JSON.stringify(amount)}`);
  const whole = m[1];
  let fraction = m[2] ?? "";
  if (fraction.length > decimals) {
    // Extra digits are only acceptable when they are zeros; anything else would need rounding.
    if (/[1-9]/.test(fraction.slice(decimals))) {
      throw new RangeError(`Amount ${amount} has more than ${decimals} decimal places; refusing to round.`);
    }
    fraction = fraction.slice(0, decimals);
  }
  return { whole, fraction: fraction.padEnd(decimals, "0") };
}

/** Format a decimal-string amount in the currency's presentation, without ever converting it to a float. */
export function formatMoney(amount: string, currency: CurrencyCode | string, decimals: number, locale = "en-US"): string {
  const { whole, fraction } = split(amount, decimals);
  const nf = new Intl.NumberFormat(locale, {
    style: "currency",
    currency,
    currencyDisplay: "narrowSymbol",
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
  // Format the exact integer part (BigInt), then substitute the exact fraction digits.
  const parts = nf.formatToParts(BigInt(whole));
  return parts.map((p) => (p.type === "fraction" ? fraction : p.value)).join("");
}

export function lessonPriceFor(
  prices: readonly LessonPrice[] | null | undefined,
  currency: CurrencyCode,
): LessonPrice | null {
  return prices?.find((p) => p.currency === currency) ?? null;
}

export function formatLessonPrice(price: LessonPrice, locale?: string): string {
  return formatMoney(price.amount, price.currency, price.decimals, locale);
}

/** ISO 4217 minor-unit digits for a currency (JPY 0, USD/EUR/ZAR 2), as known to the platform's Intl data. */
export function currencyDecimals(currency: CurrencyCode | string): number {
  return new Intl.NumberFormat("en-US", { style: "currency", currency }).resolvedOptions().maximumFractionDigits ?? 2;
}

/** A credit pack's price in one currency, or null when the pack has no price in it. */
export function formatPackPrice(pack: CreditPackPrice, currency: CurrencyCode): string | null {
  const amount = pack.prices?.[currency];
  return typeof amount === "string" ? formatMoney(amount, currency, currencyDecimals(currency)) : null;
}

/** The pack price divided per lesson, or null when absent or not an exact amount. */
export function formatPackPerLesson(pack: CreditPackPrice, currency: CurrencyCode): string | null {
  const amount = pack.prices?.[currency];
  if (typeof amount !== "string") return null;
  const decimals = currencyDecimals(currency);
  const each = dividePrice(amount, decimals, pack.credits);
  return each === null ? null : formatMoney(each, currency, decimals);
}

/**
 * Exact amount / count in the same decimals, or null when it does not divide evenly (callers then omit the
 * per-lesson figure rather than show a rounded one).
 */
export function dividePrice(amount: string, decimals: number, count: number): string | null {
  if (!Number.isInteger(count) || count <= 0) return null;
  const { whole, fraction } = split(amount, decimals);
  const minor = BigInt(whole + fraction);
  const n = BigInt(count);
  if (minor % n !== BigInt(0)) return null;
  const q = (minor / n).toString().padStart(decimals + 1, "0");
  return decimals === 0 ? q : `${q.slice(0, q.length - decimals)}.${q.slice(q.length - decimals)}`;
}
