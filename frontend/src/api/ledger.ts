import { apiFetch } from "./client";

export type AccountClass = "asset" | "liability" | "equity" | "income" | "expense";
export type Component = "employee" | "employer" | "voluntary" | "severance" | "transfer_in";

export const COMPONENT_LABELS: Record<Component, string> = {
  employee: "Employee",
  employer: "Employer",
  voluntary: "Voluntary (AVC)",
  severance: "Severance",
  transfer_in: "Transfer in",
};

export interface AccountBalance {
  id: string;
  code: string;
  name: string;
  account_class: AccountClass;
  debit: string;
  credit: string;
  balance: string;
}

export interface FundChart {
  accounts: AccountBalance[];
  tie_out: {
    debits: string;
    credits: string;
    balanced: boolean;
    member_credits_gl: string;
    member_sub_ledger: string;
    ties: boolean;
  };
  chart_status: string;
}

export interface LedgerLine {
  code: string;
  account_name: string;
  debit: string;
  credit: string;
  member_id: string | null;
  member_code: string | null;
  component: Component | null;
  description: string | null;
}

export interface JournalEntry {
  id: string;
  reference: string;
  entry_date: string;
  period: string;
  entity_type: string;
  entity_id: string | null;
  description: string;
  total: string;
  reverses: string | null;
  reversed_by: string | null;
  created_by: string | null;
  lines: LedgerLine[];
}

export interface MemberTransaction {
  id: string;
  transaction_date: string;
  period: string;
  transaction_code: number;
  transaction_name: string;
  effect: "credit" | "debit";
  component: Component;
  amount: string;
  contribution_month: string | null;
  reference: string | null;
  description: string | null;
  journal_reference: string;
  reversed: boolean;
  is_reversal: boolean;
}

export interface ComponentBalance {
  component: Component;
  contributions: string;
  bonus: string;
  withdrawals: string;
  other: string;
  balance: string;
}

export interface MemberLedger {
  balance: string;
  components: ComponentBalance[];
  transactions: MemberTransaction[];
  total: number;
}

export function getFundChart(fundId: string) {
  return apiFetch<FundChart>(`/funds/${fundId}/ledger/accounts`);
}

export function listJournal(fundId: string, params: { account?: string; page: number; pageSize: number }) {
  const q = new URLSearchParams({ page: String(params.page), page_size: String(params.pageSize) });
  if (params.account) q.set("account", params.account);
  return apiFetch<{ items: JournalEntry[]; total: number }>(`/funds/${fundId}/ledger/entries?${q}`);
}

export function getMemberLedger(memberId: string, page: number, pageSize: number) {
  return apiFetch<MemberLedger>(`/members/${memberId}/transactions?page=${page}&page_size=${pageSize}`);
}
