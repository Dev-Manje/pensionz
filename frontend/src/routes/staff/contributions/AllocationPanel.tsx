import { useEffect, useState } from "react";
import { Link as RouterLink } from "react-router-dom";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Link from "@mui/material/Link";
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
import { useFeedback } from "../../../components/feedback/FeedbackProvider";
import { useAllocate, useAllocationPreview } from "../../../queries/schedules";
import { formatAmount, formatMoney } from "../../../utils/format";
import { formatDate, formatDateTime } from "../../../utils/date";
import type { Schedule } from "../../../api/schedules";

function Figure({ label, value, strong }: { label: string; value: string; strong?: boolean }) {
  return (
    <Box sx={{ display: "flex", justifyContent: "space-between", gap: 2, py: 0.5 }}>
      <Typography color={strong ? "text.primary" : "text.secondary"} sx={{ fontWeight: strong ? 600 : 400 }}>{label}</Typography>
      <Typography sx={{ fontWeight: strong ? 700 : 500, whiteSpace: "nowrap" }}>{value}</Typography>
    </Box>
  );
}

// Matching the schedule to the employer's money and allocating it (FR-CON-005/006):
// the receipts must cover it exactly — hold until resolved.
export function AllocationPanel({ schedule, canAllocate }: { schedule: Schedule; canAllocate: boolean }) {
  const show = schedule.status === "ready" || schedule.status === "allocated";
  const query = useAllocationPreview(schedule.id, show);
  const allocate = useAllocate(schedule.id);
  const feedback = useFeedback();
  const [amounts, setAmounts] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (query.data) setAmounts(Object.fromEntries(query.data.candidates.map((c) => [c.receipt_id, Number(c.suggested) ? c.suggested : ""])));
  }, [query.data]);

  if (!show || !query.data) return null;
  const p = query.data;
  const picked = Object.values(amounts).reduce((sum, v) => sum + (Number(v.replace(/,/g, "")) || 0), 0);
  const matches = Math.abs(picked - Number(p.needed)) < 0.005;
  const live = p.allocations.find((a) => a.status === "pending_approval" || a.status === "posted");

  async function send() {
    setError(null);
    try {
      const receipts = Object.entries(amounts).filter(([, v]) => Number(v.replace(/,/g, "")) > 0).map(([receipt_id, v]) => ({ receipt_id, amount: v.replace(/,/g, "") }));
      await allocate.mutateAsync(receipts);
      feedback.success("Allocation sent to a contributions checker.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't send the allocation.");
    }
  }

  return (
    <Paper sx={{ p: { xs: 2, sm: 3 } }}>
      <Typography variant="subtitle1" component="h2" sx={{ fontWeight: 600, mb: 1 }}>Allocation</Typography>
      <Stack direction={{ xs: "column", md: "row" }} spacing={3}>
        <Box sx={{ flex: { md: "0 0 340px" }, maxWidth: { md: 340 } }}>
          <Figure label="Schedule total" value={formatMoney(p.schedule_total)} />
          {p.fees.map((f) => (
            <Figure key={f.code} label={`${f.name} ${Number(f.rate)}% · ${f.payer === "member" ? "from members" : "employer pays on top"}`}
              value={`${f.payer === "member" ? "−" : "+"} ${formatAmount(f.amount)}`} />
          ))}
          <Figure label="Money needed from receipts" value={formatMoney(p.needed)} strong />
          <Figure label="Credited to members" value={formatMoney(p.net_to_members)} strong />
        </Box>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          {live ? (
            <Alert severity={live.status === "posted" ? "success" : "warning"}
              action={live.approval_request_id && live.status === "pending_approval" ? (
                <Button color="inherit" size="small" component={RouterLink} to={`/approvals/${live.approval_request_id}`}>View request</Button>
              ) : undefined}>
              {live.status === "posted"
                ? `Allocated ${live.posted_at ? formatDateTime(live.posted_at) : ""}${live.approved_by ? ` (approved by ${live.approved_by})` : ""} — ${live.journal_reference}. Paid from ${live.receipts.join(", ")}.`
                : `Waiting for a contributions checker (sent by ${live.created_by}). Paid from ${live.receipts.join(", ")}.`}
            </Alert>
          ) : (
            <>
              {p.blocker && <Alert severity="warning" sx={{ mb: 2 }}>{p.blocker}</Alert>}
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                The employer's confirmed receipts with money available. Amounts are suggested oldest first; anything not used stays unallocated.
              </Typography>
              <TableContainer>
                <ResponsiveTable size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Receipt</TableCell>
                      <TableCell>Value date</TableCell>
                      <TableCell align="right">Available (MWK)</TableCell>
                      <TableCell align="right">Use (MWK)</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {p.candidates.length === 0 && (
                      <TableRow><TableCell colSpan={4}><Typography variant="body2" color="text.disabled" sx={{ fontStyle: "italic", textAlign: "center" }}>
                        No confirmed money from this employer is available yet.
                      </Typography></TableCell></TableRow>
                    )}
                    {p.candidates.map((c) => (
                      <TableRow key={c.receipt_id}>
                        <TableCell><Link component={RouterLink} to={`/contributions/receipts/${c.receipt_id}`}>{c.receipt_number}</Link></TableCell>
                        <TableCell>{formatDate(c.value_date)}</TableCell>
                        <TableCell align="right">{formatAmount(c.available)}</TableCell>
                        <TableCell align="right">
                          {canAllocate ? (
                            <TextField size="small" value={amounts[c.receipt_id] ?? ""} inputMode="decimal" disabled={!!p.blocker && !p.blocker.startsWith("Hold")}
                              onChange={(e) => setAmounts({ ...amounts, [c.receipt_id]: e.target.value })} sx={{ width: 140 }}
                              slotProps={{ htmlInput: { style: { textAlign: "right" }, "aria-label": `Use from ${c.receipt_number}` } }} />
                          ) : formatAmount(c.suggested)}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </ResponsiveTable>
              </TableContainer>
              {canAllocate && (
                <Stack direction={{ xs: "column", sm: "row" }} spacing={2} sx={{ mt: 2, alignItems: { sm: "center" }, justifyContent: "space-between" }}>
                  <Typography variant="body2" color={matches ? "success.main" : "text.secondary"}>
                    Using {formatMoney(picked)} of {formatMoney(p.needed)} needed
                  </Typography>
                  <Button variant="contained" onClick={send} disabled={!matches || allocate.isPending}>
                    {allocate.isPending ? "Sending…" : "Send allocation for approval"}
                  </Button>
                </Stack>
              )}
              {error && <Alert severity="error" sx={{ mt: 2 }}>{error}</Alert>}
            </>
          )}
          {p.allocations.filter((a) => a !== live).length > 0 && (
            <Box sx={{ mt: 2 }}>
              <Typography variant="caption" color="text.secondary">Earlier attempts</Typography>
              {p.allocations.filter((a) => a !== live).map((a) => (
                <Stack key={a.id} direction="row" spacing={1} sx={{ alignItems: "center", mt: 0.5 }}>
                  <StatusChip status={a.status} />
                  <Typography variant="body2">{formatMoney(a.amount)} · {a.created_by}</Typography>
                </Stack>
              ))}
            </Box>
          )}
        </Box>
      </Stack>
    </Paper>
  );
}
