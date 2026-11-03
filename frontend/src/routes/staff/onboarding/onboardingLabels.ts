import type { EmployerApplicationStatus } from "../../../api/employerApplications";
import type { StatusTone } from "../../../utils/labels";

// Employer application status in staff words.
export const APPLICATION_STAFF_TEXT: Record<EmployerApplicationStatus, { label: string; tone: StatusTone }> = {
  draft: { label: "Draft (officer)", tone: "default" },
  submitted: { label: "To review", tone: "warning" },
  returned: { label: "Returned to officer", tone: "default" },
  in_approval: { label: "Waiting for checker", tone: "info" },
  approved: { label: "Approved", tone: "success" },
  rejected: { label: "Rejected", tone: "error" },
  withdrawn: { label: "Withdrawn", tone: "default" },
};
