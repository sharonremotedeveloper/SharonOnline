"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import {
  Coins,
  ShieldCheck,
  Zap,
  ArrowRight,
  Clock,
  CheckCircle2,
  PlusCircle,
  CreditCard,
} from "lucide-react";
import { api } from "@/lib/api";
import type { components } from "@/types/api.generated";
import { CURRENCIES, CurrencyCode, detectDefaultCurrency } from "@/lib/currency";
import { CurrencySwitcher } from "@/components/public/CurrencySwitcher";
import { ErrorState } from "@/components/ui/ErrorState";
import { useApiData } from "@/hooks/useApiData";

// Generated from the backend OpenAPI schema (`npm run gen:api`), so a contract change breaks the build instead of the page.
type WalletResponse = components["schemas"]["Wallet"];
type CreditPack = {
  id: number;
  code: string;
  name: string;
  credits: number;
  prices: Record<CurrencyCode, string>;
};

export default function StudentWalletPage() {
  const [currency, setCurrency] = useState<CurrencyCode>("USD");
  const { data: wallet, error, loading, reload } = useApiData<WalletResponse>(() => api.getStudentWallet(), []);
  const { data: packs, error: packsError } = useApiData<CreditPack[]>(() => api.getCreditPacks(), []);
  const [buyingPack, setBuyingPack] = useState<number | null>(null);
  const [purchaseNotice, setPurchaseNotice] = useState<string>("");
  const [pendingPurchaseId, setPendingPurchaseId] = useState<string | null>(null);

  const curr = CURRENCIES[currency];

  useEffect(() => {
    setCurrency(detectDefaultCurrency());
  }, []);

  useEffect(() => {
    if (!pendingPurchaseId) return;
    const timer = window.setInterval(async () => {
      try {
        const purchase = await api.getCreditPurchase(pendingPurchaseId);
        if (purchase.status === "success") {
          window.clearInterval(timer);
          setPendingPurchaseId(null);
          setPurchaseNotice(`${purchase.pack.name} was confirmed and the credits are now in your wallet.`);
          reload();
        } else if (purchase.status === "failed" || purchase.status === "refunded") {
          window.clearInterval(timer);
          setPendingPurchaseId(null);
          setPurchaseNotice(`Purchase ${pendingPurchaseId} is ${purchase.status}; no new credits were added.`);
        }
      } catch (err) {
        console.error("Credit purchase status poll failed:", err);
      }
    }, 2000);
    return () => window.clearInterval(timer);
  }, [pendingPurchaseId, reload]);

  const startPackPurchase = async (pack: CreditPack) => {
    setBuyingPack(pack.id);
    setPurchaseNotice("");
    try {
      const gateway = currency === "ZAR" ? "payfast" : "paypal";
      const checkout = await api.initializeCheckout({ credit_pack_id: pack.id, gateway, currency });
      setPendingPurchaseId(checkout.target_id);
      if (gateway === "payfast" && checkout?.action_url && checkout?.fields) {
        const form = document.createElement("form");
        form.method = "POST";
        form.action = checkout.action_url;
        for (const [name, value] of Object.entries(checkout.fields)) {
          const input = document.createElement("input");
          input.type = "hidden";
          input.name = name;
          input.value = String(value);
          form.appendChild(input);
        }
        document.body.appendChild(form);
        form.submit();
        return;
      }
      setPurchaseNotice(
        `Purchase ${checkout.target_id} is awaiting a verified ${gateway} capture. Credits appear only after the webhook confirms it.`
      );
    } catch (err) {
      setPurchaseNotice(`Could not start pack checkout: ${err instanceof Error ? err.message : "Unknown error"}`);
    } finally {
      setBuyingPack(null);
    }
  };

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-10 space-y-8">
      {/* Page Header & Currency Selector */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-extrabold text-ink font-serif tracking-tight">
            Student Credit Wallet
          </h1>
          <p className="text-xs text-ink-muted mt-1">
            Manage your pre-purchased lesson tickets and review your transaction history
          </p>
        </div>

        <CurrencySwitcher variant="inline" onCurrencyChange={(c) => setCurrency(c)} />
      </div>

      {error ? (
        <ErrorState error={error} title="We could not load your wallet" onRetry={reload} />
      ) : loading || !wallet ? (
        <div className="bg-white rounded-3xl p-8 border border-divider text-center text-xs text-ink-muted">
          Loading your wallet...
        </div>
      ) : null}

      {/* Balance Summary Card */}
      {wallet && (
      <div className="bg-gradient-to-r from-teal to-teal-mid text-white rounded-3xl p-8 shadow-card flex flex-col sm:flex-row sm:items-center justify-between gap-6">
        <div className="space-y-2">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-white/10 text-xs font-bold text-accent-surface border border-white/20">
            <Coins className="w-3.5 h-3.5 text-accent" />
            <span>Active Lesson Tickets</span>
          </div>

          <div className="flex items-baseline gap-3">
            <span className="text-5xl font-black font-serif text-white">{wallet.total_credits}</span>
            <span className="text-sm font-semibold text-white/80">Available Credits</span>
          </div>

          <p className="text-xs text-white/80 max-w-sm">
            Each credit unlocks 1 full 25-minute synchronous private lesson with any verified tutor. Credits never expire.
          </p>
        </div>

        <div className="flex flex-col sm:items-end gap-2 border-t sm:border-t-0 pt-4 sm:pt-0 border-white/10">
          <Link
            href="/tutors"
            className="px-6 py-3 bg-accent hover:bg-gold-bright text-ink rounded-xl text-xs font-extrabold transition-all shadow-sm flex items-center justify-center gap-2"
          >
            <span>Book a Lesson</span>
            <ArrowRight className="w-4 h-4" />
          </Link>
          <span className="text-[11px] text-white/70">100% Satisfaction Guarantee</span>
        </div>
      </div>
      )}

      {/* Top-Up Bundle Packs Grid */}
      <div className="space-y-4">
        <div className="space-y-1">
          <h2 className="text-xl font-extrabold text-ink font-serif">Top Up Lesson Packs</h2>
          <p className="text-xs text-ink-muted">
            Save up to 15% with multi-lesson packs. Billed in {currency}.
          </p>
          {purchaseNotice && <p className="text-[11px] text-amber-800 bg-amber-50 border border-amber-200 rounded-xl px-3 py-2 inline-block">{purchaseNotice}</p>}
          {packsError ? <p className="text-[11px] text-primary">Credit packs could not be loaded.</p> : null}
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {(packs ?? []).map((bundle) => {
            const rawPrice = Number(bundle.prices[currency]);
            const formattedPrice = curr.format(rawPrice);

            return (
              <div
                key={bundle.id}
                className={`bg-white rounded-3xl p-6 border flex flex-col justify-between space-y-4 transition-all ${
                  bundle.credits === 10
                    ? "border-accent ring-2 ring-accent/30 shadow-card-hover"
                    : "border-divider shadow-card hover:shadow-card-hover"
                }`}
              >
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-ink-muted uppercase tracking-wider">
                      {bundle.name}
                    </span>
                    {bundle.credits > 1 && (
                      <span className="px-2 py-0.5 rounded-full bg-success/15 text-success text-[10px] font-bold">
                        Pack savings
                      </span>
                    )}
                  </div>

                  <div>
                    <div className="text-2xl font-black text-ink font-serif">{formattedPrice}</div>
                    <div className="text-[11px] text-ink-muted mt-0.5">
                      {curr.format(rawPrice / bundle.credits)} / lesson
                    </div>
                  </div>

                  <p className="text-xs text-ink-muted">{bundle.credits} private 25-minute lessons</p>
                </div>

                <button
                  type="button"
                  disabled={buyingPack !== null}
                  onClick={() => startPackPurchase(bundle)}
                  className={`w-full py-2.5 rounded-xl text-xs font-bold transition-all flex items-center justify-center gap-1.5 disabled:opacity-50 ${
                    bundle.credits === 10
                      ? "bg-primary hover:bg-primary-hover text-white shadow-sm"
                      : "bg-cream-surface hover:bg-cream-deep text-ink border border-divider"
                  }`}
                >
                  <PlusCircle className="w-3.5 h-3.5" />
                  <span>{buyingPack === bundle.id ? "Starting checkout..." : `Add ${bundle.credits} Credits`}</span>
                </button>
              </div>
            );
          })}
        </div>
      </div>

      {/* Credit packs on the account */}
      {wallet && (
        <div className="bg-white rounded-3xl p-6 sm:p-8 border border-divider shadow-card space-y-6">
          <div className="space-y-1 border-b border-divider pb-4">
            <h2 className="text-xl font-extrabold text-ink font-serif">Purchased Lesson Packs</h2>
            <p className="text-xs text-ink-muted">Credit packs on your account and how many lessons remain in each</p>
          </div>

          {wallet.bundles.length === 0 ? (
            <div className="py-6 text-center text-xs text-ink-muted">You have not purchased any lesson packs yet.</div>
          ) : (
            <div className="divide-y divide-divider text-xs">
              {wallet.bundles.map((b, idx) => (
                <div key={`${b.pack_name}-${b.purchased_at}-${idx}`} className="py-3.5 flex items-center justify-between">
                  <div>
                    <div className="font-bold text-ink">{b.pack_name}</div>
                    <div className="text-[11px] text-ink-muted">
                      Purchased {new Date(b.purchased_at).toLocaleDateString()}
                    </div>
                  </div>
                  <div className="font-black text-sm font-serif text-teal">
                    {b.remaining} of {b.total} Credits left
                  </div>
                </div>
              ))}
            </div>
          )}

          <p className="text-[11px] text-ink-muted border-t border-divider pt-4">
            A per-transaction credit history (redemptions and refunds) is not available yet.
          </p>
        </div>
      )}
    </div>
  );
}
