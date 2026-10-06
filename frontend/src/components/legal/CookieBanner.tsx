"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Cookie, Shield, Check, X, Settings2 } from "lucide-react";

const CONSENT_STORAGE_KEY = "sharon_cookie_consent_v1";

interface ConsentState {
  version: "v1";
  timestamp: string;
  essential: true;
  analytics: boolean;
  marketing: boolean;
}

export function CookieBanner() {
  const [mounted, setMounted] = useState(false);
  const [showBanner, setShowBanner] = useState(false);
  const [showCustomize, setShowCustomize] = useState(false);
  const [analyticsConsent, setAnalyticsConsent] = useState(false);
  const [marketingConsent, setMarketingConsent] = useState(false);

  useEffect(() => {
    setMounted(true);
    try {
      const stored = localStorage.getItem(CONSENT_STORAGE_KEY);
      if (!stored) {
        setShowBanner(true);
      }
    } catch {
      // In private browsing mode or when localStorage is blocked, fail gracefully
      setShowBanner(false);
    }
  }, []);

  const saveConsent = (analytics: boolean, marketing: boolean) => {
    const consent: ConsentState = {
      version: "v1",
      timestamp: new Date().toISOString(),
      essential: true,
      analytics,
      marketing,
    };
    try {
      localStorage.setItem(CONSENT_STORAGE_KEY, JSON.stringify(consent));
    } catch (e) {
      console.warn("Could not persist cookie consent:", e);
    }
    setShowBanner(false);
    setShowCustomize(false);
  };

  const handleAcceptAll = () => {
    saveConsent(true, true);
  };

  const handleRejectNonEssential = () => {
    saveConsent(false, false);
  };

  const handleSaveCustom = () => {
    saveConsent(analyticsConsent, marketingConsent);
  };

  if (!mounted || !showBanner) {
    return null;
  }

  return (
    <div
      role="region"
      aria-label="Cookie consent and privacy options"
      className="fixed bottom-0 inset-x-0 z-50 p-4 sm:p-6 pointer-events-none print:hidden animate-in slide-in-from-bottom duration-300"
    >
      <div className="max-w-4xl mx-auto bg-white rounded-3xl p-6 sm:p-8 border border-divider shadow-2xl pointer-events-auto ring-1 ring-ink/5">
        {!showCustomize ? (
          /* Primary Summary View */
          <div className="space-y-6">
            <div className="flex items-start gap-4">
              <div className="p-2.5 rounded-2xl bg-teal/10 text-teal shrink-0">
                <Cookie className="w-6 h-6" />
              </div>
              <div className="space-y-1.5 flex-1">
                <h2 className="text-base sm:text-lg font-bold font-serif text-ink tracking-tight">
                  Your Privacy & Cookie Choices
                </h2>
                <p className="text-xs sm:text-sm text-ink-muted leading-relaxed">
                  We use essential cookies to maintain secure authenticated logins and high-quality classroom video streaming. With your permission, we also use performance analytics cookies to optimize latency and platform features. Learn more in our{" "}
                  <Link href="/legal/cookies" className="text-teal font-semibold underline hover:text-teal-deep">
                    Cookie Policy
                  </Link>{" "}
                  and{" "}
                  <Link href="/legal/privacy" className="text-teal font-semibold underline hover:text-teal-deep">
                    Privacy Policy
                  </Link>.
                </p>
              </div>
            </div>

            <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-end gap-3 pt-2 border-t border-divider">
              <button
                type="button"
                onClick={() => setShowCustomize(true)}
                className="px-4 py-2.5 rounded-xl border border-divider bg-cream-surface hover:bg-cream-deep text-xs font-bold text-ink transition-colors flex items-center justify-center gap-2 focus:ring-2 focus:ring-teal focus:outline-none"
              >
                <Settings2 className="w-3.5 h-3.5" />
                <span>Customize Preferences</span>
              </button>

              <button
                type="button"
                onClick={handleRejectNonEssential}
                className="px-4 py-2.5 rounded-xl border border-divider bg-white hover:bg-cream-surface text-xs font-bold text-ink transition-colors flex items-center justify-center gap-1.5 focus:ring-2 focus:ring-teal focus:outline-none"
              >
                <X className="w-3.5 h-3.5" />
                <span>Reject Non-Essential</span>
              </button>

              <button
                type="button"
                onClick={handleAcceptAll}
                className="px-6 py-2.5 rounded-xl bg-teal hover:bg-teal-hover text-white text-xs font-bold transition-all shadow-sm flex items-center justify-center gap-1.5 focus:ring-2 focus:ring-teal focus:outline-none"
              >
                <Check className="w-3.5 h-3.5" />
                <span>Accept All Cookies</span>
              </button>
            </div>
          </div>
        ) : (
          /* Granular Preferences View */
          <div className="space-y-6">
            <div className="flex items-center justify-between border-b border-divider pb-4">
              <div className="flex items-center gap-3">
                <div className="p-2 rounded-xl bg-teal/10 text-teal">
                  <Shield className="w-5 h-5" />
                </div>
                <div>
                  <h2 className="text-base font-bold font-serif text-ink">
                    Customize Cookie Preferences
                  </h2>
                  <p className="text-xs text-ink-muted">
                    Choose which categories of cookies you permit us to use.
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setShowCustomize(false)}
                className="p-1 rounded-lg text-ink-muted hover:text-ink transition-colors"
                aria-label="Back to summary"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="space-y-4 max-h-72 overflow-y-auto pr-1 text-xs">
              {/* Essential Tier */}
              <div className="p-4 rounded-2xl bg-cream-surface/70 border border-divider flex items-start justify-between gap-4">
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="font-bold text-ink text-sm">Strictly Necessary Cookies</span>
                    <span className="px-2 py-0.5 rounded-full bg-teal/10 text-teal text-[10px] font-bold">
                      Always Active
                    </span>
                  </div>
                  <p className="text-ink-muted leading-relaxed">
                    Required for basic site functionality, secure JWT session management, CSRF defense, and low-latency video classroom routing.
                  </p>
                </div>
                <input
                  type="checkbox"
                  checked={true}
                  disabled={true}
                  aria-label="Strictly necessary cookies always active"
                  className="mt-1 w-4 h-4 text-teal rounded border-divider cursor-not-allowed opacity-60"
                />
              </div>

              {/* Analytics Tier */}
              <div className="p-4 rounded-2xl bg-white border border-divider hover:border-accent/40 transition-all flex items-start justify-between gap-4">
                <div className="space-y-1">
                  <span className="font-bold text-ink text-sm">Performance & Analytics</span>
                  <p className="text-ink-muted leading-relaxed">
                    Collects anonymized platform diagnostics, classroom media connection stability, and page load telemetry to help us improve service quality.
                  </p>
                </div>
                <input
                  type="checkbox"
                  id="cookie-analytics-toggle"
                  checked={analyticsConsent}
                  onChange={(e) => setAnalyticsConsent(e.target.checked)}
                  aria-label="Allow performance and analytics cookies"
                  className="mt-1 w-4 h-4 text-teal rounded border-divider focus:ring-teal cursor-pointer"
                />
              </div>

              {/* Marketing Tier */}
              <div className="p-4 rounded-2xl bg-white border border-divider hover:border-accent/40 transition-all flex items-start justify-between gap-4">
                <div className="space-y-1">
                  <span className="font-bold text-ink text-sm">Personalization & Feature Updates</span>
                  <p className="text-ink-muted leading-relaxed">
                    Allows us to notify you about relevant new curriculum topics and teacher recommendations matching your learning goals.
                  </p>
                </div>
                <input
                  type="checkbox"
                  id="cookie-marketing-toggle"
                  checked={marketingConsent}
                  onChange={(e) => setMarketingConsent(e.target.checked)}
                  aria-label="Allow marketing and communication cookies"
                  className="mt-1 w-4 h-4 text-teal rounded border-divider focus:ring-teal cursor-pointer"
                />
              </div>
            </div>

            <div className="flex flex-col sm:flex-row items-center justify-between gap-3 pt-4 border-t border-divider">
              <button
                type="button"
                onClick={() => setShowCustomize(false)}
                className="text-xs text-ink-muted hover:text-ink font-semibold"
              >
                Cancel
              </button>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={handleRejectNonEssential}
                  className="px-4 py-2 rounded-xl border border-divider bg-white hover:bg-cream-surface text-xs font-bold text-ink transition-colors"
                >
                  Reject All Optional
                </button>
                <button
                  type="button"
                  onClick={handleSaveCustom}
                  className="px-6 py-2 rounded-xl bg-teal hover:bg-teal-hover text-white text-xs font-bold transition-all shadow-sm"
                >
                  Save My Preferences
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
