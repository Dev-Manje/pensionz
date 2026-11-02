import type { ClientType, KycOptions } from "../../../api/types";

// The KYC forms as data (source: "kyc Requirements.docx", REQUIREMENTS FR-ONB-C/G/I).
// One stepper renders all three client types from these definitions; the
// backend checks completeness on submit (services/kyc_forms.py).

export type FieldType =
  | "text"
  | "email"
  | "tel"
  | "date"
  | "number"
  | "textarea"
  | "select" // options from KycOptions[optionsKey]
  | "list" // a Setup list, stored by code
  | "multi_list" // several codes from a Setup list
  | "place" // a Setup list stored by id (districts, TAs, villages), optionally under a parent field
  | "yes_no"
  | "pep" // yes/no with the PEP definition shown
  | "tags"; // several free-text values

export interface FieldDef {
  name: string;
  label: string;
  type: FieldType;
  required?: boolean;
  help?: string;
  optionsKey?: keyof KycOptions;
  list?: string;
  parentField?: string;
  // Only shown when another field has one of these values.
  showIf?: { field: string; in: unknown[] };
  // An "Other" choice needs this field filled in.
  otherField?: string;
  width?: "full";
}

export interface PeopleDef {
  name: "directors" | "signatories";
  singular: string;
  help: string;
  fields: FieldDef[];
}

export interface StepDef {
  key: string;
  title: string;
  description?: string;
  fields?: FieldDef[];
  people?: PeopleDef;
  // Special steps rendered by their own components.
  special?: "documents" | "declaration";
}

const contactPerson: FieldDef[] = [
  { name: "contact_name", label: "Contact person / representative", type: "text", required: true },
  { name: "contact_phone", label: "Contact person's phone", type: "tel", required: true },
  { name: "contact_email", label: "Contact person's email", type: "email", required: true },
];

const productFields: FieldDef[] = [
  { name: "products", label: "Products / schemes", type: "multi_list", list: "kyc_products", help: "Optional — tick any that apply." },
  { name: "scheme_numbers", label: "Scheme, investment or policy numbers", type: "tags", help: "Optional. Press Enter after each number." },
];

const personFields = (extra: FieldDef[]): FieldDef[] => [
  { name: "full_name", label: "Full name", type: "text", required: true },
  ...extra,
  { name: "nationality", label: "Nationality", type: "list", list: "countries", required: true },
  { name: "resident_in_malawi", label: "Lives in Malawi", type: "yes_no", showIf: { field: "nationality", in: ["__foreign__"] }, help: "Foreign nationals living in Malawi also need an immigration permit." },
  { name: "is_pep", label: "Politically exposed person?", type: "pep", required: true },
];

const documentsStep: StepDef = {
  key: "documents",
  title: "Documents",
  description: "Upload each document as a PDF or a clear photo (up to 10 MB). Bills must be recent.",
  special: "documents",
};
const declarationStep: StepDef = { key: "declaration", title: "Declaration", special: "declaration" };

export const KYC_STEPS: Record<ClientType, StepDef[]> = {
  corporate: [
    {
      key: "organisation",
      title: "Organisation",
      description: "Type the organisation's name in full.",
      fields: [
        { name: "entity_name", label: "Organisation name", type: "text", required: true, width: "full" },
        { name: "entity_form", label: "Type of organisation", type: "select", optionsKey: "entity_forms", required: true, otherField: "entity_form_other" },
        { name: "entity_form_other", label: "Type of organisation (other)", type: "text", showIf: { field: "entity_form", in: ["other"] } },
        { name: "registration_number", label: "Registration number", type: "text", required: true },
        { name: "tpin", label: "TPIN", type: "text" },
        ...productFields,
      ],
    },
    {
      key: "contact",
      title: "Contact details",
      fields: [
        { name: "office_phone", label: "Office phone", type: "tel", required: true },
        { name: "email", label: "Email", type: "email", required: true },
        { name: "postal_address", label: "Postal address", type: "textarea" },
        { name: "physical_address", label: "Physical address", type: "textarea", required: true },
        ...contactPerson,
      ],
    },
    {
      key: "directors",
      title: "Directors",
      people: {
        name: "directors",
        singular: "Director / senior manager",
        help: "Add every director and senior manager. Each needs an ID; foreign nationals living in Malawi also need an immigration permit.",
        fields: personFields([{ name: "position", label: "Position", type: "text", required: true }]),
      },
    },
    {
      key: "pep",
      title: "Politically exposed",
      fields: [{ name: "is_pep", label: "Is the organisation a politically exposed entity?", type: "pep", required: true, width: "full" }],
    },
    documentsStep,
    declarationStep,
  ],
  group: [
    {
      key: "group",
      title: "Group",
      description: "Type the group's name in full.",
      fields: [
        { name: "group_name", label: "Group name", type: "text", required: true, width: "full" },
        { name: "group_kind", label: "Type of group", type: "select", optionsKey: "group_kinds", required: true, otherField: "group_kind_other" },
        { name: "group_kind_other", label: "Type of group (other)", type: "text", showIf: { field: "group_kind", in: ["other"] } },
        { name: "phone", label: "Phone", type: "tel", required: true },
        { name: "email", label: "Email", type: "email" },
        { name: "postal_address", label: "Postal address", type: "textarea" },
        { name: "physical_address", label: "Physical address", type: "textarea", required: true },
        ...productFields,
      ],
    },
    {
      key: "signatories",
      title: "Signatories",
      people: {
        name: "signatories",
        singular: "Signatory",
        help: "Add every signatory — there is no limit. Each needs an ID and a proof of physical address.",
        fields: personFields([
          { name: "address", label: "Address", type: "text", required: true },
          { name: "phone", label: "Phone", type: "tel", required: true },
          { name: "email", label: "Email", type: "email" },
          { name: "occupation", label: "Occupation", type: "text", required: true },
        ]),
      },
    },
    documentsStep,
    declarationStep,
  ],
  individual: [
    {
      key: "personal",
      title: "Personal details",
      fields: [
        { name: "salutation", label: "Title", type: "list", list: "salutations" },
        { name: "first_name", label: "First name", type: "text", required: true },
        { name: "middle_name", label: "Middle name", type: "text" },
        { name: "last_name", label: "Last name", type: "text", required: true },
        { name: "maiden_name", label: "Maiden name", type: "text" },
        { name: "other_names", label: "Other names", type: "text" },
        { name: "gender", label: "Gender", type: "select", optionsKey: "genders", required: true },
        { name: "date_of_birth", label: "Date of birth", type: "date", required: true },
        { name: "marital_status", label: "Marital status", type: "select", optionsKey: "marital_statuses", required: true },
        { name: "marital_status_on_entry", label: "Marital status when joining", type: "select", optionsKey: "marital_statuses" },
        { name: "member_numbers", label: "Policy / member numbers", type: "tags", help: "Optional. Press Enter after each number." },
      ],
    },
    {
      key: "identity",
      title: "Identity and residence",
      fields: [
        { name: "id_type", label: "ID type", type: "list", list: "id_types", required: true },
        { name: "id_number", label: "ID number", type: "text", required: true },
        { name: "id_expiry", label: "ID expiry date", type: "date" },
        { name: "nationality", label: "Nationality", type: "list", list: "countries", required: true },
        { name: "country_of_residence", label: "Country of residence", type: "list", list: "countries", required: true },
        { name: "permit_type", label: "Immigration permit", type: "list", list: "permit_types", showIf: { field: "nationality", in: ["__foreign__"] }, help: "Foreign nationals living in Malawi." },
        { name: "permit_expiry", label: "Permit expiry date", type: "date", showIf: { field: "nationality", in: ["__foreign__"] } },
      ],
    },
    {
      key: "address",
      title: "Address",
      fields: [
        { name: "physical_address", label: "Physical address (description)", type: "textarea", required: true },
        { name: "postal_address", label: "Postal address", type: "textarea" },
        { name: "home_district_id", label: "Home district", type: "place", list: "districts" },
        { name: "home_ta_id", label: "Traditional authority", type: "place", list: "traditional_authorities", parentField: "home_district_id" },
        { name: "home_village_id", label: "Village", type: "place", list: "villages", parentField: "home_ta_id" },
        { name: "birth_district_id", label: "District of birth", type: "place", list: "districts" },
        { name: "birth_village", label: "Village of birth", type: "text" },
      ],
    },
    {
      key: "income",
      title: "Income",
      fields: [
        { name: "income_source", label: "Main source of income", type: "select", optionsKey: "income_sources", required: true },
        { name: "employer_name", label: "Employer", type: "text", showIf: { field: "income_source", in: ["employment"] } },
        { name: "employment_start", label: "Started on", type: "date", showIf: { field: "income_source", in: ["employment"] } },
        { name: "monthly_net_income", label: "Monthly net income (MWK)", type: "number", showIf: { field: "income_source", in: ["employment"] } },
        { name: "business_type", label: "Type of business", type: "text", showIf: { field: "income_source", in: ["business"] } },
        { name: "business_address", label: "Business physical address", type: "text", showIf: { field: "income_source", in: ["business"] } },
        { name: "business_registration", label: "Business registration number (if registered)", type: "text", showIf: { field: "income_source", in: ["business"] } },
        { name: "business_monthly_income", label: "Monthly business income (MWK)", type: "number", showIf: { field: "income_source", in: ["business"] } },
        { name: "other_income", label: "Other income (specify)", type: "text" },
        { name: "source_of_funds", label: "Source of funds", type: "text", required: true, help: "Where the money paid in comes from, e.g. salary." },
      ],
    },
    {
      key: "contact",
      title: "Contact and next of kin",
      fields: [
        { name: "telephone", label: "Telephone", type: "tel" },
        { name: "mobile", label: "Mobile number", type: "tel", required: true },
        { name: "email", label: "Email", type: "email" },
        { name: "preferred_contact", label: "Preferred way to contact you", type: "select", optionsKey: "contact_modes", required: true },
        { name: "next_of_kin.name", label: "Next of kin — name", type: "text", required: true },
        { name: "next_of_kin.relationship", label: "Next of kin — relationship", type: "list", list: "relationships", required: true },
        { name: "next_of_kin.occupation", label: "Next of kin — occupation", type: "text" },
        { name: "next_of_kin.cell", label: "Next of kin — cell number", type: "tel" },
        { name: "next_of_kin.email", label: "Next of kin — email", type: "email" },
      ],
    },
    {
      key: "pep",
      title: "Politically exposed",
      fields: [
        { name: "is_pep", label: "Are you a politically exposed person?", type: "pep", required: true, width: "full" },
        { name: "related_to_pep", label: "Are you related to, or a close associate of, a politically exposed person?", type: "yes_no", required: true, width: "full" },
      ],
    },
    documentsStep,
    declarationStep,
  ],
};

// "a.b" paths for nested values such as next_of_kin.name.
export function getPath(data: Record<string, unknown>, path: string): unknown {
  return path.split(".").reduce<unknown>((value, key) => (value && typeof value === "object" ? (value as Record<string, unknown>)[key] : undefined), data);
}

export function setPath(data: Record<string, unknown>, path: string, value: unknown): Record<string, unknown> {
  const [head, ...rest] = path.split(".");
  if (rest.length === 0) return { ...data, [head]: value };
  const child = (data[head] && typeof data[head] === "object" ? data[head] : {}) as Record<string, unknown>;
  return { ...data, [head]: setPath(child, rest.join("."), value) };
}

// "__foreign__" in showIf means "a nationality other than Malawian".
export function isShown(field: FieldDef, data: Record<string, unknown>): boolean {
  if (!field.showIf) return true;
  const value = getPath(data, field.showIf.field);
  if (field.showIf.in.includes("__foreign__")) return !!value && value !== "MW";
  return field.showIf.in.includes(value);
}

// The form's label for a stored answer ("contact_name", "next_of_kin.name", or a
// director / signatory list as a whole) — used to list what a change request changes.
export function fieldLabel(type: ClientType, name: string): string {
  for (const step of KYC_STEPS[type]) {
    const field = step.fields?.find((f) => f.name === name);
    if (field) return field.label;
    if (step.people?.name === name) return step.title;
  }
  return name.replace(/[._]/g, " ");
}
