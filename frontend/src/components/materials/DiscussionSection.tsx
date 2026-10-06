import { MessageSquare, Lightbulb } from "lucide-react";

interface DiscussionSectionProps {
  questions: string[];
}

export function DiscussionSection({ questions }: DiscussionSectionProps) {
  if (!questions || questions.length === 0) return null;

  return (
    <div className="bg-white rounded-3xl p-6 sm:p-8 border border-divider shadow-card space-y-6">
      <div className="flex items-center gap-3 border-b border-divider pb-4">
        <div className="w-10 h-10 rounded-2xl bg-cocoa/10 text-cocoa flex items-center justify-center font-bold">
          <MessageSquare className="w-5 h-5" />
        </div>
        <div>
          <h3 className="text-xl font-extrabold text-ink font-serif">
            Discussion & Debate Questions
          </h3>
          <p className="text-sm text-ink-muted">
            Practice sharing your opinion, clarifying nuances, and debating with your tutor
          </p>
        </div>
      </div>

      <div className="space-y-4">
        {questions.map((q, idx) => (
          <div
            key={idx}
            className="p-5 rounded-2xl bg-cream-surface border border-cream-deep space-y-2 hover:border-cocoa transition-colors"
          >
            <div className="flex items-start gap-3">
              <span className="w-6 h-6 rounded-full bg-cocoa text-white flex items-center justify-center text-sm font-bold shrink-0 mt-0.5">
                {idx + 1}
              </span>
              <p className="text-sm font-bold text-ink leading-relaxed">{q}</p>
            </div>
          </div>
        ))}
      </div>

      <div className="p-4 rounded-2xl bg-cream-surface/60 border border-divider flex items-center gap-2.5 text-sm text-ink-muted">
        <Lightbulb className="w-4 h-4 text-gold-bright shrink-0" />
        <span>
          <strong>Tutor Tip:</strong> Aim to speak in full sentences using target vocabulary from the lesson rather than one-word responses.
        </span>
      </div>
    </div>
  );
}
