import Link from "next/link";
import type { ReactNode } from "react";
import { ArrowLeft } from "lucide-react";

export interface PageHeaderProps {
  title: ReactNode;
  /** Where the back button goes; omit for a page without one. */
  backHref?: string;
  backLabel?: string;
  /** Short label above the title. A string gets the standard badge; a node is rendered as is. */
  eyebrow?: ReactNode;
  /** Extra context beside the eyebrow, shown from sm up only (on phones it pushed headers to 3-4 lines). */
  secondary?: ReactNode;
  /** Buttons/links on the right from sm up, below the title on phones. */
  actions?: ReactNode;
}

/**
 * The back button + eyebrow + title header used across tutor and admin pages (mobile audit G3).
 * Phones: back button and eyebrow share the first row and the title gets the full width below it.
 * From sm up: the back button sits beside the eyebrow/title block, exactly as the pages laid it out before.
 */
export function PageHeader({ title, backHref, backLabel = "Back", eyebrow, secondary, actions }: PageHeaderProps) {
  return (
    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
      <div className="grid min-w-0 grid-cols-[auto_minmax(0,1fr)] items-center gap-x-3 gap-y-2 sm:gap-y-0">
        {backHref && (
          <Link
            href={backHref}
            aria-label={backLabel}
            className="min-w-11 justify-center min-h-11 inline-flex items-center p-2.5 rounded-xl bg-white border border-divider text-ink-muted hover:text-ink hover:bg-cream-surface transition-colors shadow-xs sm:row-span-2"
          >
            <ArrowLeft className="w-4 h-4" aria-hidden="true" />
          </Link>
        )}
        {(eyebrow || secondary) && (
          <div className={`flex min-w-0 flex-wrap items-center gap-2 ${backHref ? "" : "col-span-2"}`}>
            {typeof eyebrow === "string" ? (
              <span className="text-xs font-mono font-bold text-cocoa bg-cocoa/10 px-2 py-0.5 rounded-md">{eyebrow}</span>
            ) : (
              eyebrow
            )}
            {secondary && <span className="hidden sm:inline text-xs font-bold text-ink-muted">{secondary}</span>}
          </div>
        )}
        <h1
          className={`col-span-2 text-balance text-2xl sm:text-3xl font-black text-ink font-serif ${
            backHref ? "sm:col-span-1 sm:col-start-2" : ""
          }`}
        >
          {title}
        </h1>
      </div>

      {actions && <div className="flex flex-wrap items-center gap-2.5 self-start sm:self-auto">{actions}</div>}
    </div>
  );
}
