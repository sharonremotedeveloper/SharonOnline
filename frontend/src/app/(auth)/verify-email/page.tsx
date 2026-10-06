"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { AlertTriangle, CheckCircle2 } from "lucide-react";
import { confirmEmail } from "@/lib/account";
import { ApiError, errorMessage } from "@/lib/http";
import { useAuth } from "@/context/AuthContext";
import { dashboardFor } from "@/lib/session";

type State = "checking" | "ok" | "dead" | "error";

function Verify() {
  const params = useSearchParams();
  const { isAuthenticated, user, refreshUser } = useAuth();
  const [state, setState] = useState<State>("checking");
  const [message, setMessage] = useState("");
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    const token = params.get("token");
    if (!token) {
      setState("dead");
      return;
    }
    window.history.replaceState(null, "", window.location.pathname); // keep the token out of history/referrers
    confirmEmail(token)
      .then(() => {
        setState("ok");
        void refreshUser();
      })
      .catch((err) => {
        if (err instanceof ApiError && err.status === 400) setState("dead");
        else {
          setMessage(errorMessage(err));
          setState("error");
        }
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div role="status" className="bg-white rounded-3xl p-8 max-w-md w-full border border-divider shadow-card text-center space-y-3">
      {state === "checking" && <p className="text-sm text-ink-muted">Confirming your e-mail...</p>}
      {state === "ok" && (
        <>
          <CheckCircle2 className="w-10 h-10 text-success mx-auto" aria-hidden="true" />
          <h1 className="text-lg font-extrabold text-ink font-serif">E-mail confirmed</h1>
          <Link href={isAuthenticated && user ? dashboardFor(user.role) : "/login"} className="inline-block px-4 py-2 bg-primary hover:bg-primary-hover text-white rounded-xl text-sm font-bold">
            {isAuthenticated ? "Continue" : "Sign in"}
          </Link>
        </>
      )}
      {(state === "dead" || state === "error") && (
        <>
          <AlertTriangle className="w-10 h-10 text-primary mx-auto" aria-hidden="true" />
          <h1 className="text-lg font-extrabold text-ink font-serif">
            {state === "dead" ? "This confirmation link doesn't work" : "We couldn't confirm your e-mail"}
          </h1>
          <p className="text-sm text-ink-muted leading-relaxed">
            {state === "dead"
              ? "It may have expired, or the address on your account has changed. Sign in and use “Resend” in the banner to get a new link."
              : message}
          </p>
          <Link href="/login" className="inline-block px-4 py-2 bg-primary hover:bg-primary-hover text-white rounded-xl text-sm font-bold">
            Sign in
          </Link>
        </>
      )}
    </div>
  );
}

export default function VerifyEmailPage() {
  return (
    <div className="min-h-[80vh] flex items-center justify-center px-4 py-12">
      <Suspense fallback={<div className="text-sm text-ink-muted">Loading...</div>}>
        <Verify />
      </Suspense>
    </div>
  );
}
