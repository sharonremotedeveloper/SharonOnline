import React, { forwardRef } from "react";

export interface InputProps
  extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  helperText?: string;
  icon?: React.ReactNode;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ label, error, helperText, icon, className = "", id, ...props }, ref) => {
    const inputId = id || (label ? label.toLowerCase().replace(/\s+/g, "-") : undefined);

    return (
      <div className="w-full">
        {label && (
          <label
            htmlFor={inputId}
            className="mb-1.5 block text-sm font-semibold text-ink"
          >
            {label}
          </label>
        )}
        <div className="relative">
          {icon && (
            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-ink-muted">
              {icon}
            </div>
          )}
          <input
            ref={ref}
            id={inputId}
            className={`min-h-[48px] w-full rounded-xl border bg-white px-4 py-3 text-base text-ink placeholder:text-ink-faint transition-colors focus:bg-white focus:outline-none focus:ring-2 ${
              icon ? "pl-10" : ""
            } ${
              error
                ? "border-error focus:border-error focus:ring-error"
                : "border-[#D8B7A5] focus:border-primary focus:ring-primary"
            } disabled:bg-cream-deep disabled:text-ink-muted disabled:cursor-not-allowed ${className}`}
            {...props}
          />
        </div>
        {error ? (
          <p className="mt-1 text-sm text-error font-medium">{error}</p>
        ) : helperText ? (
          <p className="mt-1 text-sm text-ink-muted">{helperText}</p>
        ) : null}
      </div>
    );
  }
);

Input.displayName = "Input";
