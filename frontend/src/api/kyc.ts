import { apiFetch, openFile } from "./client";
import type { ClientType, Declaration, KycApplication, KycOptions, KycStatus, KycSummary, RiskRating } from "./types";

const base = "/kyc/applications";

export function listKyc(status?: KycStatus | null, q?: string) {
  const params = new URLSearchParams();
  if (status) params.set("status_filter", status);
  if (q) params.set("q", q);
  const query = params.toString();
  return apiFetch<KycSummary[]>(query ? `${base}?${query}` : base);
}

export const getKyc = (id: string) => apiFetch<KycApplication>(`${base}/${id}`);
export const createKyc = (client_type: ClientType) => apiFetch<KycApplication>(base, { method: "POST", body: JSON.stringify({ client_type }) });
export const saveKyc = (id: string, data: Record<string, unknown>) =>
  apiFetch<KycApplication>(`${base}/${id}`, { method: "PUT", body: JSON.stringify({ data }) });
export const kycOptions = () => apiFetch<KycOptions>("/kyc/options");
export const getDeclaration = (type: ClientType) => apiFetch<Declaration>(`/kyc/declarations/${type}`);

export function uploadKycDocument(id: string, fields: Record<string, string | null>, file: File) {
  const form = new FormData();
  for (const [key, value] of Object.entries(fields)) if (value) form.append(key, value);
  form.append("file", file);
  return apiFetch<KycApplication>(`${base}/${id}/documents`, { method: "POST", body: form });
}

export const removeKycDocument = (id: string, docId: string) => apiFetch<KycApplication>(`${base}/${id}/documents/${docId}`, { method: "DELETE" });
export const viewKycDocument = (id: string, docId: string) => openFile(`${base}/${id}/documents/${docId}/file`);

function post<T>(path: string, body: unknown = {}) {
  return apiFetch<T>(path, { method: "POST", body: JSON.stringify(body) });
}

export const submitKyc = (id: string, declaration_version_id: string, accepted_by: string) =>
  post<KycApplication>(`${base}/${id}/submit`, { declaration_version_id, accepted_by });
export const startKycReview = (id: string) => post<KycApplication>(`${base}/${id}/start-review`);
export const reviewKycDocument = (id: string, docId: string, accept: boolean, reason?: string) =>
  post<KycApplication>(`${base}/${id}/documents/${docId}/review`, { accept, reason: reason ?? null });
export const returnKyc = (id: string, note: string) => post<KycApplication>(`${base}/${id}/return`, { note });
export const approveKyc = (id: string, note: string | null, risk_override: RiskRating | null) =>
  post<KycApplication>(`${base}/${id}/approve`, { note, risk_override });
export const rejectKyc = (id: string, note: string) => post<KycApplication>(`${base}/${id}/reject`, { note });
export const seniorDecideKyc = (id: string, approve: boolean, reason: string | null) =>
  post<KycApplication>(`${base}/${id}/senior-decision`, { approve, reason });
