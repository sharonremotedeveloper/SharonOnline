import Link from "next/link";
import { ArrowRight, CheckCircle2, Star, Shield, Clock, Award, Users } from "lucide-react";
import { HeroSection } from "@/components/public/HeroSection";
import { GoalSelector } from "@/components/public/GoalSelector";
import { HowItWorksSteps } from "@/components/public/HowItWorksSteps";
import { PowerGuardCallout } from "@/components/public/PowerGuardCallout";
import { PricingTable } from "@/components/public/PricingTable";
import { fetchFeaturedTutors } from "@/lib/api";
import { Avatar } from "@/components/ui/Avatar";
import { StarRating } from "@/components/ui/StarRating";
import { Badge } from "@/components/ui/Badge";
import { LessonPriceLabel } from "@/components/ui/LessonPriceLabel";

export default async function HomePage() {
  const featuredTutors = await fetchFeaturedTutors();

  return (
    <div className="space-y-16 pb-16">
      {/* Hero Section */}
      <HeroSection />

      {/* Stats Ribbon */}
      <section className="max-w-7xl mx-auto px-4 -mt-12 relative z-20">
        <div className="bg-white rounded-2xl shadow-card border border-divider p-6 sm:p-8 grid grid-cols-2 md:grid-cols-4 gap-6 text-center">
          <div>
            <div className="text-3xl font-extrabold text-teal font-serif">4.98 ★</div>
            <div className="text-xs text-ink-muted font-medium mt-1">Average Student Rating</div>
          </div>
          <div>
            <div className="text-3xl font-extrabold text-teal font-serif">25 Min</div>
            <div className="text-xs text-ink-muted font-medium mt-1">High-Focus Synchronous Slots</div>
          </div>
          <div>
            <div className="text-3xl font-extrabold text-teal font-serif">100%</div>
            <div className="text-xs text-ink-muted font-medium mt-1">Vetted South African Tutors</div>
          </div>
          <div>
            <LessonPriceLabel className="block text-3xl font-extrabold text-teal font-serif" />
            <div className="text-xs text-ink-muted font-medium mt-1">Price / 25-Min Lesson</div>
          </div>
        </div>
      </section>

      {/* Goal Selector Section */}
      <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 space-y-4">
        <div className="text-center max-w-2xl mx-auto">
          <h2 className="text-xs font-bold uppercase tracking-wider text-primary">Personalized Learning</h2>
          <p className="text-3xl font-extrabold text-ink font-serif mt-1">Tailored for Your Exact Goals</p>
        </div>
        <GoalSelector />
      </section>

      {/* Featured Vetted Tutors Carousel / Grid */}
      <section className="bg-cream-surface py-16 px-4 sm:px-6 lg:px-8 border-y border-divider">
        <div className="max-w-7xl mx-auto space-y-8">
          <div className="flex flex-col sm:flex-row items-center justify-between gap-4">
            <div>
              <h2 className="text-xs font-bold uppercase tracking-wider text-primary">Certified Educators</h2>
              <p className="text-3xl font-extrabold text-ink font-serif mt-1">Featured Native & South African Tutors</p>
            </div>
            <Link
              href="/tutors"
              className="inline-flex items-center gap-2 text-xs font-bold text-teal hover:text-teal-hover"
            >
              Browse All Tutors <ArrowRight className="w-4 h-4" />
            </Link>
          </div>

          {featuredTutors.length === 0 ? (
            <div className="bg-white rounded-2xl p-8 border border-divider text-center space-y-2">
              <p className="text-sm text-ink-muted">
                Our tutor profiles aren&apos;t available to show right now.
              </p>
              <Link href="/tutors" className="inline-flex items-center gap-2 text-xs font-bold text-teal hover:text-teal-hover">
                Browse tutors <ArrowRight className="w-4 h-4" />
              </Link>
            </div>
          ) : (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {featuredTutors.map((tutor) => (
              <div
                key={tutor.id}
                className="bg-white rounded-2xl p-6 border border-divider shadow-card hover:shadow-card-hover transition-all flex flex-col justify-between space-y-4"
              >
                <div className="space-y-4">
                  <div className="flex items-start gap-4">
                    <Avatar src={tutor.avatar} name={tutor.name} alt={tutor.name} size="lg" />
                    <div>
                      <h3 className="text-lg font-bold text-ink font-serif">{tutor.name}</h3>
                      {tutor.accent && <div className="text-xs text-ink-muted font-medium">{tutor.accent}</div>}
                      {tutor.review_count > 0 && tutor.rating > 0 && (
                        <div className="flex items-center gap-1.5 mt-1">
                          <StarRating rating={tutor.rating} size="sm" />
                          <span className="text-xs font-bold text-ink">({tutor.review_count})</span>
                        </div>
                      )}
                    </div>
                  </div>

                  {tutor.bio && <p className="text-xs text-ink-muted leading-relaxed line-clamp-3">{tutor.bio}</p>}

                  <div className="flex flex-wrap gap-1.5">
                    {(tutor.specialties || []).map((spec) => (
                      <Badge key={spec} variant="neutral" size="sm">
                        {spec}
                      </Badge>
                    ))}
                  </div>
                </div>

                <div className="pt-4 border-t border-divider flex items-center justify-between">
                  <div>
                    <span className="text-xs text-ink-muted">Rate: </span>
                    <LessonPriceLabel className="text-base font-extrabold text-ink font-serif" />
                    <span className="text-[10px] text-ink-muted"> / 25m</span>
                  </div>

                  <Link
                    href={`/tutors/${tutor.slug || tutor.id}`}
                    className="px-4 py-2 bg-teal hover:bg-teal-hover text-white text-xs font-bold rounded-xl shadow-sm transition-all"
                  >
                    View Profile
                  </Link>
                </div>
              </div>
            ))}
          </div>
          )}
        </div>
      </section>

      {/* How It Works */}
      <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 space-y-8">
        <div className="text-center max-w-2xl mx-auto">
          <h2 className="text-xs font-bold uppercase tracking-wider text-primary">Frictionless Experience</h2>
          <p className="text-3xl font-extrabold text-ink font-serif mt-1">How Sharon Online Works</p>
        </div>
        <HowItWorksSteps />
      </section>

      {/* Eskom Power Guard Resilience Callout */}
      <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <PowerGuardCallout />
      </section>

      {/* Pricing & Lesson Bundles */}
      <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 space-y-8">
        <div className="text-center max-w-2xl mx-auto">
          <h2 className="text-xs font-bold uppercase tracking-wider text-primary">Flexible Credit Bundles</h2>
          <p className="text-3xl font-extrabold text-ink font-serif mt-1">Invest in Your English Fluency</p>
        </div>
        <PricingTable />
      </section>

      {/* CEFR Curriculum Preview */}
      <section className="bg-cream-surface py-16 px-4 sm:px-6 lg:px-8 border-t border-divider">
        <div className="max-w-7xl mx-auto space-y-8">
          <div className="text-center max-w-2xl mx-auto">
            <h2 className="text-xs font-bold uppercase tracking-wider text-primary">Structured Learning</h2>
            <p className="text-3xl font-extrabold text-ink font-serif mt-1">Aligned with CEFR Framework</p>
            <p className="text-xs text-ink-muted mt-2">From A1 Beginner to C2 Proficient conversation</p>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4">
            {[
              { level: "A1", name: "Beginner", desc: "Basic greetings & daily phrases" },
              { level: "A2", name: "Elementary", desc: "Simple everyday conversations" },
              { level: "B1", name: "Intermediate", desc: "Travel & work opinions" },
              { level: "B2", name: "Upper-Int", desc: "Debates & professional English" },
              { level: "C1", name: "Advanced", desc: "Fluent idiomatic discussions" },
              { level: "C2", name: "Mastery", desc: "Native nuance & technical speech" },
            ].map((c) => (
              <div key={c.level} className="bg-white rounded-2xl p-4 border border-divider shadow-card text-center space-y-1">
                <div className="text-2xl font-black text-teal font-serif">{c.level}</div>
                <div className="text-xs font-bold text-ink">{c.name}</div>
                <div className="text-[11px] text-ink-muted leading-snug">{c.desc}</div>
              </div>
            ))}
          </div>

          <div className="text-center pt-4">
            <Link
              href="/materials"
              className="inline-flex items-center gap-2 text-xs font-bold text-teal hover:text-teal-hover"
            >
              Explore all curriculum lesson sheets & downloadable PDFs <ArrowRight className="w-4 h-4" />
            </Link>
          </div>
        </div>
      </section>
    </div>
  );
}
