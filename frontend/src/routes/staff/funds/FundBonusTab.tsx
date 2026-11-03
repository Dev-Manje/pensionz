import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import Alert from "@mui/material/Alert";
import Autocomplete from "@mui/material/Autocomplete";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import FormControlLabel from "@mui/material/FormControlLabel";
import FormGroup from "@mui/material/FormGroup";
import FormLabel from "@mui/material/FormLabel";
import InputAdornment from "@mui/material/InputAdornment";
import MenuItem from "@mui/material/MenuItem";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { useAuth } from "../../../auth/AuthContext";
import { LoadingState } from "../../../components/LoadingState";
import { StatusChip } from "../../../components/StatusChip";
import { useFeedback } from "../../../components/feedback/FeedbackProvider";
import { useCreateRun, useDeclarations, useProposeDeclaration } from "../../../queries/bonus";
import { useMembers } from "../../../queries/members";
import { COMPONENT_LABELS, type Component } from "../../../api/ledger";
import type { BonusDeclaration, BonusKind } from "../../../api/bonus";
import type { Fund, MemberSummary } from "../../../api/types";
import { formatDate } from "../../../utils/date";
import { formatMoney } from "../../../utils/format";
import { RUN_STATUS_TEXT } from "./bonusLabels";

const DEFAULT_COMPONENTS: Component[] = ["employee", "employer", "voluntary", "transfer_in"];

function DeclareDialog({ fund, onClose }: { fund: Fund; onClose: () => void }) {
  const propose = useProposeDeclaration(fund.id);
  const feedback = useFeedback();
  const year = new Date().getFullYear();
  const [kind, setKind] = useState<BonusKind>("final");
  const [start, setStart] = useState(`${year}-01-01`);
  const [end, setEnd] = useState(`${year}-06-30`);
  const [rate, setRate] = useState("");
  const [components, setComponents] = useState<Component[]>(DEFAULT_COMPONENTS);
  const [resolution, setResolution] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await propose.mutateAsync({ kind, period_start: start, period_end: end, rate, components, resolution: resolution || null });
      feedback.success("Sent for approval — a finance checker approves the rate before any bonus is run.");
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't send it.");
    }
  }

  const toggle = (c: Component) => setComponents((list) => (list.includes(c) ? list.filter((x) => x !== c) : [...list, c]));
  return (
    <Dialog open onClose={onClose} maxWidth="sm" fullWidth>
      <form onSubmit={submit}>
        <DialogTitle>Declare a bonus rate</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ pt: 1 }}>
            <Alert severity="info">
              Record the rate the trustees declared. Bonus = opening balance × rate × days ÷ 365, plus each contribution × rate × days from
              when it was credited to the period end ÷ 365, per member and component.
            </Alert>
            <TextField select label="Type" value={kind} onChange={(e) => setKind(e.target.value as BonusKind)} helperText={kind === "interim" ? "For members leaving before the final rate is known; trued up when the final rate is run." : "Credited to every member once the period has ended."}>
              <MenuItem value="final">Final rate</MenuItem>
              <MenuItem value="interim">Interim rate</MenuItem>
            </TextField>
            <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
              <TextField label="Period from" type="date" value={start} onChange={(e) => setStart(e.target.value)} required fullWidth slotProps={{ inputLabel: { shrink: true } }} />
              <TextField label="Period to" type="date" value={end} onChange={(e) => setEnd(e.target.value)} required fullWidth slotProps={{ inputLabel: { shrink: true } }} />
            </Stack>
            <TextField
              label="Rate a year"
              type="number"
              value={rate}
              onChange={(e) => setRate(e.target.value)}
              required
              slotProps={{ htmlInput: { min: 0, max: 100, step: "0.0001" }, input: { endAdornment: <InputAdornment position="end">% a year</InputAdornment> } }}
            />
            <Box component="fieldset" sx={{ border: 0, p: 0, m: 0 }}>
              <FormLabel component="legend" sx={{ fontSize: "0.8125rem", fontWeight: 600 }}>Components that earn bonus</FormLabel>
              <FormGroup sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr" } }}>
                {(Object.keys(COMPONENT_LABELS) as Component[]).map((c) => (
                  <FormControlLabel key={c} control={<Checkbox size="small" checked={components.includes(c)} onChange={() => toggle(c)} />} label={COMPONENT_LABELS[c]} />
                ))}
              </FormGroup>
            </Box>
            <TextField label="Trustee resolution (optional)" value={resolution} onChange={(e) => setResolution(e.target.value)} helperText="e.g. the minute number of the meeting that declared it" />
            {error && <Alert severity="error">{error}</Alert>}
          </Stack>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={onClose}>Cancel</Button>
          <Button type="submit" variant="contained" disabled={propose.isPending || !rate || components.length === 0}>
            {propose.isPending ? "Sending…" : "Send for approval"}
          </Button>
        </DialogActions>
      </form>
    </Dialog>
  );
}

function InterimDialog({ fund, declaration, onClose }: { fund: Fund; declaration: BonusDeclaration; onClose: () => void }) {
  const create = useCreateRun();
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const members = useMembers({ fund_id: fund.id, q, page_size: 25 });
  const [chosen, setChosen] = useState<MemberSummary[]>([]);
  const today = new Date().toISOString().slice(0, 10);
  const [asAt, setAsAt] = useState(today < declaration.period_end ? today : declaration.period_end);
  const [error, setError] = useState<string | null>(null);

  async function go() {
    setError(null);
    try {
      const run = await create.mutateAsync({ declarationId: declaration.id, body: { member_ids: chosen.map((m) => m.id), as_at: asAt } });
      navigate(`/funds/${fund.id}/bonus-runs/${run.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't calculate it.");
    }
  }

  return (
    <Dialog open onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>Interim bonus for leavers</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ pt: 1 }}>
          <Typography variant="body2" color="text.secondary">
            Members with an exit date in the period are calculated to that date; others to the date below.
          </Typography>
          <Autocomplete
            multiple
            options={members.data?.items ?? []}
            value={chosen}
            onChange={(_, v) => setChosen(v)}
            onInputChange={(_, v, reason) => reason === "input" && setQ(v)}
            filterOptions={(x) => x}
            loading={members.isLoading}
            getOptionLabel={(m) => `${m.account_code} — ${m.full_name}`}
            isOptionEqualToValue={(a, b) => a.id === b.id}
            renderInput={(params) => <TextField {...params} label="Members" placeholder="Search by name or account" />}
          />
          <TextField label="Calculate to" type="date" value={asAt} onChange={(e) => setAsAt(e.target.value)} slotProps={{ inputLabel: { shrink: true } }} />
          {error && <Alert severity="error">{error}</Alert>}
        </Stack>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" onClick={go} disabled={!chosen.length || create.isPending}>
          {create.isPending ? "Calculating…" : "Calculate preview"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

function DeclarationCard({ fund, d, canRun }: { fund: Fund; d: BonusDeclaration; canRun: boolean }) {
  const create = useCreateRun();
  const navigate = useNavigate();
  const feedback = useFeedback();
  const [interim, setInterim] = useState(false);
  const live = d.runs.find((r) => r.kind === "final" && r.status !== "reversed");
  const ended = d.period_end < new Date().toISOString().slice(0, 10);

  async function runFinal() {
    try {
      const run = await create.mutateAsync({ declarationId: d.id, body: {} });
      navigate(`/funds/${fund.id}/bonus-runs/${run.id}`);
    } catch (e) {
      feedback.error(e instanceof Error ? e.message : "Couldn't calculate it.");
    }
  }

  return (
    <Paper sx={{ p: { xs: 2, sm: 2.5 } }}>
      <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} sx={{ justifyContent: "space-between", alignItems: { sm: "flex-start" } }}>
        <Box>
          <Stack direction="row" spacing={1} sx={{ alignItems: "center", flexWrap: "wrap", gap: 1 }}>
            <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
              {Number(d.rate).toLocaleString(undefined, { maximumFractionDigits: 4 })}% a year
            </Typography>
            <StatusChip status={d.kind} label={d.kind === "final" ? "Final" : "Interim"} tone={d.kind === "final" ? "success" : "info"} />
          </Stack>
          <Typography variant="body2" color="text.secondary">
            {formatDate(d.period_start)} – {formatDate(d.period_end)} · {d.reference}
            {d.resolution ? ` · ${d.resolution}` : ""}
          </Typography>
          <Typography variant="body2" color="text.secondary">Earns on: {d.components.map((c) => COMPONENT_LABELS[c]).join(", ")}</Typography>
        </Box>
        {canRun && (
          <Box sx={{ flexShrink: 0 }}>
            {d.kind === "final" ? (
              !live && (
                <Button variant="contained" onClick={runFinal} disabled={!ended || create.isPending} title={ended ? undefined : "Available once the period has ended"}>
                  Run final bonus
                </Button>
              )
            ) : (
              <Button variant="outlined" onClick={() => setInterim(true)}>Interim for leavers</Button>
            )}
          </Box>
        )}
      </Stack>
      {d.runs.length > 0 && (
        <Stack spacing={0.75} sx={{ mt: 1.5 }}>
          {d.runs.map((r) => {
            const st = RUN_STATUS_TEXT[r.status];
            return (
              <Stack
                key={r.id}
                direction={{ xs: "column", sm: "row" }}
                spacing={1}
                sx={{ p: 1.25, borderRadius: 1, bgcolor: "action.hover", cursor: "pointer", justifyContent: "space-between", alignItems: { sm: "center" } }}
                onClick={() => navigate(`/funds/${fund.id}/bonus-runs/${r.id}`)}
              >
                <Typography variant="body2">
                  <strong>{r.reference}</strong> · {r.member_count} member{r.member_count === 1 ? "" : "s"} · {formatMoney(r.total_credit)}
                  {Number(r.total_debit) > 0 && ` credited, ${formatMoney(r.total_debit)} taken back`}
                </Typography>
                <StatusChip status={r.status} label={st.label} tone={st.tone} />
              </Stack>
            );
          })}
        </Stack>
      )}
      {interim && <InterimDialog fund={fund} declaration={d} onClose={() => setInterim(false)} />}
    </Paper>
  );
}

// Declared bonus per fund (FR-EAR-001…004): the trustees' rates and the runs that credit them.
export function FundBonusTab({ fund }: { fund: Fund }) {
  const { user } = useAuth();
  const canDeclare = user?.roles.includes("finance") ?? false;
  const declarations = useDeclarations(fund.id);
  const [declaring, setDeclaring] = useState(false);
  if (fund.fund_type === "defined_benefit") return <Alert severity="info">Defined benefit funds don't declare a bonus rate.</Alert>;
  return (
    <Stack spacing={2}>
      <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} sx={{ justifyContent: "space-between", alignItems: { sm: "center" } }}>
        <Typography color="text.secondary">Rates declared by the trustees and the bonus credited to members.</Typography>
        {canDeclare && <Button variant="contained" onClick={() => setDeclaring(true)} sx={{ whiteSpace: "nowrap" }}>Declare a rate</Button>}
      </Stack>
      {declarations.isLoading && <LoadingState />}
      {declarations.error && <Alert severity="error">{declarations.error.message}</Alert>}
      {declarations.data?.length === 0 && <Typography color="text.secondary">No bonus rates declared yet.</Typography>}
      {declarations.data?.map((d) => <DeclarationCard key={d.id} fund={fund} d={d} canRun={canDeclare} />)}
      {declaring && <DeclareDialog fund={fund} onClose={() => setDeclaring(false)} />}
    </Stack>
  );
}
