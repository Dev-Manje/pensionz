import { useState } from "react";
import { Link as RouterLink, useParams } from "react-router-dom";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Breadcrumbs from "@mui/material/Breadcrumbs";
import Button from "@mui/material/Button";
import Divider from "@mui/material/Divider";
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
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { useAuth } from "../../../auth/AuthContext";
import { DetailField, DetailSection } from "../../../components/DetailSection";
import { LoadingState } from "../../../components/LoadingState";
import { ResponsiveTable } from "../../../components/ResponsiveTable";
import { StatusChip } from "../../../components/StatusChip";
import { TableStateRow } from "../../../components/TableStateRow";
import { useFeedback } from "../../../components/feedback/FeedbackProvider";
import { useUrlTab } from "../../../hooks/useUrlState";
import { openMemberDocument, type DocKind, type MemberSummaryStatement, type StatementLine } from "../../../api/enquiries";
import { COMPONENT_LABELS } from "../../../api/ledger";
import { useContributionsTrail, useEnquiry, useInvitePortal, useStatement, useTrail } from "../../../queries/enquiries";
import { useMember, useNominations } from "../../../queries/members";
import { formatDate, formatPeriod, todayIso } from "../../../utils/date";
import { formatAmount, formatMoney } from "../../../utils/format";

const TABS = ["main", "current", "history", "statement", "trail", "contributions", "voluntary", "comprehensive"] as const;
type EnquiryTab = (typeof TABS)[number];
const LABELS: Record<EnquiryTab, string> = {
  main: "Main information",
  current: "Current period",
  history: "Transaction history",
  statement: "Statement",
  trail: "Transaction trail",
  contributions: "Contributions",
  voluntary: "Voluntary contributions",
  comprehensive: "Comprehensive",
};
const num = { fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap" } as const;

function yearAgo() {
  const d = new Date();
  return `${d.getFullYear() - 1}-${String(d.getMonth() + 1).padStart(2, "0")}-01`;
}

function RangeBar({ start, end, setStart, setEnd, pdf }: { start: string; end: string; setStart: (v: string) => void; setEnd: (v: string) => void; pdf?: () => void }) {
  return (
    <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} sx={{ alignItems: { sm: "center" } }}>
      <TextField size="small" label="From" type="date" value={start} onChange={(e) => setStart(e.target.value)} slotProps={{ inputLabel: { shrink: true } }} />
      <TextField size="small" label="To" type="date" value={end} onChange={(e) => setEnd(e.target.value)} slotProps={{ inputLabel: { shrink: true } }} />
      {pdf && <Button variant="outlined" onClick={pdf}>Print (PDF)</Button>}
    </Stack>
  );
}

function Lines({ lines, opening, closing, running = true }: { lines: StatementLine[]; opening?: string; closing?: string; running?: boolean }) {
  return (
    <TableContainer component={Paper}>
      <ResponsiveTable size="small">
        <TableHead>
          <TableRow>
            <TableCell>Date</TableCell>
            <TableCell>Description</TableCell>
            <TableCell>Reference</TableCell>
            <TableCell>Transaction</TableCell>
            <TableCell>Account</TableCell>
            <TableCell align="right">Debit</TableCell>
            <TableCell align="right">Credit</TableCell>
            {running && <TableCell align="right">Balance</TableCell>}
          </TableRow>
        </TableHead>
        <TableBody>
          {opening !== undefined && (
            <TableRow>
              <TableCell colSpan={running ? 7 : 6} sx={{ fontWeight: 500 }}>Balance brought forward</TableCell>
              {running && <TableCell align="right" sx={num}>{formatAmount(opening)}</TableCell>}
            </TableRow>
          )}
          <TableStateRow colSpan={running ? 8 : 7} loading={false} error={null} empty="No transactions in this period." count={lines.length} />
          {lines.map((l, i) => (
            <TableRow key={i} hover>
              <TableCell sx={num}>{formatDate(l.date)}</TableCell>
              <TableCell>{l.description}</TableCell>
              <TableCell>{l.reference ?? "—"}</TableCell>
              <TableCell>{l.transaction}</TableCell>
              <TableCell>{COMPONENT_LABELS[l.component]}</TableCell>
              <TableCell align="right" sx={num}>{Number(l.debit) ? formatAmount(l.debit) : ""}</TableCell>
              <TableCell align="right" sx={num}>{Number(l.credit) ? formatAmount(l.credit) : ""}</TableCell>
              {running && <TableCell align="right" sx={{ ...num, fontWeight: 600 }}>{formatAmount(l.balance)}</TableCell>}
            </TableRow>
          ))}
          {closing !== undefined && (
            <TableRow>
              <TableCell colSpan={running ? 7 : 6} sx={{ fontWeight: 600 }}>Current balance</TableCell>
              {running && <TableCell align="right" sx={{ ...num, fontWeight: 700 }}>{formatAmount(closing)}</TableCell>}
            </TableRow>
          )}
        </TableBody>
      </ResponsiveTable>
    </TableContainer>
  );
}

function Main({ s }: { s: MemberSummaryStatement }) {
  const account = (title: string, lines: { label: string; amount: string }[], total: string) => (
    <Paper sx={{ p: { xs: 2, sm: 2.5 }, flex: 1 }}>
      <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 1 }}>{title}</Typography>
      <Stack spacing={0.5} divider={<Divider flexItem />}>
        {lines.map((l) => (
          <Stack key={l.label} direction="row" sx={{ justifyContent: "space-between", gap: 2 }}>
            <Typography variant="body2">{l.label}</Typography>
            <Typography variant="body2" sx={num}>{formatAmount(l.amount)}</Typography>
          </Stack>
        ))}
        <Stack direction="row" sx={{ justifyContent: "space-between" }}>
          <Typography sx={{ fontWeight: 600 }}>Total</Typography>
          <Typography sx={{ ...num, fontWeight: 700 }}>{formatAmount(total)}</Typography>
        </Stack>
      </Stack>
    </Paper>
  );
  return (
    <Stack spacing={2}>
      <DetailSection title="Account">
        <DetailField label="Current balance">{formatMoney(s.balance)}</DetailField>
        <DetailField label="Status"><StatusChip status={s.status} /></DetailField>
        <DetailField label="Contributions up to">{s.contributions_up_to ? formatPeriod(s.contributions_up_to) : "None yet"}</DetailField>
        <DetailField label="Employer">{s.employer ? `${s.employer_code} — ${s.employer}` : null}</DetailField>
        <DetailField label="Category">{s.category}</DetailField>
        <DetailField label="Joined the fund">{formatDate(s.date_joined_fund)}</DetailField>
        <DetailField label="Employee no.">{s.employee_no}</DetailField>
        <DetailField label="Date of birth">{formatDate(s.date_of_birth)}</DetailField>
        <DetailField label="Portal login">{s.has_portal_login ? "Yes" : "No"}</DetailField>
      </DetailSection>
      <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
        {account("Employee account", s.employee_lines, s.employee_total)}
        {account("Employer account", s.employer_lines, s.employer_total)}
      </Stack>
      {s.ageing && (
        <Paper sx={{ p: { xs: 2, sm: 2.5 } }}>
          <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 1 }}>Aged analysis — contributions the employer still owes</Typography>
          <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr 1fr", md: "repeat(7, 1fr)" }, gap: 1.5 }}>
            {s.ageing.map((a) => <DetailField key={a.label} label={a.label}>{formatAmount(a.amount)}</DetailField>)}
          </Box>
        </Paper>
      )}
    </Stack>
  );
}

function StatementTab({ id, start, end, current }: { id: string; start: string; end: string; current?: boolean }) {
  const q = useStatement(id, start, end);
  if (q.isLoading) return <LoadingState />;
  if (q.error || !q.data) return <Alert severity="error">{q.error?.message}</Alert>;
  return <Lines lines={q.data.lines} opening={current ? undefined : q.data.opening} closing={current ? undefined : q.data.closing} running={!current} />;
}

function TrailTab({ id, start, end }: { id: string; start: string; end: string }) {
  const q = useTrail(id, start, end);
  if (q.isLoading) return <LoadingState />;
  if (q.error || !q.data) return <Alert severity="error">{q.error?.message}</Alert>;
  return (
    <Stack spacing={2}>
      <Lines lines={q.data.lines} running={false} />
      <Paper sx={{ p: 2 }}>
        <Typography variant="subtitle2" sx={{ mb: 1 }}>Totals per account</Typography>
        {q.data.totals.map((t) => (
          <Typography key={t.component} variant="body2">
            {COMPONENT_LABELS[t.component]}: debit {formatAmount(t.debit)} · credit {formatAmount(t.credit)} · net {formatAmount(String(Number(t.credit) - Number(t.debit)))}
          </Typography>
        ))}
      </Paper>
    </Stack>
  );
}

function ContributionsTab({ id, start, end, voluntary }: { id: string; start: string; end: string; voluntary?: boolean }) {
  const q = useContributionsTrail(id, start, end);
  if (q.isLoading) return <LoadingState />;
  if (q.error || !q.data) return <Alert severity="error">{q.error?.message}</Alert>;
  const months = voluntary ? q.data.months.filter((m) => Number(m.voluntary) || Number(m.voluntary_earning)) : q.data.months;
  const heads = voluntary ? ["Period", "Employee contribution", "Earning", "Total"] : ["Period", "Employee", "Company", "Emp. earning", "Comp. earning", "Earning", "Rate", "Total"];
  return (
    <TableContainer component={Paper}>
      <ResponsiveTable size="small">
        <TableHead>
          <TableRow>{heads.map((h, i) => <TableCell key={h} align={i ? "right" : "left"}>{h}</TableCell>)}</TableRow>
        </TableHead>
        <TableBody>
          <TableStateRow colSpan={heads.length} loading={false} error={null} empty="Nothing in this period." count={months.length} />
          {months.map((m) => (
            <TableRow key={m.month} hover>
              <TableCell sx={num}>{formatPeriod(m.month)}</TableCell>
              {(voluntary
                ? [m.voluntary, m.voluntary_earning, String(Number(m.voluntary) + Number(m.voluntary_earning))]
                : [m.employee, m.company, m.employee_earning, m.company_earning, m.earning]
              ).map((v, i) => <TableCell key={i} align="right" sx={num}>{formatAmount(v)}</TableCell>)}
              {!voluntary && <TableCell align="right" sx={num}>{m.earning_rate && Number(m.earning) ? `${Number(m.earning_rate)}%` : ""}</TableCell>}
              {!voluntary && <TableCell align="right" sx={{ ...num, fontWeight: 600 }}>{formatAmount(m.total)}</TableCell>}
            </TableRow>
          ))}
        </TableBody>
      </ResponsiveTable>
    </TableContainer>
  );
}

function Comprehensive({ id, s }: { id: string; s: MemberSummaryStatement }) {
  const member = useMember(id);
  const nominations = useNominations(id);
  const statement = useStatement(id, yearAgo(), todayIso());
  if (member.isLoading) return <LoadingState />;
  const m = member.data;
  const f = (m?.fields ?? {}) as Record<string, unknown>;
  return (
    <Stack spacing={2}>
      <DetailSection title="Member">
        <DetailField label="Name">{s.full_name}</DetailField>
        <DetailField label="Status"><StatusChip status={s.status} /></DetailField>
        <DetailField label="ID">{(f.id_number as string) ?? null}</DetailField>
        <DetailField label="Mobile">{(f.mobile as string) ?? null}</DetailField>
        <DetailField label="Email">{(f.email as string) ?? null}</DetailField>
        <DetailField label="Address">{(f.physical_address as string) ?? (f.postal_address as string) ?? null}</DetailField>
      </DetailSection>
      <DetailSection title="Employer & KYC">
        <DetailField label="Employer">{s.employer ? `${s.employer_code} — ${s.employer}` : null}</DetailField>
        <DetailField label="Category">{s.category}</DetailField>
        <DetailField label="Employer KYC">{m?.company.employer_kyc ?? null}</DetailField>
        <DetailField label="Member KYC">{m?.kyc.label ?? null}</DetailField>
        <DetailField label="KYC application">
          {m?.kyc.application_id ? <Link component={RouterLink} to={`/kyc/${m.kyc.application_id}`}>{m.kyc.application_reference}</Link> : null}
        </DetailField>
        <DetailField label="Review due">{m?.kyc.review_due ? formatDate(m.kyc.review_due) : null}</DetailField>
      </DetailSection>
      <Paper sx={{ p: { xs: 2, sm: 2.5 } }}>
        <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 1 }}>Balances</Typography>
        <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr 1fr" }, gap: 2 }}>
          <DetailField label="Employee account">{formatMoney(s.employee_total)}</DetailField>
          <DetailField label="Employer account">{formatMoney(s.employer_total)}</DetailField>
          <DetailField label="Total">{formatMoney(s.balance)}</DetailField>
        </Box>
      </Paper>
      <Paper sx={{ p: { xs: 2, sm: 2.5 } }}>
        <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 1 }}>Beneficiaries</Typography>
        {nominations.data?.current ? (
          nominations.data.current.beneficiaries.map((b) => (
            <Typography key={b.full_name} variant="body2">{b.full_name} — {b.relationship_label ?? b.relationship}, {Number(b.share_pct).toFixed(2)}%</Typography>
          ))
        ) : (
          <Typography variant="body2" color="text.secondary">No nomination on record.</Typography>
        )}
      </Paper>
      <Paper sx={{ p: { xs: 2, sm: 2.5 } }}>
        <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 1 }}>Last 12 months</Typography>
        {(statement.data?.lines ?? []).slice(-10).reverse().map((l, i) => (
          <Typography key={i} variant="body2">{formatDate(l.date)} · {l.description} · {Number(l.credit) ? `+${formatAmount(l.credit)}` : `−${formatAmount(l.debit)}`}</Typography>
        ))}
        {statement.data?.lines.length === 0 && <Typography variant="body2" color="text.secondary">No transactions.</Typography>}
      </Paper>
      <DetailSection title="Claims, documents and notes">
        <DetailField label="Claims">None — claims are handled from Phase 8.</DetailField>
        <DetailField label="Documents">{m?.kyc.application_reference ? `KYC documents in ${m.kyc.application_reference}` : "None"}</DetailField>
        <DetailField label="Member record">
          <Link component={RouterLink} to={`/members/${id}`}>Open the member record</Link>
        </DetailField>
      </DetailSection>
    </Stack>
  );
}

// Account enquiry (legacy "Query On"; FR-ENQ-001, 002, 008): one member's account seen every way.
export function EnquiryPage() {
  const { memberId = "" } = useParams();
  const { user } = useAuth();
  const canInvite = user?.roles.some((r) => r === "member_admin" || r === "admin") ?? false;
  const [tab, setTab] = useUrlTab(TABS);
  const q = useEnquiry(memberId);
  const invite = useInvitePortal();
  const feedback = useFeedback();
  const [start, setStart] = useState(yearAgo());
  const [end, setEnd] = useState(todayIso());
  const [asAt, setAsAt] = useState(todayIso());
  if (q.isLoading) return <LoadingState />;
  if (q.error || !q.data) return <Alert severity="error">{q.error?.message ?? "Member not found"}</Alert>;
  const s = q.data;
  const open = async (kind: DocKind) => {
    try {
      await openMemberDocument(memberId, kind, kind === "benefit" ? { as_at: asAt } : { start, end });
    } catch (e) {
      feedback.error(e instanceof Error ? e.message : "Couldn't open it.");
    }
  };
  async function sendInvite() {
    try {
      feedback.success((await invite.mutateAsync(memberId)).detail);
    } catch (e) {
      feedback.error(e instanceof Error ? e.message : "Couldn't invite the member.");
    }
  }
  const periodStart = s.current_period ?? todayIso().slice(0, 8) + "01";
  const ranged = tab === "statement" || tab === "trail" || tab === "contributions" || tab === "voluntary" || tab === "history";
  const pdfKind: Partial<Record<EnquiryTab, DocKind>> = { statement: "client", history: "client", trail: "trail", contributions: "contributions", voluntary: "voluntary" };

  return (
    <Stack spacing={2} sx={{ maxWidth: 1240 }}>
      <Breadcrumbs>
        <Link component={RouterLink} to="/enquiries" underline="hover" color="inherit">Enquiries</Link>
        <Typography color="text.primary">{s.account_code}</Typography>
      </Breadcrumbs>
      <Stack direction={{ xs: "column", md: "row" }} spacing={2} sx={{ justifyContent: "space-between", alignItems: { md: "flex-start" } }}>
        <div>
          <Typography variant="h1">{s.full_name}</Typography>
          <Stack direction="row" spacing={1} sx={{ alignItems: "center", flexWrap: "wrap", gap: 1, mt: 0.5 }}>
            <Typography color="text.secondary">{s.account_code} · {s.fund_code}{s.employer_code ? ` · ${s.employer_code}` : ""}</Typography>
            <StatusChip status={s.status} />
            <Typography sx={{ fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>{formatMoney(s.balance)}</Typography>
          </Stack>
        </div>
        <Stack direction={{ xs: "column", sm: "row" }} spacing={1} sx={{ alignItems: { sm: "center" }, "& .MuiButton-root": { whiteSpace: "nowrap" } }}>
          <TextField size="small" label="As at" type="date" value={asAt} onChange={(e) => setAsAt(e.target.value)} slotProps={{ inputLabel: { shrink: true } }} />
          <Button variant="contained" onClick={() => open("benefit")}>Benefit statement</Button>
          {canInvite && !s.has_portal_login && <Button variant="outlined" onClick={sendInvite} disabled={invite.isPending}>Invite to portal</Button>}
        </Stack>
      </Stack>
      <Tabs value={tab} onChange={(_, v: EnquiryTab) => setTab(v)} variant="scrollable" scrollButtons="auto">
        {TABS.map((t) => <Tab key={t} value={t} label={LABELS[t]} />)}
      </Tabs>
      {ranged && <RangeBar start={start} end={end} setStart={setStart} setEnd={setEnd} pdf={pdfKind[tab] ? () => open(pdfKind[tab]!) : undefined} />}
      {tab === "main" && <Main s={s} />}
      {tab === "current" && (
        <>
          <Typography color="text.secondary">Processing month {formatPeriod(periodStart)}.</Typography>
          <StatementTab id={memberId} start={periodStart} end={todayIso()} current />
        </>
      )}
      {tab === "history" && <StatementTab id={memberId} start={start} end={end} current />}
      {tab === "statement" && <StatementTab id={memberId} start={start} end={end} />}
      {tab === "trail" && <TrailTab id={memberId} start={start} end={end} />}
      {tab === "contributions" && <ContributionsTab id={memberId} start={start} end={end} />}
      {tab === "voluntary" && <ContributionsTab id={memberId} start={start} end={end} voluntary />}
      {tab === "comprehensive" && <Comprehensive id={memberId} s={s} />}
    </Stack>
  );
}
