"use client";

import Link from "next/link";
import { useState } from "react";
import { Download, Globe2, ArrowRight } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { api } from "@/lib/api";
import { countryName } from "@/lib/countries";
import { PageHeader } from "@/components/ui/PageHeader";
import { InlineError } from "@/components/ui/ErrorState";
import { NotificationSettingsCard } from "@/components/account/NotificationSettingsCard";
import { ChangePasswordCard } from "@/components/account/ChangePasswordCard";
import { CurrencySwitcher } from "@/components/public/CurrencySwitcher";

/** STU-12: account settings in one place. Name, country and time zone stay on the profile page (one form owns them). */
export default function StudentSettingsPage() {
  const { user } = useAuth();
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<unknown>(null);

  const downloadData = async () => {
    setExporting(true);
    setExportError(null);
    try {
      await api.downloadMyData();
    } catch (err) {
      setExportError(err);
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="min-h-screen bg-cream py-8 sm:py-12">
      <div className="mx-auto max-w-3xl space-y-6 px-4 sm:px-6 lg:px-8">
        <PageHeader backHref="/student/dashboard" backLabel="Back to dashboard" eyebrow="ACCOUNT" title="Settings" />

        <section aria-labelledby="region-title" className="rounded-3xl border border-divider bg-white p-5 shadow-card sm:p-7">
          <h2 id="region-title" className="font-serif text-xl font-black text-ink">
            Region and display
          </h2>
          <dl className="mt-4 grid gap-4 sm:grid-cols-2">
            <div>
              <dt className="text-xs font-bold uppercase tracking-wider text-ink-muted">Time zone</dt>
              <dd className="mt-1 flex items-center gap-2 text-sm font-bold text-ink">
                <Globe2 className="h-4 w-4 text-cocoa" aria-hidden="true" />
                {user?.timezone || "Not set"}
              </dd>
            </div>
            <div>
              <dt className="text-xs font-bold uppercase tracking-wider text-ink-muted">Country</dt>
              <dd className="mt-1 text-sm font-bold text-ink">{user?.country ? countryName(user.country) : "Not set"}</dd>
            </div>
          </dl>
          <p className="mt-3 text-sm text-ink-muted">Lesson times are shown in this time zone.</p>
          <Link
            href="/student/profile"
            className="min-h-11 mt-2 inline-flex items-center gap-1 text-sm font-bold text-cocoa hover:underline"
          >
            Change on your profile <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
          </Link>
          <div className="mt-4 border-t border-divider pt-4">
            <p className="mb-2 text-xs font-bold uppercase tracking-wider text-ink-muted">Show prices in</p>
            <div className="max-w-xs">
              <CurrencySwitcher variant="select" />
            </div>
          </div>
        </section>

        <NotificationSettingsCard role="student" />

        <ChangePasswordCard />

        <section aria-labelledby="data-title" className="rounded-3xl border border-divider bg-white p-5 shadow-card sm:p-7">
          <h2 id="data-title" className="font-serif text-xl font-black text-ink">
            Your data
          </h2>
          <p className="mt-1 text-sm text-ink-muted">
            Download a copy of the personal data we hold about you: your account, lessons, lesson credits, notifications and support messages, as a ZIP file.
            See the{" "}
            <Link href="/legal/privacy" className="font-bold text-cocoa hover:underline">
              privacy policy
            </Link>{" "}
            for your other rights.
          </p>
          <button
            type="button"
            onClick={downloadData}
            disabled={exporting}
            className="min-h-11 mt-4 inline-flex items-center gap-2 rounded-xl border border-divider bg-white px-5 text-sm font-bold text-ink shadow-xs hover:bg-cream-surface disabled:opacity-60"
          >
            <Download className="h-4 w-4 text-cocoa" aria-hidden="true" />
            {exporting ? "Preparing..." : "Download my data"}
          </button>
          <InlineError error={exportError} />
        </section>
      </div>
    </div>
  );
}
