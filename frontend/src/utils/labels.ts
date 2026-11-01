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
  // funds
  closed_to_new_members: "Closed to new members",
  wound_up: "Wound up",
  exited: "Exited",
  // effective-dated configuration
  in_force: "In force",
  scheduled: "Scheduled",
  not_set: "Not set",
  change_pending: "Change awaiting approval",
  // processing months
  open: "Open",
  closed: "Closed",
  passed: "Passed",
  failed: "Failed",
  not_available: "Not checked yet",
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
  closed_to_new_members: "warning",
  wound_up: "default",
  exited: "default",
  in_force: "success",
  scheduled: "info",
  not_set: "warning",
  change_pending: "warning",
  open: "success",
  closed: "default",
  passed: "success",
  failed: "error",
  not_available: "default",
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
