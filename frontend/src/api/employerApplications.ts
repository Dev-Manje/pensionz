import { apiFetch } from "./client";
import type { Approval, KycApplication } from "./types";

export type EmployerApplicationStatus = "draft" | "submitted" | "returned" | "in_approval" | "approved" | "rejected" | "withdrawn";
export type SalaryBasisCode = "basic" | "basic_plus_allowances" | "total_emoluments";

export interface ApplicationDetails {
  name: string;
  registration_number?: string | null;
  tpin?: string | null;
  address_line1?: string | null;
  address_line2?: string | null;
  address_line3?: string | null;
  phone?: string | null;
  email?: string | null;
  contact_name?: string | null;
  contact_email?: string | null;
  contact_phone?: string | null;
  contribution_day?: number | null;
  billing_frequency?: "monthly" | "quarterly" | "annually";
  join_date?: string | null;
}

export interface ProposedCategory {
  name: string;
  employee_rate: string;
  employer_rate: string;
  salary_basis: SalaryBasisCode;
  normal_retirement_age: number;
}

// Terms as the API takes them (schemas/category.TermsIn), JSON form.
export interface FinalTerms {
  effective_from: string;
  employee_rate_type?: "percent" | "fixed";
  employee_rate: string;
  employer_rate_type?: "percent" | "fixed";
  employer_rate: string | null;
  salary_basis: SalaryBasisCode;
  normal_retirement_age: number;
  min_entry_age?: number | null;
  max_entry_age?: number | null;
  waiting_period_months?: number;
  vesting_scale?: { years: number; vested_pct: string }[];
  default_investment_option_id: string | null;
  member_choice_allowed?: boolean;
  avc_allowed?: boolean;
  group_life_multiple?: string | null;
}

export interface FinalCategory {
  code: string;
  name: string;
  terms: FinalTerms;
}

export interface FinalTermsInput {
  code: string;
  join_date: string;
  categories: FinalCategory[];
  note?: string | null;
}

export interface EmployerApplication {
  id: string;
  reference: string;
  status: EmployerApplicationStatus;
  fund_id: string;
  fund_code: string;
  fund_name: string;
  officer_name: string;
  officer_email: string;
  details: ApplicationDetails;
  categories: ProposedCategory[];
  final_terms: FinalTermsInput | null;
  kyc_application_id: string | null;
  kyc_reference: string | null;
  kyc_status: string | null;
  scheme_id: string | null;
  review_note: string | null;
  submitted_at: string | null;
  decided_at: string | null;
  created_at: string;
  problems: string[];
  pending_approval_id: string | null;
  can_edit: boolean;
}

export interface EmployerApplicationInput {
  fund_id: string;
  details: ApplicationDetails;
  categories: ProposedCategory[];
}

export interface ApplicationFund {
  id: string;
  code: string;
  name: string;
  fund_type: string;
}

// ---- portal

export const listApplicationFunds = () => apiFetch<ApplicationFund[]>("/po/application-funds");
export const listMyApplications = () => apiFetch<EmployerApplication[]>("/po/employer-applications");
export const getMyApplication = (id: string) => apiFetch<EmployerApplication>(`/po/employer-applications/${id}`);
export const createApplication = (input: EmployerApplicationInput) =>
  apiFetch<EmployerApplication>("/po/employer-applications", { method: "POST", body: JSON.stringify(input) });
export const saveApplication = (id: string, input: EmployerApplicationInput) =>
  apiFetch<EmployerApplication>(`/po/employer-applications/${id}`, { method: "PUT", body: JSON.stringify(input) });
export const startApplicationKyc = (id: string) => apiFetch<KycApplication>(`/po/employer-applications/${id}/kyc`, { method: "POST" });
export const submitApplication = (id: string) => apiFetch<EmployerApplication>(`/po/employer-applications/${id}/submit`, { method: "POST" });
export const withdrawApplication = (id: string) => apiFetch<EmployerApplication>(`/po/employer-applications/${id}/withdraw`, { method: "POST" });

// ---- staff

export const listApplications = (status?: EmployerApplicationStatus) =>
  apiFetch<EmployerApplication[]>(`/employer-applications${status ? `?status_filter=${status}` : ""}`);
export const getApplication = (id: string) => apiFetch<EmployerApplication>(`/employer-applications/${id}`);
export const getSuggestedTerms = (id: string) => apiFetch<FinalTermsInput>(`/employer-applications/${id}/suggested-terms`);
export const returnApplication = (id: string, note: string) =>
  apiFetch<EmployerApplication>(`/employer-applications/${id}/return`, { method: "POST", body: JSON.stringify({ note }) });
export const rejectApplication = (id: string, note: string) =>
  apiFetch<EmployerApplication>(`/employer-applications/${id}/reject`, { method: "POST", body: JSON.stringify({ note }) });
export const proposeTerms = (id: string, input: FinalTermsInput) =>
  apiFetch<Approval>(`/employer-applications/${id}/propose`, { method: "POST", body: JSON.stringify(input) });
