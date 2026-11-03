import { apiFetch } from "./client";
import type { Component } from "./ledger";
import type { Approval } from "./types";

export type BonusKind = "interim" | "final";
export type BonusRunStatus = "draft" | "pending_approval" | "posted" | "discarded" | "reversed";

export interface BonusRunSummary {
  id: string;
  reference: string;
  kind: BonusKind;
  status: BonusRunStatus;
  member_count: number;
  total_credit: string;
  total_debit: string;
  posting_date: string;
  as_at: string | null;
  posted_at: string | null;
  created_at: string;
  pending_approval_id: string | null;
}

export interface BonusDeclaration {
  id: string;
  fund_id: string;
  reference: string;
  kind: BonusKind;
  period_start: string;
  period_end: string;
  rate: string;
  components: Component[];
  resolution: string | null;
  notes: string | null;
  created_at: string;
  runs: BonusRunSummary[];
}

export interface BonusRunLine {
  member_id: string;
  account_code: string;
  member_name: string;
  component: Component;
  to_date: string;
  days: number;
  opening_balance: string;
  opening_bonus: string;
  movements: string;
  movements_bonus: string;
  calculated: string;
  already_credited: string;
  amount: string;
  reversed: boolean;
}

export interface BonusRun extends BonusRunSummary {
  declaration: BonusDeclaration;
  fund_code: string;
  lines: BonusRunLine[];
  entry_ref: string | null;
}

export interface DeclarationInput {
  kind: BonusKind;
  period_start: string;
  period_end: string;
  rate: string;
  components: Component[];
  resolution?: string | null;
  notes?: string | null;
}

export const listDeclarations = (fundId: string) => apiFetch<BonusDeclaration[]>(`/funds/${fundId}/bonus-declarations`);
export const proposeDeclaration = (fundId: string, input: DeclarationInput) =>
  apiFetch<Approval>(`/funds/${fundId}/bonus-declarations`, { method: "POST", body: JSON.stringify(input) });
export const createRun = (declarationId: string, body: { member_ids?: string[]; as_at?: string | null; posting_date?: string | null }) =>
  apiFetch<BonusRun>(`/bonus-declarations/${declarationId}/runs`, { method: "POST", body: JSON.stringify(body) });
export const getRun = (id: string) => apiFetch<BonusRun>(`/bonus-runs/${id}`);
export const recalculateRun = (id: string) => apiFetch<BonusRun>(`/bonus-runs/${id}/recalculate`, { method: "POST" });
export const discardRun = (id: string) => apiFetch<BonusRun>(`/bonus-runs/${id}/discard`, { method: "POST" });
export const submitRun = (id: string) => apiFetch<Approval>(`/bonus-runs/${id}/submit`, { method: "POST" });
export const reverseRun = (id: string, body: { reason: string; member_ids?: string[] }) =>
  apiFetch<Approval>(`/bonus-runs/${id}/reverse`, { method: "POST", body: JSON.stringify(body) });
