import { apiFetch } from "./client";
import type { Approval, Scheme, SchemeInput, SchemeOfficer, SchemeSummary } from "./types";

export function listSchemes(fundId: string) {
  return apiFetch<SchemeSummary[]>(`/funds/${fundId}/schemes`);
}

export function getScheme(id: string) {
  return apiFetch<Scheme>(`/schemes/${id}`);
}

export function listOfficerCandidates() {
  return apiFetch<SchemeOfficer[]>("/schemes/officer-candidates");
}

// Both return the approval request: a scheme-setup checker must approve it.
export function proposeScheme(fundId: string, input: SchemeInput) {
  return apiFetch<Approval>(`/funds/${fundId}/schemes`, { method: "POST", body: JSON.stringify(input) });
}

export function proposeSchemeUpdate(id: string, input: SchemeInput) {
  return apiFetch<Approval>(`/schemes/${id}`, { method: "PUT", body: JSON.stringify(input) });
}
