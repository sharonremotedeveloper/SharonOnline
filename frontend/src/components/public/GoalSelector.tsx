"use client";

import { useState } from "react";
import Link from "next/link";
import { Briefcase, MessageSquare, GraduationCap, Presentation, Compass, ArrowRight, Check } from "lucide-react";

export interface GoalItem {
  id: string;
  label: string;
  icon: any;
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
    title: "Master Professional Workplace Communication",
    description:
      "Prepare for global remote work, email correspondence, cross-cultural negotiations, and executive presentations.",
    topics: ["Email Etiquette", "Salary Negotiation", "Meeting Moderation", "Client Pitching"],
    recommendedLevel: "B1 - C2 Intermediate to Advanced",
    sampleMaterialSlug: "business-email-etiquette",
  },
  {
    id: "interview",
    label: "Job Interviews",
    icon: GraduationCap,
    title: "Ace English Tech & Corporate Auditions",
    description:
      "Practice STAR method responses, self-introductions, weakness explanations, and salary expectation questions with real feedback.",
    topics: ["STAR Method", "Self Introduction", "Behavioral Questions", "Technical Q&A"],
    recommendedLevel: "B1 - C1 Upper Intermediate",
    sampleMaterialSlug: "job-interview-mastery",
  },
  {
    id: "conversation",
    label: "Daily Conversation",
    icon: MessageSquare,
    title: "Speak Effortlessly & Build Fluency",
    description:
      "Discuss daily news articles, culture, food, hobbies, and personal stories with supportive native English tutors.",
    topics: ["Daily News", "Idioms & Phrasal Verbs", "Culture & Society", "Small Talk"],
    recommendedLevel: "A1 - C2 All Levels",
    sampleMaterialSlug: "daily-news-discussion",
  },
  {
    id: "presentation",
    label: "Presentations & Speeches",
    icon: Presentation,
    title: "Deliver Impactful Slides & Keynotes",
    description:
      "Structure your arguments, smooth out pronunciation, slide transitions, and handle audience Q&A with total poise.",
    topics: ["Slide Delivery", "Q&A Handling", "Data Articulation", "Voice Modulation"],
    recommendedLevel: "B2 - C2 Advanced",
    sampleMaterialSlug: "presentation-skills-101",
  },
  {
    id: "travel",
    label: "Travel & Relocation",
    icon: Compass,
    title: "Navigate Airports, Hotels & Social Events",
    description:
      "Practical conversational English for solo travel, international relocations, visa interviews, and making international friends.",
    topics: ["Airport & Immigration", "Hotel & Dining", "Emergency Phrases", "Local Directions"],
    recommendedLevel: "A1 - B1 Beginner to Intermediate",
    sampleMaterialSlug: "travel-survival-guide",
  },
];

export function GoalSelector() {
  const [activeGoalId, setActiveGoalId] = useState<string>("work");
  const activeGoal = GOALS.find((g) => g.id === activeGoalId) || GOALS[0];
  const Icon = activeGoal.icon;

  return (
    <div className="bg-white rounded-2xl border border-divider shadow-card p-6 sm:p-8 space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-divider pb-6">
        <div>
          <h3 className="text-xl font-extrabold text-ink font-serif">What is your primary learning goal?</h3>
          <p className="text-sm text-ink-muted mt-1">
            Select your focus to see tailored lesson topics and recommended tutors.
          </p>
        </div>

        {/* Goal Tabs */}
        <div className="flex flex-wrap gap-2">
          {GOALS.map((goal) => {
            const GoalIcon = goal.icon;
            const isActive = goal.id === activeGoalId;
            return (
              <button
                key={goal.id}
                onClick={() => setActiveGoalId(goal.id)}
                className={`flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-bold transition-all ${
                  isActive
                    ? "bg-teal text-white shadow-sm"
                    : "bg-cream-surface text-ink-muted hover:bg-cream-deep hover:text-ink"
                }`}
              >
                <GoalIcon className="w-3.5 h-3.5" />
                <span>{goal.label}</span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Selected Goal Card */}
      <div className="bg-cream-surface rounded-xl p-6 border border-cream-deep grid grid-cols-1 lg:grid-cols-3 gap-6 items-center">
        <div className="lg:col-span-2 space-y-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-teal/10 text-teal flex items-center justify-center">
              <Icon className="w-5 h-5" />
            </div>
            <div>
              <span className="text-[11px] font-bold tracking-wider uppercase text-primary">
                {activeGoal.recommendedLevel}
              </span>
              <h4 className="text-lg font-bold text-ink">{activeGoal.title}</h4>
            </div>
          </div>

          <p className="text-sm text-ink-muted leading-relaxed">{activeGoal.description}</p>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-2">
            {activeGoal.topics.map((topic) => (
              <div key={topic} className="flex items-center gap-1.5 text-xs font-semibold text-ink">
                <Check className="w-3.5 h-3.5 text-success" />
                <span>{topic}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="bg-white p-5 rounded-xl border border-divider text-center space-y-3 shadow-card-sm">
          <div className="text-xs text-ink-muted font-medium">Ready to start this module?</div>
          <div className="text-sm font-bold text-ink">{activeGoal.label} Track</div>
          <Link
            href={`/tutors?specialty=${encodeURIComponent(activeGoal.label)}`}
            className="w-full inline-flex items-center justify-center gap-2 px-4 py-2.5 bg-primary hover:bg-primary-hover text-white text-xs font-bold rounded-xl transition-all shadow-sm"
          >
            Find Tutors for {activeGoal.label} <ArrowRight className="w-3.5 h-3.5" />
          </Link>
        </div>
      </div>
    </div>
  );
}
