import { useState, type FormEvent } from "react";
import Alert from "@mui/material/Alert";
import Autocomplete from "@mui/material/Autocomplete";
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
import { ResponsiveTable } from "../../../components/ResponsiveTable";
import { RowActions } from "../../../components/RowActions";
import { StatusChip } from "../../../components/StatusChip";
import { TableStateRow } from "../../../components/TableStateRow";
import { useFeedback } from "../../../components/feedback/FeedbackProvider";
import { useAuth } from "../../../auth/AuthContext";
import { useFunds } from "../../../queries/funds";
import { useOfficers, useProposeOfficer, useProposeOfficerUpdate, useSendOfficerInvitation } from "../../../queries/officers";
import { formatDateTime } from "../../../utils/date";
import type { Officer } from "../../../api/officers";
import type { FundSummary } from "../../../api/types";

function OfficerDialog({ officer, onClose }: { officer: Officer | null; onClose: () => void }) {
  const propose = useProposeOfficer();
  const update = useProposeOfficerUpdate();
  const feedback = useFeedback();
  const funds = useFunds();
  const [email, setEmail] = useState(officer?.email ?? "");
  const [fullName, setFullName] = useState(officer?.full_name ?? "");
  const [phone, setPhone] = useState(officer?.phone ?? "");
  const [fundIds, setFundIds] = useState<string[]>(officer?.funds.filter((f) => f.granted).map((f) => f.id) ?? []);
  const [error, setError] = useState<string | null>(null);
  const busy = propose.isPending || update.isPending;
  // Only active funds take new employers.
  const options = (funds.data ?? []).filter((f) => f.status === "active" || fundIds.includes(f.id));

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (fundIds.length === 0) {
      setError("Choose at least one fund the officer will work in.");
      return;
    }
    try {
      if (officer) {
        await update.mutateAsync({ id: officer.user_id, input: { full_name: fullName, phone: phone || null, fund_ids: fundIds } });
      } else {
        await propose.mutateAsync({ email, full_name: fullName, phone: phone || null, fund_ids: fundIds });
      }
      feedback.success("Sent for approval — a scheme-setup checker must approve it before it takes effect.");
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
    }
  }

  return (
    <Dialog open onClose={onClose} maxWidth="sm" fullWidth>
      <form onSubmit={submit}>
        <DialogTitle>{officer ? `Change ${officer.full_name}` : "Add a principal officer"}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ pt: 1 }}>
            <Alert severity="info">
              {officer
                ? "Changes need approval from a scheme-setup checker."
                : "Once a scheme-setup checker approves, the officer gets an email invitation to choose a password. They sign in with a one-time code sent by email and can then apply for their employer to join the chosen funds."}
            </Alert>
            {!officer && (
              <TextField label="Email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required fullWidth autoComplete="off" />
            )}
            <TextField label="Full name" value={fullName} onChange={(e) => setFullName(e.target.value)} required fullWidth slotProps={{ htmlInput: { minLength: 2 } }} />
            <TextField label="Phone" type="tel" value={phone} onChange={(e) => setPhone(e.target.value)} fullWidth helperText="Optional, e.g. 0999 123 456" />
            <Autocomplete
              multiple
              options={options}
              loading={funds.isLoading}
              value={options.filter((f) => fundIds.includes(f.id))}
              onChange={(_, chosen: FundSummary[]) => setFundIds(chosen.map((f) => f.id))}
              getOptionLabel={(f) => `${f.code} — ${f.name}`}
              isOptionEqualToValue={(a, b) => a.id === b.id}
              renderInput={(params) => (
                <TextField
                  {...params}
                  label="Funds the officer works in"
                  required={fundIds.length === 0}
                  helperText={funds.error ? `Couldn't load funds: ${funds.error.message}` : "The officer can apply for an employer to join only these funds."}
                  error={!!funds.error}
                />
              )}
            />
            {officer && officer.funds.some((f) => !f.granted) && (
              <Typography variant="body2" color="text.secondary">
                Also works in {officer.funds.filter((f) => !f.granted).map((f) => f.code).join(", ")} through their employers.
              </Typography>
            )}
            {error && <Alert severity="error">{error}</Alert>}
          </Stack>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={onClose}>Cancel</Button>
          <Button type="submit" variant="contained" disabled={busy}>
            {busy ? "Sending…" : "Send for approval"}
          </Button>
        </DialogActions>
      </form>
    </Dialog>
  );
}

function officerStatus(o: Officer) {
  if (o.status === "active" && o.awaiting_setup) return "awaiting_setup";
  return o.status;
}

// Principal officers onboarded by the pension administrator (FR-PRT-006).
export function OfficersTab() {
  const { user: me } = useAuth();
  const canChange = me?.roles.some((r) => r === "scheme_config_maker" || r === "admin") ?? false;
  const [q, setQ] = useState("");
  const officers = useOfficers(q.trim());
  const sendInvite = useSendOfficerInvitation();
  const feedback = useFeedback();
  const [editing, setEditing] = useState<Officer | "new" | null>(null);

  async function invite(o: Officer) {
    try {
      await sendInvite.mutateAsync(o.user_id);
      feedback.success(`${o.awaiting_setup ? "Invitation" : "Password reset link"} sent to ${o.email}.`);
    } catch (e) {
      feedback.error(e instanceof Error ? e.message : "Couldn't send the link.");
    }
  }

  const rows = officers.data ?? [];
  const cols = canChange ? 6 : 5;
  return (
    <>
      <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} sx={{ mb: 2, justifyContent: "space-between", alignItems: { sm: "center" } }}>
        <TextField label="Search by name or email" value={q} onChange={(e) => setQ(e.target.value)} size="small" sx={{ width: { xs: "100%", sm: 320 } }} />
        {canChange && <Button variant="contained" onClick={() => setEditing("new")}>Add officer</Button>}
      </Stack>
      <TableContainer component={Paper}>
        <ResponsiveTable size="small">
          <TableHead>
            <TableRow>
              <TableCell>Officer</TableCell>
              <TableCell>Funds</TableCell>
              <TableCell>Employers</TableCell>
              <TableCell>Status</TableCell>
              <TableCell>Last sign-in</TableCell>
              {canChange && <TableCell align="right">Actions</TableCell>}
            </TableRow>
          </TableHead>
          <TableBody>
            <TableStateRow
              colSpan={cols}
              loading={officers.isLoading}
              error={officers.error?.message ?? null}
              onRetry={() => officers.refetch()}
              empty={q ? "No officers match that search." : "No principal officers yet. Add the first one with “Add officer”."}
              count={rows.length}
            />
            {rows.map((o) => (
              <TableRow key={o.user_id} hover>
                <TableCell>
                  <Typography variant="body2" sx={{ fontWeight: 500 }}>{o.full_name}</Typography>
                  <Typography variant="caption" color="text.secondary">{o.email}</Typography>
                </TableCell>
                <TableCell>{o.funds.map((f) => f.code).join(", ") || "—"}</TableCell>
                <TableCell>
                  {o.employers.length === 0 ? (
                    <Typography variant="body2" color="text.secondary">None yet</Typography>
                  ) : (
                    o.employers.map((e) => (
                      <Typography key={e.scheme_id} variant="body2">{e.name} ({e.fund_code})</Typography>
                    ))
                  )}
                </TableCell>
                <TableCell>
                  <Stack direction="row" spacing={0.5} sx={{ flexWrap: "wrap", gap: 0.5 }}>
                    <StatusChip status={officerStatus(o)} />
                    {o.pending_approval_id && <StatusChip status="pending" label="Change waiting" />}
                  </Stack>
                </TableCell>
                <TableCell sx={{ whiteSpace: "nowrap" }}>{o.last_login_at ? formatDateTime(o.last_login_at) : "Never"}</TableCell>
                {canChange && (
                  <TableCell align="right">
                    <RowActions
                      actions={[
                        ...(o.pending_approval_id ? [] : [{ label: "Change", onClick: () => setEditing(o) }]),
                        ...(o.status === "active"
                          ? [{ label: o.awaiting_setup ? "Resend invitation" : "Send password reset link", onClick: () => invite(o) }]
                          : []),
                      ]}
                    />
                  </TableCell>
                )}
              </TableRow>
            ))}
          </TableBody>
        </ResponsiveTable>
      </TableContainer>
      {editing && <OfficerDialog officer={editing === "new" ? null : editing} onClose={() => setEditing(null)} />}
    </>
  );
}
