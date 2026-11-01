import { apiFetch } from "./client";
import type { Approval, Bank, Fund, FundInput, FundPeriods, FundSummary } from "./types";

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

export function getPeriods(fundId: string) {
  return apiFetch<FundPeriods>(`/funds/${fundId}/periods`);
}

export function openFirstPeriod(fundId: string, period: string) {
  return apiFetch<FundPeriods>(`/funds/${fundId}/periods/open`, { method: "POST", body: JSON.stringify({ period }) });
}

export function closePeriod(fundId: string, period: string) {
  return apiFetch<FundPeriods>(`/funds/${fundId}/periods/close`, { method: "POST", body: JSON.stringify({ period }) });
}

// Returns the approval request: a finance checker must approve the re-open.
export function requestReopen(fundId: string, periodId: string, reason: string) {
  return apiFetch<Approval>(`/funds/${fundId}/periods/${periodId}/reopen`, { method: "POST", body: JSON.stringify({ reason }) });
}
