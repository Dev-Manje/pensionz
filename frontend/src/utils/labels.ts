// One place for what status codes are called on screen, so every table and
// chip uses the same words.

export type StatusTone = "success" | "warning" | "error" | "info" | "default";

export const STATUS_LABELS: Record<string, string> = {
  // people and records
  active: "Active",
  inactive: "Inactive",
  deceased: "Deceased",
  suspended: "Suspended",
  deactivated: "Deactivated",
  locked: "Locked",
  awaiting_setup: "Invitation sent",
  // approvals and requests
  draft: "Draft",
  pending: "Awaiting approval",
  approved: "Approved",
  rejected: "Rejected",
  cancelled: "Withdrawn",
};

const TONES: Record<string, StatusTone> = {
  active: "success",
  approved: "success",
  inactive: "default",
  draft: "default",
  cancelled: "default",
  deactivated: "default",
  pending: "warning",
  awaiting_setup: "info",
  suspended: "error",
  locked: "error",
  rejected: "error",
  deceased: "default",
};

/** "pending" → "Awaiting approval"; unknown codes become "Sentence case". */
export function statusLabel(status: string | null | undefined): string {
  if (!status) return "—";
  if (STATUS_LABELS[status]) return STATUS_LABELS[status];
  const words = status.replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

export function statusTone(status: string | null | undefined): StatusTone {
  return (status && TONES[status]) || "default";
}
