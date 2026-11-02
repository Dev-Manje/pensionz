import { apiFetch, downloadFile, openFile } from "./client";
import type {
  Approval, BeneficiaryInput, MemberImport, MemberImportSummary, EmploymentRecords, Member, MemberDuplicate, MemberPage, MemberStatus, MemberValues, Nominations, PartyRef,
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

export const proposeMove = (id: string, body: { scheme_id: string; category_id: string; effective_date: string; employee_no: string | null; reason: string }) =>
  apiFetch<Approval>(`/members/${id}/move`, { method: "POST", body: JSON.stringify(body) });
export const getNominations = (id: string) => apiFetch<Nominations>(`/members/${id}/beneficiaries`);
export const proposeNomination = (id: string, body: { signed_date: string; note: string | null; beneficiaries: BeneficiaryInput[] }) =>
  apiFetch<Approval>(`/members/${id}/beneficiaries`, { method: "POST", body: JSON.stringify(body) });
export const getEmployment = (id: string) => apiFetch<EmploymentRecords>(`/members/${id}/employment`);
export const proposeSalary = (id: string, body: { effective_from: string; basic_salary: string; pensionable_salary: string | null; note: string | null }) =>
  apiFetch<Approval>(`/members/${id}/salaries`, { method: "POST", body: JSON.stringify(body) });
export const proposeService = (id: string, body: { periods: ServicePeriodInput[]; reason: string }) =>
  apiFetch<Approval>(`/members/${id}/service`, { method: "PUT", body: JSON.stringify(body) });

// Bulk upload (FR-MEM-006) and the printable application form (FR-MEM-007).
export const downloadImportTemplate = (schemeId: string) => downloadFile(`/members/import-template?scheme_id=${schemeId}`, "members-template.xlsx");
export const openApplicationForm = (schemeId?: string | null) => openFile(`/members/application-form${schemeId ? `?scheme_id=${schemeId}` : ""}`);
export const listImports = (fundId?: string | null) => apiFetch<MemberImportSummary[]>(`/members/imports${fundId ? `?fund_id=${fundId}` : ""}`);
export const getImport = (id: string) => apiFetch<MemberImport>(`/members/imports/${id}`);
export const downloadImportErrors = (id: string) => downloadFile(`/members/imports/${id}/errors`, "member-upload-errors.xlsx");
export function uploadImport(schemeId: string, file: File) {
  const form = new FormData();
  form.append("scheme_id", schemeId);
  form.append("file", file);
  return apiFetch<MemberImport>("/members/imports", { method: "POST", body: form });
}
export const submitImport = (id: string) => apiFetch<Approval>(`/members/imports/${id}/submit`, { method: "POST" });
export const cancelImport = (id: string) => apiFetch<MemberImportSummary>(`/members/imports/${id}/cancel`, { method: "POST" });
