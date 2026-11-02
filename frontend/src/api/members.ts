import { apiFetch } from "./client";
import type {
  Approval, BeneficiaryInput, EmploymentRecords, Member, MemberDuplicate, MemberPage, MemberStatus, MemberValues, Nominations, PartyRef,
  ServicePeriodInput,
} from "./types";

export interface MemberFilters {
  fund_id?: string | null;
  scheme_id?: string | null;
  status?: MemberStatus | null;
  q?: string;
  group_accounts?: boolean;
  page?: number;
  page_size?: number;
}

function query(params: Record<string, unknown>) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) if (value !== null && value !== undefined && value !== "") search.set(key, String(value));
  const text = search.toString();
  return text ? `?${text}` : "";
}

export const listMembers = (filters: MemberFilters) => apiFetch<MemberPage>(`/members${query({ ...filters })}`);
export const getMember = (id: string) => apiFetch<Member>(`/members/${id}`);
export const findDuplicates = (params: { id_number?: string | null; first_name?: string | null; last_name?: string | null; date_of_birth?: string | null; exclude?: string }) =>
  apiFetch<MemberDuplicate[]>(`/members/duplicates${query(params)}`);
export const kycPrefill = (partyId: string) => apiFetch<MemberValues>(`/members/kyc-prefill/${partyId}`);
export const listParties = (clientType: "individual" | "corporate") => apiFetch<PartyRef[]>(`/kyc/parties${query({ client_type: clientType })}`);

// All return the approval request: a member checker must approve it.
export const proposeMember = (fundId: string, values: MemberValues) =>
  apiFetch<Approval>(`/funds/${fundId}/members`, { method: "POST", body: JSON.stringify(values) });
export const proposeMemberUpdate = (id: string, values: MemberValues) =>
  apiFetch<Approval>(`/members/${id}`, { method: "PUT", body: JSON.stringify(values) });
export const proposeStatusChange = (id: string, body: { to_status: MemberStatus; effective_date: string; reason: string }) =>
  apiFetch<Approval>(`/members/${id}/status`, { method: "POST", body: JSON.stringify(body) });

export const getNominations = (id: string) => apiFetch<Nominations>(`/members/${id}/beneficiaries`);
export const proposeNomination = (id: string, body: { signed_date: string; note: string | null; beneficiaries: BeneficiaryInput[] }) =>
  apiFetch<Approval>(`/members/${id}/beneficiaries`, { method: "POST", body: JSON.stringify(body) });
export const getEmployment = (id: string) => apiFetch<EmploymentRecords>(`/members/${id}/employment`);
export const proposeSalary = (id: string, body: { effective_from: string; basic_salary: string; pensionable_salary: string | null; note: string | null }) =>
  apiFetch<Approval>(`/members/${id}/salaries`, { method: "POST", body: JSON.stringify(body) });
export const proposeService = (id: string, body: { periods: ServicePeriodInput[]; reason: string }) =>
  apiFetch<Approval>(`/members/${id}/service`, { method: "PUT", body: JSON.stringify(body) });
