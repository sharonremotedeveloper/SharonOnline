import Link from "next/link";
import { ArrowRight, CalendarClock, ShieldCheck, Ban } from "lucide-react";
import type { FeaturedTeacher } from "@/lib/api";
import { LessonPriceLabel } from "@/components/ui/LessonPriceLabel";
import { DemoVideoButton } from "./DemoVideoButton";
import { TutorPortrait } from "./TutorPortrait";

interface HeroSectionProps {
  tutors: FeaturedTeacher[];
}

// Set to a real video URL when one exists; until then the demo button is not shown.
const DEMO_VIDEO_URL = process.env.NEXT_PUBLIC_DEMO_VIDEO_URL || "";

export function HeroSection({ tutors }: HeroSectionProps) {
  const shown = tutors.slice(0, 3);

  return (
    <section className="relative overflow-hidden bg-cream text-ink">
      {/* Soft colour behind the content: warm, never heavy. Decorative only. */}
      <div aria-hidden="true" className="pointer-events-none absolute -right-32 -top-10 h-72 w-72 rounded-full bg-sun/30 blur-3xl sm:-right-24 sm:top-4 sm:h-[28rem] sm:w-[28rem] sm:bg-sun/50" />
      <div aria-hidden="true" className="pointer-events-none absolute -left-32 bottom-0 h-80 w-80 rounded-full bg-peach blur-3xl" />

      <div className="relative mx-auto grid max-w-7xl items-center gap-10 px-4 pb-16 pt-12 sm:px-6 sm:pt-16 lg:grid-cols-[1.05fr_0.95fr] lg:gap-14 lg:px-8 lg:pb-20 lg:pt-20">
        <div className="space-y-6">
          <p className="inline-flex items-center gap-2 rounded-full border border-divider bg-white px-4 py-1.5 text-sm font-semibold text-ink shadow-sm">
            <span className="h-2 w-2 rounded-full bg-coral" aria-hidden="true" />
            Private English lessons by video
          </p>

          <h1 className="font-serif text-5xl font-extrabold leading-[1.22] tracking-tight text-ink sm:text-6xl lg:text-7xl">
            Speak English with{" "}
            <span className="rounded-2xl bg-sun px-3 py-0.5 [box-decoration-break:clone] [-webkit-box-decoration-break:clone]">
              confidence.
            </span>
          </h1>

          <p className="max-w-xl text-lg leading-relaxed text-ink/80">
            1-on-1 lessons with friendly, certified South African tutors. Each lesson is 25 minutes. Choose a time in
            your own time zone.
          </p>

          <div className="flex flex-col gap-3 pt-1 sm:flex-row sm:items-center">
            <Link
              href="/tutors"
              className="inline-flex min-h-[56px] w-full items-center justify-center gap-2 rounded-full bg-cocoa px-9 text-lg font-bold text-white shadow-lg transition-colors hover:bg-cocoa-hover sm:w-auto"
            >
              Find your tutor <ArrowRight className="h-5 w-5 text-sun" aria-hidden="true" />
            </Link>
            {DEMO_VIDEO_URL ? (
              <DemoVideoButton src={DEMO_VIDEO_URL} />
            ) : (
              <Link
                href="/how-it-works"
                className="inline-flex min-h-[52px] items-center justify-center px-4 text-base font-semibold text-ink underline decoration-ink/30 underline-offset-4 hover:decoration-ink"
              >
                See how it works
              </Link>
            )}
          </div>

          <ul className="flex flex-wrap gap-x-6 gap-y-3 pt-3 text-base text-ink">
            <li className="flex items-center gap-2.5 whitespace-nowrap">
              <CalendarClock className="h-5 w-5 shrink-0 text-primary" aria-hidden="true" />
              <span>
                From <LessonPriceLabel className="font-bold" /> a lesson
              </span>
            </li>
            <li className="flex items-center gap-2.5 whitespace-nowrap">
              <ShieldCheck className="h-5 w-5 shrink-0 text-primary" aria-hidden="true" />
              <span>First lesson refundable</span>
            </li>
            <li className="flex items-center gap-2.5 whitespace-nowrap">
              <Ban className="h-5 w-5 shrink-0 text-primary" aria-hidden="true" />
              <span>No subscription</span>
            </li>
          </ul>
        </div>

        {/* People first: real tutors from the API, never invented ones. */}
        {shown.length > 0 ? (
          <div aria-label="Some of our tutors" className="grid grid-cols-3 gap-3 sm:gap-4">
            {shown.map((tutor, i) => (
              <Link
                key={tutor.id}
                href={`/tutors/${tutor.slug || tutor.id}`}
                className={`group relative block overflow-hidden rounded-3xl border-4 border-white bg-white shadow-xl ${
                  i === 1 ? "lg:-translate-y-6" : ""
                }`}
              >
                <TutorPortrait
                  src={tutor.avatar}
                  name={tutor.name}
                  className="aspect-[3/4] w-full"
                  sizes="(min-width: 1024px) 18vw, 30vw"
                  priority={i === 0}
                />
                <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/80 via-black/40 to-transparent p-2.5 pt-10 sm:p-3 sm:pt-12">
                  <div className="text-sm font-bold leading-tight text-white sm:text-base">{tutor.name.split(" ")[0]}</div>
                  <div className="hidden text-sm text-white/90 sm:block">South African tutor</div>
                </div>
              </Link>
            ))}
          </div>
        ) : (
          <div className="rounded-3xl border border-divider bg-white p-8 text-center shadow-card">
            <p className="font-serif text-2xl font-bold text-ink">Meet your tutor</p>
            <p className="mt-2 text-ink-muted">Browse our tutors and pick the one who suits you.</p>
            <Link href="/tutors" className="mt-5 inline-flex min-h-[48px] items-center rounded-full bg-cocoa px-6 font-bold text-white">
              See all tutors
            </Link>
          </div>
        )}
      </div>
    </section>
  );
}
