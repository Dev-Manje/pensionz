import { useState } from "react";
import { Link as RouterLink, useNavigate } from "react-router-dom";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import FormControlLabel from "@mui/material/FormControlLabel";
import Link from "@mui/material/Link";
import MenuItem from "@mui/material/MenuItem";
import Paper from "@mui/material/Paper";
import Radio from "@mui/material/Radio";
import RadioGroup from "@mui/material/RadioGroup";
import Stack from "@mui/material/Stack";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TablePagination from "@mui/material/TablePagination";
import TableRow from "@mui/material/TableRow";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import useMediaQuery from "@mui/material/useMediaQuery";
import type { Theme } from "@mui/material/styles";
import { ResponsiveTable } from "../../../components/ResponsiveTable";
import { StatusChip } from "../../../components/StatusChip";
import { TableStateRow } from "../../../components/TableStateRow";
import { useFeedback } from "../../../components/feedback/FeedbackProvider";
import { useAuth } from "../../../auth/AuthContext";
import { useUrlParam } from "../../../hooks/useUrlState";
import { useSchemes } from "../../../queries/schemes";
import { useCreateSchedule, useSchedules } from "../../../queries/schedules";
import { downloadScheduleTemplate } from "../../../api/schedules";
import { formatAmount } from "../../../utils/format";
import { formatPeriod, todayIso } from "../../../utils/date";

function previousMonth(): string {
  const [y, m] = todayIso().split("-").map(Number);
  return m === 1 ? `${y - 1}-12` : `${y}-${String(m - 1).padStart(2, "0")}`;
}

function NewScheduleDialog({ fundId, onClose }: { fundId: string; onClose: () => void }) {
  const fullScreen = useMediaQuery((t: Theme) => t.breakpoints.down("sm"));
  const schemes = useSchemes(fundId);
  const create = useCreateSchedule(fundId);
  const feedback = useFeedback();
  const navigate = useNavigate();
  const [scheme, setScheme] = useState("");
  const [month, setMonth] = useState(previousMonth());
  const [supplementary, setSupplementary] = useState(false);
  const [start, setStart] = useState<"expected" | "empty" | "upload">("expected");
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    setError(null);
    try {
      const s = await create.mutateAsync({ schemeId: scheme, month: `${month}-01`, supplementary, prefill: start === "expected", file: start === "upload" ? file : null });
      feedback.success(`Schedule ${s.reference} created.`);
      navigate(`/contributions/schedules/${s.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't create the schedule.");
    }
  }

  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="sm" fullScreen={fullScreen}>
      <DialogTitle>New contribution schedule</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <TextField select required label="Employer" value={scheme} onChange={(e) => setScheme(e.target.value)}>
            {(schemes.data ?? []).map((s) => (
              <MenuItem key={s.id} value={s.id}>{s.code} — {s.name}</MenuItem>
            ))}
          </TextField>
          <TextField required type="month" label="Contributions for" value={month} onChange={(e) => setMonth(e.target.value)} slotProps={{ inputLabel: { shrink: true } }} />
          <FormControlLabel control={<Checkbox checked={supplementary} onChange={(e) => setSupplementary(e.target.checked)} />}
            label="Supplementary schedule (back pay or corrections on top of the month's main schedule)" />
          <div>
            <Typography variant="subtitle2" sx={{ mb: 0.5 }}>Start from</Typography>
            <RadioGroup value={start} onChange={(e) => setStart(e.target.value as typeof start)}>
              <FormControlLabel value="expected" control={<Radio />} label="The employer's active members at their expected contributions" />
              <FormControlLabel value="empty" control={<Radio />} label="An empty schedule — I'll add the lines" />
              <FormControlLabel value="upload" control={<Radio />} label="A completed schedule file (.xlsx or .csv)" />
            </RadioGroup>
          </div>
          {start === "upload" && (
            <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} sx={{ alignItems: { sm: "center" } }}>
              <Button variant="outlined" component="label">
                {file ? "Change file" : "Choose file"}
                <input type="file" hidden accept=".xlsx,.csv" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
              </Button>
              <Typography variant="body2" color={file ? "text.primary" : "text.secondary"} sx={{ overflowWrap: "anywhere" }}>
                {file ? file.name : "No file chosen"}
              </Typography>
            </Stack>
          )}
          {scheme && (
            <Typography variant="body2">
              <Link component="button" onClick={() => downloadScheduleTemplate(fundId, scheme, `${month}-01`)}>Download the template</Link>{" "}
              — prefilled with the employer's active members and expected amounts for {formatPeriod(`${month}-01`)}.
            </Typography>
          )}
          {error && <Alert severity="error">{error}</Alert>}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" onClick={save} disabled={!scheme || !month || (start === "upload" && !file) || create.isPending}>
          {create.isPending ? "Creating…" : "Create schedule"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

// Contribution schedules (FR-CON-003): one per employer per month, plus supplementary ones.
export function SchedulesTab({ fundId }: { fundId: string }) {
  const { user } = useAuth();
  const navigate = useNavigate();
  const canCreate = user?.roles.includes("contributions_officer") ?? false;
  const schemes = useSchemes(fundId);
  const [schemeId, setSchemeId] = useUrlParam("employer");
  const [status, setStatus] = useUrlParam("status");
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(25);
  const [creating, setCreating] = useState(false);
  const query = useSchedules(fundId, { scheme_id: schemeId, status, page: page + 1, page_size: pageSize });
  const rows = query.data?.items ?? [];

  return (
    <Stack spacing={2}>
      <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} useFlexGap sx={{ flexWrap: "wrap", alignItems: { sm: "center" } }}>
        <TextField select size="small" label="Employer" value={schemeId ?? ""} onChange={(e) => { setSchemeId(e.target.value || null); setPage(0); }} sx={{ minWidth: 220 }}>
          <MenuItem value="">All employers</MenuItem>
          {(schemes.data ?? []).map((s) => (
            <MenuItem key={s.id} value={s.id}>{s.code} — {s.name}</MenuItem>
          ))}
        </TextField>
        <TextField select size="small" label="Status" value={status ?? ""} onChange={(e) => { setStatus(e.target.value || null); setPage(0); }} sx={{ minWidth: 180 }}>
          <MenuItem value="">Any status</MenuItem>
          <MenuItem value="draft">Draft</MenuItem>
          <MenuItem value="ready">Ready for allocation</MenuItem>
          <MenuItem value="allocated">Allocated</MenuItem>
          <MenuItem value="cancelled">Cancelled</MenuItem>
        </TextField>
        <Box sx={{ flexGrow: 1 }} />
        {canCreate && <Button variant="contained" onClick={() => setCreating(true)}>New schedule</Button>}
      </Stack>
      <Paper>
        <TableContainer>
          <ResponsiveTable size="small">
            <TableHead>
              <TableRow>
                <TableCell>Schedule</TableCell>
                <TableCell>Employer</TableCell>
                <TableCell>Month</TableCell>
                <TableCell align="right">Members</TableCell>
                <TableCell align="right">Total (MWK)</TableCell>
                <TableCell>Checks</TableCell>
                <TableCell>Status</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              <TableStateRow colSpan={7} loading={query.isLoading} error={query.error?.message ?? null} onRetry={() => query.refetch()} count={rows.length}
                empty={schemeId || status ? "Nothing matches." : "No schedules yet. Create one from the template, an upload or by hand."} />
              {rows.map((s) => (
                <TableRow key={s.id} hover onClick={() => navigate(`/contributions/schedules/${s.id}`)} sx={{ cursor: "pointer" }}>
                  <TableCell sx={{ fontWeight: 600, whiteSpace: "nowrap" }}>
                    <Link component={RouterLink} to={`/contributions/schedules/${s.id}`} underline="hover" onClick={(e) => e.stopPropagation()}>{s.reference}</Link>
                  </TableCell>
                  <TableCell>{s.employer}</TableCell>
                  <TableCell sx={{ whiteSpace: "nowrap" }}>{formatPeriod(s.contribution_month)}{s.supplementary ? " · supplementary" : ""}</TableCell>
                  <TableCell align="right">{s.line_count}</TableCell>
                  <TableCell align="right">{formatAmount(s.total)}</TableCell>
                  <TableCell>
                    {s.error_count ? <StatusChip status="failed" label={`${s.error_count} with errors`} /> : s.warning_count ? <StatusChip status="due_soon" label={`${s.warning_count} warnings`} /> : <StatusChip status="passed" label="All clear" />}
                  </TableCell>
                  <TableCell><StatusChip status={s.status} /></TableCell>
                </TableRow>
              ))}
            </TableBody>
          </ResponsiveTable>
        </TableContainer>
        <TablePagination component="div" count={query.data?.total ?? 0} page={page} rowsPerPage={pageSize} rowsPerPageOptions={[25, 50, 100]}
          onPageChange={(_, p) => setPage(p)} onRowsPerPageChange={(e) => { setPageSize(Number(e.target.value)); setPage(0); }} />
      </Paper>
      {creating && <NewScheduleDialog fundId={fundId} onClose={() => setCreating(false)} />}
    </Stack>
  );
}
