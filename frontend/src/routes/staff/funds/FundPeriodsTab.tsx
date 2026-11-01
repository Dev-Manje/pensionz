import { useState } from "react";
import { Link as RouterLink } from "react-router-dom";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import ListItemText from "@mui/material/ListItemText";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { LoadingState } from "../../../components/LoadingState";
import { ResponsiveTable } from "../../../components/ResponsiveTable";
import { StatusChip } from "../../../components/StatusChip";
import { useFeedback } from "../../../components/feedback/FeedbackProvider";
import { usePeriodAction, usePeriods } from "../../../queries/funds";
import { formatDateTime, formatPeriod, todayIso } from "../../../utils/date";
import type { Fund, FundPeriod } from "../../../api/types";

// "2026-10-01" ↔ the <input type="month"> value "2026-10".
const toMonthInput = (iso: string) => iso.slice(0, 7);
const nextMonth = (iso: string) => {
  const [y, m] = iso.split("-").map(Number);
  return m === 12 ? `${y + 1}-01-01` : `${y}-${String(m + 1).padStart(2, "0")}-01`;
};

function OpenFirst({ fund }: { fund: Fund }) {
  const action = usePeriodAction(fund.id);
  const feedback = useFeedback();
  const [month, setMonth] = useState(toMonthInput(todayIso()));
  const [error, setError] = useState<string | null>(null);

  async function open() {
    setError(null);
    try {
      await action.mutateAsync({ action: "open", period: `${month}-01` });
      feedback.success(`${formatPeriod(`${month}-01`)} is now open for ${fund.code}.`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't open the month.");
    }
  }

  return (
    <Paper sx={{ p: { xs: 2, sm: 3 } }}>
      <Typography variant="subtitle1" component="h2" sx={{ fontWeight: 600 }}>
        Open the first processing month
      </Typography>
      <Typography color="text.secondary" sx={{ mb: 2, maxWidth: 640 }}>
        Transactions for this fund can only be posted into its open month. Choose the month its records start from; later
        months open one at a time as each month is closed.
      </Typography>
      <Stack direction={{ xs: "column", sm: "row" }} spacing={2} sx={{ alignItems: { sm: "flex-start" } }}>
        <TextField label="First month" type="month" value={month} onChange={(e) => setMonth(e.target.value)} slotProps={{ inputLabel: { shrink: true } }} />
        <Button variant="contained" onClick={open} disabled={!month || action.isPending} sx={{ minHeight: 56 }}>
          {action.isPending ? "Opening…" : "Open month"}
        </Button>
      </Stack>
      {error && <Alert severity="error" sx={{ mt: 2 }}>{error}</Alert>}
    </Paper>
  );
}

function CloseDialog({ fund, period, onClose }: { fund: Fund; period: FundPeriod; onClose: () => void }) {
  const action = usePeriodAction(fund.id);
  const feedback = useFeedback();
  const [error, setError] = useState<string | null>(null);

  async function close() {
    setError(null);
    try {
      await action.mutateAsync({ action: "close", period: period.period });
      feedback.success(`${formatPeriod(period.period)} closed — ${formatPeriod(nextMonth(period.period))} is now open.`);
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't close the month.");
    }
  }

  return (
    <Dialog open onClose={onClose} maxWidth="xs" fullWidth>
      <DialogTitle>Close {formatPeriod(period.period)}?</DialogTitle>
      <DialogContent>
        <Typography>
          Nothing more can be posted to {formatPeriod(period.period)} for {fund.code}, and {formatPeriod(nextMonth(period.period))} opens.
          Re-opening it later needs a finance checker's approval.
        </Typography>
        {error && <Alert severity="error" sx={{ mt: 2 }}>{error}</Alert>}
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" onClick={close} disabled={action.isPending}>
          {action.isPending ? "Closing…" : `Close ${formatPeriod(period.period)}`}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

function ReopenDialog({ fund, period, onClose }: { fund: Fund; period: FundPeriod; onClose: () => void }) {
  const action = usePeriodAction(fund.id);
  const feedback = useFeedback();
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    setError(null);
    if (reason.trim().length < 5) {
      setError("Say why the month has to be re-opened.");
      return;
    }
    try {
      await action.mutateAsync({ action: "reopen", periodId: period.id, reason: reason.trim() });
      feedback.success("Sent for approval — a finance checker must approve the re-open.");
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't send the request.");
    }
  }

  return (
    <Dialog open onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>Re-open {formatPeriod(period.period)}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ pt: 1 }}>
          <Alert severity="info">
            Once a finance checker approves, {formatPeriod(period.period)} becomes the open month again and{" "}
            {formatPeriod(nextMonth(period.period))} is withdrawn until it is closed again. This is refused if anything has
            already been posted to {formatPeriod(nextMonth(period.period))}.
          </Alert>
          <TextField label="Reason" value={reason} onChange={(e) => setReason(e.target.value)} required multiline minRows={2} fullWidth helperText="e.g. late contribution schedule from an employer" />
          {error && <Alert severity="error">{error}</Alert>}
        </Stack>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" onClick={submit} disabled={action.isPending}>
          {action.isPending ? "Sending…" : "Send for approval"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

// Processing months for one fund (FR-CFG-002): the open month with its
// month-end checklist, closing it, and asking to re-open the last closed one.
export function FundPeriodsTab({ fund }: { fund: Fund }) {
  const query = usePeriods(fund.id);
  const [closing, setClosing] = useState(false);
  const [reopening, setReopening] = useState<FundPeriod | null>(null);

  if (query.isLoading) return <LoadingState />;
  if (query.error || !query.data) {
    return (
      <Alert severity="error" action={<Button color="inherit" onClick={() => query.refetch()}>Retry</Button>}>
        {query.error?.message ?? "Couldn't load processing months."}
      </Alert>
    );
  }
  const state = query.data;
  const latestClosed = state.history.find((p) => p.status === "closed");

  return (
    <Stack spacing={2}>
      {state.pending_reopen_approval_id && (
        <Alert
          severity="warning"
          action={
            <Button color="inherit" size="small" component={RouterLink} to={`/approvals/${state.pending_reopen_approval_id}`}>
              View request
            </Button>
          }
        >
          A request to re-open a closed month is waiting for a finance checker.
        </Alert>
      )}

      {!state.current &&
        (state.can_open_first ? (
          <OpenFirst fund={fund} />
        ) : (
          <Alert severity="info">No processing month is open yet. Finance opens the fund's first month.</Alert>
        ))}

      {state.current && (
        <Paper sx={{ p: { xs: 2, sm: 3 } }}>
          <Stack direction={{ xs: "column", sm: "row" }} spacing={2} sx={{ justifyContent: "space-between", alignItems: { sm: "flex-start" } }}>
            <div>
              <Typography variant="overline" color="text.secondary">
                Open processing month
              </Typography>
              <Typography variant="h5" component="p" sx={{ fontWeight: 600 }}>
                {formatPeriod(state.current.period)}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Opened {formatDateTime(state.current.opened_at)}
                {state.current.opened_by ? ` by ${state.current.opened_by}` : ""}
              </Typography>
            </div>
            {state.can_close && (
              <Button variant="contained" onClick={() => setClosing(true)} sx={{ alignSelf: { xs: "stretch", sm: "flex-start" } }}>
                Close {formatPeriod(state.current.period)}
              </Button>
            )}
          </Stack>
          <Typography variant="subtitle2" component="h3" sx={{ mt: 3 }}>
            Month-end checks
          </Typography>
          <List dense disablePadding>
            {state.checklist.map((c) => (
              <ListItem key={c.key} disableGutters secondaryAction={<StatusChip status={c.status} />} sx={{ pr: 16 }}>
                <ListItemText primary={c.label} secondary={c.detail} />
              </ListItem>
            ))}
          </List>
        </Paper>
      )}

      {state.history.length > 0 && (
        <TableContainer component={Paper}>
          <ResponsiveTable size="small">
            <TableHead>
              <TableRow>
                <TableCell>Month</TableCell>
                <TableCell>Status</TableCell>
                <TableCell>Opened</TableCell>
                <TableCell>Closed</TableCell>
                <TableCell align="right">Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {state.history.map((p) => (
                <TableRow key={p.id}>
                  <TableCell sx={{ fontWeight: 600, whiteSpace: "nowrap" }}>{formatPeriod(p.period)}</TableCell>
                  <TableCell>
                    <StatusChip status={p.status} />
                  </TableCell>
                  <TableCell>
                    {formatDateTime(p.opened_at)}
                    {p.opened_by ? ` · ${p.opened_by}` : ""}
                  </TableCell>
                  <TableCell>{p.closed_at ? `${formatDateTime(p.closed_at)}${p.closed_by ? ` · ${p.closed_by}` : ""}` : "—"}</TableCell>
                  <TableCell align="right">
                    {state.can_request_reopen && latestClosed?.id === p.id && (
                      <Button size="small" onClick={() => setReopening(p)}>
                        Request re-open
                      </Button>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </ResponsiveTable>
        </TableContainer>
      )}

      {closing && state.current && <CloseDialog fund={fund} period={state.current} onClose={() => setClosing(false)} />}
      {reopening && <ReopenDialog fund={fund} period={reopening} onClose={() => setReopening(null)} />}
    </Stack>
  );
}
