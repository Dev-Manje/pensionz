import { apiFetch } from "./client";
import type { Me, SignInResult, TokenPair } from "./types";

export function login(email: string, password: string) {
  return apiFetch<SignInResult>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

// Second sign-in step for portal users: the code from the email.
export function submitSignInCode(challenge: string, code: string) {
  return apiFetch<TokenPair>("/auth/sign-in-code", { method: "POST", body: JSON.stringify({ challenge, code }) });
}

export function resendSignInCode(challenge: string) {
  return apiFetch<{ detail: string }>("/auth/sign-in-code/resend", { method: "POST", body: JSON.stringify({ challenge }) });
}

export function getMe() {
  return apiFetch<Me>("/auth/me");
}

// Signs every other session out; returns tokens so this one carries on.
export function changePassword(current_password: string, new_password: string) {
  return apiFetch<TokenPair>("/auth/change-password", {
    method: "POST",
    body: JSON.stringify({ current_password, new_password }),
  });
}

// Answers the same whether or not the address has an account.
export function forgotPassword(email: string) {
  return apiFetch<{ detail: string }>("/auth/forgot-password", { method: "POST", body: JSON.stringify({ email }) });
}

export interface ResetLinkStatus {
  valid: boolean;
  purpose: "reset" | "invite" | null;
  email: string | null;
}

export function getResetLinkStatus(token: string) {
  return apiFetch<ResetLinkStatus>(`/auth/reset-password/status?token=${encodeURIComponent(token)}`);
}

// Sets the password from an emailed link and signs the user in (portal users:
// once they enter the code that is emailed next).
export function resetPassword(token: string, new_password: string) {
  return apiFetch<SignInResult>("/auth/reset-password", { method: "POST", body: JSON.stringify({ token, new_password }) });
}
