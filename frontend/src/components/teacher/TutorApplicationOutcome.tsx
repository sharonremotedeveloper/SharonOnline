"use client";

import Link from "next/link";
import { AlertTriangle, CheckCircle2, Clock3 } from "lucide-react";
import { useEffect, useRef } from "react";

import type { TutorApplicationOutcome as Outcome } from "@/lib/tutorApplication";

export function TutorApplicationOutcome({ outcome }: { outcome: Outcome }) {
  const headingRef = useRef<HTMLHeadingElement>(null);
  const isReviewing = outcome.status === "submitted" || outcome.status === "in_review";
  const isPositive = !["rejected", "suspended"].includes(outcome.status);

  useEffect(() => {
    headingRef.current?.focus();
  }, [outcome.status]);

  return <main className="min-h-screen bg-cream px-5 py-10 text-ink"><div className="mx-auto max-w-3xl">
    <section aria-labelledby="application-outcome-title" className={`rounded-3xl border bg-white p-7 text-center shadow-card sm:p-10 ${isPositive ? "border-success/30" : "border-warning-border"}`}>
      <div className={`mx-auto flex h-16 w-16 items-center justify-center rounded-full ${isPositive ? "bg-success-surface text-success-hover" : "bg-warning-surface text-warning-hover"}`}>
        {isPositive ? <CheckCircle2 className="h-9 w-9" aria-hidden="true" /> : <AlertTriangle className="h-9 w-9" aria-hidden="true" />}
      </div>
      <p className="mt-6 text-sm font-semibold uppercase tracking-[.18em] text-ink-muted">Tutor application</p>
      <h1 ref={headingRef} id="application-outcome-title" tabIndex={-1} className="mt-3 font-['Lora'] text-4xl font-medium focus:outline-none">{outcome.title}</h1>
      <p className="mx-auto mt-4 max-w-xl text-base leading-7 text-ink-muted">{outcome.summary}</p>
      {outcome.submittedAt && <p className="mt-4 inline-flex items-center gap-2 text-sm text-ink-muted"><Clock3 className="h-4 w-4" aria-hidden="true" />Submitted <time dateTime={outcome.submittedAt}>{new Date(outcome.submittedAt).toLocaleString()}</time></p>}

      {isReviewing && <div className="mx-auto mt-8 max-w-xl rounded-2xl bg-cream-deep p-6 text-left">
        <h2 className="text-xl font-semibold">What happens next</h2>
        <ol className="mt-4 space-y-4 text-sm leading-6 text-ink-muted">
          <li><strong className="text-ink">1. Review:</strong> Our team checks your profile, documents, audio and introduction video.</li>
          <li><strong className="text-ink">2. Decision:</strong> You will receive an email and an in-app notification when your application is approved or if changes are needed.</li>
          <li><strong className="text-ink">3. Onboarding:</strong> Once approved, you can continue to tutor training and availability setup.</li>
        </ol>
      </div>}

      <div className="mt-8 flex flex-col justify-center gap-3 sm:flex-row">
        {outcome.status === "approved" && <Link href="/teacher/dashboard" className="min-h-11 inline-flex items-center justify-center rounded-xl bg-cocoa px-5 py-3 font-semibold text-white">Open tutor dashboard</Link>}
        <Link href="/" className="min-h-11 inline-flex items-center justify-center rounded-xl border border-strong px-5 py-3 font-semibold">Return to home</Link>
        <Link href="/support" className="min-h-11 inline-flex items-center justify-center rounded-xl border border-strong px-5 py-3 font-semibold">Contact support</Link>
      </div>
    </section>
  </div></main>;
}
