"use client";

import { useEffect } from "react";
import { ErrorState } from "@/components/ui/ErrorState";

export default function GlobalError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    console.error("Unhandled route error:", error);
  }, [error]);

  return (
    <div className="max-w-7xl mx-auto px-4 py-20">
      <ErrorState error={error} title="Something went wrong" onRetry={reset} />
    </div>
  );
}
