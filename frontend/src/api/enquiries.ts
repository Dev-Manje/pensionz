import { apiFetch, openFile } from "./client";
import type { Component } from "./ledger";
import type { Approval, BeneficiaryInput } from "./types";

export type DocKind = "benefit" | "client" | "trail" | "contributions" | "voluntary";

export interface AmountLine {
  label: string;
  amount: string;
}

export interface MemberSummaryStatement {
  member_id: string;
  account_code: string;
  full_name: string;
  status: string;
  fund_code: string;
  fund_name: string;
  employer: string | null;
  employer_code: string | null;
  category: string | null;
  employee_no: string | null;
  date_of_birth: string;
  date_joined_fund: string;
  exit_date: string | null;
  balance: string;
  employee_total: string;
  employer_total: string;
  employee_lines: AmountLine[];
  employer_lines: AmountLine[];
  contributions_up_to: string | null;
  current_period: string | null;
  has_portal_login: boolean;
  ageing?: AmountLine[];
}

export interface StatementLine {
  date: string;
  description: string;
  reference: string | null;
  transaction: string;
  component: Component;
  debit: string;
  credit: string;
  balance: string;
}

export interface ClientStatement {
  start: string;
  end: string;
  opening: string;
  closing: string;
  lines: StatementLine[];
  ageing: AmountLine[];
}

export interface Trail {
  start: string;
  end: string;
  lines: StatementLine[];
  totals: { component: Component; debit: string; credit: string }[];
}

export interface TrailMonth {
  month: string;
  employee: string;
  company: string;
  employee_earning: string;
  company_earning: string;
  earning: string;
  earning_rate: string | null;
  total: string;
  voluntary: string;
  voluntary_earning: string;
}

export interface ContributionsTrail {
  start: string;
  end: string;
  months: TrailMonth[];
}

function range(start?: string, end?: string) {
  const p = new URLSearchParams();
  if (start) p.set("start", start);
  if (end) p.set("end", end);
  const s = p.toString();
  return s ? `?${s}` : "";
}

// ---- staff

export const getEnquiry = (id: string) => apiFetch<MemberSummaryStatement>(`/members/${id}/enquiry`);
export const getStatement = (id: string, start?: string, end?: string) => apiFetch<ClientStatement>(`/members/${id}/statement${range(start, end)}`);
export const getTrail = (id: string, start?: string, end?: string) => apiFetch<Trail>(`/members/${id}/trail${range(start, end)}`);
export const getContributionsTrail = (id: string, start?: string, end?: string) =>
  apiFetch<ContributionsTrail>(`/members/${id}/contributions-trail${range(start, end)}`);
export const openMemberDocument = (id: string, kind: DocKind, opts: { start?: string; end?: string; as_at?: string } = {}) => {
  const p = new URLSearchParams(Object.entries(opts).filter(([, v]) => v) as [string, string][]).toString();
  return openFile(`/members/${id}/documents/${kind}${p ? `?${p}` : ""}`);
};
export const openBulkStatements = (fundId: string, asAt: string, schemeId?: string) =>
  openFile(`/funds/${fundId}/benefit-statements?as_at=${asAt}${schemeId ? `&scheme_id=${schemeId}` : ""}`);
export const publishStatements = (fundId: string, asAt: string, schemeId?: string) =>
  apiFetch<{ members: number; notified: number }>(`/funds/${fundId}/benefit-statements/publish`, {
    method: "POST",
    body: JSON.stringify({ as_at: asAt, scheme_id: schemeId || null }),
  });
export const invitePortal = (id: string) => apiFetch<{ detail: string }>(`/members/${id}/portal-invite`, { method: "POST" });

// ---- member portal

export interface Membership {
  member_id: string;
  account_code: string;
  full_name: string;
  status: string;
  fund_name: string;
  employer: string | null;
  balance: string;
  contributions_up_to: string | null;
}

export interface MyMember extends MemberSummaryStatement {
  details: {
    postal_address: string | null;
    physical_address: string | null;
    telephone: string | null;
    mobile: string | null;
    email: string | null;
    preferred_contact: string | null;
    bank_name: string | null;
    bank_branch: string | null;
    bank_account_name: string | null;
    bank_account_number: string | null;
    id_number: string | null;
  };
  pending_change_id: string | null;
  pending_nomination_id: string | null;
}

export interface MyTransaction {
  id: string;
  date: string;
  transaction: string;
  code: number;
  group: string;
  component: Component;
  description: string | null;
  amount: string;
  credit: boolean;
  contribution_month: string | null;
}

export interface MyBeneficiary {
  full_name: string;
  relationship: string;
  relationship_label: string | null;
  date_of_birth: string | null;
  share_pct: string;
  phone: string | null;
  email: string | null;
  address: string | null;
  id_number: string | null;
  is_minor: boolean;
  guardian_name: string | null;
  guardian_relationship: string | null;
  guardian_phone: string | null;
  guardian_id_number: string | null;
}

export interface MyRequest {
  id: string;
  summary: string;
  kind: string;
  status: "pending" | "approved" | "rejected" | "cancelled";
  created_at: string;
  reviewed_at: string | null;
  review_comment: string | null;
}

export const listMemberships = () => apiFetch<Membership[]>("/my/members");
export const getMyMember = (id: string) => apiFetch<MyMember>(`/my/members/${id}`);
export const getMyTransactions = (id: string, page: number, pageSize = 25) =>
  apiFetch<{ total: number; items: MyTransaction[] }>(`/my/members/${id}/transactions?page=${page}&page_size=${pageSize}`);
export const getMyContributions = (id: string, start?: string, end?: string) =>
  apiFetch<ContributionsTrail>(`/my/members/${id}/contributions-trail${range(start, end)}`);
export const openMyDocument = (id: string, kind: DocKind, opts: { start?: string; end?: string; as_at?: string } = {}) => {
  const p = new URLSearchParams(Object.entries(opts).filter(([, v]) => v) as [string, string][]).toString();
  return openFile(`/my/members/${id}/documents/${kind}${p ? `?${p}` : ""}`);
};
export const getMyBeneficiaries = (id: string) =>
  apiFetch<{ signed_date: string | null; beneficiaries: MyBeneficiary[]; pending_approval_id: string | null; can_nominate: boolean }>(
    `/my/members/${id}/beneficiaries`,
  );
export const proposeMyNomination = (id: string, body: { signed_date: string; note: string | null; beneficiaries: BeneficiaryInput[] }) =>
  apiFetch<Approval>(`/my/members/${id}/beneficiaries`, { method: "POST", body: JSON.stringify(body) });
export const requestContactChange = (id: string, body: Record<string, string | null>) =>
  apiFetch<Approval>(`/my/members/${id}/contact`, { method: "POST", body: JSON.stringify(body) });
export const sendBankCode = (id: string) => apiFetch<{ detail: string }>(`/my/members/${id}/bank/code`, { method: "POST" });
export const requestBankChange = (id: string, body: { bank_id: string; bank_branch_id: string | null; bank_account_name: string; bank_account_number: string; code: string }) =>
  apiFetch<Approval>(`/my/members/${id}/bank`, { method: "POST", body: JSON.stringify(body) });
export const getMyRequests = (id: string) => apiFetch<MyRequest[]>(`/my/members/${id}/requests`);
export const startMyKyc = (id: string) => apiFetch<{ id: string }>(`/my/members/${id}/kyc`, { method: "POST" });
export const listMyKyc = () => apiFetch<{ id: string; reference: string; status: string; created_at: string; is_change: boolean }[]>("/my/kyc");
