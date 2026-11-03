import { useState } from "react";
import { Link as RouterLink } from "react-router-dom";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
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
import ErrorOutlineIcon from "@mui/icons-material/ErrorOutlineOutlined";
import WarningAmberIcon from "@mui/icons-material/WarningAmber";
import { ResponsiveTable } from "../../../components/ResponsiveTable";
import { RowActions } from "../../../components/RowActions";
import { TableStateRow } from "../../../components/TableStateRow";
import type { Schedule, ScheduleLine, ScheduleLineInput } from "../../../api/schedules";
import { formatAmount, formatMoney } from "../../../utils/format";

// Pieces of a contribution schedule screen shared by staff (/contributions/schedules/<id>)
// and the principal officer portal (/po/schedules/<id>); each passes its own save/remove calls.

const blankLine = { account_code: "", employee_no: "", member_name: "", pensionable_salary: "", employee: "", employer: "", voluntary: "", severance: "" };

export function LineDialog({ line, onSave, onClose }: {
  line: ScheduleLine | null;
  onSave: (lineId: string | null, body: ScheduleLineInput) => Promise<unknown>;
  onClose: () => void;
}) {
  const fullScreen = useMediaQuery((t: Theme) => t.breakpoints.down("sm"));
  const [v, setV] = useState(
    line
      ? { account_code: line.account_code ?? "", employee_no: line.employee_no ?? "", member_name: line.member_name ?? "",
          pensionable_salary: line.pensionable_salary ?? "", employee: line.employee, employer: line.employer, voluntary: line.voluntary, severance: line.severance }
      : blankLine,
  );
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const set = (k: keyof typeof v) => (e: { target: { value: string } }) => setV({ ...v, [k]: e.target.value });
  const num = (s: string) => s.replace(/,/g, "").trim() || "0";

  async function save() {
    setError(null);
    setSaving(true);
    try {
      await onSave(line?.id ?? null, {
        account_code: v.account_code || null, employee_no: v.employee_no || null, member_name: v.member_name || null,
        pensionable_salary: v.pensionable_salary ? num(v.pensionable_salary) : null,
        employee: num(v.employee), employer: num(v.employer), voluntary: num(v.voluntary), severance: num(v.severance),
      });
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't save the line.");
    } finally {
      setSaving(false);
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
        <Button variant="contained" onClick={save} disabled={(!v.account_code && !v.employee_no) || saving}>
          {saving ? "Checking…" : "Save and check"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

export function Totals({ s }: { s: Schedule }) {
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

// One check on a row: an error (blocks sending) or a warning (doesn't), told apart by icon as well as colour.
function Check({ kind, text }: { kind: "error" | "warning"; text: string }) {
  const Icon = kind === "error" ? ErrorOutlineIcon : WarningAmberIcon;
  return (
    <Stack direction="row" spacing={0.75} sx={{ alignItems: "flex-start", mb: 0.5, color: kind === "error" ? "error.main" : "warning.dark" }}>
      <Icon sx={{ fontSize: 16, mt: "2px", flexShrink: 0 }} aria-label={kind === "error" ? "Error" : "Warning"} />
      <Typography variant="body2" sx={{ color: "inherit", textAlign: "left" }}>{text}</Typography>
    </Stack>
  );
}

// The member lines with each row's errors (block sending) and warnings (don't).
export function ScheduleLines({ s, editable, memberLinks, onEdit, onRemove }: {
  s: Schedule;
  editable: boolean;
  // Staff link each line to the member record; the portal doesn't.
  memberLinks: boolean;
  onEdit: (line: ScheduleLine) => void;
  onRemove: (line: ScheduleLine) => void;
}) {
  const [problemsOnly, setProblemsOnly] = useState(false);
  const withProblems = s.lines.filter((l) => l.errors.length || l.warnings.length);
  const lines = problemsOnly ? withProblems : s.lines;
  return (
    <Paper>
      <Stack direction="row" sx={{ px: 2, pt: 1.5, alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 1 }}>
        <Typography variant="subtitle1" component="h2" sx={{ fontWeight: 600 }}>Members</Typography>
        <FormControlLabel control={<Switch checked={problemsOnly} onChange={(e) => setProblemsOnly(e.target.checked)} />}
          label={`Only lines with problems (${withProblems.length})`} />
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
              {editable && <TableCell align="right">Actions</TableCell>}
            </TableRow>
          </TableHead>
          <TableBody>
            <TableStateRow colSpan={editable ? 10 : 9} count={lines.length}
              empty={problemsOnly ? "No problems on this schedule." : "No lines yet — add members or upload the schedule file."} />
            {lines.map((l) => (
              <TableRow key={l.id} sx={l.errors.length ? { bgcolor: "rgba(211, 47, 47, 0.04)" } : undefined}>
                <TableCell>{l.row_no}</TableCell>
                <TableCell>
                  {memberLinks && l.member_id ? (
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
                  {l.errors.map((m) => <Check key={m} kind="error" text={m} />)}
                  {l.warnings.map((m) => <Check key={m} kind="warning" text={m} />)}
                  {!l.errors.length && !l.warnings.length && <Typography variant="body2" color="success.main">OK</Typography>}
                </TableCell>
                {editable && (
                  <TableCell align="right">
                    <RowActions actions={[
                      { label: "Edit", onClick: () => onEdit(l) },
                      { label: "Remove", onClick: () => onRemove(l), color: "error" },
                    ]} />
                  </TableCell>
                )}
              </TableRow>
            ))}
          </TableBody>
        </ResponsiveTable>
      </TableContainer>
    </Paper>
  );
}
