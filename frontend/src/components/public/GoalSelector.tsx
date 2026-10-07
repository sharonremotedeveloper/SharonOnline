"use client";

import { useState, type ComponentType } from "react";
import Link from "next/link";
import { Briefcase, MessageSquare, GraduationCap, Presentation, Compass, ArrowRight, Check } from "lucide-react";

export interface GoalItem {
  id: string;
  label: string;
  icon: ComponentType<{ className?: string; "aria-hidden"?: boolean }>;
  title: string;
  description: string;
  topics: string[];
  recommendedLevel: string;
  sampleMaterialSlug: string;
}

const GOALS: GoalItem[] = [
  {
    id: "work",
    label: "Business & Work",
    icon: Briefcase,
    title: "Speak with confidence at work",
    description: "Prepare for emails, meetings, calls with other countries and presentations to your team.",
    topics: ["Email etiquette", "Salary talks", "Running meetings", "Client calls"],
    recommendedLevel: "Levels B1 to C2",
    sampleMaterialSlug: "business-email-etiquette",
  },
  {
    id: "interview",
    label: "Job Interviews",
    icon: GraduationCap,
    title: "Get ready for English interviews",
    description: "Practise introducing yourself and answering common questions, and get honest feedback.",
    topics: ["STAR method", "Self-introduction", "Tough questions", "Technical Q&A"],
    recommendedLevel: "Levels B1 to C1",
    sampleMaterialSlug: "job-interview-mastery",
  },
  {
    id: "conversation",
    label: "Daily Conversation",
    icon: MessageSquare,
    title: "Talk naturally about everyday life",
    description: "Chat about the news, food, hobbies and culture with a patient tutor who listens.",
    topics: ["Daily news", "Idioms", "Culture", "Small talk"],
    recommendedLevel: "All levels",
    sampleMaterialSlug: "daily-news-discussion",
  },
  {
    id: "presentation",
    label: "Presentations",
    icon: Presentation,
    title: "Present clearly and calmly",
    description: "Organise your ideas, improve your pronunciation and practise answering questions.",
    topics: ["Slide delivery", "Q&A practice", "Explaining data", "Clear voice"],
    recommendedLevel: "Levels B2 to C2",
    sampleMaterialSlug: "presentation-skills-101",
  },
  {
    id: "travel",
    label: "Travel & Moving",
    icon: Compass,
    title: "Handle travel and life abroad",
    description: "Learn the English you need for airports, hotels, visas and meeting new people.",
    topics: ["Airports", "Hotels & food", "Emergencies", "Directions"],
    recommendedLevel: "Levels A1 to B1",
    sampleMaterialSlug: "travel-survival-guide",
  },
];

export function GoalSelector() {
  const [activeGoalId, setActiveGoalId] = useState<string>("work");
  const activeGoal = GOALS.find((g) => g.id === activeGoalId) || GOALS[0];
  const Icon = activeGoal.icon;

  return (
    <div className="focus-cocoa overflow-hidden rounded-[2rem] bg-coral p-3 sm:p-5">
      {/* Goal tabs: a 2/3/5 column grid, so no lone pill wraps onto its own line */}
      <div
        role="tablist"
        aria-label="Choose your learning goal"
        className="grid grid-cols-2 gap-2 pb-4 sm:grid-cols-3 lg:grid-cols-5"
      >
        {GOALS.map((goal) => {
          const GoalIcon = goal.icon;
          const isActive = goal.id === activeGoalId;
          return (
            <button
              key={goal.id}
              type="button"
              role="tab"
              id={`goal-tab-${goal.id}`}
              aria-selected={isActive}
              aria-controls="goal-panel"
              tabIndex={isActive ? 0 : -1}
              onClick={() => setActiveGoalId(goal.id)}
              onKeyDown={(e) => {
                const i = GOALS.findIndex((g) => g.id === goal.id);
                const next =
                  e.key === "ArrowRight" ? GOALS[(i + 1) % GOALS.length]
                  : e.key === "ArrowLeft" ? GOALS[(i - 1 + GOALS.length) % GOALS.length]
                  : null;
                if (next) {
                  e.preventDefault();
                  setActiveGoalId(next.id);
                  document.getElementById(`goal-tab-${next.id}`)?.focus();
                }
              }}
              className={`flex min-h-[56px] items-center justify-center gap-2 rounded-full px-3 py-2 text-center text-base font-bold transition-colors ${
                isActive ? "bg-cocoa text-white shadow-sm" : "bg-white/90 text-ink hover:bg-white"
              } ${goal.id === "travel" ? "col-span-2 sm:col-span-1" : ""}`}
            >
              <GoalIcon className="h-5 w-5 shrink-0" aria-hidden={true} />
              <span>{goal.label}</span>
            </button>
          );
        })}
      </div>

      {/* Panel */}
      <div
        role="tabpanel"
        id="goal-panel"
        aria-labelledby={`goal-tab-${activeGoal.id}`}
        className="grid items-center gap-8 rounded-3xl bg-white p-6 sm:p-8 lg:grid-cols-[1fr_auto]"
      >
        <div className="space-y-4">
          <div className="flex items-center gap-3">
            <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-sun text-cocoa">
              <Icon className="h-6 w-6" aria-hidden={true} />
            </span>
            <div>
              <p className="text-sm font-bold uppercase tracking-wider text-primary">{activeGoal.recommendedLevel}</p>
              <h3 className="font-serif text-2xl font-bold text-ink">{activeGoal.title}</h3>
            </div>
          </div>
          <p className="max-w-2xl text-base leading-relaxed text-ink-muted">{activeGoal.description}</p>
          <ul className="grid grid-cols-2 gap-x-6 gap-y-2 sm:grid-cols-4">
            {activeGoal.topics.map((topic) => (
              <li key={topic} className="flex items-center gap-2 text-base font-medium text-ink">
                <Check className="h-4 w-4 shrink-0 text-success" aria-hidden={true} />
                <span>{topic}</span>
              </li>
            ))}
          </ul>
        </div>

        <Link
          href={`/tutors?specialty=${encodeURIComponent(activeGoal.label)}`}
          className="inline-flex min-h-[52px] items-center justify-center gap-2 rounded-full bg-cocoa px-7 text-base font-bold text-white shadow-sm transition-colors hover:bg-cocoa-hover"
        >
          Find tutors for this goal <ArrowRight className="h-5 w-5" aria-hidden={true} />
        </Link>
      </div>
    </div>
  );
}
