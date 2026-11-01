import { Fragment, useState } from "react";
import { Link as RouterLink } from "react-router-dom";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import InputAdornment from "@mui/material/InputAdornment";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { ResponsiveTable } from "../../../components/ResponsiveTable";
import { RowActions } from "../../../components/RowActions";
import { StatusChip } from "../../../components/StatusChip";
import { TableStateRow } from "../../../components/TableStateRow";
import { useFeedback } from "../../../components/feedback/FeedbackProvider";
import { useAuth } from "../../../auth/AuthContext";
import { useParameters, useProposeParameter } from "../../../queries/regulatory";
import { formatDate, todayIso } from "../../../utils/date";
import type { ParameterUnit, RegulatoryParameter } from "../../../api/types";

const UNIT_ADORNMENT: Record<ParameterUnit, { start?: string; end?: string }> = {
  percent: { end: "%" },
  money: { start: "MWK" },
  years: { end: "years" },
  months: { end: "months" },
  age: { end: "years old" },
};

function ChangeDialog({ parameter, onClose }: { parameter: RegulatoryParameter; onClose: () => void }) {
  const propose = useProposeParameter();
  const feedback = useFeedback();
  const [value, setValue] = useState(parameter.current?.value ? String(Number(parameter.current.value)) : "");
  const [from, setFrom] = useState(todayIso());
  const [source, setSource] = useState("");
  const [error, setError] = useState<string | null>(null);
  const adorn = UNIT_ADORNMENT[parameter.unit];
  const backDated = from < todayIso();

  async function submit() {
    setError(null);
    try {
      await propose.mutateAsync({ key: parameter.key, value, effective_from: from, source: source.trim() || null });
      feedback.success("Sent for approval — a scheme-setup checker must approve the new value.");
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't send the change.");
    }
  }

  return (
    <Dialog open onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>Change {parameter.label.toLowerCase()}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ pt: 1 }}>
          <Typography color="text.secondary">{parameter.help}</Typography>
          <Typography>
            In force now: <strong>{parameter.current ? parameter.current.display : "not set"}</strong>
            {parameter.current && ` (since ${formatDate(parameter.current.effective_from)})`}
          </Typography>
          <TextField
            label="New value"
            type="number"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            required
            slotProps={{
              htmlInput: { min: Number(parameter.minimum), max: Number(parameter.maximum), step: parameter.unit === "percent" ? "0.01" : parameter.unit === "money" ? "0.01" : "1" },
              input: {
                startAdornment: adorn.start ? <InputAdornment position="start">{adorn.start}</InputAdornment> : undefined,
                endAdornment: adorn.end ? <InputAdornment position="end">{adorn.end}</InputAdornment> : undefined,
              },
            }}
          />
          <TextField
            label="Takes effect from"
            type="date"
            value={from}
            onChange={(e) => setFrom(e.target.value)}
            required
            slotProps={{ inputLabel: { shrink: true } }}
            helperText="Dates before this keep the value that applied then."
          />
          {backDated && (
            <Alert severity="warning">
              This date is in the past. Calculations already made are not changed, but anything worked out again for dates from{" "}
              {formatDate(from)} will use the new value. The checker will see it marked as back-dated.
            </Alert>
          )}
          <TextField label="Source" value={source} onChange={(e) => setSource(e.target.value)} fullWidth helperText="e.g. Pension Act 2023 s.66, RBM directive of 1 March 2026" />
          {error && <Alert severity="error">{error}</Alert>}
        </Stack>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" onClick={submit} disabled={!value || !from || propose.isPending}>
          {propose.isPending ? "Sending…" : "Send for approval"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

function HistoryDialog({ parameter, onClose }: { parameter: RegulatoryParameter; onClose: () => void }) {
  const today = todayIso();
  return (
    <Dialog open onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>{parameter.label} — history</DialogTitle>
      <DialogContent>
        {parameter.versions.length === 0 ? (
          <Typography color="text.secondary">No value has been set yet.</Typography>
        ) : (
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>From</TableCell>
                <TableCell>Value</TableCell>
                <TableCell>Source</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {parameter.versions.map((v) => (
                <TableRow key={v.id}>
                  <TableCell sx={{ whiteSpace: "nowrap" }}>
                    {formatDate(v.effective_from)}
                    {v.id === parameter.current?.id && <StatusChip status="in_force" tone="success" sx={{ ml: 1 }} />}
                    {v.effective_from > today && <StatusChip status="scheduled" tone="info" sx={{ ml: 1 }} />}
                  </TableCell>
                  <TableCell sx={{ fontWeight: 600 }}>{v.display}</TableCell>
                  <TableCell>{v.source ?? "—"}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onClose}>Close</Button>
      </DialogActions>
    </Dialog>
  );
}

export function ParametersTab() {
  const { user } = useAuth();
  const canChange = user?.roles.includes("scheme_config_maker") ?? false;
  const query = useParameters();
  const [changing, setChanging] = useState<RegulatoryParameter | null>(null);
  const [history, setHistory] = useState<RegulatoryParameter | null>(null);
  const rows = query.data ?? [];
  const groups = [...new Set(rows.map((p) => p.group))];

  return (
    <>
      <TableContainer component={Paper}>
        <ResponsiveTable size="small">
          <TableHead>
            <TableRow>
              <TableCell>Parameter</TableCell>
              <TableCell>In force</TableCell>
              <TableCell>Scheduled change</TableCell>
              <TableCell align="right">Actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            <TableStateRow colSpan={4} loading={query.isLoading} error={query.error?.message ?? null} onRetry={() => query.refetch()} empty="No parameters." count={rows.length} />
            {groups.map((group) => (
              <Fragment key={group}>
                <TableRow>
                  <TableCell colSpan={4} sx={{ bgcolor: "action.hover", fontWeight: 600, py: 0.75 }}>
                    {group}
                  </TableCell>
                </TableRow>
                {rows
                  .filter((p) => p.group === group)
                  .map((p) => (
                    <TableRow key={p.key} hover>
                      <TableCell>
                        <Typography variant="body2" sx={{ fontWeight: 500 }}>
                          {p.label}
                        </Typography>
                        <Typography variant="caption" color="text.secondary">
                          {p.help}
                        </Typography>
                      </TableCell>
                      <TableCell sx={{ whiteSpace: "nowrap" }}>
                        {p.current ? (
                          <>
                            <Typography variant="body2" sx={{ fontWeight: 600 }}>
                              {p.current.display}
                            </Typography>
                            <Typography variant="caption" color="text.secondary">
                              since {formatDate(p.current.effective_from)}
                            </Typography>
                          </>
                        ) : (
                          <StatusChip status="not_set" tone="warning" />
                        )}
                      </TableCell>
                      <TableCell sx={{ whiteSpace: "nowrap" }}>
                        {p.upcoming ? `${p.upcoming.display} from ${formatDate(p.upcoming.effective_from)}` : "—"}
                        {p.pending_approval_id && (
                          <div>
                            <RouterLink to={`/approvals/${p.pending_approval_id}`} aria-label={`View the waiting change to ${p.label}`}>
                              <StatusChip status="change_pending" clickable sx={{ mt: 0.5 }} />
                            </RouterLink>
                          </div>
                        )}
                      </TableCell>
                      <TableCell align="right">
                        <RowActions
                          actions={[
                            ...(canChange && !p.pending_approval_id ? [{ label: "Change", onClick: () => setChanging(p) }] : []),
                            { label: "History", onClick: () => setHistory(p) },
                          ]}
                        />
                      </TableCell>
                    </TableRow>
                  ))}
              </Fragment>
            ))}
          </TableBody>
        </ResponsiveTable>
      </TableContainer>
      {changing && <ChangeDialog parameter={changing} onClose={() => setChanging(null)} />}
      {history && <HistoryDialog parameter={history} onClose={() => setHistory(null)} />}
    </>
  );
}
