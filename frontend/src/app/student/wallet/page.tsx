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
  FileText,
} from "lucide-react";
import { api } from "@/lib/api";
import type { components } from "@/types/api.generated";
import { CurrencyCode, detectDefaultCurrency } from "@/lib/currency";
import { formatPackPerLesson, formatPackPrice, type CreditPackPrice } from "@/lib/prices";
import { CurrencySwitcher } from "@/components/public/CurrencySwitcher";
import { ErrorState } from "@/components/ui/ErrorState";
import { useApiData } from "@/hooks/useApiData";
import { PayPalButtonsWrapper } from "@/components/booking/PayPalButtonsWrapper";
import type { OutcomeView } from "@/lib/paypalOutcome";
import { rememberPendingPayFast } from "@/lib/pendingPayment";
import { ReceiptsList } from "@/components/student/ReceiptsList";
import { ReceiptDrawer } from "@/components/wallet/ReceiptDrawer";

// Generated from the backend OpenAPI schema (`npm run gen:api`), so a contract change breaks the build instead of the page.
type WalletResponse = components["schemas"]["Wallet"];
type CreditPack = CreditPackPrice;

export default function StudentWalletPage() {
  const [currency, setCurrency] = useState<CurrencyCode>("USD");
  const { data: wallet, error, loading, reload } = useApiData<WalletResponse>(() => api.getStudentWallet(), []);
  const {
    data: packs,
    error: packsError,
    loading: packsLoading,
    reload: reloadPacks,
  } = useApiData<CreditPack[]>(() => api.getCreditPacks(), []);
  const [buyingPack, setBuyingPack] = useState<number | null>(null);
  const [purchaseNotice, setPurchaseNotice] = useState<string>("");
  const [pendingPurchaseId, setPendingPurchaseId] = useState<string | null>(null);
  // The pack whose PayPal buttons are currently shown (PayPal creates the order when the student clicks the button).
  const [paypalPack, setPaypalPack] = useState<CreditPack | null>(null);
  const [receiptDrawerOpen, setReceiptDrawerOpen] = useState<boolean>(false);

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

  // ZAR packs go through PayFast (signed redirect); every other currency is paid with the PayPal buttons.
  const startPackPurchase = async (pack: CreditPack) => {
    setPurchaseNotice("");
    if (currency !== "ZAR") {
      setPaypalPack(pack);
      return;
    }
    setPaypalPack(null);
    setBuyingPack(pack.id);
    try {
      const checkout = await api.initializeCheckout({ credit_pack_id: pack.id, gateway: "payfast", currency });
      if (!checkout?.action_url || !checkout?.fields) {
        throw new Error("The server did not return a PayFast redirect.");
      }
      rememberPendingPayFast({ kind: "credit_purchase", id: String(checkout.target_id) });
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
    } catch (err) {
      setPurchaseNotice(`Could not start pack checkout: ${err instanceof Error ? err.message : "Unknown error"}`);
    } finally {
      setBuyingPack(null);
    }
  };

  // The server decided the outcome; the wallet only reflects it. Packs are credited only after a server-verified capture.
  const handlePayPalPackOutcome = (view: OutcomeView) => {
    const action = view.nextAction;
    if (action.type === "pack_credited") {
      setPaypalPack(null);
      setPurchaseNotice("Your payment was confirmed and the credits are now in your wallet.");
      reload();
    } else if (action.type === "poll") {
      setPaypalPack(null);
      setPendingPurchaseId(action.id);
      setPurchaseNotice(view.message);
    } else if (action.type === "check_then_retry") {
      setPurchaseNotice(`${view.message} Your wallet will update if the payment went through.`);
      reload();
    } else if (view.kind === "error" || view.kind === "unavailable_slot") {
      setPurchaseNotice(view.message);
    }
  };

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-10 space-y-8">
      {/* Page Header & Currency Selector */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl sm:text-4xl font-extrabold text-ink font-serif tracking-tight">
            Student Credit Wallet
          </h1>
          <p className="text-sm text-ink-muted mt-1">
            Manage your pre-purchased lesson tickets and review your transaction history
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={() => setReceiptDrawerOpen(true)}
            className="inline-flex min-h-[44px] items-center gap-2 px-4 rounded-full border border-divider bg-white hover:bg-cream-surface text-base font-bold text-ink transition-colors shadow-sm"
          >
            <FileText className="w-3.5 h-3.5 text-cocoa" />
            <span>Invoices & Receipts</span>
          </button>
          <CurrencySwitcher variant="inline" onCurrencyChange={(c) => setCurrency(c)} />
        </div>
      </div>

      {error ? (
        <ErrorState error={error} title="We could not load your wallet" onRetry={reload} />
      ) : loading || !wallet ? (
        <div className="bg-white rounded-3xl p-8 border border-divider text-center text-sm text-ink-muted">
          Loading your wallet...
        </div>
      ) : null}

      {/* Balance Summary Card */}
      {wallet && (
      <div className="bg-gradient-to-r from-cocoa to-cocoa-mid text-white rounded-3xl p-8 shadow-card flex flex-col sm:flex-row sm:items-center justify-between gap-6">
        <div className="space-y-2">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-white/10 text-sm font-bold text-sun-soft border border-white/20">
            <Coins className="w-3.5 h-3.5 text-gold-bright" />
            <span>Active Lesson Tickets</span>
          </div>

          <div className="flex items-baseline gap-3">
            <span className="text-5xl font-black font-serif text-white">{wallet.total_credits}</span>
            <span className="text-sm font-semibold text-white/80">Available Credits</span>
          </div>

          <p className="text-sm text-white/80 max-w-sm">
            Each credit unlocks 1 full 25-minute synchronous private lesson with any verified tutor. Credits expire 30 days after they are granted.
          </p>
        </div>

        <div className="flex flex-col sm:items-end gap-2 border-t sm:border-t-0 pt-4 sm:pt-0 border-white/10">
          <Link
            href="/tutors"
            className="px-6 py-3 bg-accent hover:bg-gold-bright text-ink rounded-xl text-sm font-extrabold transition-all shadow-sm flex items-center justify-center gap-2"
          >
            <span>Book a Lesson</span>
            <ArrowRight className="w-4 h-4" />
          </Link>
          <span className="text-sm text-white/85">100% Satisfaction Guarantee</span>
        </div>
      </div>
      )}

      {/* Top-Up Bundle Packs Grid */}
      <div className="space-y-4">
        <div className="space-y-1">
          <h2 className="text-xl font-extrabold text-ink font-serif">Top Up Lesson Packs</h2>
          <p className="text-sm text-ink-muted">
            Billed in {currency}.
          </p>
          {purchaseNotice && <p className="text-sm text-warning-hover bg-warning-surface border border-warning-border rounded-xl px-3 py-2 inline-block">{purchaseNotice}</p>}
        </div>

        {paypalPack && currency !== "ZAR" && (
          <div className="max-w-md space-y-2">
            <div className="flex items-center justify-between text-sm">
              <span className="font-bold text-ink">Paying for: {paypalPack.name}</span>
              <button type="button" onClick={() => setPaypalPack(null)} className="text-ink-muted hover:text-ink font-bold">
                Cancel
              </button>
            </div>
            <PayPalButtonsWrapper
              key={paypalPack.id}
              target={{ kind: "credit_pack", packId: paypalPack.id }}
              currency={currency}
              amountLabel={formatPackPrice(paypalPack, currency)}
              reference={paypalPack.name}
              onOutcome={handlePayPalPackOutcome}
            />
          </div>
        )}

        {packsError ? (
          <ErrorState error={packsError} title="We could not load the lesson packs" onRetry={reloadPacks} />
        ) : packsLoading ? (
          <div className="bg-white rounded-3xl p-8 border border-divider text-center text-sm text-ink-muted">
            Loading lesson packs...
          </div>
        ) : !packs || packs.length === 0 ? (
          <div className="bg-white rounded-3xl p-8 border border-divider text-center text-sm text-ink-muted">
            No lesson packs are available right now.
          </div>
        ) : null}

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {(packs ?? []).map((bundle) => {
            const formattedPrice = formatPackPrice(bundle, currency);
            const perLesson = formatPackPerLesson(bundle, currency);

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
                    <span className="text-sm font-bold text-ink-muted uppercase tracking-wider">
                      {bundle.name}
                    </span>
                  </div>

                  <div>
                    <div className="text-2xl font-black text-ink font-serif">
                      {formattedPrice ?? `Not available in ${currency}`}
                    </div>
                    {formattedPrice && perLesson && (
                      <div className="text-sm text-ink-muted mt-0.5">{perLesson} / lesson</div>
                    )}
                  </div>

                  <p className="text-sm text-ink-muted">{bundle.credits} private 25-minute lessons</p>
                </div>

                <button
                  type="button"
                  disabled={buyingPack !== null || !formattedPrice}
                  onClick={() => startPackPurchase(bundle)}
                  className={`w-full py-2.5 rounded-xl text-sm font-bold transition-all flex items-center justify-center gap-1.5 disabled:opacity-50 ${
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
            <p className="text-sm text-ink-muted">Credit packs on your account and how many lessons remain in each</p>
          </div>

          {wallet.bundles.length === 0 ? (
            <div className="py-6 text-center text-sm text-ink-muted">You have not purchased any lesson packs yet.</div>
          ) : (
            <div className="divide-y divide-divider text-sm">
              {wallet.bundles.map((b, idx) => (
                <div key={`${b.pack_name}-${b.purchased_at}-${idx}`} className="py-3.5 flex items-center justify-between">
                  <div>
                    <div className="font-bold text-ink">{b.pack_name}</div>
                    <div className="text-sm text-ink-muted">
                      Purchased {new Date(b.purchased_at).toLocaleDateString()}
                    </div>
                  </div>
                  <div className="font-black text-sm font-serif text-cocoa">
                    {b.remaining} of {b.total} Credits left
                  </div>
                </div>
              ))}
            </div>
          )}

          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-t border-divider pt-4 text-sm">
            <p className="text-sm text-ink-muted">
              A per-transaction credit history (redemptions and refunds) is not available yet.
            </p>
            <button
              type="button"
              onClick={() => setReceiptDrawerOpen(true)}
              className="inline-flex items-center gap-1.5 text-sm font-bold text-cocoa hover:text-cocoa-deep transition-colors"
            >
              <FileText className="w-3.5 h-3.5" />
              <span>View Invoices & Receipts</span>
            </button>
          </div>
        </div>
      )}

      <ReceiptsList />

      {/* Slide-out Receipt Drawer */}
      <ReceiptDrawer
        isOpen={receiptDrawerOpen}
        onClose={() => setReceiptDrawerOpen(false)}
      />
    </div>
  );
}
