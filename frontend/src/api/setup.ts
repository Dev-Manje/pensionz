import { apiFetch } from "./client";
import type { Approval, ListRow, SystemListSpec } from "./types";

export function describeLists() {
  return apiFetch<SystemListSpec[]>("/setup/lists");
}

export function listRows(name: string, parent?: string | null) {
  return apiFetch<ListRow[]>(`/setup/lists/${name}${parent ? `?parent=${parent}` : ""}`);
}

// Returns the approval request: a scheme-setup checker must approve it.
export function proposeListRow(name: string, body: Record<string, unknown>, id?: string) {
  return apiFetch<Approval>(`/setup/lists/${name}${id ? `/${id}` : ""}`, { method: id ? "PUT" : "POST", body: JSON.stringify(body) });
}
