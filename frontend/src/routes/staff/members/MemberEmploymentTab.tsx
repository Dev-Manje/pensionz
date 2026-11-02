import { useState } from "react";
import { Link as RouterLink } from "react-router-dom";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import AddIcon from "@mui/icons-material/Add";
import { DetailField, DetailSection } from "../../../components/DetailSection";
import { LoadingState } from "../../../components/LoadingState";
import { ResponsiveTable } from "../../../components/ResponsiveTable";
import { TableStateRow } from "../../../components/TableStateRow";
import { RepeatRow } from "../../../components/form/FormLayout";
import { useFeedback } from "../../../components/feedback/FeedbackProvider";
import { useEmployment, useMemberProposal } from "../../../queries/members";
import { proposeSalary, proposeService } from "../../../api/members";
import type { EmploymentRecords, Member, ServicePeriodInput } from "../../../api/types";
import { formatMoney } from "../../../utils/format";
import { formatDate, todayIso } from "../../../utils/date";

const money = { textAlign: "right", fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap" } as const;

function SalaryDialog({ member, onClose }: { member: Member; onClose: () => void }) {
  const feedback = useFeedback();
  const submit = useMemberProposal((body: Parameters<typeof proposeSalary>[1]) => proposeSalary(member.id, body));
  const [from, setFrom] = useState(todayIso().slice(0, 8) + "01");
  const [basic, setBasic] = useState("");
  const [pensionable, setPensionable] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function send() {
    setError(null);
    try {
      await submit.mutateAsync({ effective_from: from, basic_salary: basic, pensionable_salary: pensionable || null, note: note.trim() || null });
      feedback.success("Salary sent for approval — it applies once a member checker approves it.");
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
    }
  }

  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>Record a salary for {String(member.fields.full_name)}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <Typography color="text.secondary">Monthly amounts. A salary on a date that already has one corrects it.</Typography>
          <TextField label="From" type="date" required value={from} onChange={(e) => setFrom(e.target.value)} slotProps={{ inputLabel: { shrink: true } }} />
          <TextField label="Basic salary (MWK)" type="number" required value={basic} onChange={(e) => setBasic(e.target.value)} slotProps={{ htmlInput: { min: 0.01, step: "0.01" } }} />
          <TextField label="Pensionable salary (MWK)" type="number" value={pensionable} onChange={(e) => setPensionable(e.target.value)} slotProps={{ htmlInput: { min: 0.01, step: "0.01" } }}
            helperText="Leave empty when it equals the basic salary. Contributions are worked out on this amount." />
          <TextField label="Note" value={note} onChange={(e) => setNote(e.target.value)} helperText="Optional, e.g. annual increase letter." />
          {error && <Alert severity="error">{error}</Alert>}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" onClick={send} disabled={!from || !(Number(basic) > 0) || submit.isPending}>
          {submit.isPending ? "Sending…" : "Submit for approval"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

const EMPTY_PERIOD: ServicePeriodInput = { start_date: "", end_date: null, part_time_factor: "1", note: null };

function ServiceDialog({ member, records, onClose }: { member: Member; records: EmploymentRecords; onClose: () => void }) {
  const feedback = useFeedback();
  const submit = useMemberProposal((body: Parameters<typeof proposeService>[1]) => proposeService(member.id, body));
  const [rows, setRows] = useState<ServicePeriodInput[]>(() =>
    records.service.length ? records.service.map(({ start_date, end_date, part_time_factor, note }) => ({ start_date, end_date, part_time_factor: String(Number(part_time_factor)), note })) : [{ ...EMPTY_PERIOD, start_date: String(member.fields.date_joined_employer ?? member.fields.date_joined_fund ?? "") }],
  );
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const set = (i: number, key: keyof ServicePeriodInput, value: string | null) => setRows(rows.map((r, j) => (j === i ? { ...r, [key]: value } : r)));

  async function send() {
    setError(null);
    try {
      await submit.mutateAsync({ periods: rows, reason });
      feedback.success("Service history sent for approval.");
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
    }
  }

  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="md">
      <DialogTitle>Service history of {String(member.fields.full_name)}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <Typography color="text.secondary">
            Periods of pensionable service. Gaps between periods are breaks in service. Leave the end date empty for current service. Part-time service counts
            at its factor (0.5 = half time).
          </Typography>
          {rows.map((r, i) => (
            <RepeatRow key={i} label={`Period ${i + 1}`} onRemove={() => setRows(rows.filter((_, j) => j !== i))}>
              <TextField label="From" type="date" required value={r.start_date} onChange={(e) => set(i, "start_date", e.target.value)} slotProps={{ inputLabel: { shrink: true } }} />
              <TextField label="To" type="date" value={r.end_date ?? ""} onChange={(e) => set(i, "end_date", e.target.value || null)} slotProps={{ inputLabel: { shrink: true } }} helperText="Empty = still in service." />
              <TextField label="Part-time factor" type="number" value={r.part_time_factor} onChange={(e) => set(i, "part_time_factor", e.target.value)} slotProps={{ htmlInput: { min: 0.0001, max: 1, step: "0.05" } }} />
              <TextField label="Note" value={r.note ?? ""} onChange={(e) => set(i, "note", e.target.value || null)} />
            </RepeatRow>
          ))}
          <Button startIcon={<AddIcon />} variant="outlined" onClick={() => setRows([...rows, { ...EMPTY_PERIOD }])} sx={{ alignSelf: "flex-start" }}>
            Add period
          </Button>
          <TextField label="Reason for the change" required value={reason} onChange={(e) => setReason(e.target.value)} helperText="E.g. from the HR service record dated 1 March." />
          {error && <Alert severity="error">{error}</Alert>}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" onClick={send} disabled={rows.some((r) => !r.start_date) || reason.trim().length < 3 || submit.isPending}>
          {submit.isPending ? "Sending…" : "Submit for approval"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

function Pending({ id, what }: { id: string | null; what: string }) {
  if (!id) return null;
  return (
    <Alert severity="warning" action={<Button color="inherit" size="small" component={RouterLink} to={`/approvals/${id}`}>View request</Button>}>
      A {what} is waiting for approval.
    </Alert>
  );
}

// Salary & service tab (FR-MEM-009).
export function MemberEmploymentTab({ member }: { member: Member }) {
  const query = useEmployment(member.id);
  const [dialog, setDialog] = useState<"salary" | "service" | null>(null);
  if (query.isLoading) return <LoadingState />;
  if (query.error || !query.data) return <Alert severity="error">{query.error?.message ?? "Couldn't load the salary and service history."}</Alert>;
  const r = query.data;
  const salaried = member.status === "active" || member.status === "inactive";

  return (
    <Stack spacing={3}>
      <DetailSection title="Now">
        <DetailField label="Basic salary (monthly)">{r.current_salary && formatMoney(r.current_salary.basic_salary)}</DetailField>
        <DetailField label="Pensionable salary (monthly)">{r.current_salary && formatMoney(r.current_salary.pensionable_salary)}</DetailField>
        <DetailField label="Pensionable service">{r.service.length ? `${Number(r.pensionable_service_years).toFixed(2)} years` : null}</DetailField>
      </DetailSection>

      <Box>
        <Stack direction="row" sx={{ justifyContent: "space-between", alignItems: "center", mb: 1, gap: 1, flexWrap: "wrap" }}>
          <Typography variant="subtitle1" component="h2" sx={{ fontWeight: 600 }}>
            Salary history
          </Typography>
          {r.can_edit && salaried && !r.salary_pending_approval_id && (
            <Button variant="outlined" onClick={() => setDialog("salary")}>
              Record salary
            </Button>
          )}
        </Stack>
        <Pending id={r.salary_pending_approval_id} what="salary change" />
        <TableContainer component={Paper} sx={{ mt: r.salary_pending_approval_id ? 1 : 0 }}>
          <ResponsiveTable size="small">
            <TableHead>
              <TableRow>
                <TableCell>From</TableCell>
                <TableCell sx={money}>Basic</TableCell>
                <TableCell sx={money}>Pensionable</TableCell>
                <TableCell>Note</TableCell>
                <TableCell>Approved by</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              <TableStateRow colSpan={5} empty="No salary recorded yet. Salaries drive salary-based contributions and DB benefits." count={r.salaries.length} />
              {r.salaries.map((s) => (
                <TableRow key={s.id}>
                  <TableCell sx={{ whiteSpace: "nowrap" }}>{formatDate(s.effective_from)}</TableCell>
                  <TableCell sx={money}>{formatMoney(s.basic_salary)}</TableCell>
                  <TableCell sx={money}>{formatMoney(s.pensionable_salary)}</TableCell>
                  <TableCell>{s.note ?? "—"}</TableCell>
                  <TableCell>{s.approved_by ?? "—"}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </ResponsiveTable>
        </TableContainer>
      </Box>

      <Box>
        <Stack direction="row" sx={{ justifyContent: "space-between", alignItems: "center", mb: 1, gap: 1, flexWrap: "wrap" }}>
          <Typography variant="subtitle1" component="h2" sx={{ fontWeight: 600 }}>
            Service history
          </Typography>
          {r.can_edit && !r.service_pending_approval_id && (
            <Button variant="outlined" onClick={() => setDialog("service")}>
              Edit service history
            </Button>
          )}
        </Stack>
        <Pending id={r.service_pending_approval_id} what="service history change" />
        <TableContainer component={Paper} sx={{ mt: r.service_pending_approval_id ? 1 : 0 }}>
          <ResponsiveTable size="small">
            <TableHead>
              <TableRow>
                <TableCell>From</TableCell>
                <TableCell>To</TableCell>
                <TableCell sx={money}>Part-time factor</TableCell>
                <TableCell>Note</TableCell>
                <TableCell sx={money}>Years</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              <TableStateRow colSpan={5} empty="No service periods recorded. Defined benefit pensions are worked out from them." count={r.service.length} />
              {r.service.map((p) => (
                <TableRow key={p.start_date}>
                  <TableCell sx={{ whiteSpace: "nowrap" }}>{formatDate(p.start_date)}</TableCell>
                  <TableCell sx={{ whiteSpace: "nowrap" }}>{p.end_date ? formatDate(p.end_date) : "Current"}</TableCell>
                  <TableCell sx={money}>{Number(p.part_time_factor).toFixed(2)}</TableCell>
                  <TableCell>{p.note ?? "—"}</TableCell>
                  <TableCell sx={money}>{Number(p.years).toFixed(2)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </ResponsiveTable>
        </TableContainer>
      </Box>
      {dialog === "salary" && <SalaryDialog member={member} onClose={() => setDialog(null)} />}
      {dialog === "service" && <ServiceDialog member={member} records={r} onClose={() => setDialog(null)} />}
    </Stack>
  );
}
