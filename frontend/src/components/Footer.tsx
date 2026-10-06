import Link from "next/link";
import { ShieldCheck, Heart } from "lucide-react";

export function Footer() {
  return (
    <footer className="bg-teal-hover text-white/80 text-xs border-t border-white/10">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12 grid grid-cols-1 md:grid-cols-5 gap-8">
        <div className="md:col-span-2 space-y-4">
          <div className="flex items-center space-x-2">
            <div className="w-8 h-8 rounded-xl bg-gold flex items-center justify-center font-bold text-teal text-lg font-serif">
              S
            </div>
            <span className="font-extrabold text-xl tracking-tight text-white font-serif">
              Sharon<span className="text-gold-bright">Online</span>
            </span>
          </div>
          <p className="text-xs text-white/70 leading-relaxed max-w-sm">
            Premium 1-on-1 synchronous 25-minute English learning marketplace connecting vetted South African tutors with ambitious students in East Asia and Europe.
          </p>
          <div className="flex items-center gap-2 text-[11px] text-accent-surface">
            <ShieldCheck className="w-4 h-4 text-accent" />
            <span>POPIA (South Africa), GDPR (EU), and APPI (Japan) Certified</span>
          </div>
        </div>

        <div>
          <h4 className="text-white font-bold mb-3 text-xs tracking-wider uppercase font-serif">Platform</h4>
          <ul className="space-y-2 text-xs text-white/70">
            <li><Link href="/tutors" className="hover:text-gold-bright transition-colors">Find a Tutor</Link></li>
            <li><Link href="/materials" className="hover:text-gold-bright transition-colors">Curriculum Catalog</Link></li>
            <li><Link href="/pricing" className="hover:text-gold-bright transition-colors">Pricing & Credit Packs</Link></li>
            <li><Link href="/how-it-works" className="hover:text-gold-bright transition-colors">How It Works</Link></li>
          </ul>
        </div>

        <div>
          <h4 className="text-white font-bold mb-3 text-xs tracking-wider uppercase font-serif">Safety & Careers</h4>
          <ul className="space-y-2 text-xs text-white/70">
            <li><Link href="/trust-safety" className="hover:text-gold-bright transition-colors">Trust & Safety</Link></li>
            <li><Link href="/trust-safety" className="hover:text-gold-bright transition-colors">Eskom Power Guard</Link></li>
            <li><Link href="/teach" className="hover:text-gold-bright transition-colors">Teach With Us (SA)</Link></li>
            <li><Link href="/support" className="hover:text-gold-bright transition-colors">Support & FAQs</Link></li>
          </ul>
        </div>

        <div>
          <h4 className="text-white font-bold mb-3 text-xs tracking-wider uppercase font-serif">Legal & Governance</h4>
          <ul className="space-y-2 text-xs text-white/70">
            <li><Link href="/legal/terms" className="hover:text-gold-bright transition-colors">Terms of Service</Link></li>
            <li><Link href="/legal/privacy" className="hover:text-gold-bright transition-colors">Privacy & POPIA</Link></li>
            <li><Link href="/legal/refunds" className="hover:text-gold-bright transition-colors">Refund & Escrow Policy</Link></li>
            <li><Link href="/legal/child-safety" className="hover:text-gold-bright transition-colors">Child Safeguarding</Link></li>
            <li><Link href="/legal/cookies" className="hover:text-gold-bright transition-colors">Cookie Policy</Link></li>
          </ul>
        </div>
      </div>

      <div className="border-t border-white/10 py-6 px-4 text-center text-[11px] text-white/50 flex flex-col sm:flex-row items-center justify-between max-w-7xl mx-auto">
        <div>© 2026 Sharon Online Marketplace Ltd. All rights reserved.</div>
        <div className="flex items-center gap-1 mt-2 sm:mt-0">
          Crafted with <Heart className="w-3 h-3 text-primary fill-primary inline" /> for Global Fluency
        </div>
      </div>
    </footer>
  );
}
