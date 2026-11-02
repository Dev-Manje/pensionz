import type { RemittanceStage } from "../../api/types";
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
