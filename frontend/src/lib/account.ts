/**
 * Account recovery / e-mail verification calls (Tasks 8.5, 8.6). All go through the cookie-authenticated proxy.
 * Anonymous calls pass `skipAuth`: a 401 there is an answer, not "your session died".
 */
import { request } from "./http";

const post = (url: string, body: unknown, skipAuth: boolean) =>
  request(url, { method: "POST", body: JSON.stringify(body), skipAuth });

export const requestPasswordReset = (email: string) => post("/auth/password-reset/", { email }, true);

export const confirmPasswordReset = (p: { uid: string; token: string; new_password: string; new_password_confirm: string }) =>
  post("/auth/password-reset/confirm/", p, true);

export const changePassword = (p: { old_password: string; new_password: string; new_password_confirm: string }) =>
  post("/auth/password-change/", p, false);

export const confirmEmail = (token: string) => post("/auth/verify-email/confirm/", { token }, true);

export const resendVerificationEmail = () => post("/auth/verify-email/", {}, false);
