"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ShieldCheck } from "lucide-react";
import { isCompactFooterArea } from "@/lib/appTabs";

const linkClass =
  "inline-flex min-h-[44px] items-center text-base text-white/80 transition-colors hover:text-gold-bright";

const compactLink = "inline-flex min-h-[44px] items-center px-1 text-sm text-white/85 hover:text-gold-bright";

/** One short row for signed-in areas and account pages on phones/tablets (the full footer was 2-3 screens tall there). */
function CompactFooter() {
  return (
    <footer className="on-dark border-t border-white/10 bg-cocoa-hover px-4 py-4 text-white/85 lg:hidden">
      <nav aria-label="Footer" className="flex flex-wrap items-center justify-center gap-x-3">
        <Link href="/support" className={compactLink}>Help</Link>
        <Link href="/legal/terms" className={compactLink}>Terms</Link>
        <Link href="/legal/privacy" className={compactLink}>Privacy</Link>
        <Link href="/legal/refunds" className={compactLink}>Refunds</Link>
      </nav>
      <p className="text-center text-xs text-white/75">© {new Date().getFullYear()} Sharon Online</p>
    </footer>
  );
}

export function Footer() {
  const compact = isCompactFooterArea(usePathname() || "/");
  return (
    <>
    {compact && <CompactFooter />}
    <footer className={`on-dark border-t border-white/10 bg-cocoa-hover text-white/80 ${compact ? "hidden lg:block" : ""}`}>
      {/* Phones: brand full width, link groups two per row (one column made this 2-3 screens tall). sm+ unchanged. */}
      <div className="mx-auto grid max-w-7xl grid-cols-2 gap-x-6 gap-y-8 px-4 py-10 sm:grid-cols-2 sm:gap-10 sm:px-6 sm:py-14 lg:grid-cols-5 lg:px-8">
        <div className="col-span-2 space-y-4 sm:col-span-1 lg:col-span-2">
          <div className="flex items-center gap-2">
            <span className="flex h-8 w-8 items-center justify-center rounded-xl bg-gold font-serif text-lg font-bold text-cocoa">S</span>
            <span className="font-serif text-xl font-extrabold tracking-tight text-white">
              Sharon<span className="text-gold-bright">Online</span>
            </span>
          </div>
          <p className="max-w-sm text-base leading-relaxed text-white/80">
            Private 25-minute English lessons by video. Certified South African tutors for learners in Asia and Europe.
          </p>
          <p className="flex max-w-sm items-start gap-2 text-sm leading-relaxed text-white/85">
            <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-gold-bright" aria-hidden="true" />
            <span>
              We protect your personal data and follow the privacy laws that apply to you, including GDPR (EU), APPI
              (Japan), PIPA (Korea) and POPIA (South Africa).{" "}
              <Link href="/legal/privacy" className="font-semibold text-white underline underline-offset-2 hover:text-gold-bright">
                Read how
              </Link>
            </span>
          </p>
        </div>

        <nav aria-labelledby="footer-platform">
          <h2 id="footer-platform" className="mb-2 font-serif text-lg font-bold text-white">Learn</h2>
          <ul>
            <li><Link href="/tutors" className={linkClass}>Find a tutor</Link></li>
            <li><Link href="/materials" className={linkClass}>Lessons &amp; levels</Link></li>
            <li><Link href="/pricing" className={linkClass}>Pricing</Link></li>
            <li><Link href="/how-it-works" className={linkClass}>How it works</Link></li>
          </ul>
        </nav>

        <nav aria-labelledby="footer-help">
          <h2 id="footer-help" className="mb-2 font-serif text-lg font-bold text-white">Help</h2>
          <ul>
            <li><Link href="/support" className={linkClass}>Help &amp; FAQ</Link></li>
            <li><Link href="/trust-safety" className={linkClass}>Trust &amp; safety</Link></li>
            <li><Link href="/teach" className={linkClass}>Teach with us</Link></li>
          </ul>
        </nav>

        <nav aria-labelledby="footer-legal">
          <h2 id="footer-legal" className="mb-2 font-serif text-lg font-bold text-white">Legal</h2>
          <ul>
            <li><Link href="/legal/terms" className={linkClass}>Terms of service</Link></li>
            <li><Link href="/legal/privacy" className={linkClass}>Privacy policy</Link></li>
            <li><Link href="/legal/refunds" className={linkClass}>Refund policy</Link></li>
            <li><Link href="/legal/child-safety" className={linkClass}>Child safety</Link></li>
            <li><Link href="/legal/cookies" className={linkClass}>Cookie policy</Link></li>
          </ul>
        </nav>
      </div>

      <div className="border-t border-white/10 px-4 py-6 text-center text-sm text-white/85">
        © {new Date().getFullYear()} Sharon Online. All rights reserved.
      </div>
    </footer>
    </>
  );
}
