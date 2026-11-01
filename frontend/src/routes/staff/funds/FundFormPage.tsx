import { useState, type FormEvent } from "react";
import { Link as RouterLink, useNavigate, useParams } from "react-router-dom";
import Alert from "@mui/material/Alert";
import Breadcrumbs from "@mui/material/Breadcrumbs";
import Button from "@mui/material/Button";
import Link from "@mui/material/Link";
import MenuItem from "@mui/material/MenuItem";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import AddIcon from "@mui/icons-material/Add";
import { LoadingState } from "../../../components/LoadingState";
import { PageHeader } from "../../../components/PageHeader";
import { FormGrid, FormSection, RepeatRow } from "../../../components/form/FormLayout";
import { useFeedback } from "../../../components/feedback/FeedbackProvider";
import { useBanks, useFund, useProposeFund } from "../../../queries/funds";
import { MONTH_NAMES } from "../../../utils/date";
import {
  BANK_PURPOSE_LABELS,
  FUND_TYPE_LABELS,
  type BankAccountInput,
  type BankAccountPurpose,
  type Fund,
  type FundInput,
  type FundStatus,
  type FundType,
  type TrusteeInput,
} from "../../../api/types";

const FUND_STATUS_OPTIONS: { value: FundStatus; label: string; help: string }[] = [
  { value: "active", label: "Active", help: "Open to new members." },
  { value: "closed_to_new_members", label: "Closed to new members", help: "Existing members carry on; nobody new can join." },
  { value: "wound_up", label: "Wound up", help: "The fund has been wound up; kept for history." },
];

const EMPTY_FUND: FundInput = {
  code: "",
  name: "",
  fund_type: "standalone_dc",
  status: "active",
  registration_number: null,
  tpin: null,
  financial_year_end_month: 12,
  address_line1: null,
  address_line2: null,
  address_line3: null,
  address_line4: null,
  address_line5: null,
  phone: null,
  fax: null,
  email: null,
  website: null,
  contact_name: null,
  contact_email: null,
  contact_phone: null,
  contact_alt_phone: null,
  trustees: [],
  bank_accounts: [],
};

function toInput(fund: Fund): FundInput {
  const { trustees, bank_accounts, ...rest } = fund;
  const input = { ...EMPTY_FUND };
  for (const key of Object.keys(EMPTY_FUND) as (keyof FundInput)[]) {
    if (key in rest) (input as Record<string, unknown>)[key] = (rest as Record<string, unknown>)[key];
  }
  input.trustees = trustees.map((t) => ({ ...t }));
  input.bank_accounts = bank_accounts.map((a) => ({
    id: a.id,
    bank_id: a.bank_id,
    branch_id: a.branch_id,
    account_name: a.account_name,
    account_number: a.account_number ?? "",
    currency: a.currency,
    purpose: a.purpose,
  }));
  return input;
}

// Create or edit a fund (FR-CFG-001). The whole fund goes to a scheme-setup
// checker as one request; nothing changes until they approve it.
export function FundFormPage() {
  const { fundId } = useParams();
  const existing = useFund(fundId);
  if (fundId && existing.isLoading) return <LoadingState />;
  if (fundId && (existing.error || !existing.data)) {
    return <Alert severity="error">{existing.error?.message ?? "Fund not found"}</Alert>;
  }
  return <FundForm key={fundId ?? "new"} fund={existing.data ?? null} />;
}

function FundForm({ fund }: { fund: Fund | null }) {
  const navigate = useNavigate();
  const feedback = useFeedback();
  const banks = useBanks();
  const propose = useProposeFund();
  const [form, setForm] = useState<FundInput>(() => (fund ? toInput(fund) : { ...EMPTY_FUND }));
  const [error, setError] = useState<string | null>(null);
  const locked = new Set(fund?.locked_fields ?? []);
  const backTo = fund ? `/funds/${fund.id}` : "/funds";

  const set = <K extends keyof FundInput>(key: K, value: FundInput[K]) => setForm((f) => ({ ...f, [key]: value }));
  const text = (key: keyof FundInput, label: string, extra: Record<string, unknown> = {}) => (
    <TextField
      label={label}
      value={(form[key] as string | null) ?? ""}
      onChange={(e) => set(key, (e.target.value || null) as never)}
      fullWidth
      {...extra}
    />
  );

  const setTrustee = (i: number, patch: Partial<TrusteeInput>) =>
    set("trustees", form.trustees.map((t, j) => (j === i ? { ...t, ...patch } : t)));
  const setAccount = (i: number, patch: Partial<BankAccountInput>) =>
    set("bank_accounts", form.bank_accounts.map((a, j) => (j === i ? { ...a, ...patch } : a)));

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const request = await propose.mutateAsync({ id: fund?.id, input: form });
      feedback.success(
        fund
          ? "Change sent for approval — it takes effect once a scheme-setup checker approves it."
          : `Fund ${request.payload.code as string} sent for approval — it appears here once a scheme-setup checker approves it.`,
      );
      navigate(backTo);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
      window.scrollTo({ top: document.body.scrollHeight, behavior: "smooth" });
    }
  }

  return (
    <>
      <Breadcrumbs sx={{ mb: 1 }}>
        <Link component={RouterLink} to="/funds" underline="hover" color="inherit">
          Funds
        </Link>
        {fund && (
          <Link component={RouterLink} to={`/funds/${fund.id}`} underline="hover" color="inherit">
            {fund.code}
          </Link>
        )}
        <Typography color="text.primary">{fund ? "Edit" : "New fund"}</Typography>
      </Breadcrumbs>
      <PageHeader
        title={fund ? `Edit ${fund.name}` : "Add a fund"}
        description="Fill in what you know now — only the code, name and type are required. A scheme-setup checker approves the fund before it can be used."
      />
      <Stack component="form" spacing={2} onSubmit={submit} noValidate={false}>
        <FormSection title="Fund">
          <FormGrid>
            {text("code", "Fund code", {
              required: true,
              disabled: locked.has("code"),
              slotProps: { htmlInput: { maxLength: 10, style: { textTransform: "uppercase" } } },
              helperText: locked.has("code") ? "Can't change: the fund has members." : "Up to 10 letters or digits; legacy codes can be kept.",
            })}
            {text("name", "Fund name", { required: true, slotProps: { htmlInput: { minLength: 2 } } })}
            <TextField
              select
              label="Fund type"
              value={form.fund_type}
              onChange={(e) => set("fund_type", e.target.value as FundType)}
              required
              fullWidth
              disabled={locked.has("fund_type")}
              helperText={locked.has("fund_type") ? "Can't change: the fund has members." : "Decides which rules apply to its members."}
            >
              {(Object.keys(FUND_TYPE_LABELS) as FundType[]).map((t) => (
                <MenuItem key={t} value={t}>
                  {FUND_TYPE_LABELS[t]}
                </MenuItem>
              ))}
            </TextField>
            {text("registration_number", "Registration number", { helperText: "As registered with the regulator." })}
            {text("tpin", "TPIN", { helperText: "Taxpayer identification number." })}
            <TextField
              select
              label="Financial year ends in"
              value={form.financial_year_end_month ?? 12}
              onChange={(e) => set("financial_year_end_month", Number(e.target.value))}
              fullWidth
            >
              {MONTH_NAMES.map((m, i) => (
                <MenuItem key={m} value={i + 1}>
                  {m}
                </MenuItem>
              ))}
            </TextField>
            {fund && (
              <TextField
                select
                label="Status"
                value={form.status}
                onChange={(e) => set("status", e.target.value as FundStatus)}
                fullWidth
                helperText={FUND_STATUS_OPTIONS.find((o) => o.value === form.status)?.help}
              >
                {FUND_STATUS_OPTIONS.map((o) => (
                  <MenuItem key={o.value} value={o.value}>
                    {o.label}
                  </MenuItem>
                ))}
              </TextField>
            )}
          </FormGrid>
        </FormSection>

        <FormSection title="Address and contact">
          <FormGrid>
            {text("address_line1", "Address line 1")}
            {text("address_line2", "Address line 2")}
            {text("address_line3", "Address line 3")}
            {text("address_line4", "Address line 4")}
            {text("address_line5", "Address line 5")}
            {text("phone", "Phone", { type: "tel" })}
            {text("fax", "Fax", { type: "tel" })}
            {text("email", "Email", { type: "email" })}
            {text("website", "Website", { helperText: "e.g. www.example.mw" })}
          </FormGrid>
        </FormSection>

        <FormSection title="Contact person" description="Who we deal with day to day about this fund.">
          <FormGrid>
            {text("contact_name", "Full name")}
            {text("contact_email", "Email", { type: "email" })}
            {text("contact_phone", "Phone", { type: "tel" })}
            {text("contact_alt_phone", "Alternative phone", { type: "tel" })}
          </FormGrid>
        </FormSection>

        <FormSection
          title="Trustees"
          description="Removed trustees are kept in the fund's history."
          action={
            <Button startIcon={<AddIcon />} onClick={() => set("trustees", [...form.trustees, { full_name: "" }])}>
              Add trustee
            </Button>
          }
        >
          <Stack spacing={2}>
            {form.trustees.length === 0 && <Typography color="text.secondary">No trustees yet.</Typography>}
            {form.trustees.map((t, i) => (
              <RepeatRow key={t.id ?? `new-${i}`} label={t.full_name || `Trustee ${i + 1}`} onRemove={() => set("trustees", form.trustees.filter((_, j) => j !== i))}>
                <TextField label="Full name" value={t.full_name} onChange={(e) => setTrustee(i, { full_name: e.target.value })} required fullWidth slotProps={{ htmlInput: { minLength: 2 } }} />
                <TextField label="Designation" value={t.designation ?? ""} onChange={(e) => setTrustee(i, { designation: e.target.value || null })} fullWidth helperText="e.g. Chairperson, Member-elected trustee" />
                <TextField label="Date appointed" type="date" value={t.appointed_on ?? ""} onChange={(e) => setTrustee(i, { appointed_on: e.target.value || null })} fullWidth slotProps={{ inputLabel: { shrink: true } }} />
                <TextField label="Email" type="email" value={t.email ?? ""} onChange={(e) => setTrustee(i, { email: e.target.value || null })} fullWidth />
                <TextField label="Phone" type="tel" value={t.phone ?? ""} onChange={(e) => setTrustee(i, { phone: e.target.value || null })} fullWidth />
              </RepeatRow>
            ))}
          </Stack>
        </FormSection>

        <FormSection
          title="Bank accounts"
          description="The fund's own accounts. Removed accounts are kept for the payments and receipts that used them."
          action={
            <Button
              startIcon={<AddIcon />}
              onClick={() =>
                set("bank_accounts", [
                  ...form.bank_accounts,
                  { bank_id: "", branch_id: null, account_name: form.name, account_number: "", currency: "MWK", purpose: "collections" },
                ])
              }
            >
              Add account
            </Button>
          }
        >
          <Stack spacing={2}>
            {banks.error && <Alert severity="error">Couldn't load the bank list: {banks.error.message}</Alert>}
            {form.bank_accounts.length === 0 && <Typography color="text.secondary">No bank accounts yet.</Typography>}
            {form.bank_accounts.map((a, i) => {
              const bank = banks.data?.find((b) => b.id === a.bank_id);
              return (
                <RepeatRow
                  key={a.id ?? `new-${i}`}
                  label={bank ? `${bank.name}${a.account_number ? ` · ${a.account_number}` : ""}` : `Account ${i + 1}`}
                  onRemove={() => set("bank_accounts", form.bank_accounts.filter((_, j) => j !== i))}
                >
                  <TextField select label="Bank" value={a.bank_id} onChange={(e) => setAccount(i, { bank_id: e.target.value, branch_id: null })} required fullWidth>
                    {(banks.data ?? []).map((b) => (
                      <MenuItem key={b.id} value={b.id}>
                        {b.name}
                      </MenuItem>
                    ))}
                  </TextField>
                  <TextField select label="Branch" value={a.branch_id ?? ""} onChange={(e) => setAccount(i, { branch_id: e.target.value || null })} fullWidth disabled={!bank}>
                    <MenuItem value="">
                      <em>Not specified</em>
                    </MenuItem>
                    {(bank?.branches ?? []).map((br) => (
                      <MenuItem key={br.id} value={br.id}>
                        {br.name}
                      </MenuItem>
                    ))}
                  </TextField>
                  <TextField
                    select
                    label="Used for"
                    value={a.purpose}
                    onChange={(e) => setAccount(i, { purpose: e.target.value as BankAccountPurpose })}
                    fullWidth
                  >
                    {(Object.keys(BANK_PURPOSE_LABELS) as BankAccountPurpose[]).map((p) => (
                      <MenuItem key={p} value={p}>
                        {BANK_PURPOSE_LABELS[p]}
                      </MenuItem>
                    ))}
                  </TextField>
                  <TextField label="Account name" value={a.account_name} onChange={(e) => setAccount(i, { account_name: e.target.value })} required fullWidth />
                  <TextField
                    label="Account number"
                    value={a.account_number}
                    onChange={(e) => setAccount(i, { account_number: e.target.value })}
                    required
                    fullWidth
                    slotProps={{ htmlInput: { inputMode: "numeric", pattern: "[0-9 \\-]{4,30}" } }}
                    helperText="Digits only; spaces are ignored."
                  />
                  <TextField
                    label="Currency"
                    value={a.currency}
                    onChange={(e) => setAccount(i, { currency: e.target.value.toUpperCase() })}
                    required
                    fullWidth
                    slotProps={{ htmlInput: { maxLength: 3, pattern: "[A-Z]{3}" } }}
                  />
                </RepeatRow>
              );
            })}
          </Stack>
        </FormSection>

        {error && <Alert severity="error">{error}</Alert>}
        <Stack direction="row" spacing={1} sx={{ justifyContent: "flex-end", pb: 2 }}>
          <Button component={RouterLink} to={backTo}>
            Cancel
          </Button>
          <Button type="submit" variant="contained" disabled={propose.isPending}>
            {propose.isPending ? "Sending…" : "Submit for approval"}
          </Button>
        </Stack>
      </Stack>
    </>
  );
}
