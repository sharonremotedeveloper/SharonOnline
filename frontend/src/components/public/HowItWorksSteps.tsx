import { Search, Calendar, Video, FileText } from "lucide-react";

export function HowItWorksSteps() {
  const steps = [
    {
      number: "01",
      icon: Search,
      title: "Discover Your Tutor",
      description:
        "Filter South African & native tutors by accent, specialty, and 60-second video introductions.",
    },
    {
      number: "02",
      icon: Calendar,
      title: "Lock Your 25-Min Slot",
      description:
        "Choose open slots automatically projected into your Tokyo, Seoul, or European timezone.",
    },
    {
      number: "03",
      icon: Video,
      title: "1-Click Zoom Classroom",
      description:
        "Enter private 1-on-1 Zoom classroom directly from your dashboard with zero setup hassle.",
    },
    {
      number: "04",
      icon: FileText,
      title: "Receive Lesson Memo",
      description:
        "Review personalized grammar corrections, vocabulary cards, and homework saved in your archive.",
    },
  ];

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
      {steps.map((step, idx) => {
        const Icon = step.icon;
        return (
          <div
            key={step.number}
            className="relative bg-white p-6 rounded-2xl border border-divider shadow-card space-y-4 hover:shadow-card-hover transition-all"
          >
            <div className="flex items-center justify-between">
              <div className="w-10 h-10 rounded-xl bg-teal/10 text-teal flex items-center justify-center font-bold">
                <Icon className="w-5 h-5" />
              </div>
              <span className="text-2xl font-black text-divider font-serif">{step.number}</span>
            </div>

            <div>
              <h4 className="text-base font-bold text-ink font-serif">{step.title}</h4>
              <p className="text-xs text-ink-muted mt-2 leading-relaxed">{step.description}</p>
            </div>

            {idx < steps.length - 1 && (
              <div className="hidden lg:block absolute -right-3 top-1/2 -translate-y-1/2 w-6 h-6 rounded-full bg-cream-deep border border-divider text-ink-muted flex items-center justify-center text-[10px] z-10">
                ➔
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
