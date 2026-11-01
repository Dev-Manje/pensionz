import { useState, type FormEvent } from "react";
import { Link as RouterLink } from "react-router-dom";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import InputAdornment from "@mui/material/InputAdornment";
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
import { useFeeRules, useProposeFeeRule } from "../../../queries/feeRules";
import { useSchemes } from "../../../queries/schemes";
import { formatDate, todayIso } from "../../../utils/date";
import { formatMoney, formatRate } from "../../../utils/format";
import {
  FEE_BASIS_LABELS,
  FEE_FREQUENCY_LABELS,
  FEE_PAYER_LABELS,
  FEE_TYPE_LABELS,
  type FeeBasis,
  type FeeFrequency,
  type FeePayer,
  type FeeRule,
  type FeeRuleInput,
  type FeeType,
  type Fund,
} from "../../../api/types";

function rateText(r: Pick<FeeRule, "basis" | "rate">): string {
  if (r.basis === "flat_per_member") return `${formatMoney(r.rate)} per member`;
  return `${formatRate(r.rate, { perAnnum: r.basis === "pct_assets" })} of ${r.basis === "pct_assets" ? "assets" : "contributions"}`;
}

function inForce(r: FeeRule, today: string): string {
  if (r.effective_from > today) return "scheduled";
  if (r.effective_to && r.effective_to <= today) return "ended";
  return "in_force";
}

function select<T extends string>(label: string, value: T, onChange: (v: T) => void, labels: Record<T, string>, allowed?: T[]) {
  return (
    <TextField select label={label} value={value} onChange={(e) => onChange(e.target.value as T)} fullWidth>
      {(Object.keys(labels) as T[])
        .filter((k) => !allowed || allowed.includes(k))
        .map((k) => (
          <MenuItem key={k} value={k}>
            {labels[k]}
          </MenuItem>
        ))}
    </TextField>
  );
}

function RuleDialog({ fund, rule, onClose }: { fund: Fund; rule: FeeRule | null; onClose: () => void }) {
  const propose = useProposeFeeRule(fund.id);
  const schemes = useSchemes(fund.id);
  const feedback = useFeedback();
  const [form, setForm] = useState<FeeRuleInput>(
    rule
      ? { code: rule.code, name: rule.name, scheme_id: rule.scheme_id, fee_type: rule.fee_type, basis: rule.basis, rate: String(Number(rule.rate)), payer: rule.payer, frequency: rule.frequency, effective_from: rule.effective_from, effective_to: rule.effective_to }
      : { code: "", name: "", scheme_id: null, fee_type: "administration", basis: "pct_contributions", rate: "", payer: "member", frequency: "per_contribution", effective_from: todayIso(), effective_to: null },
  );
  const [error, setError] = useState<string | null>(null);
  const set = <K extends keyof FeeRuleInput>(key: K, value: FeeRuleInput[K]) => setForm((f) => ({ ...f, [key]: value }));
  const frequencies: FeeFrequency[] = form.basis === "pct_contributions" ? ["per_contribution"] : ["monthly", "quarterly", "annually"];

  function setBasis(basis: FeeBasis) {
    setForm((f) => ({ ...f, basis, frequency: basis === "pct_contributions" ? "per_contribution" : f.frequency === "per_contribution" ? "monthly" : f.frequency }));
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await propose.mutateAsync({ id: rule?.id, input: form });
      feedback.success("Sent for approval — a scheme-setup checker must approve it.");
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
    }
  }

  return (
    <Dialog open onClose={onClose} maxWidth="sm" fullWidth>
      <form onSubmit={submit}>
        <DialogTitle>{rule ? `Change ${rule.name}` : `Add a fee rule to ${fund.code}`}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ pt: 1 }}>
            <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
              <TextField label="Code" value={form.code} onChange={(e) => set("code", e.target.value)} required sx={{ width: { sm: 160 } }} slotProps={{ htmlInput: { maxLength: 10, style: { textTransform: "uppercase" } } }} />
              <TextField label="Name" value={form.name} onChange={(e) => set("name", e.target.value)} required fullWidth slotProps={{ htmlInput: { minLength: 2 } }} />
            </Stack>
            <TextField
              select
              label="Applies to"
              value={form.scheme_id ?? ""}
              onChange={(e) => set("scheme_id", e.target.value || null)}
              helperText="An employer's own rule replaces the fund-wide rule of the same fee type for that employer."
            >
              <MenuItem value="">The whole fund</MenuItem>
              {(schemes.data ?? []).map((s) => (
                <MenuItem key={s.id} value={s.id}>
                  {s.code} — {s.name}
                </MenuItem>
              ))}
            </TextField>
            {select("Fee", form.fee_type, (v: FeeType) => set("fee_type", v), FEE_TYPE_LABELS)}
            <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
              {select("Charged as", form.basis, setBasis, FEE_BASIS_LABELS)}
              <TextField
                label="Rate"
                type="number"
                value={form.rate}
                onChange={(e) => set("rate", e.target.value)}
                required
                fullWidth
                slotProps={{
                  htmlInput: { min: 0, step: "0.0001" },
                  input:
                    form.basis === "flat_per_member"
                      ? { startAdornment: <InputAdornment position="start">MWK</InputAdornment> }
                      : { endAdornment: <InputAdornment position="end">{form.basis === "pct_assets" ? "% a year" : "%"}</InputAdornment> },
                }}
              />
            </Stack>
            <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
              {select("Paid by", form.payer, (v: FeePayer) => set("payer", v), FEE_PAYER_LABELS)}
              {select("Charged", form.frequency, (v: FeeFrequency) => set("frequency", v), FEE_FREQUENCY_LABELS, frequencies)}
            </Stack>
            <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
              <TextField label="From" type="date" value={form.effective_from} onChange={(e) => set("effective_from", e.target.value)} required fullWidth slotProps={{ inputLabel: { shrink: true } }} />
              <TextField
                label="Until (optional)"
                type="date"
                value={form.effective_to ?? ""}
                onChange={(e) => set("effective_to", e.target.value || null)}
                fullWidth
                slotProps={{ inputLabel: { shrink: true } }}
                helperText="End a rule here before a new rate starts."
              />
            </Stack>
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

// The fund's fee rules (FR-CFG-008).
export function FundFeesTab({ fund }: { fund: Fund }) {
  const query = useFeeRules(fund.id);
  const [editing, setEditing] = useState<FeeRule | "new" | null>(null);
  const rows = query.data ?? [];
  const today = todayIso();

  return (
    <Stack spacing={2}>
      <Stack direction="row" sx={{ justifyContent: "space-between", alignItems: "center", gap: 2, flexWrap: "wrap" }}>
        <Typography color="text.secondary" sx={{ maxWidth: 640 }}>
          Fees charged in this fund, who pays them and from when. Charging and posting them comes with the fund ledger.
        </Typography>
        {fund.can_edit && (
          <Button variant="contained" onClick={() => setEditing("new")}>
            Add fee rule
          </Button>
        )}
      </Stack>
      <TableContainer component={Paper}>
        <ResponsiveTable size="small">
          <TableHead>
            <TableRow>
              <TableCell>Code</TableCell>
              <TableCell>Fee</TableCell>
              <TableCell>Applies to</TableCell>
              <TableCell>Rate</TableCell>
              <TableCell>Paid by</TableCell>
              <TableCell>Dates</TableCell>
              <TableCell>Status</TableCell>
              {fund.can_edit && <TableCell align="right">Actions</TableCell>}
            </TableRow>
          </TableHead>
          <TableBody>
            <TableStateRow
              colSpan={fund.can_edit ? 8 : 7}
              loading={query.isLoading}
              error={query.error?.message ?? null}
              onRetry={() => query.refetch()}
              empty={fund.can_edit ? "No fee rules yet. Add the first with “Add fee rule”." : "No fee rules yet."}
              count={rows.length}
            />
            {rows.map((r) => (
              <TableRow key={r.id} hover>
                <TableCell sx={{ fontWeight: 600 }}>{r.code}</TableCell>
                <TableCell>
                  <Typography variant="body2" sx={{ fontWeight: 500 }}>
                    {r.name}
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    {FEE_TYPE_LABELS[r.fee_type]} · {FEE_FREQUENCY_LABELS[r.frequency].toLowerCase()}
                  </Typography>
                </TableCell>
                <TableCell>{r.employer ?? "Whole fund"}</TableCell>
                <TableCell sx={{ whiteSpace: "nowrap" }}>{rateText(r)}</TableCell>
                <TableCell>{FEE_PAYER_LABELS[r.payer]}</TableCell>
                <TableCell sx={{ whiteSpace: "nowrap" }}>
                  {formatDate(r.effective_from)} – {r.effective_to ? formatDate(r.effective_to) : "open"}
                </TableCell>
                <TableCell>
                  <StatusChip status={inForce(r, today)} />
                  {r.pending_approval_id && (
                    <RouterLink to={`/approvals/${r.pending_approval_id}`} aria-label={`View the waiting change to ${r.name}`}>
                      <StatusChip status="change_pending" clickable sx={{ ml: 0.5 }} />
                    </RouterLink>
                  )}
                </TableCell>
                {fund.can_edit && (
                  <TableCell align="right">
                    {!r.pending_approval_id && (
                      <Button size="small" onClick={() => setEditing(r)}>
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
      {editing && <RuleDialog fund={fund} rule={editing === "new" ? null : editing} onClose={() => setEditing(null)} />}
    </Stack>
  );
}
