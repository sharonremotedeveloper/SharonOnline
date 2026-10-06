"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { CURRENCIES, CurrencyCode, detectDefaultCurrency } from "@/lib/currency";
import { api } from "@/lib/api";
import { formatPackPerLesson, formatPackPrice, type CreditPackPrice } from "@/lib/prices";
import { useApiData } from "@/hooks/useApiData";
import { ErrorState } from "@/components/ui/ErrorState";
import { CurrencySwitcher } from "./CurrencySwitcher";
import { Check, Shield, Zap, Sparkles } from "lucide-react";

export function PricingTable() {
  const [currency, setCurrency] = useState<CurrencyCode>("USD");
  const { data: packs, error, loading, reload } = useApiData<CreditPackPrice[]>(() => api.getCreditPacks(), []);

  useEffect(() => {
    setCurrency(detectDefaultCurrency());

    const handleCurrencyChange = (e: Event) => {
      const customEvent = e as CustomEvent<CurrencyCode>;
      if (customEvent.detail && CURRENCIES[customEvent.detail]) {
        setCurrency(customEvent.detail);
      }
    };

    window.addEventListener("sharon_currency_changed", handleCurrencyChange);
    return () => window.removeEventListener("sharon_currency_changed", handleCurrencyChange);
  }, []);

  return (
    <div className="space-y-8">
      {/* Currency Selector Bar */}
      <div className="flex flex-col sm:flex-row items-center justify-between gap-4 bg-white p-4 rounded-2xl border border-divider">
        <div className="text-center sm:text-left">
          <div className="text-lg font-bold text-ink font-serif">Show prices in your currency</div>
          <div className="text-sm text-ink-muted">You pay in USD, EUR or JPY with PayPal, or ZAR with PayFast.</div>
        </div>
        <CurrencySwitcher variant="inline" onCurrencyChange={(c) => setCurrency(c)} />
      </div>

      {/* Credit Pack Cards Grid: every price comes from the API as an exact decimal string */}
      {error ? (
        <ErrorState error={error} title="We could not load our prices" onRetry={reload} />
      ) : loading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6" role="status" aria-label="Loading prices">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="h-72 animate-pulse rounded-2xl border border-divider bg-white" />
          ))}
        </div>
      ) : !packs || packs.length === 0 ? (
        <div className="bg-white rounded-2xl p-8 border border-divider text-center text-base text-ink-muted">
          No lesson packs are available right now. Please check back soon.
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          {packs.map((pack) => {
            const formattedPrice = formatPackPrice(pack, currency);
            const perLessonPrice = formatPackPerLesson(pack, currency);
            const popular = pack.credits === 10;

            return (
              <div
                key={pack.id}
                className={`relative bg-white rounded-2xl p-6 border transition-shadow flex flex-col justify-between ${
                  popular
                    ? "border-primary shadow-card-hover ring-2 ring-primary/25"
                    : "border-divider shadow-card hover:shadow-card-hover"
                }`}
              >
                {popular && (
                  <div className="absolute -top-4 left-1/2 -translate-x-1/2 whitespace-nowrap px-4 py-1.5 rounded-full bg-primary text-white text-sm font-bold flex items-center gap-1.5 shadow-sm">
                    <Sparkles className="w-4 h-4" aria-hidden="true" /> Best value
                  </div>
                )}

                <div className="space-y-4">
                  <div className="flex items-center justify-between">
                    <h3 className="text-base font-bold text-ink font-serif">{pack.name}</h3>
                  </div>

                  <div>
                    {formattedPrice ? (
                      <>
                        <div className="text-4xl font-bold text-ink font-serif">{formattedPrice}</div>
                        {perLessonPrice && (
                          <div className="text-base text-ink-muted mt-1">
                            {perLessonPrice} / 25-min lesson
                          </div>
                        )}
                      </>
                    ) : (
                      <div className="text-base text-ink-muted">Not available in {currency}</div>
                    )}
                  </div>
                  <div className="border-t border-divider" />

                  <ul className="space-y-2.5 text-base text-ink">
                    <li className="flex items-center gap-2">
                      <Check className="w-4 h-4 text-success flex-shrink-0" aria-hidden="true" />
                      <span>
                        {pack.credits} lesson{pack.credits > 1 ? "s" : ""} of 25 minutes
                      </span>
                    </li>
                    <li className="flex items-center gap-2">
                      <Check className="w-4 h-4 text-success flex-shrink-0" aria-hidden="true" />
                      <span>Private 1-on-1 video lesson</span>
                    </li>
                    <li className="flex items-center gap-2">
                      <Check className="w-4 h-4 text-success flex-shrink-0" aria-hidden="true" />
                      <span>Lesson notes and new words</span>
                    </li>
                  </ul>
                </div>

                <div className="pt-6">
                  <Link
                    href={`/register?bundle=${encodeURIComponent(pack.code)}&currency=${currency}`}
                    className={`w-full min-h-[48px] rounded-full font-bold text-base flex items-center justify-center gap-2 transition-colors ${
                      popular
                        ? "bg-primary hover:bg-primary-hover text-white shadow-sm"
                        : "bg-cream-surface hover:bg-cream-deep text-ink border border-divider"
                    }`}
                  >
                    <Zap className="w-4 h-4" aria-hidden="true" /> Buy {pack.credits} lesson{pack.credits > 1 ? "s" : ""}
                  </Link>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Money-Back Guarantee & Payment Badges */}
      <div className="bg-cream-surface rounded-2xl p-6 border border-divider flex flex-col md:flex-row items-center justify-between gap-4 text-center md:text-left">
        <div className="flex items-center gap-4">
          <div className="w-12 h-12 rounded-xl bg-gold-surface text-primary flex items-center justify-center flex-shrink-0">
            <Shield className="w-6 h-6" aria-hidden="true" />
          </div>
          <div>
            <div className="text-lg font-bold text-ink font-serif">First lesson guarantee</div>
            <div className="text-base text-ink-muted">
              If your first lesson does not meet your expectations, we will re-credit your wallet or issue a 100% refund.
            </div>
          </div>
        </div>

        <ul className="flex flex-wrap items-center justify-center gap-2 text-sm font-semibold text-ink" aria-label="Payment methods">
          <li className="px-3 py-2 rounded-lg bg-white border border-divider">PayPal</li>
          <li className="px-3 py-2 rounded-lg bg-white border border-divider">PayFast</li>
          <li className="px-3 py-2 rounded-lg bg-white border border-divider">Visa &amp; Mastercard</li>
        </ul>
      </div>
    </div>
  );
}
