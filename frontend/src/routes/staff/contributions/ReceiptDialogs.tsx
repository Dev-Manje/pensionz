import { useState } from "react";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import MenuItem from "@mui/material/MenuItem";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import useMediaQuery from "@mui/material/useMediaQuery";
import type { Theme } from "@mui/material/styles";
import { useFeedback } from "../../../components/feedback/FeedbackProvider";
import { useFund } from "../../../queries/funds";
import { useSchemes } from "../../../queries/schemes";
import { useCaptureReceipt, useReceiptAction } from "../../../queries/receipts";
import { todayIso } from "../../../utils/date";
import { formatMoney } from "../../../utils/format";
import { PAYMENT_METHOD_LABELS, type PaymentMethod, type Receipt } from "../../../api/receipts";

const UNIDENTIFIED = "__unidentified__";
const monthValue = (iso: string | null | undefined) => (iso ? iso.slice(0, 7) : "");
const monthIso = (v: string) => (v ? `${v}-01` : null);

function useFullScreen() {
  return useMediaQuery((t: Theme) => t.breakpoints.down("sm"));
}

function BankAccountField({ fundId, value, onChange }: { fundId: string; value: string; onChange: (v: string) => void }) {
  const fund = useFund(fundId);
  const accounts = fund.data?.bank_accounts ?? [];
  return (
    <TextField select required label="Into fund bank account" value={value} onChange={(e) => onChange(e.target.value)}
      helperText={fund.data && !accounts.length ? "This fund has no bank account yet — add one in Funds → Bank accounts." : undefined}>
      {accounts.map((a) => (
        <MenuItem key={a.id} value={a.id}>
          {a.bank_name} · {a.account_name} ({a.account_number_masked})
        </MenuItem>
      ))}
    </TextField>
  );
}

// Money on the bank statement that came without a principal officer's notice.
export function RecordReceiptDialog({ fundId, onClose }: { fundId: string; onClose: () => void }) {
  const fullScreen = useFullScreen();
  const schemes = useSchemes(fundId);
  const capture = useCaptureReceipt(fundId);
  const feedback = useFeedback();
  const [error, setError] = useState<string | null>(null);
  const [v, setV] = useState({
    scheme: "", method: "eft" as PaymentMethod, paymentDate: todayIso(), valueDate: todayIso(), amount: "", account: "",
    payerName: "", payerReference: "", bankReference: "", month: "", notes: "",
  });
  const set = (k: keyof typeof v) => (e: { target: { value: string } }) => setV({ ...v, [k]: e.target.value });

  async function save() {
    setError(null);
    try {
      await capture.mutateAsync({
        scheme_id: v.scheme === UNIDENTIFIED ? null : v.scheme, payment_method: v.method, payment_date: v.paymentDate, value_date: v.valueDate,
        amount: v.amount.replace(/,/g, ""), bank_account_id: v.account, payer_name: v.payerName || undefined,
        payer_reference: v.payerReference || undefined, bank_reference: v.bankReference || undefined, contribution_month: monthIso(v.month),
        notes: v.notes || undefined,
      });
      feedback.success("Receipt sent to a contributions checker to confirm.");
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't record the receipt.");
    }
  }

  const ready = v.scheme && v.amount && v.account && v.paymentDate && v.valueDate;
  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="sm" fullScreen={fullScreen}>
      <DialogTitle>Record money received</DialogTitle>
      <DialogContent>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          For money on the fund's bank statement. It posts to Unallocated contributions once a contributions checker confirms it.
        </Typography>
        <Stack spacing={2}>
          <TextField select required label="From employer" value={v.scheme} onChange={set("scheme")}>
            {(schemes.data ?? []).map((s) => (
              <MenuItem key={s.id} value={s.id}>
                {s.code} — {s.name}
              </MenuItem>
            ))}
            <MenuItem value={UNIDENTIFIED}>
              <em>Not known yet (unidentified money)</em>
            </MenuItem>
          </TextField>
          <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
            <TextField required label="Amount (MWK)" value={v.amount} onChange={set("amount")} inputMode="decimal" fullWidth />
            <TextField select label="Paid by" value={v.method} onChange={set("method")} fullWidth>
              {(Object.keys(PAYMENT_METHOD_LABELS) as PaymentMethod[]).map((m) => (
                <MenuItem key={m} value={m}>{PAYMENT_METHOD_LABELS[m]}</MenuItem>
              ))}
            </TextField>
          </Stack>
          <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
            <TextField required type="date" label="Payment date" value={v.paymentDate} onChange={set("paymentDate")} slotProps={{ inputLabel: { shrink: true } }} fullWidth />
            <TextField required type="date" label="Value date" value={v.valueDate} onChange={set("valueDate")} slotProps={{ inputLabel: { shrink: true } }}
              helperText="When the money cleared into the fund's account" fullWidth />
          </Stack>
          <BankAccountField fundId={fundId} value={v.account} onChange={(account) => setV({ ...v, account })} />
          <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
            <TextField label="Payer name" value={v.payerName} onChange={set("payerName")} fullWidth />
            <TextField label="Payer's reference" value={v.payerReference} onChange={set("payerReference")} fullWidth />
          </Stack>
          <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
            <TextField label="Bank reference" value={v.bankReference} onChange={set("bankReference")} fullWidth />
            <TextField type="month" label="Contributions for" value={v.month} onChange={set("month")} slotProps={{ inputLabel: { shrink: true } }} fullWidth />
          </Stack>
          <TextField label="Notes" value={v.notes} onChange={set("notes")} multiline minRows={2} />
          {error && <Alert severity="error">{error}</Alert>}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" onClick={save} disabled={!ready || capture.isPending}>
          {capture.isPending ? "Sending…" : "Send for confirmation"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

// A principal officer's notice: staff found (or didn't find) the money on the statement.
export function ConfirmNoticeDialog({ receipt, onClose }: { receipt: Receipt; onClose: () => void }) {
  const fullScreen = useFullScreen();
  const action = useReceiptAction(receipt.id);
  const feedback = useFeedback();
  const [error, setError] = useState<string | null>(null);
  const [v, setV] = useState({
    valueDate: todayIso(), amount: receipt.notified_amount ?? "", account: "", bankReference: "",
    month: monthValue(receipt.contribution_month), notes: "",
  });
  const set = (k: keyof typeof v) => (e: { target: { value: string } }) => setV({ ...v, [k]: e.target.value });
  const differs = v.amount && receipt.notified_amount && Number(v.amount.replace(/,/g, "")) !== Number(receipt.notified_amount);

  async function save() {
    setError(null);
    try {
      await action.mutateAsync({
        action: "confirm",
        body: { value_date: v.valueDate, amount: v.amount.replace(/,/g, ""), bank_account_id: v.account, bank_reference: v.bankReference || undefined,
                contribution_month: monthIso(v.month), notes: v.notes || undefined },
      });
      feedback.success("Sent to a contributions checker to confirm.");
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't confirm the notice.");
    }
  }

  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="sm" fullScreen={fullScreen}>
      <DialogTitle>Confirm payment notice {receipt.notice_number}</DialogTitle>
      <DialogContent>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          {receipt.employer} says it paid {formatMoney(receipt.notified_amount)}. Enter what actually reached the fund's account.
        </Typography>
        <Stack spacing={2}>
          <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
            <TextField required label="Amount received (MWK)" value={v.amount} onChange={set("amount")} inputMode="decimal" fullWidth />
            <TextField required type="date" label="Value date" value={v.valueDate} onChange={set("valueDate")} slotProps={{ inputLabel: { shrink: true } }} fullWidth />
          </Stack>
          {differs && <Alert severity="warning">This differs from the amount on the notice. The difference stays with the employer to sort out.</Alert>}
          <BankAccountField fundId={receipt.fund_id} value={v.account} onChange={(account) => setV({ ...v, account })} />
          <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
            <TextField label="Bank reference" value={v.bankReference} onChange={set("bankReference")} fullWidth />
            <TextField type="month" label="Contributions for" value={v.month} onChange={set("month")} slotProps={{ inputLabel: { shrink: true } }} fullWidth />
          </Stack>
          <TextField label="Notes" value={v.notes} onChange={set("notes")} multiline minRows={2} />
          {error && <Alert severity="error">{error}</Alert>}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" onClick={save} disabled={!v.amount || !v.account || !v.valueDate || action.isPending}>
          {action.isPending ? "Sending…" : "Send for confirmation"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

export function DeclineNoticeDialog({ receipt, onClose }: { receipt: Receipt; onClose: () => void }) {
  const action = useReceiptAction(receipt.id);
  const feedback = useFeedback();
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function save() {
    setError(null);
    try {
      await action.mutateAsync({ action: "decline", reason });
      feedback.success("The employer has been told the payment couldn't be confirmed.");
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't decline the notice.");
    }
  }

  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>Money not received?</DialogTitle>
      <DialogContent>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          The principal officer is told why, so they can check with their bank or send a corrected notice.
        </Typography>
        <TextField label="Reason" value={reason} onChange={(e) => setReason(e.target.value)} multiline minRows={3} fullWidth autoFocus />
        {error && <Alert severity="error" sx={{ mt: 2 }}>{error}</Alert>}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button color="error" variant="contained" onClick={save} disabled={reason.trim().length < 5 || action.isPending}>
          Decline notice
        </Button>
      </DialogActions>
    </Dialog>
  );
}

export function IdentifyDialog({ receipt, onClose }: { receipt: Receipt; onClose: () => void }) {
  const schemes = useSchemes(receipt.fund_id);
  const action = useReceiptAction(receipt.id);
  const feedback = useFeedback();
  const [scheme, setScheme] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function save() {
    setError(null);
    try {
      await action.mutateAsync({ action: "identify", schemeId: scheme, note: note || undefined });
      feedback.success("Sent to a contributions checker to approve.");
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't place the money.");
    }
  }

  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>Whose money is this?</DialogTitle>
      <DialogContent>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          {formatMoney(receipt.unallocated)} from receipt {receipt.receipt_number} moves to the employer's unallocated money.
        </Typography>
        <Stack spacing={2}>
          <TextField select label="Employer" value={scheme} onChange={(e) => setScheme(e.target.value)}>
            {(schemes.data ?? []).map((s) => (
              <MenuItem key={s.id} value={s.id}>
                {s.code} — {s.name}
              </MenuItem>
            ))}
          </TextField>
          <TextField label="How it was identified" value={note} onChange={(e) => setNote(e.target.value)} multiline minRows={2} />
          {error && <Alert severity="error">{error}</Alert>}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" onClick={save} disabled={!scheme || action.isPending}>
          Send for approval
        </Button>
      </DialogActions>
    </Dialog>
  );
}
