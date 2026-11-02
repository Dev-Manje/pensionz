import { apiFetch, downloadFile } from "./client";

export type ScheduleStatus = "draft" | "ready" | "allocated" | "cancelled";

export interface ScheduleLine {
  id: string;
  row_no: number;
  member_id: string | null;
  account_code: string | null;
  employee_no: string | null;
  member_name: string | null;
  pensionable_salary: string | null;
  employee: string;
  employer: string;
  voluntary: string;
  severance: string;
  total: string;
  errors: string[];
  warnings: string[];
}

export interface ScheduleSummary {
  id: string;
  fund_id: string;
  scheme_id: string;
  employer: string;
  contribution_month: string;
  supplementary: boolean;
  reference: string;
  status: ScheduleStatus;
  source: "upload" | "manual" | "portal";
  filename: string | null;
  total_employee: string;
  total_employer: string;
  total_voluntary: string;
  total_severance: string;
  total: string;
  line_count: number;
  error_count: number;
  warning_count: number;
  created_by: string | null;
  created_at: string;
  submitted_by: string | null;
  submitted_at: string | null;
}

export interface Schedule extends ScheduleSummary {
  notes: string | null;
  lines: ScheduleLine[];
  can_edit: boolean;
}

export interface ScheduleLineInput {
  account_code?: string | null;
  employee_no?: string | null;
  member_name?: string | null;
  pensionable_salary?: string | null;
  employee: string;
  employer: string;
  voluntary: string;
  severance: string;
}

export interface ScheduleFilters {
  scheme_id?: string | null;
  status?: string | null;
  page: number;
  page_size: number;
}

export function listSchedules(fundId: string, f: ScheduleFilters) {
  const q = new URLSearchParams({ page: String(f.page), page_size: String(f.page_size) });
  if (f.scheme_id) q.set("scheme_id", f.scheme_id);
  if (f.status) q.set("status", f.status);
  return apiFetch<{ items: ScheduleSummary[]; total: number }>(`/funds/${fundId}/schedules?${q}`);
}

export function getSchedule(id: string) {
  return apiFetch<Schedule>(`/schedules/${id}`);
}

export function createSchedule(fundId: string, body: { scheme_id: string; contribution_month: string; supplementary: boolean; prefill: boolean }) {
  return apiFetch<Schedule>(`/funds/${fundId}/schedules`, { method: "POST", body: JSON.stringify(body) });
}

export function uploadNewSchedule(fundId: string, schemeId: string, month: string, supplementary: boolean, file: File) {
  const form = new FormData();
  form.append("scheme_id", schemeId);
  form.append("contribution_month", month);
  form.append("supplementary", String(supplementary));
  form.append("file", file);
  return apiFetch<Schedule>(`/funds/${fundId}/schedules/upload`, { method: "POST", body: form });
}

export function downloadScheduleTemplate(fundId: string, schemeId: string, month: string) {
  return downloadFile(`/funds/${fundId}/schedules/template?scheme_id=${schemeId}&month=${month}`, `schedule-${month.slice(0, 7)}.xlsx`);
}

export function scheduleAction(id: string, action: "submit" | "reopen" | "cancel" | "fill-expected") {
  return apiFetch<Schedule>(`/schedules/${id}/${action}`, { method: "POST" });
}

export function uploadScheduleFile(id: string, file: File) {
  const form = new FormData();
  form.append("file", file);
  return apiFetch<Schedule>(`/schedules/${id}/upload`, { method: "POST", body: form });
}

export function saveScheduleLine(id: string, lineId: string | null, body: ScheduleLineInput) {
  return lineId
    ? apiFetch<Schedule>(`/schedules/${id}/lines/${lineId}`, { method: "PUT", body: JSON.stringify(body) })
    : apiFetch<Schedule>(`/schedules/${id}/lines`, { method: "POST", body: JSON.stringify(body) });
}

export function removeScheduleLine(id: string, lineId: string) {
  return apiFetch<Schedule>(`/schedules/${id}/lines/${lineId}`, { method: "DELETE" });
}
