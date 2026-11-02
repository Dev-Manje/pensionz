import { apiFetch } from "./client";
import type { Approval } from "./types";

export type ReceiptStatus = "notified" | "pending_approval" | "confirmed" | "rejected" | "cancelled";
export type PaymentMethod = "eft" | "rtgs" | "cheque" | "cash_deposit" | "mobile_money";

export const PAYMENT_METHOD_LABELS: Record<PaymentMethod, string> = {
  eft: "EFT",
  rtgs: "RTGS",
  cheque: "Cheque",
  cash_deposit: "Cash deposit",
  mobile_money: "Mobile money",
};

export interface Receipt {
  id: string;
  fund_id: string;
  fund_code: string;
  scheme_id: string | null;
  employer: string | null;
  status: ReceiptStatus;
  source: "portal_notice" | "staff";
  receipt_number: string | null;
  notice_number: string | null;
  payment_method: PaymentMethod;
  notified_amount: string | null;
  amount: string | null;
  allocated_amount: string;
  unallocated: string;
  payment_date: string;
  value_date: string | null;
  bank_account_id: string | null;
  bank_account: string | null;
  payer_name: string | null;
  payer_reference: string | null;
  bank_reference: string | null;
  contribution_month: string | null;
  notes: string | null;
  has_proof: boolean;
  proof_filename: string | null;
  notified_by: string | null;
  captured_by: string | null;
  confirmed_by: string | null;
  confirmed_at: string | null;
  created_at: string;
  rejection_reason: string | null;
  approval_request_id: string | null;
  journal_reference: string | null;
  can_confirm: boolean;
  can_identify: boolean;
  document_kind: "receipt" | "acknowledgement" | null;
}

export interface ReceiptPage {
  items: Receipt[];
  total: number;
  unallocated_ageing: { label: string; count: number; amount: string }[];
  notices_waiting: number;
}

export interface ReceiptFilters {
  status?: string | null;
  unidentified?: boolean;
  unallocated?: boolean;
  q?: string;
  page: number;
  page_size: number;
}

export interface ReceiptCaptureInput {
  scheme_id: string | null;
  payment_method: PaymentMethod;
  payment_date: string;
  value_date: string;
  amount: string;
  bank_account_id: string;
  payer_name?: string;
  payer_reference?: string;
  bank_reference?: string;
  contribution_month?: string | null;
  notes?: string;
}

export interface ReceiptConfirmInput {
  value_date: string;
  amount: string;
  bank_account_id: string;
  bank_reference?: string;
  contribution_month?: string | null;
  notes?: string;
}

export function listReceipts(fundId: string, f: ReceiptFilters) {
  const q = new URLSearchParams({ page: String(f.page), page_size: String(f.page_size) });
  if (f.status) q.set("status", f.status);
  if (f.unidentified) q.set("unidentified", "true");
  if (f.unallocated) q.set("unallocated", "true");
  if (f.q) q.set("q", f.q);
  return apiFetch<ReceiptPage>(`/funds/${fundId}/receipts?${q}`);
}

export function getReceipt(id: string) {
  return apiFetch<Receipt>(`/receipts/${id}`);
}

export function captureReceipt(fundId: string, body: ReceiptCaptureInput) {
  return apiFetch<Approval>(`/funds/${fundId}/receipts`, { method: "POST", body: JSON.stringify(body) });
}

export function confirmReceipt(id: string, body: ReceiptConfirmInput) {
  return apiFetch<Approval>(`/receipts/${id}/confirm`, { method: "POST", body: JSON.stringify(body) });
}

export function declineReceipt(id: string, reason: string) {
  return apiFetch<Receipt>(`/receipts/${id}/decline`, { method: "POST", body: JSON.stringify({ reason }) });
}

export function identifyReceipt(id: string, schemeId: string, note?: string) {
  return apiFetch<Approval>(`/receipts/${id}/identify`, { method: "POST", body: JSON.stringify({ scheme_id: schemeId, note }) });
}

export function uploadProof(id: string, file: File) {
  const form = new FormData();
  form.append("file", file);
  return apiFetch<Receipt>(`/receipts/${id}/proof`, { method: "POST", body: form });
}
