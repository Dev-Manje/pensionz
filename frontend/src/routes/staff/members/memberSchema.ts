import type { FieldDef } from "../kyc/kycSchema";

// The member record's legacy tabs (Main information, Member information, KYC,
// Regulatory) regrouped by what the person capturing is doing (FR-MEM-001…004).
// Rendered by the KYC field component, so lists and places behave the same.

export const PERSONAL: FieldDef[] = [
  { name: "salutation", label: "Title", type: "list", list: "salutations" },
  { name: "first_name", label: "First name", type: "text", required: true },
  { name: "other_names", label: "Other names", type: "text" },
  { name: "last_name", label: "Last name", type: "text", required: true },
  { name: "maiden_name", label: "Maiden name", type: "text" },
  { name: "gender", label: "Gender", type: "select", optionsKey: "genders", required: true },
  { name: "date_of_birth", label: "Date of birth", type: "date", required: true },
  { name: "nationality", label: "Nationality", type: "list", list: "countries" },
  { name: "id_type", label: "ID type", type: "list", list: "id_types" },
  { name: "id_number", label: "ID number", type: "text", help: "Checked against members in every fund." },
  { name: "civil_status_on_entry", label: "Civil status on entry", type: "select", optionsKey: "marital_statuses" },
  { name: "civil_status_current", label: "Current civil status", type: "select", optionsKey: "marital_statuses" },
  { name: "civil_status_foreign", label: "Civil status (foreign)", type: "text", help: "If recorded under another country's law." },
  { name: "birth_district_id", label: "District of birth", type: "place", list: "districts" },
  { name: "birth_village", label: "Village of birth", type: "text" },
];

export const CONTACT: FieldDef[] = [
  { name: "physical_address", label: "Physical address", type: "textarea" },
  { name: "postal_address", label: "Postal address", type: "textarea" },
  { name: "postal_district_id", label: "Postal district", type: "place", list: "districts" },
  { name: "postal_village", label: "Postal village / town", type: "text" },
  { name: "home_district_id", label: "Home district", type: "place", list: "districts" },
  { name: "home_ta_id", label: "Traditional authority", type: "place", list: "traditional_authorities", parentField: "home_district_id" },
  { name: "home_village_id", label: "Home village", type: "place", list: "villages", parentField: "home_ta_id" },
  { name: "mobile", label: "Mobile", type: "tel" },
  { name: "telephone", label: "Telephone", type: "tel" },
  { name: "fax", label: "Fax", type: "tel" },
  { name: "email", label: "Email", type: "email" },
  { name: "preferred_contact", label: "Preferred way to contact", type: "select", optionsKey: "contact_modes" },
];

export const NEXT_OF_KIN: FieldDef[] = [
  { name: "next_of_kin_name", label: "Next of kin — name", type: "text" },
  { name: "next_of_kin_relationship", label: "Relationship", type: "list", list: "relationships" },
  { name: "next_of_kin_phone", label: "Telephone", type: "tel" },
  { name: "next_of_kin_email", label: "Email", type: "email" },
];

export const IDENTIFIERS: FieldDef[] = [
  { name: "employee_no", label: "Employee number", type: "text" },
  { name: "old_member_no", label: "Old member number", type: "text", help: "From the previous system, if any." },
  { name: "upid", label: "UPID", type: "text", help: "Unique pension ID, when issued." },
  { name: "bi_upid", label: "BI UPID", type: "text" },
];

// Every value the correction endpoint takes (MemberDetailsIn); new members add employer, category and account code.
export const DETAIL_KEYS = [
  "party_id", "old_member_no", "employee_no", "upid", "bi_upid", "is_group_account", "group_account_id",
  "salutation", "first_name", "other_names", "maiden_name", "last_name", "gender", "date_of_birth", "nationality", "id_type", "id_number",
  "civil_status_on_entry", "civil_status_current", "civil_status_foreign", "birth_district_id", "birth_village",
  "postal_address", "postal_district_id", "postal_village", "physical_address", "home_district_id", "home_ta_id", "home_village_id",
  "telephone", "mobile", "fax", "email", "preferred_contact",
  "bank_id", "bank_branch_id", "bank_account_name", "bank_account_number",
  "next_of_kin_name", "next_of_kin_relationship", "next_of_kin_phone", "next_of_kin_email",
  "date_joined_fund", "date_joined_employer", "regulatory_data",
] as const;

export const NO_EMPLOYER_FUNDS = ["personal_pension", "minors_trust"];
