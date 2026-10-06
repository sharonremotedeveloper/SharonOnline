import React, { type ReactNode } from "react";

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  children: ReactNode;
  variant?: "primary" | "secondary" | "quiet" | "destructive" | "gold" | "teal";
  size?: "sm" | "md" | "lg";
  full?: boolean;
  icon?: ReactNode;
  isLoading?: boolean;
}

export function Button({
  children,
  variant = "primary",
  size = "md",
  full = false,
  icon,
  isLoading = false,
  className = "",
  disabled,
  ...props
}: ButtonProps) {
  const base =
    "inline-flex items-center justify-center gap-2 font-medium rounded-md transition-all tracking-[0.01em] focus-visible:outline-2 focus-visible:outline-offset-2 active:translate-y-px disabled:opacity-60 disabled:cursor-not-allowed disabled:active:translate-y-0";

  const sizes = {
    sm: "px-3.5 py-1.5 text-xs min-h-[36px]",
    md: "px-5 py-2.5 text-sm min-h-[44px]",
    lg: "px-7 py-3.5 text-base min-h-[52px]",
  };

  const variants = {
    primary:
      "bg-primary text-white border border-primary hover:bg-primary-hover hover:border-primary-hover focus-visible:outline-primary shadow-sm",
    secondary:
      "bg-white border border-[#D8B7A5] text-ink hover:bg-cream-surface hover:border-primary focus-visible:outline-primary",
    quiet:
      "bg-transparent text-ink-muted border border-divider hover:bg-cream-surface hover:text-ink focus-visible:outline-primary",
    destructive:
      "bg-error text-white border border-error hover:bg-[#952828] focus-visible:outline-error",
    gold:
      "bg-gold text-ink font-semibold border border-gold hover:bg-gold-hover focus-visible:outline-[#8A5B14]",
    teal:
      "bg-cocoa text-white border border-cocoa hover:bg-cocoa-hover focus-visible:outline-cocoa",
  };

  const widthClass = full ? "w-full" : "";

  return (
    <button
      className={`${base} ${sizes[size]} ${variants[variant]} ${widthClass} ${className}`}
      disabled={disabled || isLoading}
      {...props}
    >
      {isLoading ? (
        <svg
          className="animate-spin -ml-1 mr-2 h-4 w-4 text-current"
          xmlns="http://www.w3.org/2000/svg"
          fill="none"
          viewBox="0 0 24 24"
        >
          <circle
            className="opacity-25"
            cx="12"
            cy="12"
            r="10"
            stroke="currentColor"
            strokeWidth="4"
          ></circle>
          <path
            className="opacity-75"
            fill="currentColor"
            d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
          ></path>
        </svg>
      ) : icon ? (
        <span className="shrink-0">{icon}</span>
      ) : null}
      {children}
    </button>
  );
}
