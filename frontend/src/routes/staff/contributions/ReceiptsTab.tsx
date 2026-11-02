import { useEffect, useState } from "react";
import { Link as RouterLink, useNavigate } from "react-router-dom";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Link from "@mui/material/Link";
import MenuItem from "@mui/material/MenuItem";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TablePagination from "@mui/material/TablePagination";
import TableRow from "@mui/material/TableRow";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { ResponsiveTable } from "../../../components/ResponsiveTable";
import { StatusChip } from "../../../components/StatusChip";
import { TableStateRow } from "../../../components/TableStateRow";
import { useAuth } from "../../../auth/AuthContext";
import { useUrlParam } from "../../../hooks/useUrlState";
import { useReceipts } from "../../../queries/receipts";
import { formatAmount, formatMoney } from "../../../utils/format";
import { formatDate } from "../../../utils/date";
import { RecordReceiptDialog } from "./ReceiptDialogs";

const VIEWS = {
  all: "All",
  notified: "Notices to confirm",
  pending_approval: "Awaiting approval",
  unallocated: "Unallocated money",
  unidentified: "Unidentified money",
  rejected: "Rejected",
} as const;
type View = keyof typeof VIEWS;

// Money in (FR-CON-004): payment notices from principal officers, confirmed
// receipts and the unallocated (suspense) money with its ageing.
export function ReceiptsTab({ fundId }: { fundId: string }) {
  const { user } = useAuth();
  const navigate = useNavigate();
  const canCapture = user?.roles.includes("contributions_officer") ?? false;
  const [viewParam, setView] = useUrlParam("view");
  const view = (viewParam && viewParam in VIEWS ? viewParam : "all") as View;
  const [q, setQ] = useUrlParam("q");
  const [search, setSearch] = useState(q ?? "");
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(25);
  const [recording, setRecording] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => {
      if ((q ?? "") !== search.trim()) { setQ(search.trim() || null); setPage(0); }
    }, 350);
    return () => clearTimeout(t);
  }, [search]); // eslint-disable-line react-hooks/exhaustive-deps

  const query = useReceipts(fundId, {
    status: view === "notified" || view === "pending_approval" || view === "rejected" ? view : null,
    unallocated: view === "unallocated", unidentified: view === "unidentified", q: q ?? "", page: page + 1, page_size: pageSize,
  });
  const data = query.data;
  const rows = data?.items ?? [];
  const suspense = (data?.unallocated_ageing ?? []).reduce((sum, b) => sum + Number(b.amount), 0);

  return (
    <Stack spacing={2}>
      {!!data?.notices_waiting && view !== "notified" && (
        <Alert severity="info" action={<Button color="inherit" size="small" onClick={() => { setView("notified"); setPage(0); }}>Show</Button>}>
          {data.notices_waiting} payment notice{data.notices_waiting === 1 ? "" : "s"} from principal officers waiting to be checked against the bank statement.
        </Alert>
      )}

      <Paper sx={{ p: { xs: 2, sm: 2.5 } }}>
        <Stack direction={{ xs: "column", md: "row" }} spacing={2} sx={{ justifyContent: "space-between" }}>
          <Box>
            <Typography variant="overline" color="text.secondary">Unallocated money</Typography>
            <Typography variant="h5" component="p" sx={{ fontWeight: 600 }}>{formatMoney(suspense)}</Typography>
            <Typography variant="body2" color="text.secondary">Confirmed receipts not yet allocated to members, by age from value date.</Typography>
          </Box>
          <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr 1fr", sm: "repeat(4, minmax(120px, 1fr))" }, gap: 1.5 }}>
            {(data?.unallocated_ageing ?? []).map((b, i) => (
              <Box key={b.label} sx={{ p: 1.5, borderRadius: 1, bgcolor: "action.hover", border: 1, borderColor: i === 3 && Number(b.amount) ? "error.main" : "transparent" }}>
                <Typography variant="caption" color="text.secondary">{b.label}</Typography>
                <Typography sx={{ fontWeight: 600 }}>{formatAmount(b.amount)}</Typography>
                <Typography variant="caption" color="text.secondary">{b.count} receipt{b.count === 1 ? "" : "s"}</Typography>
              </Box>
            ))}
          </Box>
        </Stack>
      </Paper>

      <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} useFlexGap sx={{ flexWrap: "wrap", alignItems: { sm: "center" } }}>
        <TextField size="small" label="Search" placeholder="Receipt, notice, payer or reference" value={search} onChange={(e) => setSearch(e.target.value)} sx={{ minWidth: { sm: 300 } }} />
        <TextField select size="small" label="Show" value={view} onChange={(e) => { setView(e.target.value === "all" ? null : e.target.value); setPage(0); }} sx={{ minWidth: 200 }}>
          {(Object.keys(VIEWS) as View[]).map((k) => (
            <MenuItem key={k} value={k}>{VIEWS[k]}</MenuItem>
          ))}
        </TextField>
        <Box sx={{ flexGrow: 1 }} />
        {canCapture && <Button variant="contained" onClick={() => setRecording(true)}>Record money received</Button>}
      </Stack>

      <Paper>
        <TableContainer>
          <ResponsiveTable size="small">
            <TableHead>
              <TableRow>
                <TableCell>Receipt / notice</TableCell>
                <TableCell>Employer</TableCell>
                <TableCell>Value date</TableCell>
                <TableCell align="right">Amount (MWK)</TableCell>
                <TableCell align="right">Unallocated (MWK)</TableCell>
                <TableCell>Status</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              <TableStateRow colSpan={6} loading={query.isLoading} error={query.error?.message ?? null} onRetry={() => query.refetch()} count={rows.length}
                empty={view === "all" && !q ? "No money recorded yet. Payment notices from principal officers and receipts you record appear here." : "Nothing matches."} />
              {rows.map((r) => (
                <TableRow key={r.id} hover onClick={() => navigate(`/contributions/receipts/${r.id}`)} sx={{ cursor: "pointer" }}>
                  <TableCell sx={{ fontWeight: 600, whiteSpace: "nowrap" }}>
                    <Link component={RouterLink} to={`/contributions/receipts/${r.id}`} underline="hover" onClick={(e) => e.stopPropagation()}>
                      {r.receipt_number ?? r.notice_number ?? "New receipt"}
                    </Link>
                  </TableCell>
                  <TableCell>{r.employer ?? <em>Unidentified</em>}</TableCell>
                  <TableCell sx={{ whiteSpace: "nowrap" }}>{r.value_date ? formatDate(r.value_date) : `Paid ${formatDate(r.payment_date)}`}</TableCell>
                  <TableCell align="right">{formatAmount(r.amount ?? r.notified_amount)}</TableCell>
                  <TableCell align="right">{r.status === "confirmed" ? formatAmount(r.unallocated) : "—"}</TableCell>
                  <TableCell><StatusChip status={r.status} /></TableCell>
                </TableRow>
              ))}
            </TableBody>
          </ResponsiveTable>
        </TableContainer>
        <TablePagination component="div" count={data?.total ?? 0} page={page} rowsPerPage={pageSize} rowsPerPageOptions={[25, 50, 100]}
          onPageChange={(_, p) => setPage(p)} onRowsPerPageChange={(e) => { setPageSize(Number(e.target.value)); setPage(0); }} />
      </Paper>
      {recording && <RecordReceiptDialog fundId={fundId} onClose={() => setRecording(false)} />}
    </Stack>
  );
}
