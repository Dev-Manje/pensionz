import { useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import MenuItem from "@mui/material/MenuItem";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { DetailField, DetailSection } from "../../../components/DetailSection";
import { StatusChip } from "../../../components/StatusChip";
import { useFeedback } from "../../../components/feedback/FeedbackProvider";
import { approveKyc, rejectKyc, returnKyc, seniorDecideKyc, startKycReview } from "../../../api/kyc";
import { useKycAction, useKycOptions } from "../../../queries/kyc";
import { useListRows } from "../../../queries/setup";
import { formatDate, formatDateTime } from "../../../utils/date";
import type { KycApplication, RiskRating } from "../../../api/types";
import { KycDocuments } from "./KycDocuments";
import { KYC_STEPS, fieldLabel, getPath, isShown, type FieldDef } from "./kycSchema";

function useLabel() {
  const options = useKycOptions();
  const countries = useListRows("countries");
  const lists: Record<string, ReturnType<typeof useListRows>> = {
    countries,
    id_types: useListRows("id_types"),
    relationships: useListRows("relationships"),
    permit_types: useListRows("permit_types"),
    salutations: useListRows("salutations"),
    kyc_products: useListRows("kyc_products"),
    districts: useListRows("districts"),
    traditional_authorities: useListRows("traditional_authorities"),
    villages: useListRows("villages"),
  };
  return (field: FieldDef, value: unknown): string => {
    if (value === null || value === undefined || value === "" || (Array.isArray(value) && value.length === 0)) return "—";
    const rows = field.list ? lists[field.list]?.data ?? [] : [];
    switch (field.type) {
      case "yes_no":
      case "pep":
        return value ? "Yes" : "No";
      case "select":
        return ((options.data?.[field.optionsKey!] as { value: string; label: string }[] | undefined) ?? []).find((o) => o.value === value)?.label ?? String(value);
      case "list":
        return String(rows.find((r) => r.code === value)?.name ?? value);
      case "place":
        return String(rows.find((r) => r.id === value)?.name ?? "…");
      case "multi_list":
        return (value as string[]).map((c) => String(rows.find((r) => r.code === c)?.name ?? c)).join(", ");
      case "tags":
        return (value as string[]).join(", ");
      case "date":
        return formatDate(String(value));
      default:
        return String(value);
    }
  };
}

export function KycAnswers({ app }: { app: KycApplication }) {
  const label = useLabel();
  const data = app.data;
  return (
    <Stack spacing={2}>
      {KYC_STEPS[app.client_type].map((step) => {
        if (step.fields) {
          const fields = step.fields.filter((f) => isShown(f, data));
          return (
            <DetailSection key={step.key} title={step.title}>
              {fields.map((f) => (
                <DetailField key={f.name} label={f.label}>
                  {label(f, getPath(data, f.name))}
                </DetailField>
              ))}
            </DetailSection>
          );
        }
        if (step.people) {
          const people = (Array.isArray(data[step.people.name]) ? data[step.people.name] : []) as Record<string, unknown>[];
          return people.map((p, i) => (
            <DetailSection key={`${step.key}-${i}`} title={`${step.people!.singular} ${i + 1}`}>
              {step.people!.fields.filter((f) => isShown(f, p)).map((f) => (
                <DetailField key={f.name} label={f.label}>
                  {label(f, getPath(p, f.name))}
                </DetailField>
              ))}
            </DetailSection>
          ));
        }
        return null;
      })}
    </Stack>
  );
}

type Action = "return" | "approve" | "reject" | "senior_approve" | "senior_reject";

function ActionDialog({ app, action, onClose }: { app: KycApplication; action: Action; onClose: () => void }) {
  const feedback = useFeedback();
  const [note, setNote] = useState("");
  const [override, setOverride] = useState<RiskRating | "">("");
  const [error, setError] = useState<string | null>(null);
  const run = useKycAction(async () => {
    switch (action) {
      case "return":
        return returnKyc(app.id, note);
      case "approve":
        return approveKyc(app.id, note || null, override || null);
      case "reject":
        return rejectKyc(app.id, note);
      case "senior_approve":
        return seniorDecideKyc(app.id, true, note || null);
      case "senior_reject":
        return seniorDecideKyc(app.id, false, note);
    }
  });
  const text: Record<Action, { title: string; button: string; noteLabel: string; required: boolean; done: string }> = {
    return: { title: "Return to the applicant", button: "Return", noteLabel: "What needs to change", required: true, done: "Returned to the applicant." },
    approve: {
      title: app.risk_rating === "high" ? "Recommend approval" : "Approve the client",
      button: app.risk_rating === "high" ? "Recommend" : "Approve",
      noteLabel: "Note (required when changing the risk rating)",
      required: false,
      done: "Done.",
    },
    reject: { title: "Reject the application", button: "Reject", noteLabel: "Reason", required: true, done: "Application rejected." },
    senior_approve: { title: "Approve the high-risk client", button: "Approve", noteLabel: "Note", required: false, done: "Client approved." },
    senior_reject: { title: "Reject the high-risk client", button: "Reject", noteLabel: "Reason", required: true, done: "Application rejected." },
  };
  const t = text[action];

  async function go() {
    setError(null);
    try {
      const result = await run.mutateAsync(undefined);
      feedback.success(result.status === "awaiting_senior_approval" ? "Recommended — an administrator must approve this high-risk client." : t.done);
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
    }
  }

  return (
    <Dialog open onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>{t.title}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ pt: 1 }}>
          {action === "approve" && (
            <TextField select label="Risk rating" value={override || app.risk_rating || ""} onChange={(e) => setOverride(e.target.value as RiskRating)} helperText="Rated by the rules; change it only with a reason.">
              <MenuItem value="low">Low</MenuItem>
              <MenuItem value="medium">Medium</MenuItem>
              <MenuItem value="high">High (needs enhanced due diligence and an administrator's approval)</MenuItem>
            </TextField>
          )}
          <TextField label={t.noteLabel} value={note} onChange={(e) => setNote(e.target.value)} required={t.required} multiline minRows={3} fullWidth />
          {error && <Alert severity="error">{error}</Alert>}
        </Stack>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" color={action.includes("reject") ? "error" : "primary"} onClick={go} disabled={run.isPending || (t.required && !note.trim())}>
          {run.isPending ? "Saving…" : t.button}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

// An application as compliance (and anyone else) sees it once submitted.
export function KycReview({ app }: { app: KycApplication }) {
  const feedback = useFeedback();
  const start = useKycAction(() => startKycReview(app.id));
  const [action, setAction] = useState<Action | null>(null);
  const allAccepted = app.slots.every((s) => s.document?.review_status === "accepted");

  return (
    <Stack spacing={2}>
      {app.status === "submitted" && app.can_start_review && (
        <Alert
          severity="info"
          action={
            <Button color="inherit" onClick={() => start.mutateAsync(undefined).catch((e) => feedback.error(e instanceof Error ? e.message : "Couldn't start."))}>
              Start review
            </Button>
          }
        >
          This application is waiting for a compliance review.
        </Alert>
      )}
      {app.status === "awaiting_senior_approval" && (
        <Alert severity="warning">
          High risk — {app.recommended_by ?? "compliance"} recommends approval after enhanced due diligence
          {app.review_note ? `: “${app.review_note}”` : "."} An administrator who took no other part must decide.
        </Alert>
      )}
      {app.status === "approved" && app.party && (
        <Alert severity="success">
          Approved {app.decided_at ? formatDateTime(app.decided_at) : ""} by {app.decided_by}. Next KYC review due {formatDate(app.party.kyc_review_due)}.
        </Alert>
      )}
      {app.status === "rejected" && <Alert severity="error">Rejected by {app.decided_by}: {app.decision_reason}</Alert>}
      {app.party && app.status !== "approved" && (
        <Alert severity="info">
          A change to an approved client.{" "}
          {app.changed_fields.length > 0
            ? `Changed since the last approval: ${app.changed_fields.map((f) => fieldLabel(app.client_type, f)).join(", ")}.`
            : "No answers changed since the last approval — check the documents."}
        </Alert>
      )}

      <Paper sx={{ p: { xs: 2, sm: 3 } }}>
        <Stack direction={{ xs: "column", md: "row" }} spacing={3}>
          <Box sx={{ flex: 1 }}>
            <Typography variant="subtitle1" component="h2" sx={{ fontWeight: 600, mb: 1 }}>
              Risk
            </Typography>
            {app.risk_rating ? <StatusChip status={app.risk_rating} /> : <Typography color="text.secondary">Rated on submission</Typography>}
            {app.edd_required && (
              <Typography variant="body2" sx={{ mt: 1 }}>
                Enhanced due diligence required.
              </Typography>
            )}
            {app.risk_reasons.length > 0 && (
              <Box component="ul" sx={{ mt: 1, mb: 0, pl: 2.5 }}>
                {app.risk_reasons.map((r) => (
                  <li key={r}>
                    <Typography variant="body2">{r}</Typography>
                  </li>
                ))}
              </Box>
            )}
          </Box>
          <Box sx={{ flex: 1 }}>
            <Typography variant="subtitle1" component="h2" sx={{ fontWeight: 600, mb: 1 }}>
              Declaration
            </Typography>
            <Typography variant="body2">
              {app.declaration_accepted_by
                ? `Accepted by ${app.declaration_accepted_by} on ${formatDateTime(app.declaration_accepted_at)} (version ${app.declaration_version}).`
                : "Not accepted yet."}
            </Typography>
          </Box>
          <Box sx={{ flex: 1 }}>
            <Typography variant="subtitle1" component="h2" sx={{ fontWeight: 600, mb: 1 }}>
              Existing clients with the same name or ID
            </Typography>
            {app.possible_duplicates.length === 0 ? (
              <Typography variant="body2" color="text.secondary">
                None found.
              </Typography>
            ) : (
              app.possible_duplicates.map((p) => (
                <Typography key={p.id} variant="body2">
                  {p.name} {p.identifier ? `· ${p.identifier}` : ""} · review due {formatDate(p.kyc_review_due)}
                </Typography>
              ))
            )}
          </Box>
        </Stack>
      </Paper>

      <Typography variant="h6" component="h2">
        Documents
      </Typography>
      <KycDocuments app={app} mode={app.can_review ? "review" : "view"} />

      <Typography variant="h6" component="h2">
        Details
      </Typography>
      <KycAnswers app={app} />

      {(app.can_review || app.can_senior_decide) && (
        <Paper sx={{ p: 2, position: "sticky", bottom: 0, zIndex: 1 }} elevation={3}>
          <Stack direction={{ xs: "column", sm: "row" }} spacing={1} sx={{ justifyContent: "flex-end" }}>
            {app.can_review && (
              <>
                <Button color="error" onClick={() => setAction("reject")}>
                  Reject
                </Button>
                <Button variant="outlined" onClick={() => setAction("return")}>
                  Return for changes
                </Button>
                <Button variant="contained" onClick={() => setAction("approve")} disabled={!allAccepted} title={allAccepted ? undefined : "Accept every document first"}>
                  {app.risk_rating === "high" ? "Recommend approval" : "Approve"}
                </Button>
              </>
            )}
            {app.can_senior_decide && (
              <>
                <Button color="error" variant="outlined" onClick={() => setAction("senior_reject")}>
                  Reject
                </Button>
                <Button variant="contained" onClick={() => setAction("senior_approve")}>
                  Approve high-risk client
                </Button>
              </>
            )}
          </Stack>
          {app.can_review && !allAccepted && (
            <Typography variant="caption" color="text.secondary" sx={{ display: "block", textAlign: "right", mt: 0.5 }}>
              Accept every document to approve.
            </Typography>
          )}
        </Paper>
      )}
      {action && <ActionDialog app={app} action={action} onClose={() => setAction(null)} />}
    </Stack>
  );
}
