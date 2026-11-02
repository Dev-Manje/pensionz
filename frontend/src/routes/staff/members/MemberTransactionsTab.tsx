import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
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
import { getMemberArrears } from "../../../api/arrears";
import { AgeingTiles } from "../contributions/ArrearsTab";
import type { Member } from "../../../api/types";

// The member's account (FR-ACC-001, FR-CON-001): balance per contribution
// component and every transaction posted to it, newest first.
export function MemberTransactionsTab({ member }: { member: Member }) {
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(50);
  const query = useMemberLedger(member.id, page, pageSize);
  const owed = useQuery({ queryKey: ["arrears", "member", member.id], queryFn: () => getMemberArrears(member.id), enabled: !!member.company.employer_code });

  if (query.isLoading) return <LoadingState />;
  if (query.error || !query.data) {
    return (
      <Alert severity="error" action={<Button color="inherit" onClick={() => query.refetch()}>Retry</Button>}>
        {query.error?.message ?? "Couldn't load the member's transactions."}
      </Alert>
    );
  }
  const data = query.data;
  const unpaid = (owed.data?.months ?? []).filter((m) => Number(m.arrears) && m.days_overdue);

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

      {owed.data && (
        <Paper sx={{ p: { xs: 2, sm: 3 } }}>
          <Typography variant="overline" color="text.secondary">Employer contributions in arrears</Typography>
          <Typography variant="h6" component="p" sx={{ fontWeight: 600, mb: 1.5 }}>{formatMoney(owed.data.total_arrears)}</Typography>
          <AgeingTiles buckets={owed.data.ageing} />
          {unpaid.length > 0 && (
            <Typography variant="body2" color="text.secondary" sx={{ mt: 1.5 }}>
              Unpaid: {unpaid.slice(0, 6).map((m) => `${formatPeriod(m.month)} (${formatAmount(m.arrears)})`).join(" · ")}
              {unpaid.length > 6 ? ` · and ${unpaid.length - 6} earlier months` : ""}
            </Typography>
          )}
        </Paper>
      )}

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
