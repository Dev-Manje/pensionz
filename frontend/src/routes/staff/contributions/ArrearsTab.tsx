import { Fragment, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Collapse from "@mui/material/Collapse";
import IconButton from "@mui/material/IconButton";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";
import KeyboardArrowDown from "@mui/icons-material/KeyboardArrowDown";
import KeyboardArrowUp from "@mui/icons-material/KeyboardArrowUp";
import { LoadingState } from "../../../components/LoadingState";
import { ResponsiveTable } from "../../../components/ResponsiveTable";
import { StatusChip } from "../../../components/StatusChip";
import { TableStateRow } from "../../../components/TableStateRow";
import { getFundArrears, type Bucket, type EmployerArrears } from "../../../api/arrears";
import { formatAmount, formatMoney } from "../../../utils/format";
import { formatDate, formatPeriod } from "../../../utils/date";

const MONTH_STATUS = {
  paid: { label: "Paid", tone: "success" },
  part_paid: { label: "Part paid", tone: "warning" },
  unpaid: { label: "Not paid", tone: "error" },
  not_due: { label: "Not yet due", tone: "default" },
} as const;

export function AgeingTiles({ buckets }: { buckets: Bucket[] }) {
  return (
    <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr 1fr", sm: "repeat(3, 1fr)", lg: "repeat(6, 1fr)" }, gap: 1.5 }}>
      {buckets.map((b, i) => (
        <Box key={b.label} sx={{ p: 1.5, borderRadius: 1, bgcolor: "action.hover", border: 1, borderColor: i >= 3 && Number(b.amount) ? "error.main" : "transparent" }}>
          <Typography variant="caption" color="text.secondary">{b.label}</Typography>
          <Typography sx={{ fontWeight: 600 }}>{formatAmount(b.amount)}</Typography>
        </Box>
      ))}
    </Box>
  );
}

function EmployerRow({ e, showInterest }: { e: EmployerArrears; showInterest: boolean }) {
  const [open, setOpen] = useState(false);
  return (
    <Fragment>
      <TableRow hover onClick={() => setOpen(!open)} sx={{ cursor: "pointer" }}>
        <TableCell sx={{ width: 48 }}>
          <IconButton size="small" aria-label={open ? "Hide months" : "Show months"}>{open ? <KeyboardArrowUp /> : <KeyboardArrowDown />}</IconButton>
        </TableCell>
        <TableCell sx={{ fontWeight: 600 }}>{e.employer}</TableCell>
        <TableCell align="right">{e.months_in_arrears}</TableCell>
        <TableCell>{e.oldest_bucket ?? "—"}</TableCell>
        <TableCell align="right" sx={{ fontWeight: 600, color: Number(e.total_arrears) ? "error.main" : undefined }}>{formatAmount(e.total_arrears)}</TableCell>
        {showInterest && <TableCell align="right">{e.total_interest ? formatAmount(e.total_interest) : "—"}</TableCell>}
      </TableRow>
      <TableRow>
        <TableCell colSpan={showInterest ? 6 : 5} sx={{ py: 0, borderBottom: open ? undefined : 0 }}>
          <Collapse in={open} unmountOnExit>
            <ResponsiveTable size="small" sx={{ mb: 2 }}>
              <TableHead>
                <TableRow>
                  <TableCell>Month</TableCell>
                  <TableCell>Due</TableCell>
                  <TableCell align="right">Members</TableCell>
                  <TableCell align="right">Expected</TableCell>
                  <TableCell align="right">Paid</TableCell>
                  <TableCell align="right">Arrears</TableCell>
                  <TableCell>Age</TableCell>
                  {showInterest && <TableCell align="right">Interest</TableCell>}
                  <TableCell>Status</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {e.months.map((m) => (
                  <TableRow key={m.month}>
                    <TableCell sx={{ whiteSpace: "nowrap" }}>{formatPeriod(m.month)}</TableCell>
                    <TableCell sx={{ whiteSpace: "nowrap" }}>{formatDate(m.due_date)}</TableCell>
                    <TableCell align="right">
                      {m.members_expected}
                      {m.members_without_estimate ? <Typography variant="caption" color="warning.dark" component="div">{m.members_without_estimate} without salary</Typography> : null}
                    </TableCell>
                    <TableCell align="right">{formatAmount(m.expected)}</TableCell>
                    <TableCell align="right">{formatAmount(m.paid)}</TableCell>
                    <TableCell align="right" sx={{ fontWeight: 600 }}>{m.status === "not_due" ? "—" : formatAmount(m.arrears)}</TableCell>
                    <TableCell>{m.days_overdue && Number(m.arrears) ? `${m.days_overdue} days · ${m.bucket}` : "—"}</TableCell>
                    {showInterest && <TableCell align="right">{m.interest && Number(m.interest) ? formatAmount(m.interest) : "—"}</TableCell>}
                    <TableCell><StatusChip status={m.status} label={MONTH_STATUS[m.status].label} tone={MONTH_STATUS[m.status].tone} /></TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </ResponsiveTable>
          </Collapse>
        </TableCell>
      </TableRow>
    </Fragment>
  );
}

// Arrears per employer and month (FR-CON-002, FR-CON-008): expected from members' salaries
// and category rates vs what has been allocated; aged from each month's due date.
export function ArrearsTab({ fundId }: { fundId: string }) {
  const query = useQuery({ queryKey: ["arrears", fundId], queryFn: () => getFundArrears(fundId) });
  if (query.isLoading) return <LoadingState />;
  if (query.error || !query.data) {
    return <Alert severity="error" action={<Button color="inherit" onClick={() => query.refetch()}>Retry</Button>}>{query.error?.message ?? "Couldn't work out the arrears."}</Alert>;
  }
  const a = query.data;
  const showInterest = a.interest_rate_set;
  return (
    <Stack spacing={2}>
      <Paper sx={{ p: { xs: 2, sm: 2.5 } }}>
        <Stack direction={{ xs: "column", md: "row" }} spacing={2} sx={{ justifyContent: "space-between", mb: 2 }}>
          <Box>
            <Typography variant="overline" color="text.secondary">Contributions in arrears</Typography>
            <Typography variant="h5" component="p" sx={{ fontWeight: 600 }}>{formatMoney(a.total_arrears)}</Typography>
            <Typography variant="body2" color="text.secondary">
              As at {formatDate(a.as_at)}. Expected = category rates × salaries on record; paid = allocated schedules.
            </Typography>
          </Box>
          {showInterest && a.total_interest && (
            <Box sx={{ textAlign: { md: "right" } }}>
              <Typography variant="overline" color="text.secondary">Late-payment interest (not charged)</Typography>
              <Typography variant="h6" component="p" sx={{ fontWeight: 600 }}>{formatMoney(a.total_interest)}</Typography>
            </Box>
          )}
        </Stack>
        <AgeingTiles buckets={a.ageing} />
        {!showInterest && (
          <Typography variant="body2" color="text.secondary" sx={{ mt: 1.5 }}>
            No late-payment interest rate is set in Regulatory, so interest isn't worked out.
          </Typography>
        )}
      </Paper>
      <Paper>
        <TableContainer>
          <ResponsiveTable size="small">
            <TableHead>
              <TableRow>
                <TableCell />
                <TableCell>Employer</TableCell>
                <TableCell align="right">Months in arrears</TableCell>
                <TableCell>Oldest</TableCell>
                <TableCell align="right">Arrears (MWK)</TableCell>
                {showInterest && <TableCell align="right">Interest (MWK)</TableCell>}
              </TableRow>
            </TableHead>
            <TableBody>
              <TableStateRow colSpan={showInterest ? 6 : 5} count={a.employers.length} empty="No employers with members yet." />
              {a.employers.map((e) => <EmployerRow key={e.scheme_id} e={e} showInterest={showInterest} />)}
            </TableBody>
          </ResponsiveTable>
        </TableContainer>
      </Paper>
    </Stack>
  );
}
