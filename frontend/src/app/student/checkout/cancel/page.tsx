import Link from "next/link";
import { ArrowRight } from "lucide-react";

/** PayFast sends the buyer here when they abandon the hosted payment page. Nothing is marked or changed here. */
export default function PayFastCancelPage() {
  return (
    <div className="max-w-xl mx-auto px-4 py-16 text-center space-y-4">
      <h1 className="text-xl font-extrabold text-ink font-serif">Payment cancelled</h1>
      <p className="text-xs text-ink-muted leading-relaxed">
        You left the payment page, so nothing was charged. If you were booking a lesson, your time slot stays held for a
        short while; you can pick it up again from your dashboard, or choose a new time with your tutor.
      </p>
      <div className="flex flex-col sm:flex-row gap-3 justify-center pt-2">
        <Link href="/student/dashboard" className="inline-flex items-center justify-center gap-2 px-5 py-2.5 bg-cocoa text-white rounded-xl text-xs font-bold">
          Back to my dashboard <ArrowRight className="w-3.5 h-3.5" />
        </Link>
        <Link href="/tutors" className="inline-flex items-center justify-center gap-2 px-5 py-2.5 border border-divider rounded-xl text-xs font-bold text-ink">
          Find a tutor
        </Link>
      </div>
    </div>
  );
}
