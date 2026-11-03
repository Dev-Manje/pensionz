import type { BonusRunStatus } from "../../../api/bonus";
import type { StatusTone } from "../../../utils/labels";

export const RUN_STATUS_TEXT: Record<BonusRunStatus, { label: string; tone: StatusTone }> = {
  draft: { label: "Preview — not posted", tone: "warning" },
  pending_approval: { label: "Waiting for checker", tone: "info" },
  posted: { label: "Posted", tone: "success" },
  discarded: { label: "Discarded", tone: "default" },
  reversed: { label: "Reversed", tone: "error" },
};
