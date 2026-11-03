import { useState } from "react";
import { Link as RouterLink, useParams } from "react-router-dom";
import Alert from "@mui/material/Alert";
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
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { DetailField, DetailSection } from "../../components/DetailSection";
import { LoadingState } from "../../components/LoadingState";
import { ResponsiveTable } from "../../components/ResponsiveTable";
import { StatusChip } from "../../components/StatusChip";
import { useFeedback } from "../../components/feedback/FeedbackProvider";
import { requestSalaryChange, sendExitNotice } from "../../api/po";
import type { PortalMemberDetail } from "../../api/types";
import { usePortalMember, usePortalMemberRequest } from "../../queries/po";
import { formatDate, todayIso } from "../../utils/date";
import { formatMoney } from "../../utils/format";
import { EXIT_REASONS } from "./poLabels";
import { RequestList } from "./PoRequests";
import { schemePath } from "./PoSchemePage";

function SalaryDialog({ m, onClose }: { m: PortalMemberDetail; onClose: () => void }) {
  const feedback = useFeedback();
  const send = usePortalMemberRequest((body: Parameters<typeof requestSalaryChange>[1]) => requestSalaryChange(m.id, body));
  const [v, setV] = useState({ effective_from: todayIso().slice(0, 8) + "01", basic: "", pensionable: "", note: "" });
  const [error, setError] = useState<string | null>(null);
  const clean = (s: string) => s.replace(/,/g, "").trim();

  async function go() {
    setError(null);
    try {
      await send.mutateAsync({ effective_from: v.effective_from, basic_salary: clean(v.basic), pensionable_salary: clean(v.pensionable) || null, note: v.note.trim() || null });
      feedback.success("Salary change sent for approval.");
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't send the change.");
    }
  }

  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="xs">
      <DialogTitle>Change {m.full_name}'s salary</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          {m.salary && <Typography color="text.secondary">On record: {formatMoney(m.salary)} from {formatDate(m.salary_from)}.</Typography>}
          <TextField label="New monthly basic salary (MWK)" value={v.basic} onChange={(e) => setV({ ...v, basic: e.target.value })} inputMode="decimal" autoFocus />
          <TextField label="Pensionable salary (MWK)" value={v.pensionable} onChange={(e) => setV({ ...v, pensionable: e.target.value })} inputMode="decimal"
            helperText="Leave blank if it's the same as the basic salary" />
          <TextField label="From" type="date" value={v.effective_from} onChange={(e) => setV({ ...v, effective_from: e.target.value })}
            slotProps={{ inputLabel: { shrink: true } }} />
          <TextField label="Note (optional)" value={v.note} onChange={(e) => setV({ ...v, note: e.target.value })} placeholder="e.g. annual increase" />
          {error && <Alert severity="error">{error}</Alert>}
        </Stack>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" onClick={go} disabled={!(Number(clean(v.basic)) > 0) || !v.effective_from || send.isPending}>
          {send.isPending ? "Sending…" : "Send for approval"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

function ExitDialog({ m, onClose }: { m: PortalMemberDetail; onClose: () => void }) {
  const feedback = useFeedback();
  const send = usePortalMemberRequest((body: Parameters<typeof sendExitNotice>[1]) => sendExitNotice(m.id, body));
  const [v, setV] = useState({ last_day: todayIso(), reason: "", note: "" });
  const [error, setError] = useState<string | null>(null);
  const died = v.reason === "died";

  async function go() {
    setError(null);
    try {
      await send.mutateAsync({ last_day: v.last_day, reason: v.reason, note: v.note.trim() || null });
      feedback.success("Exit notice sent — we'll stop expecting contributions once it's approved and contact you about the claim.");
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't send the notice.");
    }
  }

  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="xs">
      <DialogTitle>{m.full_name} has left</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <TextField select label="Why" value={v.reason} onChange={(e) => setV({ ...v, reason: e.target.value })} autoFocus>
            {EXIT_REASONS.map(([code, label]) => (
              <MenuItem key={code} value={code}>{label}</MenuItem>
            ))}
          </TextField>
          <TextField label={died ? "Date of death" : "Last working day"} type="date" value={v.last_day} onChange={(e) => setV({ ...v, last_day: e.target.value })}
            slotProps={{ inputLabel: { shrink: true }, htmlInput: { max: todayIso() } }} />
          <TextField label={v.reason === "other" ? "Why (required)" : "Note (optional)"} value={v.note} onChange={(e) => setV({ ...v, note: e.target.value })} multiline minRows={2} />
          <Typography variant="body2" color="text.secondary">
            {died
              ? "We're sorry. We will contact the beneficiaries about the death benefit — keep the death certificate ready."
              : "Include this month's contributions up to the last working day on the schedule. We'll contact the member about their benefit."}
          </Typography>
          {error && <Alert severity="error">{error}</Alert>}
        </Stack>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" onClick={go} disabled={!v.reason || !v.last_day || (v.reason === "other" && !v.note.trim()) || send.isPending}>
          {send.isPending ? "Sending…" : "Send exit notice"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

// One member, HR-level: the facts the employer keeps up to date, salary history and requests.
export function PoMemberPage() {
  const { memberId } = useParams();
  const query = usePortalMember(memberId);
  const [dialog, setDialog] = useState<"salary" | "exit" | null>(null);
  if (query.isLoading) return <LoadingState />;
  if (query.error || !query.data) return <Alert severity="error">{query.error?.message ?? "Member not found"}</Alert>;
  const m = query.data;
  const waiting = m.requests.some((r) => r.status === "pending");

  return (
    <Stack spacing={2} sx={{ maxWidth: 1040 }}>
      <Breadcrumbs>
        <Link component={RouterLink} to="/po" underline="hover" color="inherit">My schemes</Link>
        <Link component={RouterLink} to={schemePath(m.scheme_id, "members")} underline="hover" color="inherit">{m.scheme_name}</Link>
        <Typography color="text.primary">{m.account_code}</Typography>
      </Breadcrumbs>
      <Stack direction={{ xs: "column", sm: "row" }} spacing={2} sx={{ justifyContent: "space-between", alignItems: { sm: "flex-start" } }}>
        <div>
          <Typography variant="h1">{m.full_name}</Typography>
          <Stack direction="row" spacing={1} sx={{ alignItems: "center", mt: 0.5 }}>
            <Typography color="text.secondary">{m.account_code}</Typography>
            <StatusChip status={m.status} label={m.status_label} />
          </Stack>
        </div>
        <Stack direction="row" spacing={1}>
          {m.can_change_salary && <Button variant="outlined" onClick={() => setDialog("salary")} disabled={waiting}>Change salary</Button>}
          {m.can_give_notice && <Button variant="outlined" color="warning" onClick={() => setDialog("exit")} disabled={waiting}>Has left</Button>}
        </Stack>
      </Stack>
      {waiting && <Alert severity="info">A change for this member is waiting for approval — you can send another once it's decided.</Alert>}
      <DetailSection title="Employment">
        <DetailField label="Employee number">{m.employee_no ?? "—"}</DetailField>
        <DetailField label="Category">{m.category ?? "—"}</DetailField>
        <DetailField label="Started with you">{formatDate(m.date_joined_employer)}</DetailField>
        <DetailField label="Joined the fund">{formatDate(m.date_joined_fund)}</DetailField>
        <DetailField label="Date of birth">{formatDate(m.date_of_birth)}</DetailField>
        <DetailField label="Status since">{formatDate(m.status_effective)}</DetailField>
      </DetailSection>
      <Paper sx={{ p: { xs: 2, sm: 3 } }}>
        <Typography variant="subtitle1" component="h2" sx={{ fontWeight: 600, mb: 1 }}>Salary</Typography>
        {m.salaries.length === 0 ? (
          <Typography color="text.secondary">No salary on record — contributions can't be worked out until there is one. Use “Change salary”.</Typography>
        ) : (
          <TableContainer>
            <ResponsiveTable size="small">
              <TableHead>
                <TableRow>
                  <TableCell>From</TableCell>
                  <TableCell align="right">Basic</TableCell>
                  <TableCell align="right">Pensionable</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {m.salaries.map((s) => (
                  <TableRow key={s.effective_from}>
                    <TableCell>{formatDate(s.effective_from)}</TableCell>
                    <TableCell align="right">{formatMoney(s.basic_salary)}</TableCell>
                    <TableCell align="right">{formatMoney(s.pensionable_salary)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </ResponsiveTable>
          </TableContainer>
        )}
      </Paper>
      <RequestList rows={m.requests} title="Requests for this member" empty="No requests for this member yet." />
      {dialog === "salary" && <SalaryDialog m={m} onClose={() => setDialog(null)} />}
      {dialog === "exit" && <ExitDialog m={m} onClose={() => setDialog(null)} />}
    </Stack>
  );
}
