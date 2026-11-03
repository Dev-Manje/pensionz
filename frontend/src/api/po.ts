import { apiFetch, downloadFile, openFile } from "./client";
import type { Schedule, ScheduleLineInput } from "./schedules";
import type { PaymentMethod } from "./receipts";
import type { KycApplication, Organisation, PaymentDetail, PoDashboard, PortalScheme, RemittanceMonth } from "./types";

// Principal officer portal (/po). The server returns only the employers the
// signed-in officer is linked to — possibly several, in several funds.
export function listMySchemes() {
  return apiFetch<PortalScheme[]>("/po/schemes");
}

export function getDashboard() {
  return apiFetch<PoDashboard>("/po/dashboard");
}

export function getOrganisation(schemeId: string) {
  return apiFetch<Organisation>(`/po/schemes/${schemeId}/organisation`);
}

// The employer's KYC, or a change to approved details (prefilled from them).
export function startSchemeKyc(schemeId: string) {
  return apiFetch<KycApplication>(`/po/schemes/${schemeId}/kyc`, { method: "POST" });
}

// ---- remittances: schedules, payment notices, receipts

export const getRemittances = (schemeId: string) => apiFetch<RemittanceMonth[]>(`/po/schemes/${schemeId}/remittances`);

export const downloadPortalTemplate = (schemeId: string, month: string) =>
  downloadFile(`/po/schemes/${schemeId}/schedules/template?month=${month}`, `schedule-${month}.xlsx`);

export const startPortalSchedule = (schemeId: string, contribution_month: string, supplementary: boolean) =>
  apiFetch<Schedule>(`/po/schemes/${schemeId}/schedules`, { method: "POST", body: JSON.stringify({ contribution_month, supplementary }) });

export const getPortalSchedule = (id: string) => apiFetch<Schedule>(`/po/schedules/${id}`);

export function uploadPortalSchedule(id: string, file: File) {
  const form = new FormData();
  form.append("file", file);
  return apiFetch<Schedule>(`/po/schedules/${id}/upload`, { method: "POST", body: form });
}

export const fillPortalSchedule = (id: string) => apiFetch<Schedule>(`/po/schedules/${id}/fill-expected`, { method: "POST" });

export const savePortalLine = (id: string, lineId: string | null, body: ScheduleLineInput) =>
  apiFetch<Schedule>(lineId ? `/po/schedules/${id}/lines/${lineId}` : `/po/schedules/${id}/lines`, {
    method: lineId ? "PUT" : "POST",
    body: JSON.stringify(body),
  });

export const removePortalLine = (id: string, lineId: string) => apiFetch<Schedule>(`/po/schedules/${id}/lines/${lineId}`, { method: "DELETE" });

export const cancelPortalSchedule = (id: string) => apiFetch<Schedule>(`/po/schedules/${id}/cancel`, { method: "POST" });

// Sending money-related things needs a one-time code emailed to the officer.
export const sendRemitCode = () => apiFetch<{ sent_to: string }>("/po/remit-code", { method: "POST" });

export const submitPortalSchedule = (id: string, code: string) =>
  apiFetch<Schedule>(`/po/schedules/${id}/submit`, { method: "POST", body: JSON.stringify({ code }) });

export interface NoticeInput {
  amount: string;
  payment_date: string;
  payment_method: PaymentMethod;
  payer_reference: string | null;
  contribution_month: string | null;
  notes: string | null;
}

export const sendPaymentNotice = (schemeId: string, body: NoticeInput, code: string) =>
  apiFetch<PaymentDetail>(`/po/schemes/${schemeId}/payment-notices`, { method: "POST", body: JSON.stringify({ ...body, code }) });

export const getPayment = (id: string) => apiFetch<PaymentDetail>(`/po/remittances/${id}`);

export function uploadPaymentProof(id: string, file: File) {
  const form = new FormData();
  form.append("file", file);
  return apiFetch<PaymentDetail>(`/po/remittances/${id}/proof`, { method: "POST", body: form });
}

export const viewPaymentProof = (id: string) => openFile(`/po/remittances/${id}/proof`);
export const openPaymentDocument = (id: string) => openFile(`/po/remittances/${id}/document`);
