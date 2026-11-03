import { useRef, useState } from "react";
import { Link as RouterLink, useParams } from "react-router-dom";
import Alert from "@mui/material/Alert";
import Breadcrumbs from "@mui/material/Breadcrumbs";
import Button from "@mui/material/Button";
import Link from "@mui/material/Link";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { useQueryClient } from "@tanstack/react-query";
import { BRAND } from "../../brand";
import { DetailField, DetailSection } from "../../components/DetailSection";
import { LoadingState } from "../../components/LoadingState";
import { StatusChip } from "../../components/StatusChip";
import { useFeedback } from "../../components/feedback/FeedbackProvider";
import { openPaymentDocument, uploadPaymentProof, viewPaymentProof } from "../../api/po";
import { PAYMENT_METHOD_LABELS } from "../../api/receipts";
import { poKeys, usePayment } from "../../queries/po";
import { formatDate, formatDateTime, formatPeriod } from "../../utils/date";
import { formatMoney } from "../../utils/format";
import { PAYMENT_TEXT, SCHEDULE_TEXT } from "./poLabels";
import { schemePath } from "./PoSchemePage";

// A payment notice and, once the money is confirmed, its receipt (/po/remittances/<id> —
// the link in "payment received" / "not confirmed" notifications).
export function PoPaymentPage() {
  const { paymentId } = useParams();
  const query = usePayment(paymentId);
  const feedback = useFeedback();
  const queryClient = useQueryClient();
  const fileInput = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);

  if (query.isLoading) return <LoadingState />;
  if (query.error || !query.data) return <Alert severity="error">{query.error?.message ?? "Payment not found"}</Alert>;
  const p = query.data;
  const status = PAYMENT_TEXT[p.status];
  const title = p.receipt_number ? `Receipt ${p.receipt_number}` : `Payment notice ${p.notice_number}`;

  async function upload(file: File) {
    setUploading(true);
    try {
      const updated = await uploadPaymentProof(p.id, file);
      queryClient.setQueryData(poKeys.payment(p.id), updated);
      feedback.success("Proof of payment attached.");
    } catch (e) {
      feedback.error(e instanceof Error ? e.message : "Couldn't attach the file.");
    } finally {
      setUploading(false);
    }
  }

  return (
    <Stack spacing={2} sx={{ maxWidth: 1040 }}>
      <Breadcrumbs>
        <Link component={RouterLink} to="/po" underline="hover" color="inherit">My schemes</Link>
        <Link component={RouterLink} to={schemePath(p.scheme_id)} underline="hover" color="inherit">{p.scheme_name}</Link>
        <Typography color="text.primary">{p.receipt_number ?? p.notice_number}</Typography>
      </Breadcrumbs>
      <Stack direction={{ xs: "column", sm: "row" }} spacing={2} sx={{ justifyContent: "space-between", alignItems: { sm: "flex-start" } }}>
        <div>
          <Typography variant="h1">{title}</Typography>
          <StatusChip status={p.status} label={status.label} tone={status.tone} sx={{ mt: 1 }} />
        </div>
        {p.document_kind && (
          <Button variant="outlined" onClick={() => openPaymentDocument(p.id).catch((e) => feedback.error(e.message))}>
            {p.document_kind === "receipt" ? "Download receipt (PDF)" : "Download acknowledgement (PDF)"}
          </Button>
        )}
      </Stack>
      {p.status === "notified" && (
        <Alert severity="info">
          Received, pending confirmation — this is not a receipt yet. Once the money shows on the bank statement, {BRAND.administrator} confirms it
          and you get the receipt here and by email.
        </Alert>
      )}
      {p.status === "rejected" && <Alert severity="error">We couldn't confirm this payment: {p.rejection_reason}</Alert>}
      {p.status === "confirmed" && (
        <Alert severity="success">
          Payment confirmed {p.confirmed_at ? formatDateTime(p.confirmed_at) : ""} — receipt {p.receipt_number}.
        </Alert>
      )}
      <DetailSection title="Payment">
        <DetailField label="Amount">{formatMoney(p.amount ?? p.notified_amount)}</DetailField>
        <DetailField label="Paid on">{formatDate(p.payment_date)}</DetailField>
        <DetailField label="Paid by">{PAYMENT_METHOD_LABELS[p.payment_method]}</DetailField>
        <DetailField label="Your reference">{p.payer_reference ?? "—"}</DetailField>
        <DetailField label="For contributions of">{p.month ? formatPeriod(p.month) : "Not given"}</DetailField>
        {p.value_date && <DetailField label="In the bank on">{formatDate(p.value_date)}</DetailField>}
        {p.notice_number && <DetailField label="Notice number">{p.notice_number}</DetailField>}
        {p.notes && <DetailField label="Note">{p.notes}</DetailField>}
      </DetailSection>
      <Paper sx={{ p: { xs: 2, sm: 3 } }}>
        <Typography variant="subtitle1" component="h2" sx={{ fontWeight: 600, mb: 1 }}>
          Proof of payment
        </Typography>
        <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} sx={{ alignItems: { sm: "center" } }}>
          <Typography color={p.has_proof ? "text.primary" : "text.secondary"} sx={{ flex: 1 }}>
            {p.has_proof ? p.proof_filename : p.can_add_proof ? "None yet — attach the bank slip or transfer confirmation (PDF or photo, up to 10 MB)." : "None attached."}
          </Typography>
          {p.has_proof && <Button onClick={() => viewPaymentProof(p.id).catch((e) => feedback.error(e.message))}>View</Button>}
          {p.can_add_proof && (
            <Button variant={p.has_proof ? "text" : "contained"} onClick={() => fileInput.current?.click()} disabled={uploading}>
              {uploading ? "Uploading…" : p.has_proof ? "Replace" : "Attach file"}
            </Button>
          )}
          <input ref={fileInput} type="file" hidden accept=".pdf,image/jpeg,image/png,image/webp"
            onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) void upload(f); }} />
        </Stack>
      </Paper>
      {p.month && (
        <Paper sx={{ p: { xs: 2, sm: 3 } }}>
          <Typography variant="subtitle1" component="h2" sx={{ fontWeight: 600, mb: 1 }}>
            {formatPeriod(p.month)} schedule
          </Typography>
          {p.schedules.length === 0 ? (
            <Typography color="text.secondary">
              No schedule sent for {formatPeriod(p.month)} yet — members are credited only once the schedule arrives.{" "}
              <Link component={RouterLink} to={schemePath(p.scheme_id)}>Send it from Remittances.</Link>
            </Typography>
          ) : (
            p.schedules.map((s) => (
              <Stack key={s.id} direction="row" spacing={1} sx={{ alignItems: "center", flexWrap: "wrap" }} useFlexGap>
                <Link component={RouterLink} to={`/po/schedules/${s.id}`} underline="hover" sx={{ fontWeight: 600 }}>
                  {s.reference}
                </Link>
                <Typography color="text.secondary">{formatMoney(s.total)}</Typography>
                <StatusChip status={s.status} label={SCHEDULE_TEXT[s.status].label} tone={SCHEDULE_TEXT[s.status].tone} />
              </Stack>
            ))
          )}
        </Paper>
      )}
    </Stack>
  );
}
