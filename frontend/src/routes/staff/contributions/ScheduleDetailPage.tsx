import { useRef, useState } from "react";
import { Link as RouterLink, useParams } from "react-router-dom";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Breadcrumbs from "@mui/material/Breadcrumbs";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import FormControlLabel from "@mui/material/FormControlLabel";
import Link from "@mui/material/Link";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Switch from "@mui/material/Switch";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import useMediaQuery from "@mui/material/useMediaQuery";
import type { Theme } from "@mui/material/styles";
import { LoadingState } from "../../../components/LoadingState";
import { ResponsiveTable } from "../../../components/ResponsiveTable";
import { RowActions } from "../../../components/RowActions";
import { StatusChip } from "../../../components/StatusChip";
import { TableStateRow } from "../../../components/TableStateRow";
import { useFeedback } from "../../../components/feedback/FeedbackProvider";
import { useAuth } from "../../../auth/AuthContext";
import { AllocationPanel } from "./AllocationPanel";
import { useSchedule, useScheduleChange } from "../../../queries/schedules";
import { downloadScheduleTemplate, type Schedule, type ScheduleLine } from "../../../api/schedules";
import { formatAmount, formatMoney } from "../../../utils/format";
import { formatDateTime, formatPeriod } from "../../../utils/date";

const blankLine = { account_code: "", employee_no: "", member_name: "", pensionable_salary: "", employee: "", employer: "", voluntary: "", severance: "" };

function LineDialog({ schedule, line, onClose }: { schedule: Schedule; line: ScheduleLine | null; onClose: () => void }) {
  const fullScreen = useMediaQuery((t: Theme) => t.breakpoints.down("sm"));
  const change = useScheduleChange(schedule.id);
  const [v, setV] = useState(
    line
      ? { account_code: line.account_code ?? "", employee_no: line.employee_no ?? "", member_name: line.member_name ?? "",
          pensionable_salary: line.pensionable_salary ?? "", employee: line.employee, employer: line.employer, voluntary: line.voluntary, severance: line.severance }
      : blankLine,
  );
  const [error, setError] = useState<string | null>(null);
  const set = (k: keyof typeof v) => (e: { target: { value: string } }) => setV({ ...v, [k]: e.target.value });
  const num = (s: string) => s.replace(/,/g, "").trim() || "0";

  async function save() {
    setError(null);
    try {
      await change.mutateAsync({
        kind: "save", lineId: line?.id ?? null,
        body: { account_code: v.account_code || null, employee_no: v.employee_no || null, member_name: v.member_name || null,
                pensionable_salary: v.pensionable_salary ? num(v.pensionable_salary) : null,
                employee: num(v.employee), employer: num(v.employer), voluntary: num(v.voluntary), severance: num(v.severance) },
      });
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't save the line.");
    }
  }

  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="sm" fullScreen={fullScreen}>
      <DialogTitle>{line ? `Row ${line.row_no}` : "Add a member"}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          {line && [...line.errors, ...line.warnings].length > 0 && (
            <Alert severity={line.errors.length ? "error" : "warning"}>{[...line.errors, ...line.warnings].join(" · ")}</Alert>
          )}
          <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
            <TextField label="Account code" value={v.account_code} onChange={set("account_code")} fullWidth autoFocus={!line} />
            <TextField label="Employee no" value={v.employee_no} onChange={set("employee_no")} fullWidth />
          </Stack>
          <TextField label="Pensionable salary (MWK)" value={v.pensionable_salary} onChange={set("pensionable_salary")} inputMode="decimal"
            helperText="Leave blank to use the salary on the member record" />
          <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
            <TextField label="Employee (MWK)" value={v.employee} onChange={set("employee")} inputMode="decimal" fullWidth />
            <TextField label="Employer (MWK)" value={v.employer} onChange={set("employer")} inputMode="decimal" fullWidth />
          </Stack>
          <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
            <TextField label="Voluntary / AVC (MWK)" value={v.voluntary} onChange={set("voluntary")} inputMode="decimal" fullWidth />
            <TextField label="Severance (MWK)" value={v.severance} onChange={set("severance")} inputMode="decimal" fullWidth />
          </Stack>
          {error && <Alert severity="error">{error}</Alert>}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" onClick={save} disabled={(!v.account_code && !v.employee_no) || change.isPending}>
          {change.isPending ? "Checking…" : "Save and check"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

function Totals({ s }: { s: Schedule }) {
  const items = [
    ["Employee", s.total_employee], ["Employer", s.total_employer], ["Voluntary (AVC)", s.total_voluntary], ["Severance", s.total_severance],
  ] as const;
  return (
    <Paper sx={{ p: { xs: 2, sm: 2.5 } }}>
      <Stack direction={{ xs: "column", md: "row" }} spacing={2} sx={{ justifyContent: "space-between" }}>
        <Box>
          <Typography variant="overline" color="text.secondary">Schedule total</Typography>
          <Typography variant="h5" component="p" sx={{ fontWeight: 600 }}>{formatMoney(s.total)}</Typography>
          <Typography variant="body2" color="text.secondary">{s.line_count} member line{s.line_count === 1 ? "" : "s"}</Typography>
        </Box>
        <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr 1fr", sm: "repeat(4, minmax(120px, 1fr))" }, gap: 1.5 }}>
          {items.map(([label, value]) => (
            <Box key={label} sx={{ p: 1.5, borderRadius: 1, bgcolor: "action.hover" }}>
              <Typography variant="caption" color="text.secondary">{label}</Typography>
              <Typography sx={{ fontWeight: 600 }}>{formatAmount(value)}</Typography>
            </Box>
          ))}
        </Box>
      </Stack>
    </Paper>
  );
}

export function ScheduleDetailPage() {
  const { scheduleId } = useParams();
  const { user } = useAuth();
  const query = useSchedule(scheduleId);
  const change = useScheduleChange(scheduleId ?? "");
  const feedback = useFeedback();
  const fileInput = useRef<HTMLInputElement>(null);
  const [problemsOnly, setProblemsOnly] = useState(false);
  const [editing, setEditing] = useState<ScheduleLine | "new" | null>(null);

  if (query.isLoading) return <LoadingState />;
  if (query.error || !query.data) {
    return <Alert severity="error" action={<Button color="inherit" onClick={() => query.refetch()}>Retry</Button>}>{query.error?.message ?? "Couldn't load the schedule."}</Alert>;
  }
  const s = query.data;
  const isMaker = user?.roles.includes("contributions_officer") ?? false;
  const lines = problemsOnly ? s.lines.filter((l) => l.errors.length || l.warnings.length) : s.lines;

  async function run(a: Parameters<typeof change.mutateAsync>[0], done: string) {
    try {
      await change.mutateAsync(a);
      feedback.success(done);
    } catch (e) {
      feedback.error(e instanceof Error ? e.message : "That didn't work.");
    }
  }

  return (
    <Stack spacing={2}>
      <Breadcrumbs>
        <Link component={RouterLink} to={`/contributions?fund=${s.fund_id}&tab=schedules`} underline="hover" color="inherit">Contributions</Link>
        <Typography color="text.primary">{s.reference}</Typography>
      </Breadcrumbs>
      <Stack direction={{ xs: "column", md: "row" }} spacing={2} sx={{ justifyContent: "space-between", alignItems: { md: "flex-start" } }}>
        <div>
          <Typography variant="h5" component="h1" sx={{ fontWeight: 600 }}>
            Schedule {s.reference}
          </Typography>
          <Typography color="text.secondary">
            {s.employer} · {formatPeriod(s.contribution_month)}{s.supplementary ? " · supplementary" : ""}
            {s.filename ? ` · from ${s.filename}` : ""}
          </Typography>
          <StatusChip status={s.status} sx={{ mt: 1 }} />
        </div>
        <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: "wrap" }}>
          {s.can_edit && (
            <>
              <Button variant="contained" disabled={!!s.error_count || !s.line_count || change.isPending}
                onClick={() => run({ kind: "action", action: "submit" }, "Schedule handed over for allocation.")}>
                Submit for allocation
              </Button>
              <Button onClick={() => setEditing("new")}>Add member</Button>
              <Button onClick={() => run({ kind: "action", action: "fill-expected" }, "Missing members added at their expected amounts.")}>Add missing members</Button>
              <Button onClick={() => fileInput.current?.click()}>Upload corrected file</Button>
              <Button onClick={() => downloadScheduleTemplate(s.fund_id, s.scheme_id, s.contribution_month)}>Template</Button>
              <input ref={fileInput} type="file" hidden accept=".xlsx,.csv"
                onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) run({ kind: "upload", file: f }, "File checked — the lines were replaced."); }} />
            </>
          )}
          {s.status === "ready" && (
            <Button onClick={() => run({ kind: "action", action: "reopen" }, "Schedule re-opened for changes.")}>Re-open</Button>
          )}
          {(s.can_edit || s.status === "ready") && (
            <Button color="error" onClick={() => run({ kind: "action", action: "cancel" }, "Schedule cancelled.")}>Cancel schedule</Button>
          )}
        </Stack>
      </Stack>

      {s.status === "draft" && s.error_count > 0 && (
        <Alert severity="error">{s.error_count} line{s.error_count === 1 ? " has" : "s have"} errors. Fix or remove them before submitting.</Alert>
      )}
      {s.status === "draft" && !s.error_count && s.warning_count > 0 && (
        <Alert severity="warning">{s.warning_count} line{s.warning_count === 1 ? " has" : "s have"} warnings — check them; they don't stop the schedule.</Alert>
      )}
      {s.status === "ready" && (
        <Alert severity="info">Submitted {s.submitted_at ? formatDateTime(s.submitted_at) : ""}{s.submitted_by ? ` by ${s.submitted_by}` : ""}. Match it to the money received below.</Alert>
      )}

      <Totals s={s} />
      <AllocationPanel schedule={s} canAllocate={isMaker} />

      <Paper>
        <Stack direction="row" sx={{ px: 2, pt: 1.5, alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 1 }}>
          <Typography variant="subtitle1" component="h2" sx={{ fontWeight: 600 }}>Members</Typography>
          <FormControlLabel control={<Switch checked={problemsOnly} onChange={(e) => setProblemsOnly(e.target.checked)} />}
            label={`Only lines with problems (${s.lines.filter((l) => l.errors.length || l.warnings.length).length})`} />
        </Stack>
        <TableContainer>
          <ResponsiveTable size="small">
            <TableHead>
              <TableRow>
                <TableCell>Row</TableCell>
                <TableCell>Member</TableCell>
                <TableCell align="right">Salary</TableCell>
                <TableCell align="right">Employee</TableCell>
                <TableCell align="right">Employer</TableCell>
                <TableCell align="right">AVC</TableCell>
                <TableCell align="right">Severance</TableCell>
                <TableCell align="right">Total</TableCell>
                <TableCell>Checks</TableCell>
                {s.can_edit && <TableCell align="right">Actions</TableCell>}
              </TableRow>
            </TableHead>
            <TableBody>
              <TableStateRow colSpan={s.can_edit ? 10 : 9} count={lines.length}
                empty={problemsOnly ? "No problems on this schedule." : "No lines yet — add members or upload the schedule file."} />
              {lines.map((l) => (
                <TableRow key={l.id} sx={l.errors.length ? { bgcolor: "rgba(211, 47, 47, 0.04)" } : undefined}>
                  <TableCell>{l.row_no}</TableCell>
                  <TableCell>
                    {l.member_id ? (
                      <Link component={RouterLink} to={`/members/${l.member_id}`} underline="hover" sx={{ fontWeight: 600 }}>{l.account_code}</Link>
                    ) : (
                      <Typography component="span" sx={{ fontWeight: 600 }}>{l.account_code ?? l.employee_no ?? "—"}</Typography>
                    )}
                    <Typography variant="body2" color="text.secondary">{l.member_name}</Typography>
                  </TableCell>
                  <TableCell align="right">{l.pensionable_salary ? formatAmount(l.pensionable_salary) : "—"}</TableCell>
                  <TableCell align="right">{formatAmount(l.employee)}</TableCell>
                  <TableCell align="right">{formatAmount(l.employer)}</TableCell>
                  <TableCell align="right">{Number(l.voluntary) ? formatAmount(l.voluntary) : "—"}</TableCell>
                  <TableCell align="right">{Number(l.severance) ? formatAmount(l.severance) : "—"}</TableCell>
                  <TableCell align="right" sx={{ fontWeight: 600 }}>{formatAmount(l.total)}</TableCell>
                  <TableCell sx={{ maxWidth: 360 }}>
                    {l.errors.map((m) => <Typography key={m} variant="body2" color="error.main">{m}</Typography>)}
                    {l.warnings.map((m) => <Typography key={m} variant="body2" color="warning.dark">{m}</Typography>)}
                    {!l.errors.length && !l.warnings.length && <Typography variant="body2" color="success.main">OK</Typography>}
                  </TableCell>
                  {s.can_edit && (
                    <TableCell align="right">
                      <RowActions actions={[
                        { label: "Edit", onClick: () => setEditing(l) },
                        { label: "Remove", onClick: () => run({ kind: "remove", lineId: l.id }, `Row ${l.row_no} removed.`), color: "error" },
                      ]} />
                    </TableCell>
                  )}
                </TableRow>
              ))}
            </TableBody>
          </ResponsiveTable>
        </TableContainer>
      </Paper>
      {editing && <LineDialog schedule={s} line={editing === "new" ? null : editing} onClose={() => setEditing(null)} />}
    </Stack>
  );
}
