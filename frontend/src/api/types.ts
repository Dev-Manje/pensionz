// DTOs mirroring the backend schemas (backend/app/schemas).

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type?: string;
}

export type UserRole =
  | "admin"
  | "scheme_config_maker"
  | "scheme_config_checker"
  | "member_admin"
  | "member_checker"
  | "contributions_officer"
  | "contributions_checker"
  | "benefits_officer"
  | "benefits_checker"
  | "benefits_approver_l2"
  | "finance"
  | "finance_checker"
  | "payroll_officer"
  | "compliance"
  | "relationship_manager"
  | "auditor"
  | "trustee"
  | "principal_officer"
  | "member"
  | "individual";

export const ROLE_LABELS: Record<UserRole, string> = {
  admin: "Administrator",
  scheme_config_maker: "Scheme setup",
  scheme_config_checker: "Scheme setup checker",
  member_admin: "Member administration",
  member_checker: "Member checker",
  contributions_officer: "Contributions officer",
  contributions_checker: "Contributions checker",
  benefits_officer: "Benefits officer",
  benefits_checker: "Benefits checker",
  benefits_approver_l2: "Benefits approver (level 2)",
  finance: "Finance",
  finance_checker: "Finance checker",
  payroll_officer: "Pensioner payroll",
  compliance: "Compliance",
  relationship_manager: "Relationship manager",
  auditor: "Auditor",
  trustee: "Trustee",
  principal_officer: "Principal officer",
  member: "Member",
  individual: "Personal pension holder",
};

// Portal (non-staff) roles; everything else is administrator staff.
export const PORTAL_ROLES: UserRole[] = ["principal_officer", "member", "individual", "trustee"];
export const STAFF_ROLES = (Object.keys(ROLE_LABELS) as UserRole[]).filter((r) => !PORTAL_ROLES.includes(r));

export interface Me {
  id: string;
  email: string;
  full_name: string;
  roles: UserRole[];
  is_staff: boolean;
}

export type UserStatus = "active" | "suspended" | "deactivated";

export interface User {
  id: string;
  email: string;
  full_name: string;
  phone: string | null;
  roles: UserRole[];
  status: UserStatus;
  last_login_at: string | null;
  created_at: string;
  locked: boolean;
  awaiting_setup: boolean;
}

export interface UserCreateInput {
  email: string;
  full_name: string;
  phone?: string | null;
  roles: UserRole[];
}

export interface UserUpdateInput {
  full_name?: string;
  phone?: string | null;
  roles?: UserRole[];
  status?: UserStatus;
}

export type ApprovalStatus = "pending" | "approved" | "rejected" | "cancelled";

export interface Approval {
  id: string;
  kind: string;
  kind_label: string;
  entity_type: string;
  entity_id: string | null;
  summary: string;
  payload: Record<string, unknown>;
  previous: Record<string, unknown> | null;
  status: ApprovalStatus;
  initiated_by: string;
  initiated_by_user_id: string;
  created_at: string;
  reviewed_by: string | null;
  reviewed_at: string | null;
  review_comment: string | null;
  can_review: boolean;
  can_cancel: boolean;
}

export interface UserNotification {
  id: string;
  event: string;
  title: string;
  body: string;
  link: string | null;
  created_at: string;
  read_at: string | null;
}

export interface UserNotificationPage {
  items: UserNotification[];
  total: number;
  unread: number;
}
