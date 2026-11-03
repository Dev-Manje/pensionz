import type { ExpiryState, KycStatus, RemittanceStage } from "../../api/types";
import type { StatusTone } from "../../utils/labels";

// Plain-language stage of this month's remittance, with what happens next.
export const STAGE_TEXT: Record<RemittanceStage, { label: string; tone: StatusTone; next: string }> = {
  not_started: { label: "Not sent yet", tone: "default", next: "Send the contribution schedule and tell us about the payment." },
  payment_only: { label: "Payment noted — schedule missing", tone: "warning", next: "Send the schedule so members can be credited." },
  draft: { label: "Schedule not sent", tone: "warning", next: "Finish and send the schedule you started." },
  awaiting_allocation: {
    label: "Being processed",
    tone: "info",
    next: "Your pension administrator is matching the schedule to the money and will credit the members.",
  },
  allocated: { label: "Done — members credited", tone: "success", next: "Nothing more to do for this month." },
};

// "due in 12 days" / "due today" / "6 days overdue"
export function dueText(daysToDue: number): string {
  if (daysToDue === 0) return "due today";
  if (daysToDue > 0) return `due in ${daysToDue} day${daysToDue === 1 ? "" : "s"}`;
  const late = -daysToDue;
  return `${late} day${late === 1 ? "" : "s"} overdue`;
}

// Overdue only matters until members have been credited.
export function isLate(stage: RemittanceStage, daysToDue: number): boolean {
  return stage !== "allocated" && daysToDue < 0;
}

// KYC application status in the officer's words. Senior approval is compliance's
// internal step (it means high risk), so the officer just sees "Being reviewed".
export const KYC_STATUS_TEXT: Record<KycStatus, { label: string; tone: StatusTone }> = {
  draft: { label: "Not sent yet", tone: "default" },
  submitted: { label: "Sent — waiting for review", tone: "info" },
  in_review: { label: "Being reviewed", tone: "info" },
  awaiting_senior_approval: { label: "Being reviewed", tone: "info" },
  returned: { label: "Needs changes", tone: "warning" },
  approved: { label: "Approved", tone: "success" },
  rejected: { label: "Not approved", tone: "error" },
};

export const EXPIRY_TEXT: Record<ExpiryState, { label: string; tone: StatusTone }> = {
  current: { label: "Up to date", tone: "success" },
  due_soon: { label: "Due soon", tone: "warning" },
  expired: { label: "Expired", tone: "error" },
  overdue: { label: "Overdue", tone: "error" },
};

// A schedule's status in the officer's words.
export const SCHEDULE_TEXT: Record<"draft" | "ready" | "allocated" | "cancelled", { label: string; tone: StatusTone }> = {
  draft: { label: "Not sent yet", tone: "warning" },
  ready: { label: "Sent — being processed", tone: "info" },
  allocated: { label: "Members credited", tone: "success" },
  cancelled: { label: "Cancelled", tone: "default" },
};

// A payment notice / receipt in the officer's words.
export const PAYMENT_TEXT: Record<"notified" | "pending_approval" | "confirmed" | "rejected" | "cancelled", { label: string; tone: StatusTone }> = {
  notified: { label: "Received — pending confirmation", tone: "info" },
  pending_approval: { label: "Received — pending confirmation", tone: "info" },
  confirmed: { label: "Payment confirmed", tone: "success" },
  rejected: { label: "Not confirmed", tone: "error" },
  cancelled: { label: "Cancelled", tone: "default" },
};

// The months an officer may send a schedule for: this month back to a year ago (newest first).
export function recentMonths(today: Date, count = 13): string[] {
  const out: string[] = [];
  for (let i = 0; i < count; i++) {
    const d = new Date(today.getFullYear(), today.getMonth() - i, 1);
    out.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-01`);
  }
  return out;
}

// A request (new member, salary change, exit notice, bulk upload) in the officer's words.
export const REQUEST_TEXT: Record<"pending" | "approved" | "rejected" | "withdrawn", { label: string; tone: StatusTone }> = {
  pending: { label: "Waiting for approval", tone: "info" },
  approved: { label: "Approved", tone: "success" },
  rejected: { label: "Not approved", tone: "error" },
  withdrawn: { label: "Withdrawn", tone: "default" },
};

export const EXIT_REASONS: [string, string][] = [
  ["resigned", "Resigned"],
  ["dismissed", "Dismissed"],
  ["retrenched", "Retrenched / redundant"],
  ["contract_ended", "Contract ended"],
  ["retired", "Retired"],
  ["ill_health", "Left because of ill health"],
  ["died", "Died"],
  ["other", "Other (say why)"],
];
