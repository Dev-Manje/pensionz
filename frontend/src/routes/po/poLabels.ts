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
    next: "Your pension administrator is matching the schedule to the money — usually within 5 working days.",
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
