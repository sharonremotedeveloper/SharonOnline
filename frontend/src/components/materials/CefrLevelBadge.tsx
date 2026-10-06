import React from "react";
import { CEFRLevel } from "@/types/material";

interface CefrLevelBadgeProps {
  level: CEFRLevel | string;
  size?: "sm" | "md" | "lg";
  className?: string;
}

export function CefrLevelBadge({ level, size = "md", className = "" }: CefrLevelBadgeProps) {
  const norm = level.toUpperCase();

  const colorStyles = {
    A1: "bg-emerald-50 text-emerald-800 border-emerald-200",
    A2: "bg-emerald-50 text-emerald-800 border-emerald-200",
    B1: "bg-cocoa/10 text-cocoa border-cocoa/20",
    B2: "bg-cocoa/15 text-cocoa border-cocoa/30",
    C1: "bg-plum/10 text-plum border-plum/20",
    C2: "bg-amber-50 text-amber-900 border-amber-300",
  }[norm] || "bg-cream-surface text-ink-muted border-divider";

  const sizeStyles = {
    sm: "px-2 py-0.5 text-sm",
    md: "px-2.5 py-1 text-sm",
    lg: "px-3.5 py-1.5 text-sm font-black",
  }[size];

  const labels = {
    A1: "A1 Beginner",
    A2: "A2 Elementary",
    B1: "B1 Intermediate",
    B2: "B2 Upper-Int",
    C1: "C1 Advanced",
    C2: "C2 Proficient",
  }[norm] || norm;

  return (
    <span
      className={`inline-flex items-center font-bold rounded-full border shadow-sm ${colorStyles} ${sizeStyles} ${className}`}
    >
      {size === "sm" ? norm : labels}
    </span>
  );
}
