import { useState } from "react";
import { Link as RouterLink, useParams } from "react-router-dom";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Breadcrumbs from "@mui/material/Breadcrumbs";
import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Link from "@mui/material/Link";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { useAuth } from "../../../auth/AuthContext";
import { DetailField, DetailSection } from "../../../components/DetailSection";
import { LoadingState } from "../../../components/LoadingState";
import { ResponsiveTable } from "../../../components/ResponsiveTable";
import { StatusChip } from "../../../components/StatusChip";
import { TableStateRow } from "../../../components/TableStateRow";
import { useFeedback } from "../../../components/feedback/FeedbackProvider";
import { useBonusRun, useDiscardRun, useRecalculateRun, useReverseRun, useSubmitRun } from "../../../queries/bonus";
import { COMPONENT_LABELS } from "../../../api/ledger";
import { formatDate, formatDateTime } from "../../../utils/date";
import { formatAmount, formatMoney } from "../../../utils/format";
import { RUN_STATUS_TEXT } from "./bonusLabels";

const num = { fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap" } as const;

function ReverseDialog({ runId, memberIds, onClose }: { runId: string; memberIds: string[]; onClose: () => void }) {
  const reverse = useReverseRun();
  const feedback = useFeedback();
  const [reason, setReason] = useState("");
  async function send() {
    try {
      await reverse.mutateAsync({ id: runId, reason, member_ids: memberIds.length ? memberIds : undefined });
      feedback.success("Reversal sent for approval — a finance checker approves it.");
      onClose();
    } catch (e) {
      feedback.error(e instanceof Error ? e.message : "Couldn't send it.");
    }
  }
  return (
    <Dialog open onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>{memberIds.length ? `Reverse bonus for ${memberIds.length} member(s)` : "Reverse the whole run"}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ pt: 1 }}>
          <Typography variant="body2" color="text.secondary">
            Posts Bonus Reversal (type 5) for what was credited, in the open processing month. The run can be calculated again afterwards.
          </Typography>
          <TextField label="Reason" value={reason} onChange={(e) => setReason(e.target.value)} required multiline minRows={2} />
        </Stack>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onClose}>Cancel</Button>
        <Button color="error" variant="contained" onClick={send} disabled={reason.trim().length < 3 || reverse.isPending}>
          Send for approval
        </Button>
      </DialogActions>
    </Dialog>
  );
}

// One bonus run: the preview per member and component with the working, then
// send → finance checker → posted; reversal of the run or chosen members.
export function BonusRunPage() {
  const { fundId, runId } = useParams();
  const { user } = useAuth();
  const isMaker = user?.roles.includes("finance") ?? false;
  const query = useBonusRun(runId);
  const submit = useSubmitRun();
  const recalc = useRecalculateRun();
  const discard = useDiscardRun();
  const feedback = useFeedback();
  const [selected, setSelected] = useState<string[]>([]);
  const [reversing, setReversing] = useState(false);
  if (query.isLoading) return <LoadingState />;
  if (query.error || !query.data) return <Alert severity="error">{query.error?.message ?? "Run not found"}</Alert>;
  const run = query.data;
  const d = run.declaration;
  const st = RUN_STATUS_TEXT[run.status];
  const posted = run.status === "posted";

  async function act(kind: "submit" | "recalc" | "discard") {
    try {
      if (kind === "submit") await submit.mutateAsync(run.id);
      if (kind === "recalc") await recalc.mutateAsync(run.id);
      if (kind === "discard") {
        if (!window.confirm("Discard this preview? Nothing has been posted.")) return;
        await discard.mutateAsync(run.id);
      }
      feedback.success(kind === "submit" ? "Sent to a finance checker. Nothing is posted until they approve." : kind === "recalc" ? "Recalculated." : "Preview discarded.");
    } catch (e) {
      feedback.error(e instanceof Error ? e.message : "Something went wrong.");
    }
  }
  const toggle = (id: string) => setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));
  const reversible = new Set(run.lines.filter((l) => !l.reversed && Number(l.amount) !== 0).map((l) => l.member_id));

  return (
    <Stack spacing={2} sx={{ maxWidth: 1200 }}>
      <Breadcrumbs>
        <Link component={RouterLink} to={`/funds/${fundId}?tab=bonus`} underline="hover" color="inherit">
          {run.fund_code} bonus
        </Link>
        <Typography color="text.primary">{run.reference}</Typography>
      </Breadcrumbs>
      <Stack direction={{ xs: "column", md: "row" }} spacing={2} sx={{ justifyContent: "space-between", alignItems: { md: "flex-start" } }}>
        <div>
          <Typography variant="h1">
            {run.kind === "final" ? "Final" : "Interim"} bonus {Number(d.rate).toLocaleString(undefined, { maximumFractionDigits: 4 })}% a year
          </Typography>
          <Stack direction="row" spacing={1} sx={{ alignItems: "center", mt: 0.5, flexWrap: "wrap", gap: 1 }}>
            <Typography color="text.secondary">
              {formatDate(d.period_start)} – {formatDate(d.period_end)} · {run.reference} · {d.reference}
            </Typography>
            <StatusChip status={run.status} label={st.label} tone={st.tone} />
          </Stack>
        </div>
        {isMaker && (
          <Stack direction={{ xs: "column", sm: "row" }} spacing={1} sx={{ flexShrink: 0, "& .MuiButton-root": { whiteSpace: "nowrap" } }}>
            {run.status === "draft" && (
              <>
                <Button variant="contained" onClick={() => act("submit")} disabled={submit.isPending}>Send for approval</Button>
                <Button variant="outlined" onClick={() => act("recalc")} disabled={recalc.isPending}>Recalculate</Button>
                <Button color="error" onClick={() => act("discard")}>Discard</Button>
              </>
            )}
            {posted && !run.pending_approval_id && (
              <Button color="error" variant="outlined" onClick={() => setReversing(true)}>
                {selected.length ? `Reverse ${selected.length} selected` : "Reverse whole run"}
              </Button>
            )}
          </Stack>
        )}
      </Stack>
      {run.status === "draft" && (
        <Alert severity="warning">This is a preview — nothing is posted until a finance checker approves it. Figures are checked again at approval.</Alert>
      )}
      {run.pending_approval_id && (
        <Alert severity="info" action={<Button color="inherit" size="small" component={RouterLink} to={`/approvals/${run.pending_approval_id}`}>Open approval</Button>}>
          Waiting for a finance checker.
        </Alert>
      )}
      <DetailSection title="Run">
        <DetailField label="Members">{run.member_count}</DetailField>
        <DetailField label="Bonus credited (type 6)">{formatMoney(run.total_credit)}</DetailField>
        <DetailField label="Bonus taken back (type 5)">{Number(run.total_debit) ? formatMoney(run.total_debit) : "—"}</DetailField>
        <DetailField label="Posting date">{formatDate(run.posting_date)}</DetailField>
        {run.as_at && <DetailField label="Calculated to">{formatDate(run.as_at)}</DetailField>}
        <DetailField label="Posted">{run.posted_at ? `${formatDateTime(run.posted_at)}${run.entry_ref ? ` · ${run.entry_ref}` : ""}` : null}</DetailField>
        <DetailField label="Earning components">{d.components.map((c) => COMPONENT_LABELS[c]).join(", ")}</DetailField>
      </DetailSection>
      <TableContainer component={Paper}>
        <ResponsiveTable size="small">
          <TableHead>
            <TableRow>
              {posted && <TableCell padding="checkbox" />}
              <TableCell>Member</TableCell>
              <TableCell>Component</TableCell>
              <TableCell align="right">Days</TableCell>
              <TableCell align="right">Opening balance</TableCell>
              <TableCell align="right">Movements</TableCell>
              <TableCell align="right">Calculated</TableCell>
              <TableCell align="right">Already credited</TableCell>
              <TableCell align="right">To post</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            <TableStateRow colSpan={posted ? 9 : 8} loading={false} error={null} empty="No member earns bonus in this run." count={run.lines.length} />
            {run.lines.map((l) => (
              <TableRow key={`${l.member_id}-${l.component}`} hover sx={l.reversed ? { opacity: 0.55 } : undefined}>
                {posted && (
                  <TableCell padding="checkbox">
                    {reversible.has(l.member_id) && (
                      <Checkbox size="small" checked={selected.includes(l.member_id)} onChange={() => toggle(l.member_id)} slotProps={{ input: { "aria-label": `Select ${l.account_code}` } }} />
                    )}
                  </TableCell>
                )}
                <TableCell>
                  <Link component={RouterLink} to={`/members/${l.member_id}`} underline="hover" sx={{ fontWeight: 500 }}>{l.account_code}</Link>
                  <Typography variant="caption" color="text.secondary" component="div">{l.member_name}</Typography>
                </TableCell>
                <TableCell>{COMPONENT_LABELS[l.component]}</TableCell>
                <TableCell align="right" sx={num}>{l.days}{l.to_date !== d.period_end && <Typography variant="caption" color="text.secondary" component="div">to {formatDate(l.to_date)}</Typography>}</TableCell>
                <TableCell align="right" sx={num}>{formatAmount(l.opening_balance)}</TableCell>
                <TableCell align="right" sx={num}>{formatAmount(l.movements)}</TableCell>
                <TableCell align="right" sx={num}>{formatAmount(l.calculated)}</TableCell>
                <TableCell align="right" sx={num}>{Number(l.already_credited) ? formatAmount(l.already_credited) : "—"}</TableCell>
                <TableCell align="right" sx={{ ...num, fontWeight: 600, color: Number(l.amount) < 0 ? "error.main" : undefined }}>
                  {formatAmount(l.amount)}
                  {l.reversed && <Typography variant="caption" color="error.main" component="div">reversed</Typography>}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </ResponsiveTable>
      </TableContainer>
      <Box>
        <Typography variant="caption" color="text.secondary">
          Calculated = opening balance × rate × days ÷ 365 + each movement × rate × days from its date to the end ÷ 365, rounded to the
          tambala once per member and component.
        </Typography>
      </Box>
      {reversing && <ReverseDialog runId={run.id} memberIds={selected} onClose={() => { setReversing(false); setSelected([]); }} />}
    </Stack>
  );
}
