"use client";

import { Newspaper, Briefcase, MessageSquare, GraduationCap, Sparkles } from "lucide-react";

interface MaterialCategoryTabsProps {
  selectedCategory: string;
  onSelectCategory: (cat: string) => void;
}

export const MATERIAL_CATEGORIES = [
  { value: "", label: "All Curriculum", icon: Sparkles },
  { value: "daily_news", label: "Daily News & Discussion", icon: Newspaper },
  { value: "business", label: "Business & Workplace", icon: Briefcase },
  { value: "freetalk", label: "FreeTalk Prompts", icon: MessageSquare },
  { value: "test_prep", label: "Job Interview & Test Prep", icon: GraduationCap },
];

export function MaterialCategoryTabs({
  selectedCategory,
  onSelectCategory,
}: MaterialCategoryTabsProps) {
  return (
    <div className="flex flex-wrap gap-2">
      {MATERIAL_CATEGORIES.map((cat) => {
        const Icon = cat.icon;
        const isActive = selectedCategory === cat.value;

        return (
          <button
            key={cat.value}
            onClick={() => onSelectCategory(cat.value)}
            className={`flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-bold transition-all ${
              isActive
                ? "bg-teal text-white shadow-sm"
                : "bg-cream-surface text-ink-muted hover:bg-cream-deep hover:text-ink border border-divider"
            }`}
          >
            <Icon className="w-3.5 h-3.5" />
            <span>{cat.label}</span>
          </button>
        );
      })}
    </div>
  );
}
