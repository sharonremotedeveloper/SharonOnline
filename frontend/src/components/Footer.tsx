import Link from "next/link";

export function Footer() {
  return (
    <footer className="bg-[#092B28] text-white/70 text-sm border-t border-white/10 mt-20">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12 grid grid-cols-1 md:grid-cols-4 gap-8">
        <div>
          <div className="flex items-center space-x-2 mb-3">
            <div className="w-7 h-7 rounded bg-gold-500 flex items-center justify-center font-bold text-brand-950 text-sm">
              S
            </div>
            <span className="font-bold text-lg tracking-tight text-white">
              Sharon<span className="text-gold-500">Online</span>
            </span>
          </div>
          <p className="text-xs text-white/60 leading-relaxed">
            Premium synchronous 25-minute English tutoring connecting certified South African tutors with ambitious learners across Japan, Korea, and Europe.
          </p>
        </div>

        <div>
          <h4 className="text-white font-semibold mb-3 text-xs tracking-wider uppercase">Platform</h4>
          <ul className="space-y-2 text-xs">
            <li><Link href="/tutors" className="hover:text-white transition-colors">Find a Tutor</Link></li>
            <li><Link href="/materials" className="hover:text-white transition-colors">Curriculum Library</Link></li>
            <li><Link href="/pricing" className="hover:text-white transition-colors">Pricing & Credit Packs</Link></li>
            <li><Link href="/student/dashboard" className="hover:text-white transition-colors">Student Dashboard</Link></li>
          </ul>
        </div>

        <div>
          <h4 className="text-white font-semibold mb-3 text-xs tracking-wider uppercase">For Teachers</h4>
          <ul className="space-y-2 text-xs">
            <li><Link href="/teacher/dashboard" className="hover:text-white transition-colors">Teacher Dashboard</Link></li>
            <li><Link href="/teacher/schedule" className="hover:text-white transition-colors">Schedule Manager</Link></li>
            <li><a href="mailto:sharon@sharonesl.com" className="hover:text-white transition-colors">Apply to Teach</a></li>
          </ul>
        </div>

        <div>
          <h4 className="text-white font-semibold mb-3 text-xs tracking-wider uppercase">Compliance & Trust</h4>
          <p className="text-xs text-white/60 mb-2">
            Compliant with POPIA (South Africa), GDPR (Europe), and APPI (Japan).
          </p>
          <div className="text-xs text-white/40">
            © 2026 Sharon Online. All rights reserved.
          </div>
        </div>
      </div>
    </footer>
  );
}
