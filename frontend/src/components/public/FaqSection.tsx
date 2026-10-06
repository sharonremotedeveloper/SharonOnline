import Link from "next/link";
import { ChevronDown } from "lucide-react";
import { SectionHeading } from "./SectionHeading";

// Plain English (about B1), written for readers who learn English as a second language.
export const FAQS = [
  {
    q: "Is my English good enough to start?",
    a: "Yes. We teach every level, from complete beginner (A1) to advanced (C2). Your tutor will adjust the lesson to you.",
  },
  {
    q: "What time will my lesson be?",
    a: "You see every time in your own time zone, for example Tokyo or Seoul time. You do not need to calculate anything.",
  },
  {
    q: "Do I need to install anything?",
    a: "No. Lessons run in your web browser on a computer, tablet or phone. You need a camera, a microphone and a stable internet connection.",
  },
  {
    q: "What if my first lesson is not right for me?",
    a: "If your first lesson does not meet your expectations, we will give the credit back to your wallet or refund you in full.",
  },
  {
    q: "Can I cancel or change a lesson?",
    a: "Yes. You can cancel or move a lesson before it starts. The refund and change rules are in our refund policy.",
  },
  {
    q: "Is it safe to pay?",
    a: "Yes. You pay through PayPal or PayFast. We never see or store your card number.",
  },
];

export function FaqSection() {
  return (
    <div className="space-y-8">
      <SectionHeading id="faq-heading" eyebrow="Questions" title="Frequently asked questions" />
      <div className="mx-auto max-w-3xl divide-y divide-divider overflow-hidden rounded-2xl border border-divider bg-white shadow-card">
        {FAQS.map((item) => (
          <details key={item.q} className="group">
            <summary className="flex min-h-[56px] cursor-pointer list-none items-center justify-between gap-4 px-5 py-4 text-left text-lg font-semibold text-ink hover:bg-cream-surface [&::-webkit-details-marker]:hidden">
              {item.q}
              <ChevronDown
                className="h-5 w-5 shrink-0 text-primary transition-transform group-open:rotate-180"
                aria-hidden="true"
              />
            </summary>
            <p className="px-5 pb-5 text-base leading-relaxed text-ink-muted">{item.a}</p>
          </details>
        ))}
      </div>
      <p className="text-center text-base text-ink-muted">
        More questions?{" "}
        <Link href="/support" className="inline-flex min-h-[44px] items-center font-bold text-teal underline underline-offset-4 hover:text-teal-hover">
          Visit our help centre
        </Link>
      </p>
    </div>
  );
}
