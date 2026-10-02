"use client";

import React, { createContext, useContext, useEffect, useState, useCallback, ReactNode } from "react";
import { AuthTokens, AuthUser, RegisterPayload, UserRole } from "@/types/auth";
import {
  clearAuthSession,
  getStoredTokens,
  parseJwtPayload,
  saveAuthSession,
} from "@/lib/auth";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

interface AuthContextType {
  user: AuthUser | null;
  role: UserRole | null;
  tokens: AuthTokens | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (credentials: { username: string; password: string }) => Promise<{ success: boolean; role: UserRole; error?: string }>;
  register: (payload: RegisterPayload) => Promise<{ success: boolean; error?: string }>;
  logout: () => void;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

// Staging Mock Users for seamless verification & dry-runs
const MOCK_USERS: Record<string, { user: AuthUser; pass: string }> = {
  admin: {
    pass: "password123",
    user: {
      id: "usr-admin-01",
      username: "admin",
      email: "admin@sharonesl.com",
      first_name: "Sharon",
      last_name: "Admin",
      role: "admin",
      country: "ZA",
      timezone: "Africa/Johannesburg",
      avatar_url: "https://images.unsplash.com/photo-1573496359142-b8d87734a5a2?auto=format&fit=crop&w=200&q=80",
    },
  },
  student_aiko: {
    pass: "password123",
    user: {
      id: "usr-student-01",
      username: "student_aiko",
      email: "aiko.tanaka@tokyo-corp.jp",
      first_name: "Aiko",
      last_name: "Tanaka",
      role: "student",
      country: "JP",
      timezone: "Asia/Tokyo",
      credits: 6,
      avatar_url: "https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=200&q=80",
    },
  },
  teacher_sharon: {
    pass: "password123",
    user: {
      id: "usr-teacher-01",
      username: "teacher_sharon",
      email: "sharon.tutor@sharonesl.com",
      first_name: "Sharon",
      last_name: "M.",
      role: "teacher",
      country: "ZA",
      timezone: "Africa/Johannesburg",
      is_verified: true,
      avatar_url: "https://images.unsplash.com/photo-1573496359142-b8d87734a5a2?auto=format&fit=crop&w=200&q=80",
    },
  },
};

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [tokens, setTokens] = useState<AuthTokens | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const hydrateSession = useCallback(async () => {
    setIsLoading(true);
    try {
      const storedTokens = getStoredTokens();
      if (!storedTokens) {
        setUser(null);
        setTokens(null);
        setIsLoading(false);
        return;
      }

      setTokens(storedTokens);

      // Verify token with backend or fallback to cached profile / decoded payload
      try {
        const res = await fetch(`${API_BASE}/auth/me/`, {
          headers: {
            Authorization: `Bearer ${storedTokens.access}`,
          },
        });

        if (res.ok) {
          const userData = await res.json();
          setUser(userData);
          saveAuthSession(storedTokens, userData);
          setIsLoading(false);
          return;
        }
      } catch (err) {
        // Backend offline, fallback to localStorage/decoded token
      }

      const cachedProfile = localStorage.getItem("user_profile");
      if (cachedProfile) {
        setUser(JSON.parse(cachedProfile));
      } else {
        const payload = parseJwtPayload(storedTokens.access);
        if (payload) {
          const fallbackUser: AuthUser = {
            id: payload.user_id || "usr-cached",
            username: payload.username || "User",
            email: payload.email || "",
            first_name: payload.first_name || "",
            last_name: payload.last_name || "",
            role: (payload.role as UserRole) || "student",
            country: payload.country || "JP",
            timezone: payload.timezone || "Asia/Tokyo",
          };
          setUser(fallbackUser);
        }
      }
    } catch (e) {
      console.error("Failed to hydrate auth session:", e);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    hydrateSession();
  }, [hydrateSession]);

  const login = async ({ username, password }: { username: string; password: string }) => {
    setIsLoading(true);

    // 1. Try real Django REST API endpoint
    try {
      const res = await fetch(`${API_BASE}/auth/token/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });

      if (res.ok) {
        const data = await res.json();
        const access = data.access;
        const refresh = data.refresh;
        const newTokens: AuthTokens = { access, refresh };

        // Fetch user profile
        let userProfile: AuthUser;
        const meRes = await fetch(`${API_BASE}/auth/me/`, {
          headers: { Authorization: `Bearer ${access}` },
        });

        if (meRes.ok) {
          userProfile = await meRes.json();
        } else {
          const claims = parseJwtPayload(access);
          userProfile = {
            id: claims.user_id || `usr-${username}`,
            username: claims.username || username,
            email: claims.email || `${username}@example.com`,
            first_name: claims.first_name || username,
            last_name: claims.last_name || "",
            role: (claims.role as UserRole) || "student",
            country: claims.country || "JP",
            timezone: claims.timezone || "Asia/Tokyo",
          };
        }

        saveAuthSession(newTokens, userProfile);
        setTokens(newTokens);
        setUser(userProfile);
        setIsLoading(false);
        return { success: true, role: userProfile.role };
      }
    } catch (err) {
      // Backend unavailable, fallback to built-in staging credentials
    }

    // 2. Check built-in mock accounts
    const mock = MOCK_USERS[username];
    if (mock && (mock.pass === password || password === "password123")) {
      const mockTokens: AuthTokens = {
        access: `mock_jwt_access_${mock.user.role}_${Date.now()}`,
        refresh: `mock_jwt_refresh_${mock.user.role}_${Date.now()}`,
      };
      saveAuthSession(mockTokens, mock.user);
      setTokens(mockTokens);
      setUser(mock.user);
      setIsLoading(false);
      return { success: true, role: mock.user.role };
    }

    setIsLoading(false);
    return { success: false, role: "student" as UserRole, error: "Invalid username or password" };
  };

  const register = async (payload: RegisterPayload) => {
    setIsLoading(true);

    try {
      const res = await fetch(`${API_BASE}/auth/register/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (res.ok) {
        setIsLoading(false);
        return { success: true };
      } else {
        const errData = await res.json();
        setIsLoading(false);
        const errorMsg = typeof errData === "object" ? Object.values(errData).flat().join(" ") : "Registration failed";
        return { success: false, error: errorMsg };
      }
    } catch (err) {
      // Offline fallback: simulate successful registration
      const newUser: AuthUser = {
        id: `usr-${Date.now()}`,
        username: payload.username,
        email: payload.email,
        first_name: payload.first_name,
        last_name: payload.last_name,
        role: payload.role,
        country: payload.country,
        timezone: payload.timezone,
        credits: payload.role === "student" ? 1 : undefined,
        is_verified: payload.role === "teacher" ? false : undefined,
      };

      const mockTokens: AuthTokens = {
        access: `mock_jwt_access_${payload.role}_${Date.now()}`,
        refresh: `mock_jwt_refresh_${payload.role}_${Date.now()}`,
      };

      saveAuthSession(mockTokens, newUser);
      setTokens(mockTokens);
      setUser(newUser);
      setIsLoading(false);
      return { success: true };
    }
  };

  const logout = () => {
    // Revoke the refresh token server-side (7.7). keepalive lets the request outlive the redirect below;
    // local session is always cleared even if the network call fails, so the user is never stuck logged in.
    if (tokens?.access && tokens?.refresh && !tokens.access.startsWith("mock")) {
      const apiBase = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";
      void fetch(`${apiBase}/auth/logout/`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${tokens.access}` },
        body: JSON.stringify({ refresh: tokens.refresh }),
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

  const refreshUser = async () => {
    await hydrateSession();
  };

  const value: AuthContextType = {
    user,
    role: user?.role || null,
    tokens,
    isAuthenticated: !!user,
    isLoading,
    login,
    register,
    logout,
    refreshUser,
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
