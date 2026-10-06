import { FileCheck2, ClipboardCheck, GraduationCap, Star } from "lucide-react";
import { SectionHeading } from "./SectionHeading";

const STEPS = [
  { icon: FileCheck2, title: "We check ID and certificates", text: "Every tutor sends proof of identity and their teaching certificate." },
  { icon: ClipboardCheck, title: "Our team reviews them", text: "Staff score each applicant on a written checklist before anyone is approved." },
  { icon: GraduationCap, title: "They finish our training", text: "Tutors complete our training before they can take student bookings." },
  { icon: Star, title: "You help keep standards high", text: "After each lesson you can leave a private review for our team." },
];

export function VettingSteps() {
  return (
    <div className="space-y-8">
      <SectionHeading
        eyebrow="Safe and trusted"
        title="How we choose our tutors"
        description="Not everyone who applies can teach on Sharon Online. Here is what every tutor goes through."
      />
      <ol className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
        {STEPS.map(({ icon: Icon, title, text }, i) => (
          <li key={title} className="flex gap-4 rounded-2xl border border-divider bg-white p-5 shadow-card lg:block">
            <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-teal text-gold-bright">
              <Icon className="h-6 w-6" aria-hidden="true" />
            </span>
            <div className="lg:mt-4">
              <h3 className="font-serif text-lg font-bold text-ink">
                <span className="sr-only">Step {i + 1}: </span>
                {title}
              </h3>
              <p className="mt-1 text-base leading-relaxed text-ink-muted">{text}</p>
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}
