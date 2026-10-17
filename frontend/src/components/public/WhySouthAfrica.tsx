import { Clock, HeartHandshake, Globe2 } from "lucide-react";
import { SectionHeading } from "./SectionHeading";

const REASONS = [
  {
    tone: "bg-sky-soft",
    icon: Clock,
    title: "Time zones that work for you",
    text: "South Africa is 0 to 1 hour from Europe. It is 7 hours behind Japan and Korea, so a tutor's afternoon is your evening.",
  },
  {
    tone: "bg-peach-soft",
    icon: HeartHandshake,
    title: "Friendly and patient",
    text: "Our tutors are used to teaching learners from other countries. They speak clearly and give you time to answer.",
  },
  {
    tone: "bg-sun-soft",
    icon: Globe2,
    title: "Certified teachers",
    text: "Tutors hold a TEFL or similar teaching certificate, and we check it before they can take lessons.",
  },
];

export function WhySouthAfrica() {
  return (
    <div className="space-y-6 sm:space-y-8">
      <SectionHeading
        eyebrow="Why Sharon Online"
        title="Why learn with South African tutors?"
        description="English is spoken here every day, and the time difference suits learners in Asia and Europe."
      />
      <ul className="grid gap-3 sm:gap-5 md:grid-cols-3">
        {REASONS.map(({ icon: Icon, title, text, tone }) => (
          <li key={title} className={`flex gap-4 rounded-3xl p-4 sm:block sm:p-6 ${tone}`}>
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-cocoa text-sun sm:h-12 sm:w-12">
              <Icon className="h-6 w-6" aria-hidden="true" />
            </span>
            <div className="sm:mt-4"><h3 className="font-serif text-xl font-bold text-ink">{title}</h3>
            <p className="mt-2 text-base leading-relaxed text-ink/80">{text}</p></div>
          </li>
        ))}
      </ul>
    </div>
  );
}
