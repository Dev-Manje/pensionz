import { useRef, useState } from "react";
import { Link as RouterLink, useParams } from "react-router-dom";
import Alert from "@mui/material/Alert";
import Breadcrumbs from "@mui/material/Breadcrumbs";
import Button from "@mui/material/Button";
import Link from "@mui/material/Link";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { DetailField, DetailSection } from "../../../components/DetailSection";
import { LoadingState } from "../../../components/LoadingState";
import { StatusChip } from "../../../components/StatusChip";
import { useFeedback } from "../../../components/feedback/FeedbackProvider";
import { useAuth } from "../../../auth/AuthContext";
import { openFile } from "../../../api/client";
import { useReceipt, useReceiptAction } from "../../../queries/receipts";
import { formatMoney } from "../../../utils/format";
import { formatDate, formatDateTime, formatPeriod } from "../../../utils/date";
import { PAYMENT_METHOD_LABELS } from "../../../api/receipts";
import { ConfirmNoticeDialog, DeclineNoticeDialog, IdentifyDialog } from "./ReceiptDialogs";

export function ReceiptDetailPage() {
  const { receiptId } = useParams();
  const query = useReceipt(receiptId);
  const { user } = useAuth();
  const feedback = useFeedback();
  const action = useReceiptAction(receiptId ?? "");
  const fileInput = useRef<HTMLInputElement>(null);
  const [dialog, setDialog] = useState<"confirm" | "decline" | "identify" | null>(null);

  if (query.isLoading) return <LoadingState />;
  if (query.error || !query.data) {
    return <Alert severity="error" action={<Button color="inherit" onClick={() => query.refetch()}>Retry</Button>}>{query.error?.message ?? "Couldn't load the receipt."}</Alert>;
  }
  const r = query.data;
  const title = r.receipt_number ?? r.notice_number ?? "Receipt";
  const isMaker = user?.roles.includes("contributions_officer") ?? false;
  const canAttach = isMaker && (r.status === "notified" || r.status === "pending_approval");

  async function attach(file: File | undefined) {
    if (!file) return;
    try {
      await action.mutateAsync({ action: "proof", file });
      feedback.success("Proof of payment attached.");
    } catch (e) {
      feedback.error(e instanceof Error ? e.message : "Couldn't attach the file.");
    }
  }

  return (
    <Stack spacing={2}>
      <Breadcrumbs>
        <Link component={RouterLink} to={`/contributions?fund=${r.fund_id}`} underline="hover" color="inherit">Contributions</Link>
        <Typography color="text.primary">{title}</Typography>
      </Breadcrumbs>
      <Stack direction={{ xs: "column", sm: "row" }} spacing={2} sx={{ justifyContent: "space-between", alignItems: { sm: "flex-start" } }}>
        <div>
          <Typography variant="h5" component="h1" sx={{ fontWeight: 600 }}>
            {r.status === "confirmed" ? `Receipt ${r.receipt_number}` : r.notice_number ? `Payment notice ${r.notice_number}` : "Money received"}
          </Typography>
          <Typography color="text.secondary">{r.employer ?? "Unidentified payer"} · {r.fund_code}</Typography>
          <StatusChip status={r.status} sx={{ mt: 1 }} />
        </div>
        <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: "wrap" }}>
          {r.can_confirm && <Button variant="contained" onClick={() => setDialog("confirm")}>Confirm against bank</Button>}
          {r.can_confirm && <Button color="error" onClick={() => setDialog("decline")}>Not received</Button>}
          {r.can_identify && <Button variant="contained" onClick={() => setDialog("identify")}>Identify employer</Button>}
          {r.document_kind && (
            <Button variant="outlined" onClick={() => openFile(`/receipts/${r.id}/document`)}>
              {r.document_kind === "receipt" ? "Print receipt" : "Print acknowledgement"}
            </Button>
          )}
        </Stack>
      </Stack>

      {r.status === "pending_approval" && r.approval_request_id && (
        <Alert severity="warning" action={<Button color="inherit" size="small" component={RouterLink} to={`/approvals/${r.approval_request_id}`}>View request</Button>}>
          Waiting for a contributions checker to confirm{r.captured_by ? ` (sent by ${r.captured_by})` : ""}. Nothing is posted until then.
        </Alert>
      )}
      {r.status === "notified" && (
        <Alert severity="info">
          The principal officer has been told this payment is received and pending confirmation. Check it against the fund's bank statement.
        </Alert>
      )}
      {r.status === "rejected" && <Alert severity="error">{r.rejection_reason ? `Not confirmed: ${r.rejection_reason}` : "Not confirmed by the checker."}</Alert>}
      {r.status === "confirmed" && !r.scheme_id && (
        <Alert severity="warning">Nobody has identified who sent this money yet, so it can't be allocated.</Alert>
      )}

      <DetailSection title="Money">
        {r.notified_amount && <DetailField label="Amount on the notice">{formatMoney(r.notified_amount)}</DetailField>}
        <DetailField label="Amount received">{r.amount ? formatMoney(r.amount) : "Not confirmed yet"}</DetailField>
        {r.status === "confirmed" && <DetailField label="Allocated">{formatMoney(r.allocated_amount)}</DetailField>}
        {r.status === "confirmed" && <DetailField label="Unallocated">{formatMoney(r.unallocated)}</DetailField>}
        <DetailField label="Paid by">{PAYMENT_METHOD_LABELS[r.payment_method]}</DetailField>
        <DetailField label="Payment date">{formatDate(r.payment_date)}</DetailField>
        <DetailField label="Value date">{r.value_date ? formatDate(r.value_date) : null}</DetailField>
        <DetailField label="Fund bank account">{r.bank_account}</DetailField>
        <DetailField label="Contributions for">{r.contribution_month ? formatPeriod(r.contribution_month) : null}</DetailField>
      </DetailSection>

      <DetailSection title="References">
        <DetailField label="Payer">{r.payer_name}</DetailField>
        <DetailField label="Payer's reference">{r.payer_reference}</DetailField>
        <DetailField label="Bank reference">{r.bank_reference}</DetailField>
        <DetailField label="Ledger entry">
          {r.journal_reference && <Link component={RouterLink} to={`/funds/${r.fund_id}?tab=ledger`}>{r.journal_reference}</Link>}
        </DetailField>
        <DetailField label="Proof of payment">
          {r.has_proof ? (
            <Link component="button" onClick={() => openFile(`/receipts/${r.id}/proof`)}>{r.proof_filename ?? "View"}</Link>
          ) : null}
          {canAttach && (
            <>
              <Button size="small" onClick={() => fileInput.current?.click()} sx={{ ml: r.has_proof ? 1 : 0 }}>
                {r.has_proof ? "Replace" : "Attach file"}
              </Button>
              <input ref={fileInput} type="file" hidden accept="application/pdf,image/*" onChange={(e) => attach(e.target.files?.[0])} />
            </>
          )}
        </DetailField>
        <DetailField label="Notes">{r.notes}</DetailField>
      </DetailSection>

      <DetailSection title="Trail">
        {r.notified_by && <DetailField label="Notice from">{`${r.notified_by} · ${formatDateTime(r.created_at)}`}</DetailField>}
        <DetailField label="Captured by">{r.captured_by}</DetailField>
        <DetailField label="Confirmed by">{r.confirmed_by ? `${r.confirmed_by} · ${formatDateTime(r.confirmed_at)}` : null}</DetailField>
      </DetailSection>

      {dialog === "confirm" && <ConfirmNoticeDialog receipt={r} onClose={() => setDialog(null)} />}
      {dialog === "decline" && <DeclineNoticeDialog receipt={r} onClose={() => setDialog(null)} />}
      {dialog === "identify" && <IdentifyDialog receipt={r} onClose={() => setDialog(null)} />}
    </Stack>
  );
}
