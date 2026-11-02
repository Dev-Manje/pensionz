import { Fragment, useState } from "react";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Collapse from "@mui/material/Collapse";
import IconButton from "@mui/material/IconButton";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TablePagination from "@mui/material/TablePagination";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";
import KeyboardArrowDown from "@mui/icons-material/KeyboardArrowDown";
import KeyboardArrowUp from "@mui/icons-material/KeyboardArrowUp";
import { LoadingState } from "../../../components/LoadingState";
import { ResponsiveTable } from "../../../components/ResponsiveTable";
import { TableStateRow } from "../../../components/TableStateRow";
import { useFundChart, useJournal } from "../../../queries/ledger";
import { formatAmount } from "../../../utils/format";
import { formatDate, formatPeriod } from "../../../utils/date";
import { COMPONENT_LABELS, type JournalEntry } from "../../../api/ledger";
import type { Fund } from "../../../api/types";

const CLASS_LABELS = { asset: "Asset", liability: "Liability", equity: "Equity", income: "Income", expense: "Expense" } as const;

function EntryRow({ entry }: { entry: JournalEntry }) {
  const [open, setOpen] = useState(false);
  return (
    <Fragment>
      <TableRow hover>
        <TableCell sx={{ width: 48 }}>
          <IconButton size="small" aria-label={open ? "Hide lines" : "Show lines"} onClick={() => setOpen(!open)}>
            {open ? <KeyboardArrowUp /> : <KeyboardArrowDown />}
          </IconButton>
        </TableCell>
        <TableCell sx={{ fontWeight: 600, whiteSpace: "nowrap" }}>{entry.reference}</TableCell>
        <TableCell sx={{ whiteSpace: "nowrap" }}>{formatDate(entry.entry_date)}</TableCell>
        <TableCell>
          {entry.description}
          {entry.reverses && <Chip size="small" label={`Reverses ${entry.reverses}`} sx={{ ml: 1 }} />}
          {entry.reversed_by && <Chip size="small" color="warning" label={`Reversed by ${entry.reversed_by}`} sx={{ ml: 1 }} />}
        </TableCell>
        <TableCell align="right" sx={{ whiteSpace: "nowrap" }}>{formatAmount(entry.total)}</TableCell>
      </TableRow>
      <TableRow>
        <TableCell colSpan={5} sx={{ py: 0, borderBottom: open ? undefined : 0 }}>
          <Collapse in={open} unmountOnExit>
            <Typography variant="caption" color="text.secondary" component="p" sx={{ mt: 1 }}>
              {formatPeriod(entry.period)} · {entry.entity_type.replace(/_/g, " ")}
              {entry.created_by ? ` · posted by ${entry.created_by}` : ""}
            </Typography>
            <ResponsiveTable size="small" sx={{ mb: 2 }}>
              <TableHead>
                <TableRow>
                  <TableCell>Account</TableCell>
                  <TableCell>Member</TableCell>
                  <TableCell align="right">Debit</TableCell>
                  <TableCell align="right">Credit</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {entry.lines.map((l, i) => (
                  <TableRow key={i}>
                    <TableCell>
                      {l.code} {l.account_name}
                    </TableCell>
                    <TableCell>
                      {l.member_code ?? "—"}
                      {l.component ? ` · ${COMPONENT_LABELS[l.component]}` : ""}
                    </TableCell>
                    <TableCell align="right">{Number(l.debit) ? formatAmount(l.debit) : ""}</TableCell>
                    <TableCell align="right">{Number(l.credit) ? formatAmount(l.credit) : ""}</TableCell>
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

// The fund's books (FR-ACC-001…003): chart of accounts with balances (trial
// balance), the member sub-ledger tie-out, and the journal.
export function FundLedgerTab({ fund }: { fund: Fund }) {
  const chart = useFundChart(fund.id);
  const [account, setAccount] = useState("");
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(25);
  const journal = useJournal(fund.id, account, page, pageSize);

  if (chart.isLoading) return <LoadingState />;
  if (chart.error || !chart.data) {
    return (
      <Alert severity="error" action={<Button color="inherit" onClick={() => chart.refetch()}>Retry</Button>}>
        {chart.error?.message ?? "Couldn't load the ledger."}
      </Alert>
    );
  }
  const { accounts, tie_out: t } = chart.data;
  const active = accounts.filter((a) => Number(a.debit) || Number(a.credit));
  const shown = active.length ? active : accounts;
  const entries = journal.data?.items ?? [];

  return (
    <Stack spacing={2}>
      {chart.data.chart_status === "proposed" && (
        <Alert severity="info">This is the proposed chart of accounts — finance still has to confirm it.</Alert>
      )}
      {t.balanced && t.ties ? (
        <Alert severity="success">
          Ledger balanced. Member accounts total MWK {formatAmount(t.member_sub_ledger)}, which agrees with GL 2000 Member Fund Credits.
        </Alert>
      ) : (
        <Alert severity="error">
          {!t.balanced
            ? `Debits ${formatAmount(t.debits)} don't equal credits ${formatAmount(t.credits)}.`
            : `GL 2000 (${formatAmount(t.member_credits_gl)}) doesn't agree with member accounts (${formatAmount(t.member_sub_ledger)}).`}
        </Alert>
      )}

      <Paper>
        <Typography variant="subtitle1" component="h2" sx={{ fontWeight: 600, px: 2, pt: 2 }}>
          Trial balance
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ px: 2, pb: 1 }}>
          {active.length ? "Accounts with postings. Choose an account to see its entries." : "Nothing posted yet — all accounts of the chart are listed."}
        </Typography>
        <TableContainer>
          <ResponsiveTable size="small">
            <TableHead>
              <TableRow>
                <TableCell>Code</TableCell>
                <TableCell>Account</TableCell>
                <TableCell>Class</TableCell>
                <TableCell align="right">Debit (MWK)</TableCell>
                <TableCell align="right">Credit (MWK)</TableCell>
                <TableCell align="right">Balance (MWK)</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {shown.map((a) => (
                <TableRow
                  key={a.id}
                  hover
                  selected={account === a.code}
                  onClick={() => { setAccount(account === a.code ? "" : a.code); setPage(0); }}
                  sx={{ cursor: "pointer" }}
                >
                  <TableCell sx={{ fontWeight: 600 }}>{a.code}</TableCell>
                  <TableCell>{a.name}</TableCell>
                  <TableCell>{CLASS_LABELS[a.account_class]}</TableCell>
                  <TableCell align="right">{formatAmount(a.debit)}</TableCell>
                  <TableCell align="right">{formatAmount(a.credit)}</TableCell>
                  <TableCell align="right" sx={{ fontWeight: 600 }}>{formatAmount(a.balance)}</TableCell>
                </TableRow>
              ))}
              <TableRow>
                <TableCell sx={{ fontWeight: 700 }}>Total</TableCell>
                <TableCell />
                <TableCell />
                <TableCell align="right" sx={{ fontWeight: 700 }}>{formatAmount(t.debits)}</TableCell>
                <TableCell align="right" sx={{ fontWeight: 700 }}>{formatAmount(t.credits)}</TableCell>
                <TableCell />
              </TableRow>
            </TableBody>
          </ResponsiveTable>
        </TableContainer>
      </Paper>

      <Paper>
        <Stack direction="row" spacing={1} sx={{ px: 2, pt: 2, alignItems: "center", flexWrap: "wrap" }}>
          <Typography variant="subtitle1" component="h2" sx={{ fontWeight: 600 }}>
            Journal
          </Typography>
          {account && <Chip size="small" label={`Account ${account}`} onDelete={() => { setAccount(""); setPage(0); }} />}
        </Stack>
        <TableContainer>
          <ResponsiveTable size="small">
            <TableHead>
              <TableRow>
                <TableCell />
                <TableCell>Reference</TableCell>
                <TableCell>Date</TableCell>
                <TableCell>Description</TableCell>
                <TableCell align="right">Amount (MWK)</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              <TableStateRow
                colSpan={5}
                loading={journal.isLoading}
                error={journal.error?.message ?? null}
                onRetry={() => journal.refetch()}
                count={entries.length}
                empty="No entries yet. Receipts and contribution allocations post here."
              />
              {entries.map((e) => (
                <EntryRow key={e.id} entry={e} />
              ))}
            </TableBody>
          </ResponsiveTable>
        </TableContainer>
        <TablePagination
          component="div"
          count={journal.data?.total ?? 0}
          page={page}
          rowsPerPage={pageSize}
          rowsPerPageOptions={[25, 50, 100]}
          onPageChange={(_, p) => setPage(p)}
          onRowsPerPageChange={(e) => { setPageSize(Number(e.target.value)); setPage(0); }}
        />
      </Paper>
    </Stack>
  );
}
