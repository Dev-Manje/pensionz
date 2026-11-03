import { useState } from "react";
import { Link as RouterLink, useNavigate, useParams } from "react-router-dom";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Breadcrumbs from "@mui/material/Breadcrumbs";
import Button from "@mui/material/Button";
import Link from "@mui/material/Link";
import MenuItem from "@mui/material/MenuItem";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { BRAND } from "../../brand";
import { DetailField, DetailSection } from "../../components/DetailSection";
import { LoadingState } from "../../components/LoadingState";
import { StatusChip } from "../../components/StatusChip";
import { useFeedback } from "../../components/feedback/FeedbackProvider";
import { FormGrid, FormSection, RepeatRow } from "../../components/form/FormLayout";
import {
  useApplicationFunds, useCreateApplication, useMyApplication, useSaveApplication, useStartApplicationKyc, useSubmitApplication,
  useWithdrawApplication,
} from "../../queries/employerApplications";
import { SALARY_BASIS_LABELS, type SalaryBasis } from "../../api/types";
import type { ApplicationDetails, EmployerApplication, EmployerApplicationInput, ProposedCategory } from "../../api/employerApplications";
import { formatDate, formatDateTime, formatPeriod } from "../../utils/date";
import { APPLICATION_STATUS_TEXT, KYC_STATUS_TEXT } from "./poLabels";
import type { KycStatus } from "../../api/types";

const EMPTY_CATEGORY: ProposedCategory = { name: "", employee_rate: "5", employer_rate: "10", salary_basis: "basic", normal_retirement_age: 60 };

const DETAIL_TEXT: [keyof ApplicationDetails, string][] = [
  ["registration_number", "Registration number"],
  ["tpin", "TPIN"],
  ["address_line1", "Address"],
  ["address_line2", "Address line 2"],
  ["address_line3", "Town / district"],
  ["phone", "Phone"],
  ["email", "Email"],
  ["contact_name", "Contact person"],
  ["contact_email", "Contact email"],
  ["contact_phone", "Contact phone"],
];

export const applicationPath = (id: string) => `/po/applications/${id}`;

function Field({ label, value, onChange, ...rest }: { label: string; value: string | number | null | undefined; onChange: (v: string) => void } & Omit<React.ComponentProps<typeof TextField>, "value" | "onChange">) {
  return <TextField label={label} value={value ?? ""} onChange={(e) => onChange(e.target.value)} fullWidth {...rest} />;
}

function ApplicationForm({ app, onSaved }: { app: EmployerApplication | null; onSaved: (a: EmployerApplication) => void }) {
  const funds = useApplicationFunds();
  const create = useCreateApplication();
  const save = useSaveApplication();
  const feedback = useFeedback();
  const [fundId, setFundId] = useState(app?.fund_id ?? "");
  const [details, setDetails] = useState<ApplicationDetails>(app?.details ?? { name: "", billing_frequency: "monthly" });
  const [cats, setCats] = useState<ProposedCategory[]>(app?.categories.length ? app.categories : [{ ...EMPTY_CATEGORY, name: "Staff" }]);
  const [error, setError] = useState<string | null>(null);
  const busy = create.isPending || save.isPending;
  const set = (key: keyof ApplicationDetails) => (v: string) => setDetails((d) => ({ ...d, [key]: v }));
  const setCat = (i: number, patch: Partial<ProposedCategory>) => setCats((list) => list.map((c, j) => (j === i ? { ...c, ...patch } : c)));
  const fundOptions = funds.data ?? [];

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    const input: EmployerApplicationInput = {
      fund_id: fundId,
      details: { ...details, contribution_day: details.contribution_day ? Number(details.contribution_day) : null },
      categories: cats.filter((c) => c.name.trim()).map((c) => ({ ...c, normal_retirement_age: Number(c.normal_retirement_age) })),
    };
    try {
      const saved = app ? await save.mutateAsync({ id: app.id, input }) : await create.mutateAsync(input);
      feedback.success("Saved. You can come back to it at any time.");
      onSaved(saved);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't save.");
    }
  }

  if (funds.data && fundOptions.length === 0) {
    return (
      <Alert severity="info">
        You can't apply for an employer yet: {BRAND.administrator} hasn't added a fund for you. Ask them to set you up for the fund your
        employer wants to join.
      </Alert>
    );
  }

  return (
    <Stack component="form" spacing={2} onSubmit={submit}>
      <FormSection title="Fund" description="The fund your employer wants to join.">
        <TextField select label="Fund" value={fundId} onChange={(e) => setFundId(e.target.value)} required fullWidth sx={{ maxWidth: 480 }}>
          {fundOptions.map((f) => (
            <MenuItem key={f.id} value={f.id}>
              {f.name} ({f.code})
            </MenuItem>
          ))}
        </TextField>
      </FormSection>
      <FormSection title="Organisation">
        <FormGrid>
          <Field label="Organisation name" value={details.name} onChange={set("name")} required slotProps={{ htmlInput: { minLength: 2 } }} />
          <Field label="Registration number" value={details.registration_number} onChange={set("registration_number")} />
          <Field label="TPIN" value={details.tpin} onChange={set("tpin")} />
          <Field label="Address" value={details.address_line1} onChange={set("address_line1")} />
          <Field label="Address line 2" value={details.address_line2} onChange={set("address_line2")} />
          <Field label="Town / district" value={details.address_line3} onChange={set("address_line3")} />
          <Field label="Phone" type="tel" value={details.phone} onChange={set("phone")} />
          <Field label="Email" type="email" value={details.email} onChange={set("email")} />
        </FormGrid>
      </FormSection>
      <FormSection title="Contact person" description="Who the administrator talks to about contributions.">
        <FormGrid>
          <Field label="Name" value={details.contact_name} onChange={set("contact_name")} />
          <Field label="Email" type="email" value={details.contact_email} onChange={set("contact_email")} />
          <Field label="Phone" type="tel" value={details.contact_phone} onChange={set("contact_phone")} />
        </FormGrid>
      </FormSection>
      <FormSection title="Contributions">
        <FormGrid>
          <Field
            label="First contribution month"
            type="month"
            value={details.join_date?.slice(0, 7)}
            onChange={(v) => setDetails((d) => ({ ...d, join_date: v ? `${v}-01` : null }))}
            slotProps={{ inputLabel: { shrink: true } }}
          />
          <Field
            label="Due day of the following month"
            type="number"
            value={details.contribution_day}
            onChange={set("contribution_day")}
            helperText="1 to 28 — e.g. 14 means each month's contributions are paid by the 14th of the next month."
            slotProps={{ htmlInput: { min: 1, max: 28 } }}
          />
        </FormGrid>
      </FormSection>
      <FormSection
        title="Categories of members"
        description="Groups of members with the same contribution rates, e.g. Staff and Management. The administrator checks them against the statutory minimums and may adjust them before approving."
        action={<Button onClick={() => setCats((c) => [...c, { ...EMPTY_CATEGORY }])} disabled={cats.length >= 10}>Add category</Button>}
      >
        <Stack spacing={1.5}>
          {cats.map((c, i) => (
            <RepeatRow key={i} label={c.name || `Category ${i + 1}`} onRemove={() => setCats((list) => list.filter((_, j) => j !== i))}>
              <Field label="Name" value={c.name} onChange={(v) => setCat(i, { name: v })} required />
              <Field label="Employee contribution %" type="number" value={c.employee_rate} onChange={(v) => setCat(i, { employee_rate: v })} slotProps={{ htmlInput: { min: 0, max: 100, step: "0.01" } }} required />
              <Field label="Employer contribution %" type="number" value={c.employer_rate} onChange={(v) => setCat(i, { employer_rate: v })} slotProps={{ htmlInput: { min: 0, max: 100, step: "0.01" } }} required />
              <TextField select label="Salary basis" value={c.salary_basis} onChange={(e) => setCat(i, { salary_basis: e.target.value as SalaryBasis })} fullWidth>
                {(Object.keys(SALARY_BASIS_LABELS) as SalaryBasis[]).map((k) => (
                  <MenuItem key={k} value={k}>{SALARY_BASIS_LABELS[k]}</MenuItem>
                ))}
              </TextField>
              <Field label="Normal retirement age" type="number" value={c.normal_retirement_age} onChange={(v) => setCat(i, { normal_retirement_age: Number(v) })} slotProps={{ htmlInput: { min: 40, max: 80 } }} required />
            </RepeatRow>
          ))}
          {cats.length === 0 && <Typography color="text.secondary">Add at least one category.</Typography>}
        </Stack>
      </FormSection>
      {error && <Alert severity="error">{error}</Alert>}
      <Box>
        <Button type="submit" variant="contained" disabled={busy}>
          {busy ? "Saving…" : app ? "Save changes" : "Save and continue"}
        </Button>
      </Box>
    </Stack>
  );
}

function KycStep({ app }: { app: EmployerApplication }) {
  const start = useStartApplicationKyc();
  const navigate = useNavigate();
  const feedback = useFeedback();
  const kycPath = (id: string) => `/po/kyc/${id}?application=${app.id}`;
  const status = app.kyc_status ? KYC_STATUS_TEXT[app.kyc_status as KycStatus] : null;

  async function begin() {
    try {
      const k = await start.mutateAsync(app.id);
      navigate(kycPath(k.id));
    } catch (e) {
      feedback.error(e instanceof Error ? e.message : "Couldn't start the KYC.");
    }
  }

  return (
    <FormSection title="Organisation KYC" description="The organisation's details, directors and documents (know-your-customer). Compliance reviews it.">
      {app.kyc_application_id && status ? (
        <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} sx={{ alignItems: { sm: "center" } }}>
          <Typography>{app.kyc_reference}</Typography>
          <StatusChip status={app.kyc_status!} label={status.label} tone={status.tone} />
          <Button component={RouterLink} to={kycPath(app.kyc_application_id)} variant="outlined">
            {app.kyc_status === "draft" || app.kyc_status === "returned" ? "Continue KYC" : "View KYC"}
          </Button>
        </Stack>
      ) : (
        <Button variant="outlined" onClick={begin} disabled={start.isPending || !app.can_edit}>
          Start organisation KYC
        </Button>
      )}
    </FormSection>
  );
}

function Summary({ app }: { app: EmployerApplication }) {
  const terms = app.final_terms;
  return (
    <>
      <DetailSection title="Organisation">
        <DetailField label="Fund">{app.fund_name}</DetailField>
        <DetailField label="Organisation name">{app.details.name}</DetailField>
        {DETAIL_TEXT.filter(([k]) => app.details[k]).map(([k, label]) => (
          <DetailField key={k} label={label}>{app.details[k] as string}</DetailField>
        ))}
        <DetailField label="First contribution month">{formatPeriod(app.details.join_date)}</DetailField>
        <DetailField label="Due day">{app.details.contribution_day ? `${app.details.contribution_day} of the following month` : null}</DetailField>
      </DetailSection>
      <Paper sx={{ p: { xs: 2, sm: 3 } }}>
        <Typography variant="subtitle1" component="h2" sx={{ fontWeight: 600, mb: 1.5 }}>
          {terms ? "Categories — final terms" : "Categories as proposed"}
        </Typography>
        <Stack spacing={1}>
          {terms
            ? terms.categories.map((c) => (
                <Typography key={c.code} variant="body2">
                  <strong>{c.name}</strong> ({c.code}): employee {c.terms.employee_rate}%, employer {c.terms.employer_rate}% of{" "}
                  {SALARY_BASIS_LABELS[c.terms.salary_basis].toLowerCase()}, retirement at {c.terms.normal_retirement_age}
                </Typography>
              ))
            : app.categories.map((c) => (
                <Typography key={c.name} variant="body2">
                  <strong>{c.name}</strong>: employee {c.employee_rate}%, employer {c.employer_rate}% of {SALARY_BASIS_LABELS[c.salary_basis].toLowerCase()},
                  retirement at {c.normal_retirement_age}
                </Typography>
              ))}
        </Stack>
      </Paper>
    </>
  );
}

// An officer's application for a new employer to join a fund (decided 2026-11-03):
// details + categories, the organisation KYC, then send; the administrator
// reviews, may adjust the terms, and approves — the employer then appears under My schemes.
export function PoApplicationPage() {
  const { applicationId } = useParams();
  const isNew = applicationId === "new";
  const navigate = useNavigate();
  const feedback = useFeedback();
  const query = useMyApplication(isNew ? undefined : applicationId);
  const submit = useSubmitApplication();
  const withdraw = useWithdrawApplication();
  if (!isNew && query.isLoading) return <LoadingState />;
  if (!isNew && (query.error || !query.data)) return <Alert severity="error">{query.error?.message ?? "Application not found"}</Alert>;
  const app = isNew ? null : query.data!;
  const status = app ? APPLICATION_STATUS_TEXT[app.status] : null;

  async function send() {
    try {
      await submit.mutateAsync(app!.id);
      feedback.success(`Sent to ${BRAND.administrator}. You'll be told by email when it's decided.`);
    } catch (e) {
      feedback.error(e instanceof Error ? e.message : "Couldn't send it.");
    }
  }

  async function doWithdraw() {
    if (!window.confirm("Withdraw this application? The administrator will stop reviewing it. You can start a new one later.")) return;
    try {
      await withdraw.mutateAsync(app!.id);
      feedback.success("Application withdrawn.");
    } catch (e) {
      feedback.error(e instanceof Error ? e.message : "Couldn't withdraw it.");
    }
  }

  return (
    <Stack spacing={2} sx={{ maxWidth: 1040 }}>
      <Breadcrumbs>
        <Link component={RouterLink} to="/po" underline="hover" color="inherit">
          My schemes
        </Link>
        <Typography color="text.primary">{app ? app.reference : "Apply for an employer"}</Typography>
      </Breadcrumbs>
      <div>
        <Typography variant="h1">{app?.details.name || "Apply for an employer to join a fund"}</Typography>
        {app && status && (
          <Stack direction="row" spacing={1} sx={{ alignItems: "center", mt: 0.5, flexWrap: "wrap", gap: 1 }}>
            <Typography color="text.secondary">
              {app.fund_name} · {app.reference}
            </Typography>
            <StatusChip status={app.status} label={status.label} tone={status.tone} />
          </Stack>
        )}
      </div>
      {app?.status === "returned" && app.review_note && <Alert severity="warning">Sent back by {BRAND.administrator}: {app.review_note}</Alert>}
      {app && ["submitted", "in_approval"].includes(app.status) && (
        <Alert severity="info">
          Sent {formatDateTime(app.submitted_at)} — {BRAND.administrator} is reviewing the details and the organisation KYC — you'll be told by email
          when it's decided, or if anything needs changing.
        </Alert>
      )}
      {app?.status === "approved" && app.scheme_id && (
        <Alert
          severity="success"
          action={<Button color="inherit" size="small" component={RouterLink} to={`/po/schemes/${app.scheme_id}`}>Open employer</Button>}
        >
          Approved {formatDate(app.decided_at)}: the employer is set up. You can now add its members and send contribution schedules.
          {app.review_note ? ` Note: ${app.review_note}` : ""}
        </Alert>
      )}
      {app?.status === "rejected" && <Alert severity="error">Not accepted: {app.review_note}</Alert>}

      {(isNew || app?.can_edit) && (
        <ApplicationForm key={app?.id ?? "new"} app={app} onSaved={(saved) => isNew && navigate(applicationPath(saved.id), { replace: true })} />
      )}
      {app && <KycStep app={app} />}
      {app && !app.can_edit && <Summary app={app} />}
      {app?.can_edit && (
        <Paper sx={{ p: { xs: 2, sm: 3 } }}>
          <Typography variant="subtitle1" component="h2" sx={{ fontWeight: 600, mb: 1 }}>
            Send the application
          </Typography>
          {app.problems.length > 0 ? (
            <Alert severity="warning" sx={{ mb: 2 }}>
              Before you can send it:
              <Box component="ul" sx={{ m: 0, pl: 2.5 }}>
                {app.problems.map((p) => (
                  <li key={p}>{p}</li>
                ))}
              </Box>
            </Alert>
          ) : (
            <Typography color="text.secondary" sx={{ mb: 2 }}>
              Everything is filled in. Save any changes above first, then send it to {BRAND.administrator}.
            </Typography>
          )}
          <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5}>
            <Button variant="contained" onClick={send} disabled={app.problems.length > 0 || submit.isPending}>
              Send to {BRAND.administrator}
            </Button>
            <Button color="error" onClick={doWithdraw}>Withdraw application</Button>
          </Stack>
        </Paper>
      )}
      {app?.status === "submitted" && (
        <Box>
          <Button color="error" onClick={doWithdraw}>Withdraw application</Button>
        </Box>
      )}
    </Stack>
  );
}
