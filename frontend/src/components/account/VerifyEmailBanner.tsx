"use client";

import { useState } from "react";
import { MailWarning } from "lucide-react";
import { resendVerificationEmail } from "@/lib/account";
import { errorMessage } from "@/lib/http";
import { useAuth } from "@/context/AuthContext";

/** Shown to signed-in users whose address is not yet confirmed. `email_verified === false` only: an older API that omits it shows nothing. */
export function VerifyEmailBanner() {
  const { user } = useAuth();
  const [state, setState] = useState<"idle" | "sending" | "sent">("idle");
  const [error, setError] = useState("");

  if (!user || user.email_verified !== false) return null;

  const resend = async () => {
    setState("sending");
    setError("");
    try {
      await resendVerificationEmail();
      setState("sent");
    } catch (err) {
      setError(errorMessage(err));
      setState("idle");
    }
  };

  return (
    <div role="status" className="bg-gold-bright/20 border-b border-gold-bright/40 px-4 py-2 text-xs text-ink flex flex-wrap items-center justify-center gap-x-3 gap-y-1">
      <MailWarning className="w-4 h-4 text-cocoa shrink-0" aria-hidden="true" />
      <span>
        Please confirm <strong>{user.email}</strong> so we can reach you about your lessons.
      </span>
      {state === "sent" ? (
        <span className="font-bold text-success">Link sent - check your inbox.</span>
      ) : (
        <button type="button" onClick={resend} disabled={state === "sending"} className="font-bold text-cocoa hover:underline disabled:opacity-50">
          {state === "sending" ? "Sending..." : "Resend link"}
        </button>
      )}
      {error && <span className="text-primary font-medium">{error}</span>}
    </div>
  );
}
