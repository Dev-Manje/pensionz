import { apiFetch } from "./client";
import type { Approval, RegulatoryParameter, TaxCalc, TaxTableKind, TaxTables } from "./types";

export function listParameters() {
  return apiFetch<RegulatoryParameter[]>("/regulatory/parameters");
}

// Returns the approval request: a scheme-setup checker must approve it.
export function proposeParameter(key: string, input: { value: string; effective_from: string; source: string | null }) {
  return apiFetch<Approval>(`/regulatory/parameters/${key}/versions`, { method: "POST", body: JSON.stringify(input) });
}

export function getTaxTables(kind: TaxTableKind) {
  return apiFetch<TaxTables>(`/regulatory/tax-tables/${kind}`);
}

export function proposeTaxTable(kind: TaxTableKind, input: { effective_from: string; source: string | null; bands: { lower: string; rate_pct: string }[] }) {
  return apiFetch<Approval>(`/regulatory/tax-tables/${kind}`, { method: "POST", body: JSON.stringify(input) });
}

export function calculateTax(kind: TaxTableKind, amount: string) {
  return apiFetch<TaxCalc>(`/regulatory/tax-tables/${kind}/calculate?amount=${encodeURIComponent(amount)}`);
}
