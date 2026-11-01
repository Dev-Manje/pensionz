import { apiFetch } from "./client";
import type { Approval, ApprovalStatus } from "./types";

export function listApprovals(status: ApprovalStatus | "all" = "pending") {
  return apiFetch<Approval[]>(status === "all" ? "/approvals?status_filter=" : `/approvals?status_filter=${status}`);
}

export function getApproval(id: string) {
  return apiFetch<Approval>(`/approvals/${id}`);
}

export function approveRequest(id: string, comment?: string) {
  return apiFetch<Approval>(`/approvals/${id}/approve`, { method: "POST", body: JSON.stringify({ comment: comment || null }) });
}

export function rejectRequest(id: string, comment: string) {
  return apiFetch<Approval>(`/approvals/${id}/reject`, { method: "POST", body: JSON.stringify({ comment }) });
}

export function cancelRequest(id: string) {
  return apiFetch<Approval>(`/approvals/${id}/cancel`, { method: "POST" });
}
