import Link from "next/link";
import { Check, ArrowRight, ShieldCheck, Zap } from "lucide-react";

export default function PricingPage() {
  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12 space-y-16">
      {/* Header */}
      <div className="text-center max-w-3xl mx-auto space-y-3">
        <h1 className="text-4xl font-extrabold text-gray-900 tracking-tight">
          Transparent, Flexible Pricing
        </h1>
        <p className="text-base text-gray-600">
          No mandatory monthly recurring subscriptions. Pay per lesson or save with lesson credit packs.
        </p>
      </div>

      {/* Pricing Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-8 max-w-5xl mx-auto">
        {/* Single Lesson */}
        <div className="bg-white rounded-2xl border border-gray-200 p-8 shadow-card flex flex-col justify-between space-y-6">
          <div className="space-y-4">
            <h3 className="font-extrabold text-lg text-gray-900">Single Lesson</h3>
            <p className="text-xs text-gray-500">Perfect for trying out a new tutor or occasional practice.</p>
            <div className="flex items-baseline gap-1">
              <span className="text-4xl font-black text-gray-900">$9.00</span>
              <span className="text-xs text-gray-500 font-semibold">USD / class</span>
            </div>
            <div className="text-[11px] text-gray-400">~¥1,380 JPY · ~R160 ZAR</div>

            <ul className="space-y-3 pt-4 border-t border-gray-100 text-xs text-gray-600">
              <li className="flex items-center gap-2">
                <Check className="w-4 h-4 text-emerald-600 flex-shrink-0" /> 1x 25-minute synchronous 1-on-1 lesson
              </li>
              <li className="flex items-center gap-2">
                <Check className="w-4 h-4 text-emerald-600 flex-shrink-0" /> Dedicated Zoom classroom room link
              </li>
              <li className="flex items-center gap-2">
                <Check className="w-4 h-4 text-emerald-600 flex-shrink-0" /> Full post-lesson memo & vocabulary cards
              </li>
              <li className="flex items-center gap-2">
                <Check className="w-4 h-4 text-emerald-600 flex-shrink-0" /> PayFast (ZAR) & PayPal (USD/EUR/JPY)
              </li>
            </ul>
          </div>

          <Link
            href="/tutors"
            className="w-full py-3 bg-gray-100 hover:bg-gray-200 text-gray-900 font-bold rounded-xl text-xs text-center transition-all"
          >
            Find a Tutor
          </Link>
        </div>

        {/* 5-Lesson Pack */}
        <div className="bg-white rounded-2xl border-2 border-brand-800 p-8 shadow-card-hover flex flex-col justify-between space-y-6 relative">
          <div className="absolute -top-3.5 left-1/2 -translate-x-1/2 bg-brand-900 text-gold-500 text-[11px] font-extrabold px-3 py-1 rounded-full uppercase tracking-wider shadow-sm">
            Most Popular
          </div>

          <div className="space-y-4">
            <h3 className="font-extrabold text-lg text-gray-900">5-Lesson Bundle</h3>
            <p className="text-xs text-gray-500">Ideal for consistent weekly speaking improvement.</p>
            <div className="flex items-baseline gap-1">
              <span className="text-4xl font-black text-brand-900">$42.00</span>
              <span className="text-xs text-gray-500 font-semibold">USD</span>
            </div>
            <div className="text-[11px] text-emerald-600 font-bold">$8.40 / lesson (Save 7%) · ~R750 ZAR</div>

            <ul className="space-y-3 pt-4 border-t border-gray-100 text-xs text-gray-600">
              <li className="flex items-center gap-2 font-medium text-gray-900">
                <Check className="w-4 h-4 text-emerald-600 flex-shrink-0" /> 5x 25-minute lesson credits
              </li>
              <li className="flex items-center gap-2">
                <Check className="w-4 h-4 text-emerald-600 flex-shrink-0" /> Valid across any verified tutor
              </li>
              <li className="flex items-center gap-2">
                <Check className="w-4 h-4 text-emerald-600 flex-shrink-0" /> 6-month validity window
              </li>
              <li className="flex items-center gap-2">
                <Check className="w-4 h-4 text-emerald-600 flex-shrink-0" /> 1-click booking without re-entering cards
              </li>
            </ul>
          </div>

          <Link
            href="/tutors"
            className="w-full py-3 bg-brand-900 hover:bg-brand-950 text-white font-bold rounded-xl text-xs text-center transition-all shadow-md flex items-center justify-center gap-2"
          >
            Get 5-Lesson Pack <ArrowRight className="w-3.5 h-3.5" />
          </Link>
        </div>

        {/* 10-Lesson Pack */}
        <div className="bg-white rounded-2xl border border-gray-200 p-8 shadow-card flex flex-col justify-between space-y-6">
          <div className="space-y-4">
            <h3 className="font-extrabold text-lg text-gray-900">10-Lesson Bundle</h3>
            <p className="text-xs text-gray-500">Maximum savings for dedicated language learners.</p>
            <div className="flex items-baseline gap-1">
              <span className="text-4xl font-black text-gray-900">$79.00</span>
              <span className="text-xs text-gray-500 font-semibold">USD</span>
            </div>
            <div className="text-[11px] text-emerald-600 font-bold">$7.90 / lesson (Save 12%) · ~R1,400 ZAR</div>

            <ul className="space-y-3 pt-4 border-t border-gray-100 text-xs text-gray-600">
              <li className="flex items-center gap-2 font-medium text-gray-900">
                <Check className="w-4 h-4 text-emerald-600 flex-shrink-0" /> 10x 25-minute lesson credits
              </li>
              <li className="flex items-center gap-2">
                <Check className="w-4 h-4 text-emerald-600 flex-shrink-0" /> Valid across all tutors & specialties
              </li>
              <li className="flex items-center gap-2">
                <Check className="w-4 h-4 text-emerald-600 flex-shrink-0" /> 12-month validity window
              </li>
              <li className="flex items-center gap-2">
                <Check className="w-4 h-4 text-emerald-600 flex-shrink-0" /> Lowest per-lesson processing fee
              </li>
            </ul>
          </div>

          <Link
            href="/tutors"
            className="w-full py-3 bg-gray-100 hover:bg-gray-200 text-gray-900 font-bold rounded-xl text-xs text-center transition-all"
          >
            Get 10-Lesson Pack
          </Link>
        </div>
      </div>
    </div>
  );
}
