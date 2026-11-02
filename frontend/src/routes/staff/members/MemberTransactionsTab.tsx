import { useState } from "react";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TablePagination from "@mui/material/TablePagination";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";
import { LoadingState } from "../../../components/LoadingState";
import { ResponsiveTable } from "../../../components/ResponsiveTable";
import { TableStateRow } from "../../../components/TableStateRow";
import { useMemberLedger } from "../../../queries/ledger";
import { formatAmount, formatMoney } from "../../../utils/format";
import { formatDate, formatPeriod } from "../../../utils/date";
import { COMPONENT_LABELS } from "../../../api/ledger";
import type { Member } from "../../../api/types";

// The member's account (FR-ACC-001, FR-CON-001): balance per contribution
// component and every transaction posted to it, newest first.
export function MemberTransactionsTab({ member }: { member: Member }) {
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(50);
  const query = useMemberLedger(member.id, page, pageSize);

  if (query.isLoading) return <LoadingState />;
  if (query.error || !query.data) {
    return (
      <Alert severity="error" action={<Button color="inherit" onClick={() => query.refetch()}>Retry</Button>}>
        {query.error?.message ?? "Couldn't load the member's transactions."}
      </Alert>
    );
  }
  const data = query.data;

  return (
    <Stack spacing={2}>
      <Paper sx={{ p: { xs: 2, sm: 3 } }}>
        <Typography variant="overline" color="text.secondary">
          Account balance
        </Typography>
        <Typography variant="h5" component="p" sx={{ fontWeight: 600 }}>
          {formatMoney(data.balance)}
        </Typography>
      </Paper>

      {data.components.length > 0 && (
        <TableContainer component={Paper}>
          <ResponsiveTable size="small">
            <TableHead>
              <TableRow>
                <TableCell>Component</TableCell>
                <TableCell align="right">Contributions</TableCell>
                <TableCell align="right">Bonus</TableCell>
                <TableCell align="right">Withdrawals</TableCell>
                <TableCell align="right">Balance (MWK)</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {data.components.map((c) => (
                <TableRow key={c.component}>
                  <TableCell sx={{ fontWeight: 600 }}>{COMPONENT_LABELS[c.component]}</TableCell>
                  <TableCell align="right">{formatAmount(c.contributions)}</TableCell>
                  <TableCell align="right">{formatAmount(c.bonus)}</TableCell>
                  <TableCell align="right">{formatAmount(c.withdrawals)}</TableCell>
                  <TableCell align="right" sx={{ fontWeight: 600 }}>{formatAmount(c.balance)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </ResponsiveTable>
        </TableContainer>
      )}

      <Paper>
        <TableContainer>
          <ResponsiveTable size="small">
            <TableHead>
              <TableRow>
                <TableCell>Date</TableCell>
                <TableCell>Transaction</TableCell>
                <TableCell>Component</TableCell>
                <TableCell>For</TableCell>
                <TableCell>Reference</TableCell>
                <TableCell align="right">Debit</TableCell>
                <TableCell align="right">Credit</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              <TableStateRow
                colSpan={7}
                count={data.transactions.length}
                empty="No transactions yet. Allocated contributions appear here."
              />
              {data.transactions.map((t) => (
                <TableRow key={t.id}>
                  <TableCell sx={{ whiteSpace: "nowrap" }}>{formatDate(t.transaction_date)}</TableCell>
                  <TableCell>
                    {t.transaction_code} · {t.transaction_name}
                    {t.reversed && <Chip size="small" color="warning" label="Reversed" sx={{ ml: 1 }} />}
                  </TableCell>
                  <TableCell>{COMPONENT_LABELS[t.component]}</TableCell>
                  <TableCell sx={{ whiteSpace: "nowrap" }}>{t.contribution_month ? formatPeriod(t.contribution_month) : "—"}</TableCell>
                  <TableCell>{t.reference ?? t.journal_reference}</TableCell>
                  <TableCell align="right">{t.effect === "debit" ? formatAmount(t.amount) : ""}</TableCell>
                  <TableCell align="right">{t.effect === "credit" ? formatAmount(t.amount) : ""}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </ResponsiveTable>
        </TableContainer>
        <TablePagination
          component="div"
          count={data.total}
          page={page}
          rowsPerPage={pageSize}
          rowsPerPageOptions={[50, 100, 200]}
          onPageChange={(_, p) => setPage(p)}
          onRowsPerPageChange={(e) => { setPageSize(Number(e.target.value)); setPage(0); }}
        />
      </Paper>
    </Stack>
  );
}
