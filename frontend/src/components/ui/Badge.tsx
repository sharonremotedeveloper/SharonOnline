import React, { type ReactNode } from "react";

export interface BadgeProps {
  children: ReactNode;
  variant?:
    | "accent"
    | "gold"
    | "success"
    | "error"
    | "teal"
    | "plum"
    | "neutral";
  dot?: boolean;
  className?: string;
}

export function Badge({
  children,
  variant = "neutral",
  dot = false,
  className = "",
}: BadgeProps) {
  const styles = {
    accent: "bg-cream-surface text-primary border-[#E8C2B3]",
    gold: "bg-gold-surface text-[#8A5B14] border-[#F2DCA8]",
    success: "bg-success-surface text-success border-[#C3D7C8]",
    error: "bg-error-surface text-error border-[#F2C2BA]",
    teal: "bg-teal-surface text-teal border-teal-border",
    plum: "bg-plum-surface text-plum border-[#E6D4E5]",
    neutral: "bg-[#F3EBE4] text-ink-muted border-[#E4D3C6]",
  }[variant];

  const dotColors = {
    accent: "bg-primary",
    gold: "bg-gold",
    success: "bg-success",
    error: "bg-error",
    teal: "bg-teal",
    plum: "bg-plum",
    neutral: "bg-ink-muted",
  }[variant];

  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold tracking-wide border ${styles} ${className}`}
    >
      {dot && <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${dotColors}`} />}
      {children}
    </span>
  );
}
