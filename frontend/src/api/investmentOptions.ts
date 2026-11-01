import { apiFetch } from "./client";
import type { Approval, InvestmentOption, InvestmentOptionInput } from "./types";

export function listInvestmentOptions(fundId: string) {
  return apiFetch<InvestmentOption[]>(`/funds/${fundId}/investment-options`);
}

// Both return the approval request: a scheme-setup checker must approve it.
export function proposeInvestmentOption(fundId: string, input: InvestmentOptionInput, id?: string) {
  return apiFetch<Approval>(`/funds/${fundId}/investment-options${id ? `/${id}` : ""}`, {
    method: id ? "PUT" : "POST",
    body: JSON.stringify(input),
  });
}
