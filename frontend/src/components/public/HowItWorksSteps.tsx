import { Search, Calendar, Video, FileText } from "lucide-react";

const STEPS = [
  {
    tone: "bg-peach",
    icon: Search,
    title: "Choose a tutor",
    description: "Look at tutor photos and topics. Pick the person you want to learn with.",
  },
  {
    tone: "bg-sun-soft",
    icon: Calendar,
    title: "Pick a time",
    description: "Every time shown is in your own time zone, such as Tokyo, Seoul or Europe.",
  },
  {
    tone: "bg-sky",
    icon: Video,
    title: "Join your lesson",
    description: "Open the lesson from your dashboard. It runs in your browser, with nothing to install.",
  },
  {
    tone: "bg-coral-soft",
    icon: FileText,
    title: "Get your notes",
    description: "After the lesson your tutor sends a short note with corrections and new words.",
  },
];

export function HowItWorksSteps() {
  return (
    <ol className="grid grid-cols-1 gap-3 sm:grid-cols-2 sm:gap-5 lg:grid-cols-4">
      {STEPS.map((step, idx) => {
        const Icon = step.icon;
        return (
          <li
            key={step.title}
            className={`relative rounded-3xl p-4 sm:p-6 ${step.tone}`}
          >
            <div className="flex items-center justify-between">
              <span className="flex h-10 w-10 items-center justify-center rounded-full bg-cocoa text-sun sm:h-12 sm:w-12">
                <Icon className="h-6 w-6" aria-hidden="true" />
              </span>
              {/* Step numbers use the brand colour, not the pale divider tone (it was 1.46:1 against white). */}
              <span className="font-serif text-3xl font-extrabold text-cocoa sm:text-4xl" aria-hidden="true">
                {idx + 1}
              </span>
            </div>
            <h3 className="mt-3 font-serif text-xl font-bold text-ink sm:mt-4">
              <span className="sr-only">Step {idx + 1}: </span>
              {step.title}
            </h3>
            <p className="mt-2 text-base leading-relaxed text-ink/80">{step.description}</p>
          </li>
        );
      })}
    </ol>
  );
}
