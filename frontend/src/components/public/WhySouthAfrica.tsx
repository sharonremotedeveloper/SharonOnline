import { Clock, HeartHandshake, Globe2 } from "lucide-react";
import { SectionHeading } from "./SectionHeading";

const REASONS = [
  {
    icon: Clock,
    title: "Time zones that work for you",
    text: "South Africa is 0 to 1 hour from Europe. It is 7 hours behind Japan and Korea, so a tutor's afternoon is your evening.",
  },
  {
    icon: HeartHandshake,
    title: "Friendly and patient",
    text: "Our tutors are used to teaching learners from other countries. They speak clearly and give you time to answer.",
  },
  {
    icon: Globe2,
    title: "Certified teachers",
    text: "Tutors hold a TEFL or similar teaching certificate, and we check it before they can take lessons.",
  },
];

export function WhySouthAfrica() {
  return (
    <div className="space-y-8">
      <SectionHeading
        eyebrow="Why Sharon Online"
        title="Why learn with South African tutors?"
        description="English is spoken here every day, and the time difference suits learners in Asia and Europe."
      />
      <ul className="grid gap-5 md:grid-cols-3">
        {REASONS.map(({ icon: Icon, title, text }) => (
          <li key={title} className="rounded-2xl border border-divider bg-white p-6 shadow-card">
            <span className="flex h-12 w-12 items-center justify-center rounded-xl bg-gold-surface text-primary">
              <Icon className="h-6 w-6" aria-hidden="true" />
            </span>
            <h3 className="mt-4 font-serif text-xl font-bold text-ink">{title}</h3>
            <p className="mt-2 text-base leading-relaxed text-ink-muted">{text}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}
