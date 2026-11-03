import { Link as RouterLink, useNavigate } from "react-router-dom";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Link from "@mui/material/Link";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";
import { useQueryClient } from "@tanstack/react-query";
import { BRAND } from "../../brand";
import { DetailField, DetailSection } from "../../components/DetailSection";
import { LoadingState } from "../../components/LoadingState";
import { ResponsiveTable } from "../../components/ResponsiveTable";
import { StatusChip } from "../../components/StatusChip";
import { useFeedback } from "../../components/feedback/FeedbackProvider";
import { startSchemeKyc } from "../../api/po";
import type { PortalKycApplication } from "../../api/types";
import { useKycAction } from "../../queries/kyc";
import { poKeys, useOrganisation } from "../../queries/po";
import { formatDate } from "../../utils/date";
import { EXPIRY_TEXT, KYC_STATUS_TEXT } from "./poLabels";

function InProgress({ app }: { app: PortalKycApplication }) {
  const what = app.is_change ? "Change of details" : "Your organisation's KYC";
  const returned = app.status === "returned";
  const editable = app.status === "draft" || returned;
  return (
    <Alert
      severity={returned ? "warning" : "info"}
      action={
        <Button component={RouterLink} to={`/po/kyc/${app.id}`} color="inherit" size="small">
          {editable ? "Continue" : "View"}
        </Button>
      }
    >
      <strong>
        {what} {app.reference}: {KYC_STATUS_TEXT[app.status].label.toLowerCase()}.
      </strong>{" "}
      {returned && app.review_note
        ? `Compliance asks: ${app.review_note}`
        : app.status === "draft"
          ? "Finish it and send it for review."
          : `It's with ${BRAND.administrator} for checking — you'll be told by email when it's decided.`}
    </Alert>
  );
}

function History({ rows }: { rows: PortalKycApplication[] }) {
  if (rows.length === 0) return null;
  return (
    <Paper sx={{ p: { xs: 2, sm: 3 } }}>
      <Typography variant="subtitle1" component="h2" sx={{ fontWeight: 600, mb: 1 }}>
        Earlier applications
      </Typography>
      <TableContainer>
        <ResponsiveTable size="small">
          <TableHead>
            <TableRow>
              <TableCell>Reference</TableCell>
              <TableCell>What</TableCell>
              <TableCell>Sent</TableCell>
              <TableCell>Outcome</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.map((a) => (
              <TableRow key={a.id}>
                <TableCell sx={{ fontWeight: 600 }}>
                  <Link component={RouterLink} to={`/po/kyc/${a.id}`} underline="hover">
                    {a.reference}
                  </Link>
                </TableCell>
                <TableCell>{a.is_change ? "Change of details" : "First KYC"}</TableCell>
                <TableCell>{a.submitted_at ? formatDate(a.submitted_at) : "—"}</TableCell>
                <TableCell>
                  <StatusChip status={a.status} label={KYC_STATUS_TEXT[a.status].label} tone={KYC_STATUS_TEXT[a.status].tone} />
                  {a.decision_reason && (
                    <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
                      {a.decision_reason}
                    </Typography>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </ResponsiveTable>
      </TableContainer>
    </Paper>
  );
}

// The employer as a client (FR-PRT-001): its approved KYC details and documents,
// when the next review is due, and changes — every change goes through
// compliance as a KYC application prefilled from the approved details.
export function PoOrganisation({ schemeId }: { schemeId: string }) {
  const org = useOrganisation(schemeId);
  const navigate = useNavigate();
  const feedback = useFeedback();
  const queryClient = useQueryClient();
  const start = useKycAction(() => startSchemeKyc(schemeId));

  async function begin() {
    try {
      const app = await start.mutateAsync(undefined);
      queryClient.invalidateQueries({ queryKey: poKeys.organisation(schemeId) });
      navigate(`/po/kyc/${app.id}`);
    } catch (e) {
      feedback.error(e instanceof Error ? e.message : "Couldn't start the application.");
    }
  }

  if (org.isLoading) return <LoadingState />;
  if (org.error || !org.data)
    return (
      <Alert severity="error" action={<Button color="inherit" size="small" onClick={() => org.refetch()}>Try again</Button>}>
        {org.error?.message ?? "Couldn't load the organisation details."}
      </Alert>
    );
  const o = org.data;
  const review = o.review_state ? EXPIRY_TEXT[o.review_state] : null;

  return (
    <Stack spacing={2}>
      {o.in_progress && <InProgress app={o.in_progress} />}
      {!o.has_client && !o.in_progress && (
        <Paper sx={{ p: { xs: 2.5, sm: 3 } }}>
          <Typography variant="h2" sx={{ mb: 1 }}>
            Verify your organisation
          </Typography>
          <Typography color="text.secondary" sx={{ mb: 2, maxWidth: 640 }}>
            The law requires {BRAND.administrator} to know who each employer is (KYC). Fill in your organisation's details, its directors,
            and upload the documents asked for — it takes about 15 minutes and you can save and come back.
          </Typography>
          <Button variant="contained" onClick={begin} disabled={start.isPending}>
            {start.isPending ? "Starting…" : "Start KYC"}
          </Button>
        </Paper>
      )}
      {o.has_client && (
        <Paper sx={{ p: { xs: 2.5, sm: 3 } }}>
          <Stack direction={{ xs: "column", sm: "row" }} spacing={2} sx={{ justifyContent: "space-between", alignItems: { sm: "center" } }}>
            <div>
              <Stack direction="row" spacing={1} sx={{ alignItems: "center", mb: 0.5 }}>
                <Typography variant="subtitle1" component="h2" sx={{ fontWeight: 600 }}>
                  KYC review
                </Typography>
                {review && <StatusChip status={o.review_state!} label={review.label} tone={review.tone} />}
              </Stack>
              <Typography variant="body2" color="text.secondary">
                Approved {o.approved_at ? formatDate(o.approved_at) : "—"} ({o.approved_reference}). Next review due by {formatDate(o.review_due)}.
              </Typography>
            </div>
            <Button variant="outlined" onClick={begin} disabled={start.isPending || !!o.in_progress} sx={{ alignSelf: { xs: "flex-start", sm: "center" } }}>
              {start.isPending ? "Starting…" : "Change details"}
            </Button>
          </Stack>
          {!o.in_progress && (
            <Typography variant="body2" color="text.secondary" sx={{ mt: 1.5 }}>
              Moved office, new directors, a new contact person, or a document about to expire? Use “Change details” — the form starts from
              what we hold, so change only what's different. Compliance checks the change before it takes effect.
            </Typography>
          )}
        </Paper>
      )}
      {o.details.length > 0 && (
        <DetailSection title="Organisation details">
          {o.details.map((d) => (
            <DetailField key={d.label} label={d.label}>
              {d.value}
            </DetailField>
          ))}
        </DetailSection>
      )}
      {o.people.length > 0 && (
        <DetailSection title={o.people_title}>
          {o.people.map((p, i) => (
            <DetailField key={`${p.name}-${i}`} label={p.role ?? "—"}>
              {p.name}
            </DetailField>
          ))}
        </DetailSection>
      )}
      {o.documents.length > 0 && (
        <Paper sx={{ p: { xs: 2, sm: 3 } }}>
          <Typography variant="subtitle1" component="h2" sx={{ fontWeight: 600, mb: 1 }}>
            Documents on file
          </Typography>
          <TableContainer>
            <ResponsiveTable size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Document</TableCell>
                  <TableCell>Type</TableCell>
                  <TableCell>Issued</TableCell>
                  <TableCell>Expires</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {o.documents.map((d) => (
                  <TableRow key={d.label}>
                    <TableCell sx={{ fontWeight: 600 }}>{d.label}</TableCell>
                    <TableCell>{d.type_label}</TableCell>
                    <TableCell>{d.issue_date ? formatDate(d.issue_date) : "—"}</TableCell>
                    <TableCell>
                      <Box component="span" sx={{ mr: 1 }}>
                        {d.expiry_date ? formatDate(d.expiry_date) : "Doesn't expire"}
                      </Box>
                      {d.state && d.state !== "current" && <StatusChip status={d.state} label={EXPIRY_TEXT[d.state].label} tone={EXPIRY_TEXT[d.state].tone} />}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </ResponsiveTable>
          </TableContainer>
        </Paper>
      )}
      <History rows={o.history} />
    </Stack>
  );
}
