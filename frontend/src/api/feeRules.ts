import { apiFetch } from "./client";
import type { Approval, FeeRule, FeeRuleInput } from "./types";

export function listFeeRules(fundId: string) {
  return apiFetch<FeeRule[]>(`/funds/${fundId}/fee-rules`);
}

// Returns the approval request: a scheme-setup checker must approve it.
export function proposeFeeRule(fundId: string, input: FeeRuleInput, id?: string) {
  return apiFetch<Approval>(`/funds/${fundId}/fee-rules${id ? `/${id}` : ""}`, { method: id ? "PUT" : "POST", body: JSON.stringify(input) });
}
