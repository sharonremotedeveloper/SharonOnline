import React, { type ReactNode } from "react";
import { AlertTriangle, CheckCircle2, Info, XCircle } from "lucide-react";

export interface BadgeProps {
  children: ReactNode;
  variant?:
    | "accent"
    | "gold"
    | "success"
    | "error"
    | "info"
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
    info: "bg-info-surface text-info border-info-border",
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
    info: "bg-info",
    teal: "bg-cocoa",
    plum: "bg-plum",
    neutral: "bg-ink-muted",
  }[variant];

  // Status is never colour alone: success, warning, error and info each carry an icon beside the label.
  const StatusIcon = { success: CheckCircle2, gold: AlertTriangle, error: XCircle, info: Info }[variant as "success" | "gold" | "error" | "info"];

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full font-semibold tracking-wide border ${styles} ${sizeStyles} ${className}`}
    >
      {StatusIcon && <StatusIcon className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />}
      {dot && !StatusIcon && <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${dotColors}`} />}
      {children}
    </span>
  );
}
