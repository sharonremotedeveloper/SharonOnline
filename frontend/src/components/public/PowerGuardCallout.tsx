import Link from "next/link";
import { BatteryCharging, ArrowRight } from "lucide-react";

/**
 * A single calm reassurance line. It used to be a full-width "100% uninterrupted, guaranteed" banner: that overclaimed
 * and made overseas students think about power cuts. The detail now lives on /trust-safety.
 */
export function PowerGuardCallout() {
  return (
    <aside className="flex flex-col gap-4 rounded-3xl focus-cocoa bg-sky p-5 sm:flex-row sm:items-center sm:p-6">
      <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-cocoa text-sun">
        <BatteryCharging className="h-6 w-6" aria-hidden="true" />
      </span>
      <div className="flex-1">
        <h3 className="font-serif text-lg font-bold text-ink">Your lesson is protected if the power goes out</h3>
        <p className="mt-1 text-base leading-relaxed text-ink/80">
          Our tutors use backup power for their internet. If a lesson is still cut off, you get a new lesson or your
          money back.
        </p>
      </div>
      <Link
        href="/trust-safety"
        className="inline-flex min-h-[44px] shrink-0 items-center gap-1.5 text-base font-bold text-cocoa underline-offset-4 hover:underline"
      >
        How we protect lessons <ArrowRight className="h-4 w-4" aria-hidden="true" />
      </Link>
    </aside>
  );
}
