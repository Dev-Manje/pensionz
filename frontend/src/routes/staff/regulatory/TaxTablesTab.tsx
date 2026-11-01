import { useState } from "react";
import { Link as RouterLink } from "react-router-dom";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import IconButton from "@mui/material/IconButton";
import InputAdornment from "@mui/material/InputAdornment";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import TextField from "@mui/material/TextField";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Typography from "@mui/material/Typography";
import AddIcon from "@mui/icons-material/Add";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutlined";
import { LoadingState } from "../../../components/LoadingState";
import { StatusChip } from "../../../components/StatusChip";
import { useFeedback } from "../../../components/feedback/FeedbackProvider";
import { useAuth } from "../../../auth/AuthContext";
import { useUrlParam } from "../../../hooks/useUrlState";
import {
  useProposeTaxTable,
  useTaxCalc,
  useTaxTables,
} from "../../../queries/regulatory";
import { formatDate, todayIso } from "../../../utils/date";
import { formatMoney, formatRate } from "../../../utils/format";
import {
  TAX_TABLE_LABELS,
  type TaxTable,
  type TaxTableKind,
} from "../../../api/types";

const KINDS = Object.keys(TAX_TABLE_LABELS) as TaxTableKind[];

function Bands({ table }: { table: TaxTable }) {
  return (
    <Box sx={{ overflowX: "auto" }}>
      <Table
        size="small"
        aria-label="Tax bands"
        sx={{ "& td, & th": { px: { xs: 1, sm: 2 } } }}
      >
        <TableHead>
          <TableRow>
            <TableCell>Income from</TableCell>
            <TableCell>Up to</TableCell>
            <TableCell align="right">Rate</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {table.bands.map((b) => (
            <TableRow key={b.lower}>
              <TableCell
                sx={{
                  fontVariantNumeric: "tabular-nums",
                  whiteSpace: "nowrap",
                }}
              >
                {formatMoney(b.lower)}
              </TableCell>
              <TableCell
                sx={{
                  fontVariantNumeric: "tabular-nums",
                  whiteSpace: "nowrap",
                }}
              >
                {b.upper ? formatMoney(b.upper) : "and above"}
              </TableCell>
              <TableCell
                align="right"
                sx={{ fontVariantNumeric: "tabular-nums" }}
              >
                {formatRate(b.rate_pct, { perAnnum: false })}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Box>
  );
}

function Calculator({ kind }: { kind: TaxTableKind }) {
  const [amount, setAmount] = useState("");
  const calc = useTaxCalc(kind, amount);
  return (
    <Stack
      direction={{ xs: "column", sm: "row" }}
      spacing={2}
      sx={{ alignItems: { sm: "center" } }}
    >
      <TextField
        label="Try an amount"
        type="number"
        size="small"
        value={amount}
        onChange={(e) => setAmount(e.target.value)}
        slotProps={{
          htmlInput: { min: 0, step: "0.01" },
          input: {
            startAdornment: (
              <InputAdornment position="start">MWK</InputAdornment>
            ),
          },
        }}
      />
      {calc.data && amount !== "" && (
        <Typography aria-live="polite">
          Tax: <strong>{formatMoney(calc.data.tax)}</strong>
        </Typography>
      )}
      {calc.error && (
        <Typography color="error">{calc.error.message}</Typography>
      )}
    </Stack>
  );
}

interface BandRow {
  lower: string;
  rate_pct: string;
}

function NewVersionDialog({
  kind,
  base,
  onClose,
}: {
  kind: TaxTableKind;
  base: TaxTable | null;
  onClose: () => void;
}) {
  const propose = useProposeTaxTable(kind);
  const feedback = useFeedback();
  const [from, setFrom] = useState(todayIso());
  const [source, setSource] = useState("");
  const [bands, setBands] = useState<BandRow[]>(
    base
      ? base.bands.map((b) => ({
          lower: String(Number(b.lower)),
          rate_pct: String(Number(b.rate_pct)),
        }))
      : [{ lower: "0", rate_pct: "0" }],
  );
  const [error, setError] = useState<string | null>(null);
  const setBand = (i: number, patch: Partial<BandRow>) =>
    setBands((rows) => rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));

  async function submit() {
    setError(null);
    try {
      await propose.mutateAsync({
        effective_from: from,
        source: source.trim() || null,
        bands,
      });
      feedback.success(
        "Sent for approval — a scheme-setup checker must approve the new table.",
      );
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't send the table.");
    }
  }

  return (
    <Dialog open onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>New {TAX_TABLE_LABELS[kind]} table</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ pt: 1 }}>
          <TextField
            label="Takes effect from"
            type="date"
            value={from}
            onChange={(e) => setFrom(e.target.value)}
            required
            slotProps={{ inputLabel: { shrink: true } }}
          />
          <Typography variant="body2" color="text.secondary">
            Each band taxes income from its starting amount up to the next
            band's start; the last band has no upper limit. The first band
            starts at 0.
          </Typography>
          {bands.map((b, i) => (
            <Stack
              key={i}
              direction="row"
              spacing={1}
              sx={{ alignItems: "center" }}
            >
              <TextField
                label={i === 0 ? "From (first band)" : "From"}
                type="number"
                size="small"
                value={b.lower}
                onChange={(e) => setBand(i, { lower: e.target.value })}
                disabled={i === 0}
                sx={{ flex: 2 }}
                slotProps={{
                  htmlInput: { min: 0, step: "0.01" },
                  input: {
                    startAdornment: (
                      <InputAdornment position="start">MWK</InputAdornment>
                    ),
                  },
                }}
              />
              <TextField
                label="Rate"
                type="number"
                size="small"
                value={b.rate_pct}
                onChange={(e) => setBand(i, { rate_pct: e.target.value })}
                sx={{ flex: 1 }}
                slotProps={{
                  htmlInput: { min: 0, max: 100, step: "0.01" },
                  input: {
                    endAdornment: (
                      <InputAdornment position="end">%</InputAdornment>
                    ),
                  },
                }}
              />
              <IconButton
                aria-label={`Remove band ${i + 1}`}
                onClick={() =>
                  setBands((rows) => rows.filter((_, j) => j !== i))
                }
                disabled={i === 0}
              >
                <DeleteOutlineIcon fontSize="small" />
              </IconButton>
            </Stack>
          ))}
          <Button
            startIcon={<AddIcon />}
            onClick={() =>
              setBands((rows) => [...rows, { lower: "", rate_pct: "" }])
            }
            sx={{ alignSelf: "flex-start" }}
            disabled={bands.length >= 20}
          >
            Add band
          </Button>
          <TextField
            label="Source"
            value={source}
            onChange={(e) => setSource(e.target.value)}
            fullWidth
            helperText="e.g. Taxation Act, MRA rates from 1 April 2027"
          />
          {error && <Alert severity="error">{error}</Alert>}
        </Stack>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onClose}>Cancel</Button>
        <Button
          variant="contained"
          onClick={submit}
          disabled={
            propose.isPending ||
            bands.some((b) => b.lower === "" || b.rate_pct === "")
          }
        >
          {propose.isPending ? "Sending…" : "Send for approval"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

export function TaxTablesTab() {
  const { user } = useAuth();
  const canChange = user?.roles.includes("scheme_config_maker") ?? false;
  const [kindParam, setKind] = useUrlParam("table");
  const kind: TaxTableKind = KINDS.includes(kindParam as TaxTableKind)
    ? (kindParam as TaxTableKind)
    : "paye_monthly";
  const query = useTaxTables(kind);
  const [creating, setCreating] = useState(false);
  const data = query.data;

  return (
    <Stack spacing={2}>
      <ToggleButtonGroup
        exclusive
        size="small"
        value={kind}
        onChange={(_, v: TaxTableKind | null) => v && setKind(v)}
        aria-label="Tax table"
      >
        {KINDS.map((k) => (
          <ToggleButton key={k} value={k}>
            {TAX_TABLE_LABELS[k]}
          </ToggleButton>
        ))}
      </ToggleButtonGroup>
      {query.isLoading && <LoadingState />}
      {query.error && <Alert severity="error">{query.error.message}</Alert>}
      {data && (
        <>
          {data.pending_approval_id && (
            <Alert
              severity="warning"
              action={
                <Button
                  color="inherit"
                  size="small"
                  component={RouterLink}
                  to={`/approvals/${data.pending_approval_id}`}
                >
                  View request
                </Button>
              }
            >
              A new version of this table is waiting for approval.
            </Alert>
          )}
          <Paper sx={{ p: { xs: 2, sm: 3 } }}>
            <Stack
              direction={{ xs: "column", sm: "row" }}
              spacing={2}
              sx={{
                justifyContent: "space-between",
                alignItems: { sm: "flex-start" },
                mb: 2,
              }}
            >
              <div>
                <Typography
                  variant="subtitle1"
                  component="h2"
                  sx={{ fontWeight: 600 }}
                >
                  {data.current
                    ? `In force since ${formatDate(data.current.effective_from)}`
                    : "No table in force"}
                </Typography>
                {data.current?.source && (
                  <Typography variant="body2" color="text.secondary">
                    Source: {data.current.source}
                  </Typography>
                )}
              </div>
              {canChange && !data.pending_approval_id && (
                <Button variant="contained" onClick={() => setCreating(true)}>
                  New version
                </Button>
              )}
            </Stack>
            {data.current ? (
              <Stack spacing={2}>
                <Bands table={data.current} />
                <Calculator kind={kind} />
              </Stack>
            ) : (
              <Typography color="text.secondary">
                No {data.label.toLowerCase()} table has been set up yet
                {canChange ? " — add one with “New version”." : "."}
              </Typography>
            )}
          </Paper>
          {data.upcoming && (
            <Paper sx={{ p: { xs: 2, sm: 3 } }}>
              <Stack
                direction="row"
                spacing={1}
                sx={{ alignItems: "center", mb: 1 }}
              >
                <Typography
                  variant="subtitle1"
                  component="h2"
                  sx={{ fontWeight: 600 }}
                >
                  From {formatDate(data.upcoming.effective_from)}
                </Typography>
                <StatusChip status="scheduled" tone="info" />
              </Stack>
              <Bands table={data.upcoming} />
            </Paper>
          )}
          {data.versions.length > 1 && (
            <Typography variant="body2" color="text.secondary">
              Earlier versions start{" "}
              {data.versions
                .filter(
                  (v) =>
                    v.id !== data.current?.id && v.id !== data.upcoming?.id,
                )
                .map((v) => formatDate(v.effective_from))
                .join(", ") || "—"}
              .
            </Typography>
          )}
        </>
      )}
      {creating && data && (
        <NewVersionDialog
          kind={kind}
          base={data.upcoming ?? data.current}
          onClose={() => setCreating(false)}
        />
      )}
    </Stack>
  );
}
