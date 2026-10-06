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
  size?: "sm" | "md" | "lg";
  dot?: boolean;
  className?: string;
}

export function Badge({
  children,
  variant = "neutral",
  size = "md",
  dot = false,
  className = "",
}: BadgeProps) {
  // Every pair is >= 4.5:1 (see the contrast ledger in tailwind.config.ts). Status is also carried by the label text, never colour alone.
  const styles = {
    accent: "bg-cream-surface text-primary border-peach",
    gold: "bg-warning-surface text-warning border-warning-border",
    success: "bg-success-surface text-success border-success-border",
    error: "bg-error-surface text-error border-error-border",
    teal: "bg-cocoa-surface text-cocoa border-cocoa-border",
    plum: "bg-plum-surface text-plum border-peach",
    neutral: "bg-cream-deep text-ink-muted border-divider",
  }[variant];

  const sizeStyles = {
    sm: "px-2 py-0.5 text-xs",
    md: "px-2.5 py-0.5 text-xs",
    lg: "px-3 py-1 text-xs font-bold",
  }[size];

  const dotColors = {
    accent: "bg-primary",
    gold: "bg-warning",
    success: "bg-success",
    error: "bg-error",
    teal: "bg-cocoa",
    plum: "bg-plum",
    neutral: "bg-ink-muted",
  }[variant];

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full font-semibold tracking-wide border ${styles} ${sizeStyles} ${className}`}
    >
      {dot && <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${dotColors}`} />}
      {children}
    </span>
  );
}
