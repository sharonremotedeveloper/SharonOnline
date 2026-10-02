"use client";

import { useState } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  Building2,
  Lock,
  Check,
  ShieldCheck,
  HelpCircle,
} from "lucide-react";
import { api } from "@/lib/api";
import { InlineError } from "@/components/ui/ErrorState";
import { TeacherPayoutBankAccount } from "@/types/teacher";

const SA_BANKS = [
  { name: "Capitec Bank", branchCode: "470010" },
  { name: "First National Bank (FNB)", branchCode: "250655" },
  { name: "Standard Bank", branchCode: "051001" },
  { name: "Nedbank", branchCode: "198765" },
  { name: "Absa Bank", branchCode: "632005" },
  { name: "Discovery Bank", branchCode: "679000" },
  { name: "TymeBank", branchCode: "678910" },
  { name: "Investec Bank", branchCode: "580105" },
];

export default function TeacherPayoutSettingsPage() {
  const [bankName, setBankName] = useState(SA_BANKS[0].name);
  const [branchCode, setBranchCode] = useState(SA_BANKS[0].branchCode);
  const [accountHolder, setAccountHolder] = useState("");
  const [accountNumber, setAccountNumber] = useState("");
  const [accountType, setAccountType] = useState<"cheque" | "savings">("savings");
  const [idNumber, setIdNumber] = useState("");

  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const handleBankChange = (selectedName: string) => {
    setBankName(selectedName);
    const found = SA_BANKS.find((b) => b.name === selectedName);
    if (found) {
      setBranchCode(found.branchCode);
    }
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    // Validate 6-digit branch code
    if (!/^\d{6}$/.test(branchCode.trim())) {
      setError("Universal branch code must be exactly 6 digits (e.g. 470010).");
      return;
    }

    if (!accountNumber.trim() || accountNumber.trim().length < 6) {
      setError("Please enter a valid bank account number.");
      return;
    }

    setSaving(true);
    try {
      const payload: TeacherPayoutBankAccount = {
        bank_name: bankName,
        account_holder_name: accountHolder,
        account_number: accountNumber,
        branch_code: branchCode.trim(),
        account_type: accountType,
        id_number: idNumber,
      };

      await api.updatePayoutSettings(payload);
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch (err) {
      console.error("Failed to update payout settings:", err);
      setError(err);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="min-h-screen bg-cream py-8 sm:py-12">
      <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 space-y-8">
        {/* Navigation */}
        <div className="flex items-center justify-between">
          <Link
            href="/teacher/wallet"
            className="inline-flex items-center gap-2 text-xs font-bold text-ink-muted hover:text-ink transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
            <span>Return to Earnings Wallet</span>
          </Link>
          <span className="text-xs font-bold text-emerald-800 bg-emerald-50 px-3 py-1 rounded-full border border-emerald-200">
            SARB EFT Gateway
          </span>
        </div>

        {/* Header Card */}
        <div className="bg-white rounded-3xl p-6 sm:p-8 border border-divider shadow-card space-y-2">
          <div className="flex items-center gap-2.5">
            <div className="w-10 h-10 rounded-2xl bg-teal/10 text-teal flex items-center justify-center">
              <Building2 className="w-5 h-5" />
            </div>
            <div>
              <h1 className="text-2xl font-black text-ink font-serif">South African EFT Payout Settings</h1>
              <p className="text-xs text-ink-muted">
                Configure your South African bank account for bi-weekly direct EFT settlements in ZAR.
              </p>
            </div>
          </div>
        </div>

        {/* Security Alert Callout */}
        <div className="p-4 rounded-2xl bg-cream-surface border border-divider flex items-start gap-3 text-xs">
          <Lock className="w-4 h-4 text-teal shrink-0 mt-0.5" />
          <div className="space-y-0.5">
            <span className="font-bold text-ink">Bank-Grade Encryption</span>
            <p className="text-[11px] text-ink-muted leading-relaxed">
              Your banking details are AES-256 encrypted at rest and transmitted securely via South African Reserve
              Bank (SARB) automated clearing bureau channels. Settlements execute on the 1st and 15th of each month.
            </p>
          </div>
        </div>

        {/* Settings Form */}
        <form onSubmit={handleSave} className="bg-white rounded-3xl p-6 sm:p-8 border border-divider shadow-card space-y-6">
          <InlineError error={error} />

          {saved && (
            <div className="p-4 rounded-2xl bg-emerald-50 border border-emerald-200 text-xs text-emerald-900 font-bold flex items-center gap-2">
              <Check className="w-4 h-4 shrink-0 text-emerald-700" />
              <span>Banking information saved.</span>
            </div>
          )}

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {/* Bank Name Selector */}
            <div className="space-y-1.5">
              <label className="text-xs font-bold uppercase tracking-wider text-ink block">Bank Institution</label>
              <select
                value={bankName}
                onChange={(e) => handleBankChange(e.target.value)}
                className="w-full p-3 bg-cream-surface rounded-xl border border-divider text-xs font-bold text-ink focus:outline-none focus:ring-2 focus:ring-teal/30"
              >
                {SA_BANKS.map((b) => (
                  <option key={b.name} value={b.name}>
                    {b.name}
                  </option>
                ))}
              </select>
            </div>

            {/* Universal Branch Code */}
            <div className="space-y-1.5">
              <label className="text-xs font-bold uppercase tracking-wider text-ink block">
                Universal Branch Code (6 digits)
              </label>
              <input
                type="text"
                maxLength={6}
                value={branchCode}
                onChange={(e) => setBranchCode(e.target.value)}
                placeholder="470010"
                className="w-full p-3 bg-cream-surface rounded-xl border border-divider text-xs font-mono font-bold text-ink focus:outline-none focus:ring-2 focus:ring-teal/30"
                required
              />
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {/* Account Holder Name */}
            <div className="space-y-1.5">
              <label className="text-xs font-bold uppercase tracking-wider text-ink block">Account Holder Name</label>
              <input
                type="text"
                value={accountHolder}
                onChange={(e) => setAccountHolder(e.target.value)}
                placeholder="e.g. Sharon Mupesa"
                className="w-full p-3 bg-cream-surface rounded-xl border border-divider text-xs font-bold text-ink focus:outline-none focus:ring-2 focus:ring-teal/30"
                required
              />
            </div>

            {/* Account Number */}
            <div className="space-y-1.5">
              <label className="text-xs font-bold uppercase tracking-wider text-ink block">Account Number</label>
              <input
                type="text"
                value={accountNumber}
                onChange={(e) => setAccountNumber(e.target.value)}
                placeholder="e.g. 1234567890"
                className="w-full p-3 bg-cream-surface rounded-xl border border-divider text-xs font-mono font-bold text-ink focus:outline-none focus:ring-2 focus:ring-teal/30"
                required
              />
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {/* Account Type */}
            <div className="space-y-1.5">
              <label className="text-xs font-bold uppercase tracking-wider text-ink block">Account Type</label>
              <div className="grid grid-cols-2 gap-2">
                <button
                  type="button"
                  onClick={() => setAccountType("savings")}
                  className={`py-2.5 px-3 rounded-xl text-xs font-bold border transition-colors ${
                    accountType === "savings"
                      ? "bg-teal text-white border-teal shadow-xs"
                      : "bg-cream-surface text-ink-muted border-divider hover:bg-cream-deep"
                  }`}
                >
                  Savings Account
                </button>
                <button
                  type="button"
                  onClick={() => setAccountType("cheque")}
                  className={`py-2.5 px-3 rounded-xl text-xs font-bold border transition-colors ${
                    accountType === "cheque"
                      ? "bg-teal text-white border-teal shadow-xs"
                      : "bg-cream-surface text-ink-muted border-divider hover:bg-cream-deep"
                  }`}
                >
                  Cheque / Current
                </button>
              </div>
            </div>

            {/* SA ID / Passport */}
            <div className="space-y-1.5">
              <label className="text-xs font-bold uppercase tracking-wider text-ink block">
                SA National ID or Passport Number
              </label>
              <input
                type="text"
                value={idNumber}
                onChange={(e) => setIdNumber(e.target.value)}
                placeholder="13-digit SA ID Number"
                className="w-full p-3 bg-cream-surface rounded-xl border border-divider text-xs font-mono text-ink focus:outline-none focus:ring-2 focus:ring-teal/30"
              />
            </div>
          </div>

          {/* Submit Button */}
          <div className="pt-4 border-t border-divider flex items-center justify-end">
            <button
              type="submit"
              disabled={saving}
              className="px-8 py-3.5 bg-teal hover:bg-teal-hover text-white text-xs font-black rounded-2xl flex items-center gap-2 shadow-md transition-all hover:scale-[1.01]"
            >
              <ShieldCheck className="w-4 h-4" />
              <span>{saving ? "Verifying & Encrypting..." : "Save Payout Bank Details"}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
