import { useState, type FormEvent } from "react";
import { Link as RouterLink, useNavigate, useParams } from "react-router-dom";
import Alert from "@mui/material/Alert";
import Autocomplete from "@mui/material/Autocomplete";
import Breadcrumbs from "@mui/material/Breadcrumbs";
import Button from "@mui/material/Button";
import Link from "@mui/material/Link";
import MenuItem from "@mui/material/MenuItem";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { LoadingState } from "../../../../components/LoadingState";
import { PageHeader } from "../../../../components/PageHeader";
import { FormGrid, FormSection } from "../../../../components/form/FormLayout";
import { useFeedback } from "../../../../components/feedback/FeedbackProvider";
import { useFund } from "../../../../queries/funds";
import { useOfficerCandidates, useProposeScheme, useScheme } from "../../../../queries/schemes";
import { useParties } from "../../../../queries/members";
import {
  BILLING_FREQUENCY_LABELS,
  type BillingFrequency,
  type Fund,
  type Scheme,
  type SchemeInput,
  type SchemeOfficer,
  type SchemeStatus,
} from "../../../../api/types";
import { dueDayLabel } from "./schemeLabels";

const STATUS_OPTIONS: { value: SchemeStatus; label: string; help: string }[] = [
  { value: "active", label: "Active", help: "Contributions are expected every period." },
  { value: "suspended", label: "Suspended", help: "Contributions are on hold; members stay in the fund." },
  { value: "exited", label: "Exited", help: "The employer has left the fund." },
];

const EMPTY: SchemeInput = {
  code: "",
  name: "",
  status: "active",
  registration_number: null,
  tpin: null,
  join_date: null,
  exit_date: null,
  contribution_day: null,
  billing_frequency: "monthly",
  address_line1: null,
  address_line2: null,
  address_line3: null,
  phone: null,
  email: null,
  contact_name: null,
  contact_email: null,
  contact_phone: null,
  officer_ids: [],
  party_id: null,
};

function toInput(s: Scheme): SchemeInput {
  const input = { ...EMPTY };
  for (const key of Object.keys(EMPTY) as (keyof SchemeInput)[]) {
    if (key in s) (input as Record<string, unknown>)[key] = (s as unknown as Record<string, unknown>)[key];
  }
  input.officer_ids = s.officers.map((o) => o.user_id);
  return input;
}

// Create or edit a participating employer (FR-CFG-003). The whole employer,
// including its principal officers, goes to a scheme-setup checker.
export function SchemeFormPage() {
  const { fundId, schemeId } = useParams();
  const fund = useFund(fundId);
  const existing = useScheme(schemeId);
  if (fund.isLoading || (schemeId && existing.isLoading)) return <LoadingState />;
  const error = fund.error ?? existing.error;
  if (error || !fund.data || (schemeId && !existing.data)) return <Alert severity="error">{error?.message ?? "Not found"}</Alert>;
  return <SchemeForm key={schemeId ?? "new"} fund={fund.data} scheme={existing.data ?? null} />;
}

function SchemeForm({ fund, scheme }: { fund: Fund; scheme: Scheme | null }) {
  const navigate = useNavigate();
  const feedback = useFeedback();
  const propose = useProposeScheme(fund.id);
  const candidates = useOfficerCandidates();
  const parties = useParties("corporate");
  const partyOptions = parties.data ?? [];
  const [form, setForm] = useState<SchemeInput>(() => (scheme ? toInput(scheme) : { ...EMPTY }));
  const [error, setError] = useState<string | null>(null);
  const backTo = scheme ? `/funds/${fund.id}/employers/${scheme.id}` : `/funds/${fund.id}?tab=employers`;

  const set = <K extends keyof SchemeInput>(key: K, value: SchemeInput[K]) => setForm((f) => ({ ...f, [key]: value }));
  const text = (key: keyof SchemeInput, label: string, extra: Record<string, unknown> = {}) => (
    <TextField label={label} value={(form[key] as string | null) ?? ""} onChange={(e) => set(key, (e.target.value || null) as never)} fullWidth {...extra} />
  );
  const officerOptions = candidates.data ?? [];
  // Keep already-linked officers selectable even if they no longer appear as candidates.
  const known = new Map<string, SchemeOfficer>([...(scheme?.officers ?? []), ...officerOptions].map((o) => [o.user_id, o]));

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await propose.mutateAsync({ id: scheme?.id, input: form });
      feedback.success(
        scheme
          ? "Change sent for approval — it takes effect once a scheme-setup checker approves it."
          : `Employer ${form.code.toUpperCase()} sent for approval — it appears in the fund once a scheme-setup checker approves it.`,
      );
      navigate(backTo);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
    }
  }

  return (
    <>
      <Breadcrumbs sx={{ mb: 1 }}>
        <Link component={RouterLink} to="/funds" underline="hover" color="inherit">
          Funds
        </Link>
        <Link component={RouterLink} to={`/funds/${fund.id}?tab=employers`} underline="hover" color="inherit">
          {fund.code}
        </Link>
        {scheme && (
          <Link component={RouterLink} to={`/funds/${fund.id}/employers/${scheme.id}`} underline="hover" color="inherit">
            {scheme.code}
          </Link>
        )}
        <Typography color="text.primary">{scheme ? "Edit" : "New employer"}</Typography>
      </Breadcrumbs>
      <PageHeader
        title={scheme ? `Edit ${scheme.name}` : `Add an employer to ${fund.code}`}
        description="A scheme-setup checker approves the employer (and any principal officers linked to it) before it takes effect."
      />
      <Stack component="form" spacing={2} onSubmit={submit}>
        <FormSection title="Employer">
          <FormGrid>
            {text("code", "Employer code", {
              required: true,
              slotProps: { htmlInput: { maxLength: 10, style: { textTransform: "uppercase" } } },
              helperText: "Up to 10 letters or digits, unique in this fund.",
            })}
            {text("name", "Employer name", { required: true, slotProps: { htmlInput: { minLength: 2 } } })}
            {text("registration_number", "Registration number")}
            {text("tpin", "TPIN")}
            {text("join_date", "Joined the fund", { type: "date", slotProps: { inputLabel: { shrink: true } } })}
            {scheme && (
              <TextField
                select
                label="Status"
                value={form.status}
                onChange={(e) => set("status", e.target.value as SchemeStatus)}
                fullWidth
                helperText={STATUS_OPTIONS.find((o) => o.value === form.status)?.help}
              >
                {STATUS_OPTIONS.map((o) => (
                  <MenuItem key={o.value} value={o.value}>
                    {o.label}
                  </MenuItem>
                ))}
              </TextField>
            )}
            {form.status === "exited" &&
              text("exit_date", "Left the fund", { type: "date", required: true, slotProps: { inputLabel: { shrink: true } } })}
          </FormGrid>
        </FormSection>

        <FormSection title="Contributions" description="When this employer's contributions are due, for arrears and reminders.">
          <FormGrid>
            <TextField
              label="Due by day"
              type="number"
              value={form.contribution_day ?? ""}
              onChange={(e) => set("contribution_day", e.target.value ? Number(e.target.value) : null)}
              required
              fullWidth
              slotProps={{ htmlInput: { min: 1, max: 28 } }}
              helperText={form.contribution_day ? `Due by the ${dueDayLabel(form.contribution_day)}` : "Day 1–28 of the month after the contributions month."}
            />
            <TextField select label="Billing" value={form.billing_frequency} onChange={(e) => set("billing_frequency", e.target.value as BillingFrequency)} fullWidth>
              {(Object.keys(BILLING_FREQUENCY_LABELS) as BillingFrequency[]).map((b) => (
                <MenuItem key={b} value={b}>
                  {BILLING_FREQUENCY_LABELS[b]}
                </MenuItem>
              ))}
            </TextField>
          </FormGrid>
        </FormSection>

        <FormSection title="Address and contact">
          <FormGrid>
            {text("address_line1", "Address line 1")}
            {text("address_line2", "Address line 2")}
            {text("address_line3", "Address line 3")}
            {text("phone", "Phone", { type: "tel" })}
            {text("email", "Email", { type: "email" })}
            {text("contact_name", "Contact person")}
            {text("contact_email", "Contact email", { type: "email" })}
            {text("contact_phone", "Contact phone", { type: "tel" })}
          </FormGrid>
        </FormSection>

        <FormSection title="KYC client" description="The employer's approved corporate KYC (FR-ONB-105). Approve the organisation under KYC first.">
          <Autocomplete
            options={partyOptions}
            loading={parties.isLoading}
            value={partyOptions.find((p) => p.id === form.party_id) ?? null}
            onChange={(_, p) => set("party_id", p?.id ?? null)}
            getOptionLabel={(p) => `${p.name}${p.identifier ? ` (${p.identifier})` : ""}`}
            isOptionEqualToValue={(a, b) => a.id === b.id}
            renderInput={(params) => (
              <TextField {...params} label="Approved organisation" helperText={parties.error ? `Couldn't load KYC clients: ${parties.error.message}` : "Optional until the organisation's KYC is approved."} error={!!parties.error} />
            )}
          />
        </FormSection>

        <FormSection title="Principal officers" description="People at the employer who remit contributions and manage members in the portal.">
          <Autocomplete
            multiple
            options={[...known.values()]}
            loading={candidates.isLoading}
            value={form.officer_ids.map((id) => known.get(id)).filter((o): o is SchemeOfficer => !!o)}
            onChange={(_, chosen: SchemeOfficer[]) => set("officer_ids", chosen.map((o) => o.user_id))}
            getOptionLabel={(o) => `${o.full_name} (${o.email})`}
            isOptionEqualToValue={(a, b) => a.user_id === b.user_id}
            renderInput={(params) => (
              <TextField
                {...params}
                label="Linked principal officers"
                helperText={
                  candidates.error
                    ? `Couldn't load principal officers: ${candidates.error.message}`
                    : "Only users with the principal officer role are listed. An administrator creates their logins under Users."
                }
                error={!!candidates.error}
              />
            )}
          />
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
