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
import { CreditLedgerEntry } from "@/types/booking";
import { DEFAULT_BUNDLES, CURRENCIES, CurrencyCode, detectDefaultCurrency } from "@/lib/currency";
import { CurrencySwitcher } from "@/components/public/CurrencySwitcher";

export default function StudentWalletPage() {
  const [balance, setBalance] = useState(5);
  const [ledger, setLedger] = useState<CreditLedgerEntry[]>([]);
  const [currency, setCurrency] = useState<CurrencyCode>("USD");
  const [loading, setLoading] = useState(true);
  const [purchasing, setPurchasing] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState("");

  const curr = CURRENCIES[currency];

  useEffect(() => {
    setCurrency(detectDefaultCurrency());

    async function loadWallet() {
      setLoading(true);
      try {
        const data = await api.getStudentWallet();
        setBalance(data.available_credits);
        setLedger(data.ledger);
      } catch (err) {
        console.error("Failed to load student wallet:", err);
      } finally {
        setLoading(false);
      }
    }
    loadWallet();
  }, []);

  const handleBuyBundle = (bundle: typeof DEFAULT_BUNDLES[0]) => {
    setPurchasing(bundle.id);
    setTimeout(() => {
      setBalance((prev) => prev + bundle.credits);
      const newEntry: CreditLedgerEntry = {
        id: `led-${Date.now()}`,
        description: `Purchased ${bundle.name} (${bundle.credits} Lessons)`,
        credits_delta: +bundle.credits,
        date: new Date().toISOString().split("T")[0],
        type: "purchase",
      };
      setLedger((prev) => [newEntry, ...prev]);
      setPurchasing(null);
      setSuccessMessage(`Successfully purchased ${bundle.credits} lesson credits!`);
      setTimeout(() => setSuccessMessage(""), 4000);
    }, 1000);
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

      {successMessage && (
        <div className="p-4 bg-success/15 border border-success/30 rounded-2xl text-xs text-success font-bold flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4 shrink-0" />
          <span>{successMessage}</span>
        </div>
      )}

      {/* Balance Summary Card */}
      <div className="bg-gradient-to-r from-teal to-teal-mid text-white rounded-3xl p-8 shadow-card flex flex-col sm:flex-row sm:items-center justify-between gap-6">
        <div className="space-y-2">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-white/10 text-xs font-bold text-accent-surface border border-white/20">
            <Coins className="w-3.5 h-3.5 text-accent" />
            <span>Active Lesson Tickets</span>
          </div>

          <div className="flex items-baseline gap-3">
            <span className="text-5xl font-black font-serif text-white">{balance}</span>
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

      {/* Top-Up Bundle Packs Grid */}
      <div className="space-y-4">
        <div className="space-y-1">
          <h2 className="text-xl font-extrabold text-ink font-serif">Top Up Lesson Packs</h2>
          <p className="text-xs text-ink-muted">
            Save up to 15% with multi-lesson packs. Billed in {currency}.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {DEFAULT_BUNDLES.map((bundle) => {
            const rawPrice = bundle.prices[currency];
            const formattedPrice = curr.format(rawPrice);
            const isProcessing = purchasing === bundle.id;

            return (
              <div
                key={bundle.id}
                className={`bg-white rounded-3xl p-6 border flex flex-col justify-between space-y-4 transition-all ${
                  bundle.popular
                    ? "border-accent ring-2 ring-accent/30 shadow-card-hover"
                    : "border-divider shadow-card hover:shadow-card-hover"
                }`}
              >
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-ink-muted uppercase tracking-wider">
                      {bundle.name}
                    </span>
                    {bundle.discount && (
                      <span className="px-2 py-0.5 rounded-full bg-success/15 text-success text-[10px] font-bold">
                        {bundle.discount}
                      </span>
                    )}
                  </div>

                  <div>
                    <div className="text-2xl font-black text-ink font-serif">{formattedPrice}</div>
                    <div className="text-[11px] text-ink-muted mt-0.5">
                      {curr.format(rawPrice / bundle.credits)} / lesson
                    </div>
                  </div>

                  <p className="text-xs text-ink-muted">{bundle.tagline}</p>
                </div>

                <button
                  onClick={() => handleBuyBundle(bundle)}
                  disabled={isProcessing}
                  className={`w-full py-2.5 rounded-xl text-xs font-bold transition-all flex items-center justify-center gap-1.5 ${
                    bundle.popular
                      ? "bg-primary hover:bg-primary-hover text-white shadow-sm"
                      : "bg-cream-surface hover:bg-cream-deep text-ink border border-divider"
                  }`}
                >
                  <PlusCircle className="w-3.5 h-3.5" />
                  <span>{isProcessing ? "Processing..." : `Add ${bundle.credits} Credits`}</span>
                </button>
              </div>
            );
          })}
        </div>
      </div>

      {/* Credit Ledger / History */}
      <div className="bg-white rounded-3xl p-6 sm:p-8 border border-divider shadow-card space-y-6">
        <div className="space-y-1 border-b border-divider pb-4">
          <h2 className="text-xl font-extrabold text-ink font-serif">Credit History & Ledger</h2>
          <p className="text-xs text-ink-muted">Audit trail of all credits purchased and redeemed</p>
        </div>

        <div className="divide-y divide-divider text-xs">
          {ledger.map((entry) => (
            <div key={entry.id} className="py-3.5 flex items-center justify-between">
              <div>
                <div className="font-bold text-ink">{entry.description}</div>
                <div className="text-[11px] text-ink-muted">{entry.date}</div>
              </div>

              <div
                className={`font-black text-sm font-serif ${
                  entry.credits_delta > 0 ? "text-success" : "text-primary"
                }`}
              >
                {entry.credits_delta > 0 ? `+${entry.credits_delta}` : entry.credits_delta} Credits
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
