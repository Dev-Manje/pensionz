import type { ReactNode } from "react";
import { Link as RouterLink, useParams } from "react-router-dom";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Breadcrumbs from "@mui/material/Breadcrumbs";
import Button from "@mui/material/Button";
import Link from "@mui/material/Link";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Tab from "@mui/material/Tab";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Tabs from "@mui/material/Tabs";
import Typography from "@mui/material/Typography";
import { LoadingState } from "../../../components/LoadingState";
import { PageHeader } from "../../../components/PageHeader";
import { ResponsiveTable } from "../../../components/ResponsiveTable";
import { StatusChip } from "../../../components/StatusChip";
import { TableStateRow } from "../../../components/TableStateRow";
import { useUrlTab } from "../../../hooks/useUrlState";
import { useFund } from "../../../queries/funds";
import { formatDate, MONTH_NAMES } from "../../../utils/date";
import { BANK_PURPOSE_LABELS, FUND_TYPE_LABELS, type Fund } from "../../../api/types";

const TABS = ["details", "trustees", "bank-accounts"] as const;
type FundTab = (typeof TABS)[number];

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <Box>
      <Typography variant="caption" color="text.secondary" component="dt">
        {label}
      </Typography>
      <Typography component="dd" sx={{ m: 0, overflowWrap: "anywhere" }}>
        {children || "—"}
      </Typography>
    </Box>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <Paper sx={{ p: { xs: 2, sm: 3 } }}>
      <Typography variant="subtitle1" component="h2" sx={{ fontWeight: 600, mb: 2 }}>
        {title}
      </Typography>
      <Box component="dl" sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr", lg: "repeat(3, 1fr)" }, gap: 2, m: 0 }}>
        {children}
      </Box>
    </Paper>
  );
}

function Details({ fund }: { fund: Fund }) {
  const address = [fund.address_line1, fund.address_line2, fund.address_line3, fund.address_line4, fund.address_line5].filter(Boolean);
  return (
    <Stack spacing={2}>
      <Section title="Registration">
        <Field label="Fund code">{fund.code}</Field>
        <Field label="Fund type">{FUND_TYPE_LABELS[fund.fund_type]}</Field>
        <Field label="Registration number">{fund.registration_number}</Field>
        <Field label="TPIN">{fund.tpin}</Field>
        <Field label="Financial year ends">
          {fund.financial_year_end_month ? MONTH_NAMES[fund.financial_year_end_month - 1] : "December (calendar year)"}
        </Field>
      </Section>
      <Section title="Address and contact">
        <Field label="Address">
          {address.length > 0 &&
            address.map((line) => (
              <span key={line} style={{ display: "block" }}>
                {line}
              </span>
            ))}
        </Field>
        <Field label="Phone">{fund.phone}</Field>
        <Field label="Fax">{fund.fax}</Field>
        <Field label="Email">{fund.email}</Field>
        <Field label="Website">{fund.website}</Field>
      </Section>
      <Section title="Contact person">
        <Field label="Name">{fund.contact_name}</Field>
        <Field label="Email">{fund.contact_email}</Field>
        <Field label="Phone">{fund.contact_phone}</Field>
        <Field label="Alternative phone">{fund.contact_alt_phone}</Field>
      </Section>
    </Stack>
  );
}

function Trustees({ fund }: { fund: Fund }) {
  return (
    <TableContainer component={Paper}>
      <ResponsiveTable size="small">
        <TableHead>
          <TableRow>
            <TableCell>Name</TableCell>
            <TableCell>Designation</TableCell>
            <TableCell>Email</TableCell>
            <TableCell>Phone</TableCell>
            <TableCell>Appointed</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          <TableStateRow colSpan={5} loading={false} error={null} empty="No trustees recorded. Add them with “Edit fund”." count={fund.trustees.length} />
          {fund.trustees.map((t) => (
            <TableRow key={t.id}>
              <TableCell sx={{ fontWeight: 500 }}>{t.full_name}</TableCell>
              <TableCell>{t.designation ?? "—"}</TableCell>
              <TableCell>{t.email ?? "—"}</TableCell>
              <TableCell>{t.phone ?? "—"}</TableCell>
              <TableCell sx={{ whiteSpace: "nowrap" }}>{formatDate(t.appointed_on)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </ResponsiveTable>
    </TableContainer>
  );
}

function BankAccounts({ fund }: { fund: Fund }) {
  return (
    <TableContainer component={Paper}>
      <ResponsiveTable size="small">
        <TableHead>
          <TableRow>
            <TableCell>Bank</TableCell>
            <TableCell>Branch</TableCell>
            <TableCell>Account name</TableCell>
            <TableCell>Account number</TableCell>
            <TableCell>Currency</TableCell>
            <TableCell>Used for</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          <TableStateRow colSpan={6} loading={false} error={null} empty="No bank accounts recorded. Add them with “Edit fund”." count={fund.bank_accounts.length} />
          {fund.bank_accounts.map((a) => (
            <TableRow key={a.id}>
              <TableCell sx={{ fontWeight: 500 }}>{a.bank_name}</TableCell>
              <TableCell>{a.branch_name ?? "—"}</TableCell>
              <TableCell>{a.account_name}</TableCell>
              <TableCell sx={{ fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap" }}>{a.account_number ?? a.account_number_masked}</TableCell>
              <TableCell>{a.currency}</TableCell>
              <TableCell>{BANK_PURPOSE_LABELS[a.purpose]}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </ResponsiveTable>
    </TableContainer>
  );
}

export function FundDetailPage() {
  const { fundId } = useParams();
  const query = useFund(fundId);
  const [tab, setTab] = useUrlTab(TABS);

  if (query.isLoading) return <LoadingState />;
  if (query.error || !query.data) {
    return (
      <Alert severity="error" action={<Button component={RouterLink} to="/funds">Back to funds</Button>}>
        {query.error?.message ?? "Fund not found"}
      </Alert>
    );
  }
  const fund = query.data;

  return (
    <>
      <Breadcrumbs sx={{ mb: 1 }}>
        <Link component={RouterLink} to="/funds" underline="hover" color="inherit">
          Funds
        </Link>
        <Typography color="text.primary">{fund.code}</Typography>
      </Breadcrumbs>
      <PageHeader
        title={fund.name}
        description={`${fund.code} · ${FUND_TYPE_LABELS[fund.fund_type]}`}
        action={
          fund.can_edit &&
          !fund.pending_approval_id && (
            <Button variant="contained" component={RouterLink} to={`/funds/${fund.id}/edit`}>
              Edit fund
            </Button>
          )
        }
      />
      <Stack direction="row" spacing={1} sx={{ mb: 2, mt: -1.5 }}>
        <StatusChip status={fund.status} />
      </Stack>
      {fund.pending_approval_id && (
        <Alert
          severity="warning"
          sx={{ mb: 2 }}
          action={
            <Button color="inherit" size="small" component={RouterLink} to={`/approvals/${fund.pending_approval_id}`}>
              View change
            </Button>
          }
        >
          A change to this fund is waiting for approval. It can be edited again once that change is decided.
        </Alert>
      )}
      <Tabs value={tab} onChange={(_, v: FundTab) => setTab(v)} sx={{ mb: 2 }} variant="scrollable" scrollButtons="auto">
        <Tab value="details" label="Details" />
        <Tab value="trustees" label={`Trustees (${fund.trustees.length})`} />
        <Tab value="bank-accounts" label={`Bank accounts (${fund.bank_accounts.length})`} />
      </Tabs>
      {tab === "details" && <Details fund={fund} />}
      {tab === "trustees" && <Trustees fund={fund} />}
      {tab === "bank-accounts" && <BankAccounts fund={fund} />}
    </>
  );
}
