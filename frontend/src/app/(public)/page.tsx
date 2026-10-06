import Link from "next/link";
import { ArrowRight, Clock, UserRound, BadgeCheck, Wallet } from "lucide-react";
import { HeroSection } from "@/components/public/HeroSection";
import { GoalSelector } from "@/components/public/GoalSelector";
import { HowItWorksSteps } from "@/components/public/HowItWorksSteps";
import { PowerGuardCallout } from "@/components/public/PowerGuardCallout";
import { PricingTable } from "@/components/public/PricingTable";
import { SectionHeading } from "@/components/public/SectionHeading";
import { FeaturedTutorCard } from "@/components/public/FeaturedTutorCard";
import { WhySouthAfrica } from "@/components/public/WhySouthAfrica";
import { VettingSteps } from "@/components/public/VettingSteps";
import { FaqSection, FAQS } from "@/components/public/FaqSection";
import { fetchFeaturedTutors } from "@/lib/api";
import { LessonPriceLabel } from "@/components/ui/LessonPriceLabel";

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL || "http://localhost:3000";

// Only facts that are true of the product. No rating or review count appears here unless it comes from real data.
const structuredData = [
  {
    "@context": "https://schema.org",
    "@type": "EducationalOrganization",
    name: "Sharon Online",
    url: SITE_URL,
    description: "Private 25-minute English lessons by video with certified South African tutors.",
  },
  {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: FAQS.map((f) => ({
      "@type": "Question",
      name: f.q,
      acceptedAnswer: { "@type": "Answer", text: f.a },
    })),
  },
];

const CEFR_LEVELS = [
  { level: "A1", name: "Beginner", desc: "Greetings and simple phrases" },
  { level: "A2", name: "Elementary", desc: "Everyday conversations" },
  { level: "B1", name: "Intermediate", desc: "Travel and work topics" },
  { level: "B2", name: "Upper intermediate", desc: "Debates and professional English" },
  { level: "C1", name: "Advanced", desc: "Fluent, natural discussion" },
  { level: "C2", name: "Mastery", desc: "Near-native detail and nuance" },
];

export default async function HomePage() {
  const featuredTutors = await fetchFeaturedTutors();

  return (
    <div className="pb-20">
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(structuredData) }} />

      <HeroSection tutors={featuredTutors} />

      {/* Facts about the lesson, not self-awarded numbers */}
      <section aria-label="Lesson basics" className="relative z-20 -mt-10 px-4 sm:px-6 lg:px-8">
        <ul className="mx-auto grid max-w-5xl grid-cols-2 gap-px overflow-hidden rounded-2xl border border-divider bg-divider shadow-card md:grid-cols-4">
          <li className="flex flex-col items-center gap-1 bg-white p-5 text-center sm:p-6">
            <Clock className="h-6 w-6 text-primary" aria-hidden="true" />
            <span className="font-serif text-2xl font-bold text-ink">25 minutes</span>
            <span className="text-sm text-ink-muted">A short lesson that fits your day</span>
          </li>
          <li className="flex flex-col items-center gap-1 bg-white p-5 text-center sm:p-6">
            <UserRound className="h-6 w-6 text-primary" aria-hidden="true" />
            <span className="font-serif text-2xl font-bold text-ink">1-on-1</span>
            <span className="text-sm text-ink-muted">Just you and your tutor</span>
          </li>
          <li className="flex flex-col items-center gap-1 bg-white p-5 text-center sm:p-6">
            <BadgeCheck className="h-6 w-6 text-primary" aria-hidden="true" />
            <span className="font-serif text-2xl font-bold text-ink">Checked tutors</span>
            <span className="text-sm text-ink-muted">Approved by our team first</span>
          </li>
          <li className="flex flex-col items-center gap-1 bg-white p-5 text-center sm:p-6">
            <Wallet className="h-6 w-6 text-primary" aria-hidden="true" />
            <LessonPriceLabel className="font-serif text-2xl font-bold text-ink" />
            <span className="text-sm text-ink-muted">Per lesson. Packs cost less.</span>
          </li>
        </ul>
      </section>

      {/* Tutors */}
      <section aria-labelledby="tutors-heading" className="mt-20 border-y border-divider bg-cream-surface px-4 py-16 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-[76rem] space-y-10">
          <div className="flex flex-col items-center justify-between gap-4 sm:flex-row sm:items-end">
            <SectionHeading
              id="tutors-heading"
              align="left"
              eyebrow="Meet our tutors"
              title="Learn with a tutor you like"
              description="Look at the photo, read about them, then book a time."
            />
            <Link
              href="/tutors"
              className="inline-flex min-h-[44px] shrink-0 items-center gap-2 text-base font-bold text-teal underline-offset-4 hover:underline"
            >
              See all tutors <ArrowRight className="h-4 w-4" aria-hidden="true" />
            </Link>
          </div>

          {featuredTutors.length === 0 ? (
            <div className="rounded-2xl border border-divider bg-white p-8 text-center">
              <p className="text-base text-ink-muted">We cannot show our tutors right now. Please try again in a moment.</p>
              <Link href="/tutors" className="mt-3 inline-flex min-h-[44px] items-center gap-2 text-base font-bold text-teal">
                Go to the tutor list <ArrowRight className="h-4 w-4" aria-hidden="true" />
              </Link>
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-6 md:grid-cols-3">
              {featuredTutors.map((tutor) => (
                <FeaturedTutorCard key={tutor.id} tutor={tutor} />
              ))}
            </div>
          )}
        </div>
      </section>

      {/* How it works */}
      <section aria-labelledby="how-heading" className="mx-auto mt-20 max-w-7xl space-y-10 px-4 sm:px-6 lg:px-8">
        <SectionHeading id="how-heading" eyebrow="Simple steps" title="How Sharon Online works" />
        <HowItWorksSteps />
      </section>

      {/* Why South Africa */}
      <section className="mx-auto mt-20 max-w-7xl space-y-8 px-4 sm:px-6 lg:px-8">
        <WhySouthAfrica />
        <PowerGuardCallout />
      </section>

      {/* Goals */}
      <section aria-labelledby="goals-heading" className="mx-auto mt-20 max-w-7xl space-y-10 px-4 sm:px-6 lg:px-8">
        <SectionHeading
          id="goals-heading"
          eyebrow="Your goal"
          title="Lessons for what you need English for"
          description="Choose a goal to see the topics we can practise together."
        />
        <GoalSelector />
      </section>

      {/* Vetting */}
      <section className="mt-20 bg-white px-4 py-16 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-[76rem]">
          <VettingSteps />
        </div>
      </section>

      {/* Pricing */}
      <section aria-labelledby="pricing-heading" className="mx-auto mt-20 max-w-7xl space-y-10 px-4 sm:px-6 lg:px-8">
        <SectionHeading
          id="pricing-heading"
          eyebrow="Pricing"
          title="Simple prices. No subscription."
          description="Buy one lesson or a pack. Bigger packs cost less per lesson."
        />
        <PricingTable />
      </section>

      {/* Levels */}
      <section aria-labelledby="levels-heading" className="mt-20 border-y border-divider bg-cream-surface px-4 py-16 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-[76rem] space-y-10">
          <SectionHeading
            id="levels-heading"
            eyebrow="All levels"
            title="From first words to fluent speech"
            description="Our lessons follow CEFR, the standard scale for language levels."
          />
          <ul className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
            {CEFR_LEVELS.map((c) => (
              <li key={c.level} className="rounded-2xl border border-divider bg-white p-4 text-center shadow-card">
                <div className="font-serif text-3xl font-bold text-teal">{c.level}</div>
                <div className="mt-1 text-base font-bold text-ink">{c.name}</div>
                <div className="mt-1 text-sm leading-snug text-ink-muted">{c.desc}</div>
              </li>
            ))}
          </ul>
          <div className="text-center">
            <Link
              href="/materials"
              className="inline-flex min-h-[44px] items-center gap-2 text-base font-bold text-teal underline-offset-4 hover:underline"
            >
              See our lesson materials <ArrowRight className="h-4 w-4" aria-hidden="true" />
            </Link>
          </div>
        </div>
      </section>

      {/* FAQ */}
      <section aria-labelledby="faq-heading" className="mx-auto mt-20 max-w-7xl px-4 sm:px-6 lg:px-8">
        <FaqSection />
      </section>

      {/* Closing call to action */}
      <section className="on-dark mx-auto mt-20 max-w-5xl px-4 sm:px-6 lg:px-8">
        <div className="rounded-3xl bg-gradient-to-br from-teal to-teal-hover px-6 py-12 text-center text-white shadow-card sm:px-12">
          <h2 className="font-serif text-3xl font-bold sm:text-4xl">Ready to start speaking?</h2>
          <p className="mx-auto mt-3 max-w-xl text-lg text-white/90">
            Book your first lesson. If it is not right for you, we give your credit back or refund you.
          </p>
          <Link
            href="/tutors"
            className="mt-7 inline-flex min-h-[52px] items-center justify-center gap-2 rounded-xl bg-primary px-8 text-base font-bold text-white shadow-lg transition-colors hover:bg-primary-hover"
          >
            Find your tutor <ArrowRight className="h-5 w-5" aria-hidden="true" />
          </Link>
        </div>
      </section>
    </div>
  );
}
