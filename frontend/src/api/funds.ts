import { apiFetch } from "./client";
import type { Approval, Bank, Fund, FundInput, FundSummary } from "./types";

export function listFunds(q?: string) {
  return apiFetch<FundSummary[]>(`/funds${q ? `?q=${encodeURIComponent(q)}` : ""}`);
}

export function getFund(id: string) {
  return apiFetch<Fund>(`/funds/${id}`);
}

// Both return the approval request: a scheme-setup checker must approve it.
export function proposeFund(input: FundInput) {
  return apiFetch<Approval>("/funds", { method: "POST", body: JSON.stringify(input) });
}

export function proposeFundUpdate(id: string, input: FundInput) {
  return apiFetch<Approval>(`/funds/${id}`, { method: "PUT", body: JSON.stringify(input) });
}

export function listBanks() {
  return apiFetch<Bank[]>("/reference/banks");
}
