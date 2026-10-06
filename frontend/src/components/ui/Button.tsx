import React, { type ReactNode } from "react";

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  children: ReactNode;
  variant?: "primary" | "secondary" | "danger" | "accent";
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
    "inline-flex items-center justify-center gap-2 font-bold rounded-full transition-all tracking-[0.01em] focus-visible:outline-2 focus-visible:outline-offset-2 active:translate-y-px disabled:opacity-60 disabled:cursor-not-allowed disabled:active:translate-y-0";

  const sizes = {
    sm: "px-4 py-1.5 text-sm min-h-[44px]",
    md: "px-6 py-2.5 text-base min-h-[48px]",
    lg: "px-7 py-3.5 text-base min-h-[52px]",
  };

  // Four solid/outline styles only. Contrast: white on cocoa 12.6, ink on sun 11.28, white on error 5.93 (hover 8.34),
  // secondary border is border-strong (4.69 on white). Hover always changes fill or border, never only the cursor.
  const variants = {
    primary:
      "bg-cocoa text-white border border-cocoa hover:bg-cocoa-hover hover:border-cocoa-hover focus-visible:outline-primary shadow-sm",
    secondary:
      "bg-white border border-strong text-ink hover:bg-cream-deep hover:border-cocoa focus-visible:outline-primary",
    danger:
      "bg-error text-white border border-error hover:bg-error-hover hover:border-error-hover focus-visible:outline-error",
    accent:
      "bg-accent text-ink border border-accent hover:bg-accent-500 hover:border-accent-500 focus-visible:outline-cocoa",
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
