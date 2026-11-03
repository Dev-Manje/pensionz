import { useState } from "react";
import { Link as RouterLink, useNavigate } from "react-router-dom";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Divider from "@mui/material/Divider";
import FormControlLabel from "@mui/material/FormControlLabel";
import Link from "@mui/material/Link";
import MenuItem from "@mui/material/MenuItem";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Switch from "@mui/material/Switch";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import useMediaQuery from "@mui/material/useMediaQuery";
import type { Theme } from "@mui/material/styles";
import { useQueryClient } from "@tanstack/react-query";
import { LoadingState } from "../../components/LoadingState";
import { StatusChip } from "../../components/StatusChip";
import { useFeedback } from "../../components/feedback/FeedbackProvider";
import { sendPaymentNotice, startPortalSchedule, type NoticeInput } from "../../api/po";
import { PAYMENT_METHOD_LABELS, type PaymentMethod } from "../../api/receipts";
import type { RemittanceMonth } from "../../api/types";
import { poKeys, useRemittances } from "../../queries/po";
import { formatDate, formatPeriod, todayIso } from "../../utils/date";
import { formatMoney } from "../../utils/format";
import { PAYMENT_TEXT, SCHEDULE_TEXT, STAGE_TEXT, recentMonths } from "./poLabels";
import { RemitCodeDialog } from "./RemitCodeDialog";

function lastMonth(): string {
  return recentMonths(new Date(), 2)[1];
}

function StartScheduleDialog({ schemeId, onClose }: { schemeId: string; onClose: () => void }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [month, setMonth] = useState(lastMonth());
  const [supplementary, setSupplementary] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function go() {
    setError(null);
    setBusy(true);
    try {
      const s = await startPortalSchedule(schemeId, month, supplementary);
      queryClient.invalidateQueries({ queryKey: poKeys.remittances(schemeId) });
      navigate(`/po/schedules/${s.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't start the schedule.");
      setBusy(false);
    }
  }

  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="xs">
      <DialogTitle>Send a contribution schedule</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <TextField select label="Contributions for" value={month} onChange={(e) => setMonth(e.target.value)}>
            {recentMonths(new Date()).map((m) => (
              <MenuItem key={m} value={m}>
                {formatPeriod(m)}
              </MenuItem>
            ))}
          </TextField>
          <FormControlLabel
            control={<Switch checked={supplementary} onChange={(e) => setSupplementary(e.target.checked)} />}
            label="Supplementary (back pay or a correction to a month already sent)"
          />
          <Typography variant="body2" color="text.secondary">
            The schedule starts with every active member at the amounts their salary and rates give. Change what's different, or download
            the spreadsheet, fill it in and upload it.
          </Typography>
          {error && <Alert severity="error">{error}</Alert>}
        </Stack>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" onClick={go} disabled={busy}>
          {busy ? "Starting…" : "Start"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

function NoticeDialog({ schemeId, onClose }: { schemeId: string; onClose: () => void }) {
  const fullScreen = useMediaQuery((t: Theme) => t.breakpoints.down("sm"));
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const feedback = useFeedback();
  const [v, setV] = useState({ amount: "", payment_date: todayIso(), payment_method: "eft" as PaymentMethod, payer_reference: "", month: lastMonth(), notes: "" });
  const [confirming, setConfirming] = useState(false);
  const amount = v.amount.replace(/,/g, "").trim();
  const valid = Number(amount) > 0 && !!v.payment_date && v.payment_date <= todayIso();
  const body: NoticeInput = {
    amount, payment_date: v.payment_date, payment_method: v.payment_method, payer_reference: v.payer_reference.trim() || null,
    contribution_month: v.month || null, notes: v.notes.trim() || null,
  };

  async function send(code: string) {
    const notice = await sendPaymentNotice(schemeId, body, code);
    queryClient.invalidateQueries({ queryKey: ["po"] });
    feedback.success(`Payment notice ${notice.notice_number} sent — received, pending confirmation.`);
    navigate(`/po/remittances/${notice.id}`);
  }

  if (confirming) {
    return (
      <RemitCodeDialog title="Confirm the payment notice" confirmLabel="Send notice" onConfirm={send} onClose={() => setConfirming(false)}>
        <Typography>
          {formatMoney(amount)} paid by {PAYMENT_METHOD_LABELS[v.payment_method]} on {formatDate(v.payment_date)}
          {v.month ? `, for ${formatPeriod(v.month)} contributions` : ""}.
        </Typography>
      </RemitCodeDialog>
    );
  }

  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="sm" fullScreen={fullScreen}>
      <DialogTitle>Tell us about a payment</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <Typography color="text.secondary">
            Once you have paid into the fund's bank account, tell us here. We confirm it against the bank statement and send you a receipt.
          </Typography>
          <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
            <TextField label="Amount paid (MWK)" value={v.amount} onChange={(e) => setV({ ...v, amount: e.target.value })} inputMode="decimal" fullWidth autoFocus />
            <TextField label="Payment date" type="date" value={v.payment_date} onChange={(e) => setV({ ...v, payment_date: e.target.value })}
              slotProps={{ inputLabel: { shrink: true }, htmlInput: { max: todayIso() } }} fullWidth />
          </Stack>
          <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
            <TextField select label="Paid by" value={v.payment_method} onChange={(e) => setV({ ...v, payment_method: e.target.value as PaymentMethod })} fullWidth>
              {(Object.keys(PAYMENT_METHOD_LABELS) as PaymentMethod[]).map((m) => (
                <MenuItem key={m} value={m}>
                  {PAYMENT_METHOD_LABELS[m]}
                </MenuItem>
              ))}
            </TextField>
            <TextField label="Your reference" value={v.payer_reference} onChange={(e) => setV({ ...v, payer_reference: e.target.value })}
              helperText="As it shows on the bank transfer" fullWidth />
          </Stack>
          <TextField select label="For contributions of" value={v.month} onChange={(e) => setV({ ...v, month: e.target.value })}>
            {recentMonths(new Date()).map((m) => (
              <MenuItem key={m} value={m}>
                {formatPeriod(m)}
              </MenuItem>
            ))}
            <MenuItem value="">Several months / not sure</MenuItem>
          </TextField>
          <TextField label="Note (optional)" value={v.notes} onChange={(e) => setV({ ...v, notes: e.target.value })} multiline minRows={2} />
          <Typography variant="body2" color="text.secondary">You can attach the bank slip or transfer confirmation on the next page.</Typography>
        </Stack>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" onClick={() => setConfirming(true)} disabled={!valid}>
          Continue
        </Button>
      </DialogActions>
    </Dialog>
  );
}

function MonthCard({ m }: { m: RemittanceMonth }) {
  const stage = STAGE_TEXT[m.stage];
  const outstanding = Number(m.schedule_total) - Number(m.paid) - Number(m.noted);
  return (
    <Paper variant="outlined" sx={{ p: 2 }}>
      <Stack direction={{ xs: "column", sm: "row" }} spacing={1} sx={{ justifyContent: "space-between", alignItems: { sm: "center" }, mb: 1 }}>
        <Typography variant="subtitle1" component="h3" sx={{ fontWeight: 600 }}>
          {m.month ? `${formatPeriod(m.month)} contributions` : "Payments not linked to a month"}
        </Typography>
        {m.month && <StatusChip status={m.stage} label={stage.label} tone={stage.tone} sx={{ alignSelf: { xs: "flex-start", sm: "center" } }} />}
      </Stack>
      <Stack spacing={1} divider={<Divider flexItem />}>
        {m.schedules.map((s) => (
          <Stack key={s.id} direction={{ xs: "column", sm: "row" }} spacing={1} sx={{ justifyContent: "space-between" }}>
            <Box>
              <Link component={RouterLink} to={`/po/schedules/${s.id}`} underline="hover" sx={{ fontWeight: 600 }}>
                Schedule {s.reference}
              </Link>
              {s.supplementary && " (supplementary)"}
              <Typography variant="body2" color="text.secondary">
                {s.line_count} member{s.line_count === 1 ? "" : "s"} · {formatMoney(s.total)}
                {s.error_count > 0 && s.status === "draft" ? ` · ${s.error_count} row${s.error_count === 1 ? "" : "s"} to fix` : ""}
                {s.credited_at ? ` · credited ${formatDate(s.credited_at)}` : s.submitted_at ? ` · sent ${formatDate(s.submitted_at)}` : ""}
                {!s.from_portal ? " · prepared by your administrator" : ""}
              </Typography>
            </Box>
            <StatusChip status={s.status} label={SCHEDULE_TEXT[s.status].label} tone={SCHEDULE_TEXT[s.status].tone} sx={{ alignSelf: { xs: "flex-start", sm: "center" } }} />
          </Stack>
        ))}
        {m.payments.map((p) => (
          <Stack key={p.id} direction={{ xs: "column", sm: "row" }} spacing={1} sx={{ justifyContent: "space-between" }}>
            <Box>
              <Link component={RouterLink} to={`/po/remittances/${p.id}`} underline="hover" sx={{ fontWeight: 600 }}>
                {p.receipt_number ? `Receipt ${p.receipt_number}` : `Payment notice ${p.notice_number}`}
              </Link>
              <Typography variant="body2" color="text.secondary">
                {formatMoney(p.amount ?? p.notified_amount)} paid {formatDate(p.payment_date)}
                {p.rejection_reason ? ` · ${p.rejection_reason}` : ""}
              </Typography>
            </Box>
            <StatusChip status={p.status} label={PAYMENT_TEXT[p.status].label} tone={PAYMENT_TEXT[p.status].tone} sx={{ alignSelf: { xs: "flex-start", sm: "center" } }} />
          </Stack>
        ))}
        {m.schedules.length === 0 && m.payments.length === 0 && (
          <Typography variant="body2" color="text.secondary">
            Nothing sent yet. {stage.next}
          </Typography>
        )}
      </Stack>
      {m.month && m.schedules.length > 0 && outstanding > 0.005 && (
        <Typography variant="body2" sx={{ mt: 1, color: "warning.dark" }}>
          Payments cover {formatMoney(Number(m.paid) + Number(m.noted))} of the {formatMoney(m.schedule_total)} on the schedule —{" "}
          {formatMoney(outstanding)} still to pay.
        </Typography>
      )}
    </Paper>
  );
}

// The employer's remittances (FR-PRT-001): month by month, the schedules sent and
// the payments made, with where each has got to; start a schedule or a payment notice.
export function PoRemittances({ schemeId }: { schemeId: string }) {
  const query = useRemittances(schemeId);
  const [dialog, setDialog] = useState<"schedule" | "notice" | null>(null);

  return (
    <Stack spacing={2}>
      <Paper sx={{ p: { xs: 2, sm: 2.5 } }}>
        <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} sx={{ justifyContent: "space-between", alignItems: { sm: "center" } }}>
          <Typography color="text.secondary" sx={{ maxWidth: 560 }}>
            Each month: send the schedule (who gets what), pay into the fund's bank account, and tell us about the payment.
          </Typography>
          <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
            <Button variant="contained" onClick={() => setDialog("schedule")}>
              Send a schedule
            </Button>
            <Button variant="outlined" onClick={() => setDialog("notice")}>
              Tell us about a payment
            </Button>
          </Stack>
        </Stack>
      </Paper>
      {query.isLoading && <LoadingState />}
      {query.error && (
        <Alert severity="error" action={<Button color="inherit" size="small" onClick={() => query.refetch()}>Try again</Button>}>
          {query.error.message}
        </Alert>
      )}
      {query.data?.map((m) => <MonthCard key={m.month ?? "none"} m={m} />)}
      {dialog === "schedule" && <StartScheduleDialog schemeId={schemeId} onClose={() => setDialog(null)} />}
      {dialog === "notice" && <NoticeDialog schemeId={schemeId} onClose={() => setDialog(null)} />}
    </Stack>
  );
}
