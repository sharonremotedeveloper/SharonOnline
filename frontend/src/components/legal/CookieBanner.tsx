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
      className="fixed bottom-0 inset-x-0 z-40 p-2 sm:p-4 pointer-events-none print:hidden animate-in slide-in-from-bottom duration-300"
    >
      <div className="max-w-5xl mx-auto bg-white rounded-2xl p-4 sm:p-5 border border-divider shadow-2xl pointer-events-auto ring-1 ring-ink/5">
        {!showCustomize ? (
          /* Slim bar: a few lines on a phone so the menu and the page stay reachable */
          <div className="flex flex-col lg:flex-row lg:items-center gap-3 lg:gap-6">
            <p className="flex-1 text-sm text-ink-muted leading-snug">
              <Cookie className="mr-1.5 -mt-0.5 inline h-4 w-4 text-teal" aria-hidden="true" />
              We use essential cookies to keep you signed in and lessons running. Optional analytics cookies help us improve the site, and only run if you say yes.{" "}
              <Link href="/legal/cookies" className="text-teal font-semibold underline underline-offset-2 hover:text-teal-hover">
                Cookie policy
              </Link>
            </p>

            <div className="grid grid-cols-2 sm:flex sm:items-center gap-2 shrink-0">
              <button
                type="button"
                onClick={handleRejectNonEssential}
                className="col-span-1 min-h-[44px] px-4 rounded-xl border border-ink/20 bg-white hover:bg-cream-surface text-sm font-bold text-ink transition-colors focus-visible:ring-2 focus-visible:ring-teal focus:outline-none"
              >
                Reject optional
              </button>
              <button
                type="button"
                onClick={handleAcceptAll}
                className="col-span-1 min-h-[44px] px-4 rounded-xl bg-teal hover:bg-teal-hover text-white text-sm font-bold transition-colors shadow-sm focus-visible:ring-2 focus-visible:ring-teal focus:outline-none"
              >
                Accept all
              </button>
              <button
                type="button"
                onClick={() => setShowCustomize(true)}
                className="col-span-2 sm:col-span-1 min-h-[44px] px-3 rounded-xl text-sm font-semibold text-teal underline underline-offset-2 hover:text-teal-hover flex items-center justify-center gap-1.5 focus-visible:ring-2 focus-visible:ring-teal focus:outline-none"
              >
                <Settings2 className="w-4 h-4" aria-hidden="true" />
                <span>Choose</span>
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

            <div className="space-y-4 max-h-[45vh] overflow-y-auto pr-1 text-sm">
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
