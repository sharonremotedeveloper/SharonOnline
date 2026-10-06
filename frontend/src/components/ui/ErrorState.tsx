import React from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";
import { errorMessage } from "@/lib/http";

interface ErrorStateProps {
  /** Any thrown value (ApiError, Error, string) or a ready-made message. */
  error: unknown;
  /** Heading shown above the message. */
  title?: string;
  onRetry?: () => void;
  className?: string;
}

/** Full-block error panel for a section/page whose data failed to load. Never shows fabricated content. */
export function ErrorState({ error, title = "We couldn't load this", onRetry, className = "" }: ErrorStateProps) {
  const message = typeof error === "string" ? error : errorMessage(error);
  return (
    <div
      role="alert"
      className={`bg-white border border-error/30 rounded-2xl p-8 text-center space-y-3 max-w-xl mx-auto ${className}`}
    >
      <AlertTriangle className="w-8 h-8 text-error mx-auto" aria-hidden="true" />
      <h2 className="text-base font-bold text-ink font-serif">{title}</h2>
      <p className="text-sm text-ink-muted">{message}</p>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="min-h-11 inline-flex items-center gap-2 px-4 py-2 rounded-full bg-cocoa text-white text-sm font-bold hover:bg-cocoa-hover transition-colors"
        >
          <RefreshCw className="w-3.5 h-3.5" aria-hidden="true" /> Try again
        </button>
      )}
    </div>
  );
}

/** Small inline banner for a failed action (save, submit...). Render only when `error` is set. */
export function InlineError({ error, className = "" }: { error: unknown; className?: string }) {
  if (!error) return null;
  const message = typeof error === "string" ? error : errorMessage(error);
  return (
    <div
      role="alert"
      className={`flex items-start gap-2 bg-error/5 border border-error/30 text-error rounded-xl px-3 py-2 text-xs font-medium ${className}`}
    >
      <AlertTriangle className="w-4 h-4 shrink-0 mt-px" aria-hidden="true" />
      <span>{message}</span>
    </div>
  );
}
