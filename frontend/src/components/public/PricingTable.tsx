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
      <div className="flex flex-col sm:flex-row items-center justify-between gap-4 bg-cream-surface p-4 rounded-2xl border border-divider">
        <div>
          <div className="text-xs font-bold uppercase tracking-wider text-primary">Transparent Pricing</div>
          <div className="text-base font-extrabold text-ink font-serif">Select your local display currency</div>
        </div>
        <CurrencySwitcher variant="inline" onCurrencyChange={(c) => setCurrency(c)} />
      </div>

      {/* Credit Pack Cards Grid: every price comes from the API as an exact decimal string */}
      {error ? (
        <ErrorState error={error} title="We could not load our prices" onRetry={reload} />
      ) : loading ? (
        <div className="bg-white rounded-2xl p-8 border border-divider text-center text-xs text-ink-muted">
          Loading prices...
        </div>
      ) : !packs || packs.length === 0 ? (
        <div className="bg-white rounded-2xl p-8 border border-divider text-center text-xs text-ink-muted">
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
                className={`relative bg-white rounded-2xl p-6 border transition-all flex flex-col justify-between ${
                  popular
                    ? "border-accent shadow-card-hover ring-2 ring-accent/30"
                    : "border-divider shadow-card hover:shadow-card-hover"
                }`}
              >
                {popular && (
                  <div className="absolute -top-3.5 left-1/2 -translate-x-1/2 px-3 py-1 rounded-full bg-accent text-ink text-[11px] font-black tracking-wider uppercase flex items-center gap-1 shadow-sm">
                    <Sparkles className="w-3 h-3" /> Most Popular
                  </div>
                )}

                <div className="space-y-4">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-ink-muted uppercase tracking-wider">{pack.name}</span>
                  </div>

                  <div>
                    {formattedPrice ? (
                      <>
                        <div className="text-3xl font-extrabold text-ink font-serif">{formattedPrice}</div>
                        {perLessonPrice && (
                          <div className="text-xs font-semibold text-ink-muted mt-1">
                            {perLessonPrice} / 25-min lesson
                          </div>
                        )}
                      </>
                    ) : (
                      <div className="text-xs font-semibold text-ink-muted">Not available in {currency}</div>
                    )}
                  </div>

                  <p className="text-xs text-ink-muted leading-relaxed border-t border-divider pt-3">
                    {pack.credits} x 25-min private lesson{pack.credits > 1 ? "s" : ""}
                  </p>

                  <ul className="space-y-2 text-xs text-ink font-medium">
                    <li className="flex items-center gap-2">
                      <Check className="w-3.5 h-3.5 text-success flex-shrink-0" />
                      <span>
                        {pack.credits} Lesson Ticket{pack.credits > 1 ? "s" : ""}
                      </span>
                    </li>
                    <li className="flex items-center gap-2">
                      <Check className="w-3.5 h-3.5 text-success flex-shrink-0" />
                      <span>1-on-1 Private Zoom Classroom</span>
                    </li>
                    <li className="flex items-center gap-2">
                      <Check className="w-3.5 h-3.5 text-success flex-shrink-0" />
                      <span>Post-Lesson Memo & Vocab Bank</span>
                    </li>
                  </ul>
                </div>

                <div className="pt-6">
                  <Link
                    href={`/register?bundle=${encodeURIComponent(pack.code)}&currency=${currency}`}
                    className={`w-full py-3 rounded-xl font-bold text-xs flex items-center justify-center gap-2 transition-all ${
                      popular
                        ? "bg-primary hover:bg-primary-hover text-white shadow-sm"
                        : "bg-cream-surface hover:bg-cream-deep text-ink border border-divider"
                    }`}
                  >
                    <Zap className="w-3.5 h-3.5" /> Buy {pack.credits} Lesson{pack.credits > 1 ? "s" : ""}
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
          <div className="w-12 h-12 rounded-xl bg-gold/15 text-gold-bright flex items-center justify-center flex-shrink-0">
            <Shield className="w-6 h-6" />
          </div>
          <div>
            <div className="text-sm font-bold text-ink">100% Satisfaction Guarantee</div>
            <div className="text-xs text-ink-muted">
              If your first lesson does not meet your expectations, we will re-credit your wallet or issue a 100% refund.
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3 text-xs font-semibold text-ink-muted">
          <span className="px-3 py-1.5 rounded-lg bg-white border border-divider shadow-card-sm">PayFast (ZAR EFT)</span>
          <span className="px-3 py-1.5 rounded-lg bg-white border border-divider shadow-card-sm">PayPal (USD/EUR/JPY)</span>
          <span className="px-3 py-1.5 rounded-lg bg-white border border-divider shadow-card-sm">Visa & Mastercard</span>
        </div>
      </div>
    </div>
  );
}
