import { useState } from "react";
import { Link as RouterLink } from "react-router-dom";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
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
import { ResponsiveTable } from "../../../components/ResponsiveTable";
import { StatusChip } from "../../../components/StatusChip";
import { TableStateRow } from "../../../components/TableStateRow";
import { useFeedback } from "../../../components/feedback/FeedbackProvider";
import { useInvestmentOptions, useProposeInvestmentOption } from "../../../queries/investmentOptions";
import { formatDate } from "../../../utils/date";
import {
  PRICING_METHOD_LABELS,
  type Fund,
  type InvestmentOption,
  type InvestmentOptionInput,
  type InvestmentOptionStatus,
  type PricingMethod,
} from "../../../api/types";

const PRICING_HELP: Record<PricingMethod, string> = {
  declared_rate: "Members earn the bonus rate the trustees declare each period.",
  unit_price: "Members hold units priced from the portfolio's value (pricing is built in a later phase).",
};

function OptionDialog({ fund, option, onClose }: { fund: Fund; option: InvestmentOption | null; onClose: () => void }) {
  const propose = useProposeInvestmentOption(fund.id);
  const feedback = useFeedback();
  const [form, setForm] = useState<InvestmentOptionInput>(
    option
      ? { code: option.code, name: option.name, pricing_method: option.pricing_method, status: option.status, launch_date: option.launch_date, description: option.description }
      : { code: "", name: "", pricing_method: "declared_rate", status: "active", launch_date: null, description: null },
  );
  const [error, setError] = useState<string | null>(null);
  const set = <K extends keyof InvestmentOptionInput>(key: K, value: InvestmentOptionInput[K]) => setForm((f) => ({ ...f, [key]: value }));

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await propose.mutateAsync({ id: option?.id, input: form });
      feedback.success("Sent for approval — a scheme-setup checker must approve it.");
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
    }
  }

  return (
    <Dialog open onClose={onClose} maxWidth="sm" fullWidth>
      <form onSubmit={submit}>
        <DialogTitle>{option ? `Change ${option.name}` : `Add an investment option to ${fund.code}`}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ pt: 1 }}>
            <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
              <TextField
                label="Code"
                value={form.code}
                onChange={(e) => set("code", e.target.value)}
                required
                slotProps={{ htmlInput: { maxLength: 10, style: { textTransform: "uppercase" } } }}
                sx={{ width: { sm: 160 } }}
              />
              <TextField label="Name" value={form.name} onChange={(e) => set("name", e.target.value)} required fullWidth slotProps={{ htmlInput: { minLength: 2 } }} />
            </Stack>
            <TextField
              select
              label="Pricing method"
              value={form.pricing_method}
              onChange={(e) => set("pricing_method", e.target.value as PricingMethod)}
              disabled={!!option}
              helperText={option ? "Can't change once set — close this option and add a new one instead." : PRICING_HELP[form.pricing_method]}
            >
              {(Object.keys(PRICING_METHOD_LABELS) as PricingMethod[]).map((m) => (
                <MenuItem key={m} value={m}>
                  {PRICING_METHOD_LABELS[m]}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              label="Launch date"
              type="date"
              value={form.launch_date ?? ""}
              onChange={(e) => set("launch_date", e.target.value || null)}
              slotProps={{ inputLabel: { shrink: true } }}
            />
            {option && (
              <TextField
                select
                label="Status"
                value={form.status}
                onChange={(e) => set("status", e.target.value as InvestmentOptionStatus)}
                helperText={form.status === "closed" ? "Money already invested stays; no new money or switches in." : "Open for new money."}
              >
                <MenuItem value="active">Active</MenuItem>
                <MenuItem value="closed">Closed</MenuItem>
              </TextField>
            )}
            <TextField label="Description" value={form.description ?? ""} onChange={(e) => set("description", e.target.value || null)} multiline minRows={2} fullWidth />
            {error && <Alert severity="error">{error}</Alert>}
          </Stack>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={onClose}>Cancel</Button>
          <Button type="submit" variant="contained" disabled={propose.isPending}>
            {propose.isPending ? "Sending…" : "Send for approval"}
          </Button>
        </DialogActions>
      </form>
    </Dialog>
  );
}

// The fund's investment options (FR-CFG-007); categories pick their default from these.
export function FundOptionsTab({ fund }: { fund: Fund }) {
  const query = useInvestmentOptions(fund.id);
  const [editing, setEditing] = useState<InvestmentOption | "new" | null>(null);
  const rows = query.data ?? [];
  const isDb = fund.fund_type === "defined_benefit";

  if (isDb) {
    return <Alert severity="info">Defined benefit funds pay a formula benefit, so members have no investment options to choose from.</Alert>;
  }
  return (
    <Stack spacing={2}>
      <Stack direction="row" sx={{ justifyContent: "space-between", alignItems: "center", gap: 2, flexWrap: "wrap" }}>
        <Typography color="text.secondary" sx={{ maxWidth: 640 }}>
          Where members' money is invested. Each benefit category names its default option.
        </Typography>
        {fund.can_edit && (
          <Button variant="contained" onClick={() => setEditing("new")}>
            Add option
          </Button>
        )}
      </Stack>
      <TableContainer component={Paper}>
        <ResponsiveTable size="small">
          <TableHead>
            <TableRow>
              <TableCell>Code</TableCell>
              <TableCell>Option</TableCell>
              <TableCell>Pricing</TableCell>
              <TableCell>Launched</TableCell>
              <TableCell>Status</TableCell>
              {fund.can_edit && <TableCell align="right">Actions</TableCell>}
            </TableRow>
          </TableHead>
          <TableBody>
            <TableStateRow
              colSpan={fund.can_edit ? 6 : 5}
              loading={query.isLoading}
              error={query.error?.message ?? null}
              onRetry={() => query.refetch()}
              empty={fund.can_edit ? "No investment options yet. Add the first with “Add option”." : "No investment options yet."}
              count={rows.length}
            />
            {rows.map((o) => (
              <TableRow key={o.id} hover>
                <TableCell sx={{ fontWeight: 600 }}>{o.code}</TableCell>
                <TableCell>
                  <Typography variant="body2" sx={{ fontWeight: 500 }}>
                    {o.name}
                  </Typography>
                  {o.description && (
                    <Typography variant="caption" color="text.secondary">
                      {o.description}
                    </Typography>
                  )}
                </TableCell>
                <TableCell>{PRICING_METHOD_LABELS[o.pricing_method]}</TableCell>
                <TableCell sx={{ whiteSpace: "nowrap" }}>{formatDate(o.launch_date)}</TableCell>
                <TableCell>
                  <StatusChip status={o.status} />
                  {o.pending_approval_id && (
                    <RouterLink to={`/approvals/${o.pending_approval_id}`} aria-label={`View the waiting change to ${o.name}`}>
                      <StatusChip status="change_pending" clickable sx={{ ml: 0.5 }} />
                    </RouterLink>
                  )}
                </TableCell>
                {fund.can_edit && (
                  <TableCell align="right">
                    {!o.pending_approval_id && (
                      <Button size="small" onClick={() => setEditing(o)}>
                        Change
                      </Button>
                    )}
                  </TableCell>
                )}
              </TableRow>
            ))}
          </TableBody>
        </ResponsiveTable>
      </TableContainer>
      {editing && <OptionDialog fund={fund} option={editing === "new" ? null : editing} onClose={() => setEditing(null)} />}
    </Stack>
  );
}
