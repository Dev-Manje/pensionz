import { useEffect, useState } from "react";
import { Link as RouterLink, useParams } from "react-router-dom";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Breadcrumbs from "@mui/material/Breadcrumbs";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Link from "@mui/material/Link";
import MenuItem from "@mui/material/MenuItem";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import useMediaQuery from "@mui/material/useMediaQuery";
import { useTheme } from "@mui/material/styles";
import { useAuth } from "../../../auth/AuthContext";
import { DetailField, DetailSection } from "../../../components/DetailSection";
import { LoadingState } from "../../../components/LoadingState";
import { StatusChip } from "../../../components/StatusChip";
import { useFeedback } from "../../../components/feedback/FeedbackProvider";
import { FormGrid, RepeatRow } from "../../../components/form/FormLayout";
import { useInvestmentOptions } from "../../../queries/investmentOptions";
import {
  useApplication, useProposeTerms, useRejectApplication, useReturnApplication, useSuggestedTerms,
} from "../../../queries/employerApplications";
import { SALARY_BASIS_LABELS, type SalaryBasis } from "../../../api/types";
import type { EmployerApplication, FinalCategory, FinalTermsInput } from "../../../api/employerApplications";
import { formatDate, formatDateTime, formatPeriod } from "../../../utils/date";
import { APPLICATION_STAFF_TEXT } from "./onboardingLabels";

function NoteDialog({ title, label, confirm, onSend, onClose }: { title: string; label: string; confirm: string; onSend: (note: string) => Promise<void>; onClose: () => void }) {
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <Dialog open onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>{title}</DialogTitle>
      <DialogContent>
        <TextField label={label} value={note} onChange={(e) => setNote(e.target.value)} multiline minRows={3} fullWidth required sx={{ mt: 1 }} />
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onClose}>Cancel</Button>
        <Button
          variant="contained"
          disabled={!note.trim() || busy}
          onClick={async () => {
            setBusy(true);
            try {
              await onSend(note.trim());
            } finally {
              setBusy(false);
            }
          }}
        >
          {confirm}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

// Scheme setup's final terms: employer code, join date, each category's code
// and terms (the officer's rates prefilled; default investment option set here).
function TermsDialog({ app, onClose }: { app: EmployerApplication; onClose: () => void }) {
  const theme = useTheme();
  const fullScreen = useMediaQuery(theme.breakpoints.down("sm"));
  const suggested = useSuggestedTerms(app.id, true);
  const options = useInvestmentOptions(app.fund_id);
  const propose = useProposeTerms();
  const feedback = useFeedback();
  const [terms, setTerms] = useState<FinalTermsInput | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (suggested.data && !terms) setTerms(app.final_terms ?? suggested.data);
  }, [suggested.data]); // eslint-disable-line react-hooks/exhaustive-deps

  const setCat = (i: number, patch: Partial<FinalCategory["terms"]> & { code?: string; name?: string }) =>
    setTerms((t) =>
      t && {
        ...t,
        categories: t.categories.map((c, j) => {
          if (j !== i) return c;
          const { code, name, ...rest } = patch;
          return { code: code ?? c.code, name: name ?? c.name, terms: { ...c.terms, ...rest } };
        }),
      },
    );

  async function send() {
    if (!terms) return;
    setError(null);
    try {
      const input: FinalTermsInput = {
        ...terms,
        categories: terms.categories.map((c) => ({ ...c, terms: { ...c.terms, effective_from: terms.join_date } })),
      };
      await propose.mutateAsync({ id: app.id, input });
      feedback.success("Sent for approval — a scheme-setup checker approves it, then the employer is created.");
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't send it.");
    }
  }

  const active = (options.data ?? []).filter((o) => o.status === "active");
  return (
    <Dialog open onClose={onClose} maxWidth="md" fullWidth fullScreen={fullScreen}>
      <DialogTitle>Final terms for {app.details.name}</DialogTitle>
      <DialogContent>
        {!terms ? (
          <LoadingState />
        ) : (
          <Stack spacing={2} sx={{ pt: 1 }}>
            <Alert severity="info">
              Prefilled from the officer's proposal. Change anything needed — the officer sees the final terms once approved. Fees and
              investment options stay with scheme setup.
            </Alert>
            <FormGrid>
              <TextField label="Employer code" value={terms.code} onChange={(e) => setTerms({ ...terms, code: e.target.value.toUpperCase() })} required helperText="Up to 10 letters or digits, unique in the fund." />
              <TextField
                label="Join date"
                type="date"
                value={terms.join_date}
                onChange={(e) => setTerms({ ...terms, join_date: e.target.value })}
                required
                slotProps={{ inputLabel: { shrink: true } }}
                helperText="Category terms apply from this date."
              />
            </FormGrid>
            {terms.categories.map((c, i) => (
              <RepeatRow key={i} label={`${c.name} (${c.code})`} onRemove={() => setTerms({ ...terms, categories: terms.categories.filter((_, j) => j !== i) })}>
                <TextField label="Code" value={c.code} onChange={(e) => setCat(i, { code: e.target.value.toUpperCase() })} required />
                <TextField label="Name" value={c.name} onChange={(e) => setCat(i, { name: e.target.value })} required />
                <TextField label="Employee %" type="number" value={c.terms.employee_rate} onChange={(e) => setCat(i, { employee_rate: e.target.value })} required />
                <TextField label="Employer %" type="number" value={c.terms.employer_rate ?? ""} onChange={(e) => setCat(i, { employer_rate: e.target.value })} required />
                <TextField select label="Salary basis" value={c.terms.salary_basis} onChange={(e) => setCat(i, { salary_basis: e.target.value as SalaryBasis })}>
                  {(Object.keys(SALARY_BASIS_LABELS) as SalaryBasis[]).map((k) => (
                    <MenuItem key={k} value={k}>{SALARY_BASIS_LABELS[k]}</MenuItem>
                  ))}
                </TextField>
                <TextField label="Normal retirement age" type="number" value={c.terms.normal_retirement_age} onChange={(e) => setCat(i, { normal_retirement_age: Number(e.target.value) })} required />
                <TextField select label="Default investment option" value={c.terms.default_investment_option_id ?? ""} onChange={(e) => setCat(i, { default_investment_option_id: e.target.value || null })} required>
                  {active.map((o) => (
                    <MenuItem key={o.id} value={o.id}>{o.name}</MenuItem>
                  ))}
                </TextField>
                <TextField label="Waiting period (months)" type="number" value={c.terms.waiting_period_months ?? 0} onChange={(e) => setCat(i, { waiting_period_months: Number(e.target.value) })} />
                <TextField label="Group life (× salary)" type="number" value={c.terms.group_life_multiple ?? ""} onChange={(e) => setCat(i, { group_life_multiple: e.target.value || null })} />
              </RepeatRow>
            ))}
            <TextField
              label="Note to the officer (optional)"
              value={terms.note ?? ""}
              onChange={(e) => setTerms({ ...terms, note: e.target.value || null })}
              multiline
              minRows={2}
              helperText="e.g. why a rate was changed. Shown to the officer when approved."
            />
            {error && <Alert severity="error">{error}</Alert>}
          </Stack>
        )}
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" onClick={send} disabled={!terms || propose.isPending || terms.categories.length === 0}>
          {propose.isPending ? "Sending…" : "Send for approval"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

// One employer application for scheme setup: details, the officer's proposal,
// the KYC's progress, and the actions (return, reject, final terms → checker).
export function ApplicationReviewPage() {
  const { applicationId } = useParams();
  const { user } = useAuth();
  const query = useApplication(applicationId);
  const returnIt = useReturnApplication();
  const rejectIt = useRejectApplication();
  const feedback = useFeedback();
  const [dialog, setDialog] = useState<"return" | "reject" | "terms" | null>(null);
  if (query.isLoading) return <LoadingState />;
  if (query.error || !query.data) return <Alert severity="error">{query.error?.message ?? "Application not found"}</Alert>;
  const app = query.data;
  const st = APPLICATION_STAFF_TEXT[app.status];
  const canReview = (user?.roles.includes("scheme_config_maker") ?? false) && app.status === "submitted";
  const d = app.details;

  async function decide(kind: "return" | "reject", note: string) {
    try {
      await (kind === "return" ? returnIt : rejectIt).mutateAsync({ id: app.id, note });
      feedback.success(kind === "return" ? "Sent back to the officer." : "Application rejected; the officer has been told.");
      setDialog(null);
    } catch (e) {
      feedback.error(e instanceof Error ? e.message : "Something went wrong.");
    }
  }

  return (
    <Stack spacing={2} sx={{ maxWidth: 1100 }}>
      <Breadcrumbs>
        <Link component={RouterLink} to="/onboarding?tab=applications" underline="hover" color="inherit">
          Employer applications
        </Link>
        <Typography color="text.primary">{app.reference}</Typography>
      </Breadcrumbs>
      <Stack direction={{ xs: "column", md: "row" }} spacing={2} sx={{ justifyContent: "space-between", alignItems: { md: "flex-start" } }}>
        <div>
          <Typography variant="h1">{d.name}</Typography>
          <Stack direction="row" spacing={1} sx={{ alignItems: "center", mt: 0.5, flexWrap: "wrap", gap: 1 }}>
            <Typography color="text.secondary">
              {app.fund_name} · {app.reference} · from {app.officer_name} ({app.officer_email})
            </Typography>
            <StatusChip status={app.status} label={st.label} tone={st.tone} />
          </Stack>
        </div>
        {canReview && (
          <Stack direction={{ xs: "column", sm: "row" }} spacing={1} sx={{ flexShrink: 0, "& .MuiButton-root": { whiteSpace: "nowrap" } }}>
            <Button variant="contained" onClick={() => setDialog("terms")} disabled={app.problems.length > 0}>
              Set final terms
            </Button>
            <Button variant="outlined" onClick={() => setDialog("return")}>Return to officer</Button>
            <Button color="error" onClick={() => setDialog("reject")}>Reject</Button>
          </Stack>
        )}
      </Stack>
      {app.status === "submitted" && app.problems.length > 0 && <Alert severity="warning">{app.problems.join(". ")}.</Alert>}
      {app.pending_approval_id && (
        <Alert severity="info" action={<Button color="inherit" size="small" component={RouterLink} to={`/approvals/${app.pending_approval_id}`}>Open approval</Button>}>
          The final terms are waiting for a scheme-setup checker.
        </Alert>
      )}
      {app.status === "approved" && app.scheme_id && (
        <Alert severity="success" action={<Button color="inherit" size="small" component={RouterLink} to={`/funds/${app.fund_id}/employers/${app.scheme_id}`}>Open employer</Button>}>
          Approved {formatDate(app.decided_at)} — employer {app.final_terms?.code} created with {app.officer_name} as principal officer.
        </Alert>
      )}
      {app.review_note && app.status !== "approved" && <Alert severity="warning">Note to the officer: {app.review_note}</Alert>}

      <DetailSection title="Organisation">
        <DetailField label="Registration number">{d.registration_number}</DetailField>
        <DetailField label="TPIN">{d.tpin}</DetailField>
        <DetailField label="Address">{[d.address_line1, d.address_line2, d.address_line3].filter(Boolean).join(", ")}</DetailField>
        <DetailField label="Phone">{d.phone}</DetailField>
        <DetailField label="Email">{d.email}</DetailField>
        <DetailField label="Contact">{[d.contact_name, d.contact_email, d.contact_phone].filter(Boolean).join(" · ")}</DetailField>
        <DetailField label="First contribution month">{formatPeriod(d.join_date)}</DetailField>
        <DetailField label="Due day">{d.contribution_day ? `${d.contribution_day} of the following month` : null}</DetailField>
        <DetailField label="Sent">{formatDateTime(app.submitted_at)}</DetailField>
      </DetailSection>

      <Paper sx={{ p: { xs: 2, sm: 3 } }}>
        <Typography variant="subtitle1" component="h2" sx={{ fontWeight: 600, mb: 1.5 }}>
          Organisation KYC
        </Typography>
        {app.kyc_application_id ? (
          <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} sx={{ alignItems: { sm: "center" } }}>
            <Typography>{app.kyc_reference}</Typography>
            {app.kyc_status && <StatusChip status={app.kyc_status} />}
            <Button component={RouterLink} to={`/kyc/${app.kyc_application_id}`} variant="outlined" size="small">
              Open in KYC
            </Button>
          </Stack>
        ) : (
          <Typography color="text.secondary">Not started.</Typography>
        )}
        <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
          Compliance reviews the KYC in the KYC screen. The final terms can be sent for approval once it is approved.
        </Typography>
      </Paper>

      <Paper sx={{ p: { xs: 2, sm: 3 } }}>
        <Typography variant="subtitle1" component="h2" sx={{ fontWeight: 600, mb: 1.5 }}>
          {app.final_terms ? "Final terms" : "Categories as proposed by the officer"}
        </Typography>
        <Stack spacing={1}>
          {app.categories.map((c) => {
            const final = app.final_terms?.categories.find((f) => f.name === c.name);
            return (
              <Box key={c.name}>
                <Typography variant="body2">
                  <strong>{c.name}</strong>: employee {c.employee_rate}%, employer {c.employer_rate}% of {SALARY_BASIS_LABELS[c.salary_basis].toLowerCase()},
                  retirement at {c.normal_retirement_age}
                </Typography>
                {final && (final.terms.employee_rate !== c.employee_rate || final.terms.employer_rate !== c.employer_rate) && (
                  <Typography variant="body2" color="warning.main">
                    Final: employee {final.terms.employee_rate}%, employer {final.terms.employer_rate}%
                  </Typography>
                )}
              </Box>
            );
          })}
        </Stack>
      </Paper>

      {dialog === "terms" && <TermsDialog app={app} onClose={() => setDialog(null)} />}
      {dialog === "return" && (
        <NoteDialog title="Return to the officer" label="What needs changing" confirm="Return" onSend={(n) => decide("return", n)} onClose={() => setDialog(null)} />
      )}
      {dialog === "reject" && (
        <NoteDialog title="Reject the application" label="Reason (the officer sees it)" confirm="Reject" onSend={(n) => decide("reject", n)} onClose={() => setDialog(null)} />
      )}
    </Stack>
  );
}
