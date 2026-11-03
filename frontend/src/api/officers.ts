import { apiFetch } from "./client";
import type { Approval, UserStatus } from "./types";

export interface OfficerFund {
  id: string;
  code: string;
  name: string;
  // Granted by staff; false = only through one of the officer's employers.
  granted: boolean;
}

export interface Officer {
  user_id: string;
  full_name: string;
  email: string;
  phone: string | null;
  status: UserStatus;
  awaiting_setup: boolean;
  last_login_at: string | null;
  funds: OfficerFund[];
  employers: { scheme_id: string; code: string; name: string; fund_code: string }[];
  pending_approval_id: string | null;
}

export interface OfficerInput {
  email?: string;
  full_name?: string;
  phone?: string | null;
  fund_ids?: string[];
}

export function listOfficers(q?: string) {
  return apiFetch<Officer[]>(`/officers${q ? `?q=${encodeURIComponent(q)}` : ""}`);
}

// Both return the approval request: a scheme-setup checker approves it.
export function proposeOfficer(input: OfficerInput) {
  return apiFetch<Approval>("/officers", { method: "POST", body: JSON.stringify(input) });
}

export function proposeOfficerUpdate(id: string, input: OfficerInput) {
  return apiFetch<Approval>(`/officers/${id}`, { method: "PATCH", body: JSON.stringify(input) });
}

export function sendOfficerInvitation(id: string) {
  return apiFetch<{ detail: string }>(`/officers/${id}/send-invitation`, { method: "POST" });
}
