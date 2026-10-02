import { AuthTokens, AuthUser, UserRole } from "@/types/auth";

const ACCESS_COOKIE = "sharon_access_token";
const REFRESH_COOKIE = "sharon_refresh_token";
const ROLE_COOKIE = "sharon_user_role";

export function setCookie(name: string, value: string, days = 7) {
  if (typeof document === "undefined") return;
  const expires = new Date(Date.now() + days * 864e5).toUTCString();
  document.cookie = `${name}=${encodeURIComponent(value)}; expires=${expires}; path=/; SameSite=Lax`;
}

export function getCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(new RegExp("(^|;\\s*)(" + name + ")=([^;]*)"));
  return match ? decodeURIComponent(match[3]) : null;
}

export function removeCookie(name: string) {
  if (typeof document === "undefined") return;
  document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/; SameSite=Lax`;
}

export function saveAuthSession(tokens: AuthTokens, user: AuthUser) {
  if (typeof window !== "undefined") {
    localStorage.setItem("access_token", tokens.access);
    localStorage.setItem("refresh_token", tokens.refresh);
    localStorage.setItem("user_role", user.role);
    localStorage.setItem("user_profile", JSON.stringify(user));
  }

  setCookie(ACCESS_COOKIE, tokens.access);
  setCookie(REFRESH_COOKIE, tokens.refresh);
  setCookie(ROLE_COOKIE, user.role);
}

/** Replace just the tokens (after a refresh) without touching the cached profile/role. */
export function updateStoredTokens(tokens: AuthTokens) {
  if (typeof window !== "undefined") {
    localStorage.setItem("access_token", tokens.access);
    localStorage.setItem("refresh_token", tokens.refresh);
  }
  setCookie(ACCESS_COOKIE, tokens.access);
  setCookie(REFRESH_COOKIE, tokens.refresh);
}

export function clearAuthSession() {
  if (typeof window !== "undefined") {
    localStorage.removeItem("access_token");
    localStorage.removeItem("refresh_token");
    localStorage.removeItem("user_role");
    localStorage.removeItem("user_profile");
  }

  removeCookie(ACCESS_COOKIE);
  removeCookie(REFRESH_COOKIE);
  removeCookie(ROLE_COOKIE);
}

export function getStoredTokens(): AuthTokens | null {
  if (typeof window === "undefined") return null;
  const access = localStorage.getItem("access_token") || getCookie(ACCESS_COOKIE);
  const refresh = localStorage.getItem("refresh_token") || getCookie(REFRESH_COOKIE);

  if (access && refresh) {
    return { access, refresh };
  }
  return null;
}

export function parseJwtPayload(token: string): any | null {
  try {
    const base64Url = token.split(".")[1];
    if (!base64Url) return null;
    const base64 = base64Url.replace(/-/g, "+").replace(/_/g, "/");
    const jsonPayload = decodeURIComponent(
      atob(base64)
        .split("")
        .map((c) => "%" + ("00" + c.charCodeAt(0).toString(16)).slice(-2))
        .join("")
    );
    return JSON.parse(jsonPayload);
  } catch (e) {
    return null;
  }
}
