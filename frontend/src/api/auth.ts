import { apiFetch } from "./client";
import type { Me, TokenPair } from "./types";

export function login(email: string, password: string) {
  return apiFetch<TokenPair>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
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

// Sets the password from an emailed link and signs the user in.
export function resetPassword(token: string, new_password: string) {
  return apiFetch<TokenPair>("/auth/reset-password", { method: "POST", body: JSON.stringify({ token, new_password }) });
}
