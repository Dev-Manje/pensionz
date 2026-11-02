import { apiFetch } from "./client";

export interface ArrearsMonth {
  month: string;
  due_date: string;
  members_expected: number;
  members_without_estimate: number;
  expected: string;
  paid: string;
  arrears: string;
  days_overdue: number;
  bucket: string;
  interest: string | null;
  status: "paid" | "part_paid" | "unpaid" | "not_due";
}

export interface EmployerArrears {
  scheme_id: string;
  employer: string;
  total_arrears: string;
  total_interest: string | null;
  months_in_arrears: number;
  oldest_bucket: string | null;
  months: ArrearsMonth[];
}

export interface Bucket {
  label: string;
  amount: string;
}

export interface FundArrears {
  as_at: string;
  interest_rate_set: boolean;
  total_arrears: string;
  total_interest: string | null;
  ageing: Bucket[];
  employers: EmployerArrears[];
}

export interface MemberArrears {
  total_arrears: string;
  ageing: Bucket[];
  months: { month: string; expected: string | null; credited: string; arrears: string; days_overdue: number; bucket: string }[];
}

export function getFundArrears(fundId: string) {
  return apiFetch<FundArrears>(`/funds/${fundId}/arrears`);
}

export function getMemberArrears(memberId: string) {
  return apiFetch<MemberArrears>(`/members/${memberId}/arrears`);
}
