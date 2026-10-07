"use client";

import React, { createContext, useContext, useEffect, useState, useCallback, ReactNode } from "react";
import { AuthUser, RegisterPayload, UserRole } from "@/types/auth";
import { ApiError, errorMessage, purgeLegacyBrowserSession, request } from "@/lib/http";

interface AuthResult {
  success: boolean;
  error?: string;
  fieldErrors?: Record<string, string[]>;
}

interface AuthContextType {
  user: AuthUser | null;
  role: UserRole | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  /** Set when a session may exist but the server could not be reached to verify it. */
  sessionError: string | null;
  login: (credentials: { username: string; password: string }) => Promise<AuthResult & { role: UserRole }>;
  register: (payload: RegisterPayload) => Promise<AuthResult>;
  logout: () => void;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

function loginErrorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 401 || err.status === 400) return "Invalid username/e-mail or password.";
    if (err.status === 429) return "Too many attempts. Please wait a minute and try again.";
  }
  return errorMessage(err, "Sign-in failed. Please try again.");
}

/**
 * Session state. The tokens themselves are never visible here: they live in HttpOnly cookies managed by the
 * /api/session/* route handlers. The browser only learns who the user is.
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [sessionError, setSessionError] = useState<string | null>(null);

  const hydrateSession = useCallback(async () => {
    setIsLoading(true);
    setSessionError(null);
    try {
      // skipAuth: "not signed in" is a normal answer on public pages, not a reason to redirect.
      const data = await request<{ user: AuthUser | null }>("/api/session/me", { skipAuth: true });
      setUser(data.user ?? null);
    } catch (err) {
      setUser(null);
      if (err instanceof ApiError && err.status !== 401) setSessionError(errorMessage(err));
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    purgeLegacyBrowserSession(); // wipe tokens left in localStorage / JS-readable cookies by the old implementation
    hydrateSession();
  }, [hydrateSession]);

  const login: AuthContextType["login"] = async ({ username, password }) => {
    setIsLoading(true);
    try {
      const data = await request<{ user: AuthUser }>("/api/session/login", {
        method: "POST",
        body: JSON.stringify({ username, password }),
        skipAuth: true,
      });
      setUser(data.user);
      setSessionError(null);
      return { success: true, role: data.user.role };
    } catch (err) {
      setUser(null);
      return { success: false, role: "student" as UserRole, error: loginErrorMessage(err) };
    } finally {
      setIsLoading(false);
    }
  };

  const register: AuthContextType["register"] = async (payload) => {
    setIsLoading(true);
    try {
      await request("/auth/register/", { method: "POST", body: JSON.stringify(payload), skipAuth: true });
      return { success: true };
    } catch (err) {
      // No offline "pretend it worked" path: a failed signup must look like a failed signup.
      const fieldErrors = err instanceof ApiError ? err.fieldErrors : undefined;
      return { success: false, error: errorMessage(err, "Registration failed."), fieldErrors };
    } finally {
      setIsLoading(false);
    }
  };

  const logout = () => {
    // The server revokes the refresh token and clears the cookies. We leave the page either way so the user is never
    // stuck looking signed-in; a failed revoke is logged server-side (the cookies are cleared regardless).
    setUser(null);
    void request("/api/session/logout", { method: "POST", skipAuth: true, keepalive: true })
      .catch((err) => console.warn("Logout request failed; cookies may remain until they expire", err))
      .finally(() => {
        if (typeof window !== "undefined") window.location.href = "/login";
      });
  };

  const value: AuthContextType = {
    user,
    role: user?.role || null,
    isAuthenticated: !!user,
    isLoading,
    sessionError,
    login,
    register,
    logout,
    refreshUser: hydrateSession,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextType {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
