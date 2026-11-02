// One place for what status codes are called on screen, so every table and
// chip uses the same words.

export type StatusTone = "success" | "warning" | "error" | "info" | "default";

export const STATUS_LABELS: Record<string, string> = {
  // people and records
  active: "Active",
  inactive: "Inactive",
  deceased: "Deceased",
  deferred: "Deferred (paid-up)",
  pensioner: "Pensioner",
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
  retired: "Retired",
  ended: "Ended",
  // KYC
  submitted: "Submitted",
  in_review: "In review",
  returned: "Returned for changes",
  awaiting_senior_approval: "Awaiting senior approval",
  accepted: "Accepted",
  pending_review: "Awaiting review",
  overdue: "Overdue",
  due_soon: "Due soon",
  upcoming: "Upcoming",
  low: "Low risk",
  medium: "Medium risk",
  high: "High risk",
  change_pending: "Change awaiting approval",
  // processing months
  open: "Open",
  closed: "Closed",
  passed: "Passed",
  failed: "Failed",
  not_available: "Not checked yet",
  // bulk uploads
  validated: "Checked — not submitted",
  pending_approval: "Awaiting approval",
  imported: "Imported",
  // contribution receipts
  notified: "Notice — to confirm",
  confirmed: "Confirmed",
  // contribution schedules
  ready: "Ready for allocation",
  allocated: "Allocated",
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
  deferred: "info",
  pensioner: "info",
  closed_to_new_members: "warning",
  wound_up: "default",
  exited: "default",
  in_force: "success",
  scheduled: "info",
  not_set: "warning",
  retired: "default",
  ended: "default",
  submitted: "info",
  in_review: "info",
  returned: "warning",
  awaiting_senior_approval: "warning",
  accepted: "success",
  pending_review: "info",
  overdue: "error",
  due_soon: "warning",
  upcoming: "info",
  low: "success",
  medium: "warning",
  high: "error",
  change_pending: "warning",
  open: "success",
  closed: "default",
  passed: "success",
  failed: "error",
  not_available: "default",
  validated: "info",
  pending_approval: "warning",
  imported: "success",
  notified: "info",
  confirmed: "success",
  ready: "info",
  allocated: "success",
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
