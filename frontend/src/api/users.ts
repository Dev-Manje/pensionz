import { apiFetch } from "./client";
import type { Approval, User, UserCreateInput, UserUpdateInput } from "./types";

export function listUsers(q?: string) {
  return apiFetch<User[]>(`/users${q ? `?q=${encodeURIComponent(q)}` : ""}`);
}

// Both return the approval request: another administrator must approve it.
export function proposeUser(input: UserCreateInput) {
  return apiFetch<Approval>("/users", { method: "POST", body: JSON.stringify(input) });
}

export function proposeUserUpdate(id: string, input: UserUpdateInput) {
  return apiFetch<Approval>(`/users/${id}`, { method: "PATCH", body: JSON.stringify(input) });
}

export function sendPasswordLink(id: string) {
  return apiFetch<{ detail: string }>(`/users/${id}/send-password-link`, { method: "POST" });
}
