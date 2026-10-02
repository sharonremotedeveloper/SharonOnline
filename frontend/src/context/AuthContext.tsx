"use client";

import React, { createContext, useContext, useEffect, useState, useCallback, ReactNode } from "react";
import { AuthTokens, AuthUser, RegisterPayload, UserRole } from "@/types/auth";
import { clearAuthSession, getStoredTokens, saveAuthSession, updateStoredTokens } from "@/lib/auth";
import { API_BASE, ApiError, USE_MOCKS, errorMessage, request } from "@/lib/http";

interface AuthResult {
  success: boolean;
  error?: string;
  fieldErrors?: Record<string, string[]>;
}

interface AuthContextType {
  user: AuthUser | null;
  role: UserRole | null;
  tokens: AuthTokens | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  /** Set when a stored session exists but the backend could not be reached to verify it. */
  sessionError: string | null;
  login: (credentials: { username: string; password: string }) => Promise<AuthResult & { role: UserRole }>;
  register: (payload: RegisterPayload) => Promise<AuthResult>;
  logout: () => void;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

function loginErrorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 401 || err.status === 400) return "Invalid username or password.";
    if (err.status === 429) return "Too many attempts. Please wait a minute and try again.";
  }
  return errorMessage(err, "Sign-in failed. Please try again.");
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [tokens, setTokens] = useState<AuthTokens | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [sessionError, setSessionError] = useState<string | null>(null);

  const hydrateSession = useCallback(async () => {
    setIsLoading(true);
    setSessionError(null);
    try {
      const stored = getStoredTokens();
      if (!stored) {
        setUser(null);
        setTokens(null);
        return;
      }

      // Mock-mode sessions have no backend to verify against.
      if (USE_MOCKS && stored.access.startsWith("mock_")) {
        const cached = localStorage.getItem("user_profile");
        setTokens(stored);
        setUser(cached ? JSON.parse(cached) : null);
        return;
      }

      try {
        // `request` refreshes an expired access token itself; the stored tokens may have changed by the time it returns.
        const profile = await request<AuthUser>("/auth/me/");
        const current = getStoredTokens() || stored;
        setTokens(current);
        setUser(profile);
        saveAuthSession(current, profile);
      } catch (err) {
        if (err instanceof ApiError && err.isNetworkError) {
          // Backend unreachable: do NOT wipe the session and do NOT trust a cached/decoded profile.
          setTokens(stored);
          setUser(null);
          setSessionError(errorMessage(err));
        } else {
          // 401 after a failed refresh, 403, etc.: the session is genuinely invalid.
          clearAuthSession();
          setUser(null);
          setTokens(null);
        }
      }
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    hydrateSession();
  }, [hydrateSession]);

  const login: AuthContextType["login"] = async ({ username, password }) => {
    setIsLoading(true);
    try {
      const data = await request<AuthTokens>("/auth/token/", {
        method: "POST",
        body: JSON.stringify({ username, password }),
        skipAuth: true,
      });
      const newTokens: AuthTokens = { access: data.access, refresh: data.refresh };
      updateStoredTokens(newTokens); // so the next call carries the new access token
      const profile = await request<AuthUser>("/auth/me/");
      saveAuthSession(newTokens, profile);
      setTokens(newTokens);
      setUser(profile);
      setSessionError(null);
      return { success: true, role: profile.role };
    } catch (err) {
      clearAuthSession();
      if (USE_MOCKS && err instanceof ApiError && (err.isNetworkError || err.status === 401)) {
        const { mockLogin } = await import("@/lib/mockAuth");
        const mock = mockLogin(username, password);
        if (mock) {
          saveAuthSession(mock.tokens, mock.user);
          setTokens(mock.tokens);
          setUser(mock.user);
          return { success: true, role: mock.user.role };
        }
      }
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
    // Revoke the refresh token server-side. The endpoint is authenticated by the refresh token itself, so this works
    // even when the access token has expired. keepalive lets it outlive the redirect below.
    const current = tokens || getStoredTokens();
    if (current?.refresh && !current.refresh.startsWith("mock_")) {
      void fetch(`${API_BASE}/auth/logout/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh: current.refresh }),
        keepalive: true,
      }).catch((err) => console.warn("Server-side logout failed; refresh token remains valid until expiry", err));
    }
    clearAuthSession();
    setUser(null);
    setTokens(null);
    if (typeof window !== "undefined") {
      window.location.href = "/login";
    }
  };

  const value: AuthContextType = {
    user,
    role: user?.role || null,
    tokens,
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
