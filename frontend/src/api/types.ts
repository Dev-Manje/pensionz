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
  fund_ids: string[];
}

// Roles that see every fund without being given access to each (FR-SEC-001).
export const ALL_FUNDS_ROLES: UserRole[] = ["admin", "auditor"];

export interface UserCreateInput {
  email: string;
  full_name: string;
  phone?: string | null;
  roles: UserRole[];
  fund_ids?: string[];
}

export interface UserUpdateInput {
  full_name?: string;
  phone?: string | null;
  roles?: UserRole[];
  status?: UserStatus;
  fund_ids?: string[];
}

// ---- Funds (FR-CFG-001) and reference data

export type FundType = "standalone_dc" | "umbrella_dc" | "personal_pension" | "defined_benefit" | "minors_trust";
export type FundStatus = "active" | "closed_to_new_members" | "wound_up";
export type BankAccountPurpose = "collections" | "payments" | "general";

export const FUND_TYPE_LABELS: Record<FundType, string> = {
  standalone_dc: "Stand-alone DC",
  umbrella_dc: "Umbrella DC",
  personal_pension: "Personal pension",
  defined_benefit: "Defined benefit",
  minors_trust: "Minors' trust",
};

export const BANK_PURPOSE_LABELS: Record<BankAccountPurpose, string> = {
  collections: "Contribution collections",
  payments: "Benefit payments",
  general: "General",
};

export interface BankBranch {
  id: string;
  name: string;
  code: string | null;
}

export interface Bank {
  id: string;
  name: string;
  short_name: string | null;
  swift_code: string | null;
  branches: BankBranch[];
}

export interface Trustee {
  id: string;
  full_name: string;
  designation: string | null;
  email: string | null;
  phone: string | null;
  appointed_on: string | null;
}

export interface FundBankAccount {
  id: string;
  bank_id: string;
  bank_name: string;
  branch_id: string | null;
  branch_name: string | null;
  account_name: string;
  // Null when the viewer's roles only allow the masked number.
  account_number: string | null;
  account_number_masked: string;
  currency: string;
  purpose: BankAccountPurpose;
}

export interface FundSummary {
  id: string;
  code: string;
  name: string;
  fund_type: FundType;
  status: FundStatus;
  trustee_count: number;
  bank_account_count: number;
  pending_approval_id: string | null;
  // First day of the open processing month.
  current_period: string | null;
}

export interface FundDetails {
  registration_number: string | null;
  tpin: string | null;
  financial_year_end_month: number | null;
  address_line1: string | null;
  address_line2: string | null;
  address_line3: string | null;
  address_line4: string | null;
  address_line5: string | null;
  phone: string | null;
  fax: string | null;
  email: string | null;
  website: string | null;
  contact_name: string | null;
  contact_email: string | null;
  contact_phone: string | null;
  contact_alt_phone: string | null;
}

export interface Fund extends FundSummary, FundDetails {
  trustees: Trustee[];
  bank_accounts: FundBankAccount[];
  locked_fields: string[];
  can_edit: boolean;
}

export interface TrusteeInput {
  id?: string | null;
  full_name: string;
  designation?: string | null;
  email?: string | null;
  phone?: string | null;
  appointed_on?: string | null;
}

export interface BankAccountInput {
  id?: string | null;
  bank_id: string;
  branch_id?: string | null;
  account_name: string;
  account_number: string;
  currency: string;
  purpose: BankAccountPurpose;
}

// The whole fund as it should be; create and edit both go to a checker.
export interface FundInput extends FundDetails {
  code: string;
  name: string;
  fund_type: FundType;
  status: FundStatus;
  trustees: TrusteeInput[];
  bank_accounts: BankAccountInput[];
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

// ---- Processing months (FR-CFG-002)

export type PeriodStatus = "open" | "closed";

export interface FundPeriod {
  id: string;
  period: string; // first day of the month
  status: PeriodStatus;
  opened_at: string;
  opened_by: string | null;
  closed_at: string | null;
  closed_by: string | null;
}

export interface CloseCheck {
  key: string;
  label: string;
  status: "passed" | "failed" | "not_available";
  detail: string | null;
}

export interface FundPeriods {
  current: FundPeriod | null;
  checklist: CloseCheck[];
  history: FundPeriod[];
  pending_reopen_approval_id: string | null;
  can_open_first: boolean;
  can_close: boolean;
  can_request_reopen: boolean;
}

// ---- Participating employers / schemes (FR-CFG-003)

export type SchemeStatus = "active" | "suspended" | "exited";
export type BillingFrequency = "monthly" | "quarterly" | "annually";

export const BILLING_FREQUENCY_LABELS: Record<BillingFrequency, string> = {
  monthly: "Monthly",
  quarterly: "Quarterly",
  annually: "Annually",
};

export interface SchemeOfficer {
  user_id: string;
  full_name: string;
  email: string;
}

export interface SchemeSummary {
  id: string;
  fund_id: string;
  code: string;
  name: string;
  status: SchemeStatus;
  contribution_day: number;
  billing_frequency: BillingFrequency;
  contact_name: string | null;
  officer_count: number;
  pending_approval_id: string | null;
}

export interface SchemeDetails {
  registration_number: string | null;
  tpin: string | null;
  join_date: string | null;
  exit_date: string | null;
  address_line1: string | null;
  address_line2: string | null;
  address_line3: string | null;
  phone: string | null;
  email: string | null;
  contact_email: string | null;
  contact_phone: string | null;
}

export interface Scheme extends SchemeSummary, SchemeDetails {
  fund_code: string;
  fund_name: string;
  officers: SchemeOfficer[];
  can_edit: boolean;
}

// The whole employer as it should be, including linked principal officers.
export interface SchemeInput extends SchemeDetails {
  code: string;
  name: string;
  status: SchemeStatus;
  contribution_day: number | null;
  billing_frequency: BillingFrequency;
  contact_name: string | null;
  officer_ids: string[];
}

// ---- Regulatory parameters & tax tables (FR-CFG-009)

export type ParameterUnit = "percent" | "years" | "months" | "age" | "money";

export interface ParameterVersion {
  id: string;
  value: string;
  display: string;
  effective_from: string;
  source: string | null;
}

export interface RegulatoryParameter {
  key: string;
  label: string;
  unit: ParameterUnit;
  group: string;
  help: string;
  minimum: string;
  maximum: string;
  current: ParameterVersion | null;
  upcoming: ParameterVersion | null;
  versions: ParameterVersion[];
  pending_approval_id: string | null;
}

export type TaxTableKind = "paye_monthly" | "lump_sum";

export const TAX_TABLE_LABELS: Record<TaxTableKind, string> = {
  paye_monthly: "PAYE on pensions (monthly)",
  lump_sum: "Tax on lump sums",
};

export interface TaxBand {
  lower: string;
  upper: string | null;
  rate_pct: string;
}

export interface TaxTable {
  id: string;
  kind: TaxTableKind;
  effective_from: string;
  source: string | null;
  bands: TaxBand[];
}

export interface TaxTables {
  kind: TaxTableKind;
  label: string;
  current: TaxTable | null;
  upcoming: TaxTable | null;
  versions: TaxTable[];
  pending_approval_id: string | null;
}

export interface TaxCalc {
  amount: string;
  tax: string;
  table_effective_from: string | null;
}

// ---- Investment options (FR-CFG-007)

export type PricingMethod = "declared_rate" | "unit_price";
export type InvestmentOptionStatus = "active" | "closed";

export const PRICING_METHOD_LABELS: Record<PricingMethod, string> = {
  declared_rate: "Declared rate (bonus)",
  unit_price: "Unit priced",
};

export interface InvestmentOptionInput {
  code: string;
  name: string;
  pricing_method: PricingMethod;
  status: InvestmentOptionStatus;
  launch_date: string | null;
  description: string | null;
}

export interface InvestmentOption extends InvestmentOptionInput {
  id: string;
  fund_id: string;
  pending_approval_id: string | null;
}

// ---- Benefit categories (FR-CFG-004)

export type CategoryStatus = "active" | "closed";
export type BenefitDesign = "dc" | "db";
export type RateType = "percent" | "fixed";
export type SalaryBasis = "basic" | "basic_plus_allowances" | "total_emoluments";

export const SALARY_BASIS_LABELS: Record<SalaryBasis, string> = {
  basic: "Basic salary",
  basic_plus_allowances: "Basic salary plus fixed allowances",
  total_emoluments: "Total emoluments",
};

export interface VestingStep {
  years: number;
  vested_pct: string;
}

export interface CategoryTermsInput {
  effective_from: string;
  employee_rate_type: RateType;
  employee_rate: string;
  employer_rate_type: RateType;
  employer_rate: string | null;
  salary_basis: SalaryBasis;
  normal_retirement_age: number | null;
  min_entry_age: number | null;
  max_entry_age: number | null;
  waiting_period_months: number;
  vesting_scale: VestingStep[];
  default_investment_option_id: string | null;
  member_choice_allowed: boolean;
  avc_allowed: boolean;
  group_life_multiple: string | null;
  accrual_denominator: number | null;
  final_salary_months: number | null;
}

export interface CategoryTerms extends CategoryTermsInput {
  id: string;
  design: BenefitDesign;
  default_investment_option: string | null;
}

export interface BenefitCategory {
  id: string;
  scheme_id: string;
  fund_id: string;
  code: string;
  name: string;
  status: CategoryStatus;
  design: BenefitDesign;
  current: CategoryTerms | null;
  upcoming: CategoryTerms | null;
  history: CategoryTerms[];
  pending_approval_id: string | null;
}

// ---- Setup lists (FR-CFG-005, 006, 010) — described by the backend, rendered generically

export type ListFieldType = "text" | "number" | "boolean" | "select" | "ref";

export interface ListField {
  name: string;
  label: string;
  type: ListFieldType;
  required: boolean;
  max_length: number | null;
  minimum: number | null;
  maximum: number | null;
  options: { value: string; label: string }[];
  ref: string | null;
  help: string | null;
  locked_on_edit: boolean;
  upper: boolean;
  default: unknown;
  column: boolean;
}

export interface SystemListSpec {
  name: string;
  label: string;
  plural: string;
  group: string;
  description: string;
  parent_field: string | null;
  fields: ListField[];
}

export type ListRow = Record<string, unknown> & { id: string; pending_approval_id: string | null };

// ---- Fee rules (FR-CFG-008)

export type FeeType = "administration" | "investment_management" | "risk_premium" | "statutory_levy" | "other";
export type FeeBasis = "pct_contributions" | "pct_assets" | "flat_per_member";
export type FeePayer = "fund" | "employer" | "member";
export type FeeFrequency = "per_contribution" | "monthly" | "quarterly" | "annually";

export const FEE_TYPE_LABELS: Record<FeeType, string> = {
  administration: "Administration",
  investment_management: "Investment management",
  risk_premium: "Risk premium",
  statutory_levy: "Statutory levy",
  other: "Other",
};
export const FEE_BASIS_LABELS: Record<FeeBasis, string> = {
  pct_contributions: "% of contributions",
  pct_assets: "% of assets a year",
  flat_per_member: "Flat amount per member",
};
export const FEE_PAYER_LABELS: Record<FeePayer, string> = { fund: "The fund", employer: "The employer", member: "The member" };
export const FEE_FREQUENCY_LABELS: Record<FeeFrequency, string> = {
  per_contribution: "On each contribution",
  monthly: "Monthly",
  quarterly: "Quarterly",
  annually: "Annually",
};

export interface FeeRuleInput {
  code: string;
  name: string;
  scheme_id: string | null;
  fee_type: FeeType;
  basis: FeeBasis;
  rate: string;
  payer: FeePayer;
  frequency: FeeFrequency;
  effective_from: string;
  effective_to: string | null;
}

export interface FeeRule extends FeeRuleInput {
  id: string;
  fund_id: string;
  employer: string | null;
  pending_approval_id: string | null;
}
