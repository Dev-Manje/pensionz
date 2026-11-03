import { useState } from "react";
import { Link as RouterLink, Navigate, Route, Routes, useNavigate, useParams } from "react-router-dom";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Divider from "@mui/material/Divider";
import Link from "@mui/material/Link";
import MenuItem from "@mui/material/MenuItem";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Tab from "@mui/material/Tab";
import TablePagination from "@mui/material/TablePagination";
import Tabs from "@mui/material/Tabs";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { useAuth } from "../../auth/AuthContext";
import { BRAND } from "../../brand";
import { DetailField, DetailSection } from "../../components/DetailSection";
import { LoadingState } from "../../components/LoadingState";
import { StatusChip } from "../../components/StatusChip";
import { useFeedback } from "../../components/feedback/FeedbackProvider";
import { openMyDocument, type DocKind, type MyMember } from "../../api/enquiries";
import { COMPONENT_LABELS } from "../../api/ledger";
import type { Nomination } from "../../api/types";
import {
  useBankChange, useBankCode, useContactChange, useMemberships, useMyBeneficiaries, useMyKyc, useMyMember, useMyNomination, useMyRequests,
  useMyTransactions, useStartMyKyc,
} from "../../queries/enquiries";
import { useBanks } from "../../queries/funds";
import { formatDate, formatDateTime, formatPeriod, todayIso } from "../../utils/date";
import { formatMoney } from "../../utils/format";
import { NominationDialog } from "../staff/members/MemberBeneficiariesTab";
import { MemberKycPage } from "./MemberKycPage";

const SECTIONS = ["overview", "transactions", "statements", "beneficiaries", "details", "requests"] as const;
type Section = (typeof SECTIONS)[number];
const SECTION_LABELS: Record<Section, string> = {
  overview: "My savings",
  transactions: "Transactions",
  statements: "Statements",
  beneficiaries: "Beneficiaries",
  details: "My details",
  requests: "Requests",
};
const money = { fontVariantNumeric: "tabular-nums", fontWeight: 600 } as const;

export const memberPath = (id: string, section: Section = "overview") => (section === "overview" ? `/member/${id}` : `/member/${id}/${section}`);

function Account({ title, lines, total }: { title: string; lines: { label: string; amount: string }[]; total: string }) {
  return (
    <Paper sx={{ p: { xs: 2, sm: 2.5 }, flex: 1, minWidth: 0 }}>
      <Typography variant="subtitle1" component="h3" sx={{ fontWeight: 600, mb: 1 }}>
        {title}
      </Typography>
      <Stack spacing={0.75} divider={<Divider flexItem />}>
        {lines
          .filter((l) => Number(l.amount) !== 0 || !l.label.startsWith("Less"))
          .map((l) => (
            <Stack key={l.label} direction="row" sx={{ justifyContent: "space-between", gap: 2 }}>
              <Typography variant="body2">{l.label}</Typography>
              <Typography variant="body2" sx={{ fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap" }}>{formatMoney(l.amount)}</Typography>
            </Stack>
          ))}
        <Stack direction="row" sx={{ justifyContent: "space-between", gap: 2 }}>
          <Typography sx={{ fontWeight: 600 }}>Total</Typography>
          <Typography sx={money}>{formatMoney(total)}</Typography>
        </Stack>
      </Stack>
    </Paper>
  );
}

function Overview({ m }: { m: MyMember }) {
  return (
    <Stack spacing={2}>
      <Paper sx={{ p: { xs: 2.5, sm: 3 } }}>
        <Typography color="text.secondary">Total savings</Typography>
        <Typography variant="h1" component="p" sx={{ ...money, fontSize: { xs: "2rem", sm: "2.5rem" } }}>
          {formatMoney(m.balance)}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          {m.contributions_up_to ? `Contributions credited up to ${formatPeriod(m.contributions_up_to)}.` : "No contributions credited yet."} Bonus
          (earnings) is credited when the trustees declare it.
        </Typography>
      </Paper>
      <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
        <Account title="Employee account" lines={m.employee_lines} total={m.employee_total} />
        <Account title="Employer account" lines={m.employer_lines} total={m.employer_total} />
      </Stack>
      <Typography variant="caption" color="text.secondary">
        What you can take when you leave depends on the fund rules (vesting of the employer account) and tax at the time.
      </Typography>
    </Stack>
  );
}

function Transactions({ id }: { id: string }) {
  const [page, setPage] = useState(0);
  const q = useMyTransactions(id, page + 1);
  if (q.isLoading) return <LoadingState />;
  if (q.error) return <Alert severity="error">{q.error.message}</Alert>;
  const items = q.data?.items ?? [];
  return (
    <Paper>
      {items.length === 0 && <Typography sx={{ p: 2 }} color="text.secondary">No transactions yet.</Typography>}
      <Stack divider={<Divider />}>
        {items.map((t) => (
          <Stack key={t.id} direction="row" sx={{ p: 2, justifyContent: "space-between", gap: 2 }}>
            <Box sx={{ minWidth: 0 }}>
              <Typography sx={{ fontWeight: 500 }}>{t.description || t.transaction}</Typography>
              <Typography variant="body2" color="text.secondary">
                {formatDate(t.date)} · {t.transaction} · {COMPONENT_LABELS[t.component]}
              </Typography>
            </Box>
            <Typography sx={{ ...money, whiteSpace: "nowrap", color: t.credit ? "success.main" : "error.main" }}>
              {t.credit ? "+" : "−"}
              {formatMoney(t.amount)}
            </Typography>
          </Stack>
        ))}
      </Stack>
      <TablePagination component="div" count={q.data?.total ?? 0} page={page} onPageChange={(_, p) => setPage(p)} rowsPerPage={25} rowsPerPageOptions={[25]} />
    </Paper>
  );
}

function Statements({ id }: { id: string }) {
  const feedback = useFeedback();
  const today = todayIso();
  const [asAt, setAsAt] = useState(today);
  const [start, setStart] = useState(`${new Date().getFullYear() - 1}-01-01`);
  const [end, setEnd] = useState(today);
  async function open(kind: DocKind) {
    try {
      await openMyDocument(id, kind, kind === "benefit" ? { as_at: asAt } : { start, end });
    } catch (e) {
      feedback.error(e instanceof Error ? e.message : "Couldn't open the statement.");
    }
  }
  return (
    <Stack spacing={2}>
      <Paper sx={{ p: { xs: 2, sm: 3 } }}>
        <Typography variant="subtitle1" component="h2" sx={{ fontWeight: 600 }}>Benefit statement</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>Your employee and employer accounts and total benefit on a date.</Typography>
        <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5}>
          <TextField label="As at" type="date" size="small" value={asAt} onChange={(e) => setAsAt(e.target.value)} slotProps={{ inputLabel: { shrink: true }, htmlInput: { max: today } }} />
          <Button variant="contained" onClick={() => open("benefit")}>Open benefit statement (PDF)</Button>
        </Stack>
      </Paper>
      <Paper sx={{ p: { xs: 2, sm: 3 } }}>
        <Typography variant="subtitle1" component="h2" sx={{ fontWeight: 600 }}>Statements for a period</Typography>
        <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} sx={{ my: 2 }}>
          <TextField label="From" type="date" size="small" value={start} onChange={(e) => setStart(e.target.value)} slotProps={{ inputLabel: { shrink: true } }} />
          <TextField label="To" type="date" size="small" value={end} onChange={(e) => setEnd(e.target.value)} slotProps={{ inputLabel: { shrink: true } }} />
        </Stack>
        <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5}>
          <Button variant="outlined" onClick={() => open("client")}>Account statement</Button>
          <Button variant="outlined" onClick={() => open("contributions")}>Contributions trail</Button>
          <Button variant="outlined" onClick={() => open("voluntary")}>Voluntary contributions</Button>
        </Stack>
      </Paper>
    </Stack>
  );
}

function Beneficiaries({ m }: { m: MyMember }) {
  const q = useMyBeneficiaries(m.member_id);
  const nominate = useMyNomination(m.member_id);
  const feedback = useFeedback();
  const [editing, setEditing] = useState(false);
  if (q.isLoading) return <LoadingState />;
  if (q.error || !q.data) return <Alert severity="error">{q.error?.message}</Alert>;
  const n = q.data;
  return (
    <Stack spacing={2}>
      {n.pending_approval_id && <Alert severity="info">Your new nomination is waiting for {BRAND.administrator} to check it.</Alert>}
      <Paper sx={{ p: { xs: 2, sm: 3 } }}>
        <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} sx={{ justifyContent: "space-between", alignItems: { sm: "center" }, mb: 2 }}>
          <div>
            <Typography variant="subtitle1" component="h2" sx={{ fontWeight: 600 }}>Who should receive your benefit if you die</Typography>
            <Typography variant="body2" color="text.secondary">
              {n.signed_date ? `Nomination signed ${formatDate(n.signed_date)}.` : "You haven't nominated anyone yet."} The trustees decide who is paid; your
              nomination guides them.
            </Typography>
          </div>
          {n.can_nominate && !n.pending_approval_id && (
            <Button variant="contained" onClick={() => setEditing(true)} sx={{ whiteSpace: "nowrap" }}>
              {n.beneficiaries.length ? "Change nomination" : "Nominate beneficiaries"}
            </Button>
          )}
        </Stack>
        <Stack divider={<Divider />} spacing={1}>
          {n.beneficiaries.map((b) => (
            <Stack key={b.full_name} direction="row" sx={{ justifyContent: "space-between", gap: 2 }}>
              <Box>
                <Typography sx={{ fontWeight: 500 }}>{b.full_name}</Typography>
                <Typography variant="body2" color="text.secondary">
                  {b.relationship_label ?? b.relationship}
                  {b.is_minor && b.guardian_name ? ` · guardian ${b.guardian_name}` : ""}
                </Typography>
              </Box>
              <Typography sx={money}>{Number(b.share_pct).toFixed(2)}%</Typography>
            </Stack>
          ))}
        </Stack>
      </Paper>
      {editing && (
        <NominationDialog
          memberName={m.full_name}
          current={n.beneficiaries.length ? ({ beneficiaries: n.beneficiaries } as unknown as Pick<Nomination, "beneficiaries">) : null}
          intro="List everyone you want to nominate, with their share."
          onSend={async (body) => {
            await nominate.mutateAsync(body);
            feedback.success(`Sent — ${BRAND.administrator} checks it before it replaces your current nomination.`);
          }}
          onClose={() => setEditing(false)}
        />
      )}
    </Stack>
  );
}

function ContactDialog({ m, onClose }: { m: MyMember; onClose: () => void }) {
  const change = useContactChange(m.member_id);
  const feedback = useFeedback();
  const [v, setV] = useState({
    postal_address: m.details.postal_address ?? "", physical_address: m.details.physical_address ?? "", telephone: m.details.telephone ?? "",
    mobile: m.details.mobile ?? "", email: m.details.email ?? "",
  });
  const [error, setError] = useState<string | null>(null);
  async function send() {
    setError(null);
    try {
      await change.mutateAsync(Object.fromEntries(Object.entries(v).map(([k, x]) => [k, x.trim() || null])));
      feedback.success(`Sent — ${BRAND.administrator} checks the change before it takes effect.`);
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't send it.");
    }
  }
  const field = (key: keyof typeof v, label: string, type = "text") => (
    <TextField label={label} type={type} value={v[key]} onChange={(e) => setV({ ...v, [key]: e.target.value })} fullWidth />
  );
  return (
    <Dialog open onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>Change my contact details</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ pt: 1 }}>
          {field("mobile", "Mobile", "tel")}
          {field("telephone", "Other phone", "tel")}
          {field("email", "Email", "email")}
          {field("postal_address", "Postal address")}
          {field("physical_address", "Physical address")}
          {error && <Alert severity="error">{error}</Alert>}
        </Stack>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" onClick={send} disabled={change.isPending}>Send for checking</Button>
      </DialogActions>
    </Dialog>
  );
}

function BankDialog({ m, onClose }: { m: MyMember; onClose: () => void }) {
  const banks = useBanks();
  const sendCode = useBankCode(m.member_id);
  const change = useBankChange(m.member_id);
  const feedback = useFeedback();
  const [bankId, setBankId] = useState("");
  const [branchId, setBranchId] = useState("");
  const [name, setName] = useState(m.full_name);
  const [number, setNumber] = useState("");
  const [code, setCode] = useState("");
  const [sentTo, setSentTo] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const bank = banks.data?.find((b) => b.id === bankId);

  async function askCode() {
    setError(null);
    try {
      setSentTo((await sendCode.mutateAsync()).detail);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't send the code.");
    }
  }
  async function send() {
    setError(null);
    try {
      await change.mutateAsync({ bank_id: bankId, bank_branch_id: branchId || null, bank_account_name: name, bank_account_number: number, code });
      feedback.success(`Sent — ${BRAND.administrator} checks the new account before any payment goes to it.`);
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't send it.");
    }
  }
  return (
    <Dialog open onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>Change my bank account</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ pt: 1 }}>
          <Alert severity="info">For your safety we send a one-time code to your email, and {BRAND.administrator} checks the change before it is used.</Alert>
          <TextField select label="Bank" value={bankId} onChange={(e) => { setBankId(e.target.value); setBranchId(""); }} required fullWidth>
            {(banks.data ?? []).map((b) => <MenuItem key={b.id} value={b.id}>{b.name}</MenuItem>)}
          </TextField>
          <TextField select label="Branch" value={branchId} onChange={(e) => setBranchId(e.target.value)} fullWidth disabled={!bank}>
            {(bank?.branches ?? []).map((b) => <MenuItem key={b.id} value={b.id}>{b.name}</MenuItem>)}
          </TextField>
          <TextField label="Account name" value={name} onChange={(e) => setName(e.target.value)} required fullWidth />
          <TextField label="Account number" value={number} onChange={(e) => setNumber(e.target.value.replace(/\s/g, ""))} required fullWidth slotProps={{ htmlInput: { inputMode: "numeric" } }} />
          {sentTo ? (
            <TextField label="6-digit code" value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))} helperText={sentTo} fullWidth slotProps={{ htmlInput: { inputMode: "numeric" } }} />
          ) : (
            <Box><Button variant="outlined" onClick={askCode} disabled={!bankId || !number || sendCode.isPending}>Email me a code</Button></Box>
          )}
          {error && <Alert severity="error">{error}</Alert>}
        </Stack>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" onClick={send} disabled={code.length !== 6 || change.isPending}>Send for checking</Button>
      </DialogActions>
    </Dialog>
  );
}

function Details({ m }: { m: MyMember }) {
  const [dialog, setDialog] = useState<"contact" | "bank" | null>(null);
  const kyc = useMyKyc();
  const start = useStartMyKyc(m.member_id);
  const navigate = useNavigate();
  const feedback = useFeedback();
  const open = (kyc.data ?? []).find((a) => ["draft", "returned", "submitted", "in_review", "awaiting_senior_approval"].includes(a.status));
  const d = m.details;
  async function startKyc() {
    try {
      const app = await start.mutateAsync();
      navigate(`/member/kyc/${app.id}`);
    } catch (e) {
      feedback.error(e instanceof Error ? e.message : "Couldn't start it.");
    }
  }
  return (
    <Stack spacing={2}>
      {m.pending_change_id && <Alert severity="info">A change to your details is waiting for {BRAND.administrator} to check it.</Alert>}
      <DetailSection title="Contact details">
        <DetailField label="Mobile">{d.mobile}</DetailField>
        <DetailField label="Other phone">{d.telephone}</DetailField>
        <DetailField label="Email">{d.email}</DetailField>
        <DetailField label="Postal address">{d.postal_address}</DetailField>
        <DetailField label="Physical address">{d.physical_address}</DetailField>
      </DetailSection>
      <DetailSection title="Bank account for payments">
        <DetailField label="Bank">{d.bank_name}</DetailField>
        <DetailField label="Branch">{d.bank_branch}</DetailField>
        <DetailField label="Account">{d.bank_account_number ? `${d.bank_account_name ?? ""} ${d.bank_account_number}` : null}</DetailField>
      </DetailSection>
      <DetailSection title="Membership">
        <DetailField label="Member number">{m.account_code}</DetailField>
        <DetailField label="Employer">{m.employer}</DetailField>
        <DetailField label="Category">{m.category}</DetailField>
        <DetailField label="Joined the fund">{formatDate(m.date_joined_fund)}</DetailField>
        <DetailField label="Date of birth">{formatDate(m.date_of_birth)}</DetailField>
        <DetailField label="ID number">{d.id_number}</DetailField>
      </DetailSection>
      {!m.pending_change_id && (
        <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5}>
          <Button variant="contained" onClick={() => setDialog("contact")}>Change contact details</Button>
          <Button variant="outlined" onClick={() => setDialog("bank")}>Change bank account</Button>
        </Stack>
      )}
      <Paper sx={{ p: { xs: 2, sm: 3 } }}>
        <Typography variant="subtitle1" component="h2" sx={{ fontWeight: 600 }}>KYC details and documents</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
          Update your identity details or upload a new ID or proof of address. Compliance checks them.
        </Typography>
        {open ? (
          <Button variant="outlined" component={RouterLink} to={`/member/kyc/${open.id}`}>Continue {open.reference}</Button>
        ) : (
          <Button variant="outlined" onClick={startKyc} disabled={start.isPending}>Update my KYC</Button>
        )}
      </Paper>
      {dialog === "contact" && <ContactDialog m={m} onClose={() => setDialog(null)} />}
      {dialog === "bank" && <BankDialog m={m} onClose={() => setDialog(null)} />}
    </Stack>
  );
}

function Requests({ id }: { id: string }) {
  const q = useMyRequests(id);
  if (q.isLoading) return <LoadingState />;
  if (q.error) return <Alert severity="error">{q.error.message}</Alert>;
  const rows = q.data ?? [];
  const tone = { pending: "info", approved: "success", rejected: "error", cancelled: "default" } as const;
  const label = { pending: "Being checked", approved: "Done", rejected: "Not accepted", cancelled: "Withdrawn" } as const;
  return (
    <Paper>
      {rows.length === 0 && <Typography sx={{ p: 2 }} color="text.secondary">You haven't asked for any changes yet.</Typography>}
      <Stack divider={<Divider />}>
        {rows.map((r) => (
          <Box key={r.id} sx={{ p: 2 }}>
            <Stack direction="row" sx={{ justifyContent: "space-between", gap: 1, alignItems: "flex-start" }}>
              <Typography sx={{ fontWeight: 500 }}>{r.summary.replace(/ \(requested from the member portal\)/, "")}</Typography>
              <StatusChip status={r.status} label={label[r.status]} tone={tone[r.status]} />
            </Stack>
            <Typography variant="body2" color="text.secondary">
              Sent {formatDateTime(r.created_at)}
              {r.reviewed_at ? ` · decided ${formatDateTime(r.reviewed_at)}` : ""}
            </Typography>
            {r.review_comment && <Typography variant="body2">Note: {r.review_comment}</Typography>}
          </Box>
        ))}
      </Stack>
    </Paper>
  );
}

function MemberPage() {
  const { memberId = "", section } = useParams();
  const navigate = useNavigate();
  const memberships = useMemberships();
  const q = useMyMember(memberId);
  const tab: Section = SECTIONS.includes(section as Section) ? (section as Section) : "overview";
  if (q.isLoading) return <LoadingState />;
  if (q.error || !q.data) return <Alert severity="error">{q.error?.message ?? "Membership not found"}</Alert>;
  const m = q.data;
  const many = (memberships.data?.length ?? 0) > 1;
  return (
    <Stack spacing={2} sx={{ maxWidth: 1040 }}>
      <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} sx={{ justifyContent: "space-between", alignItems: { sm: "flex-end" } }}>
        <div>
          <Typography variant="h1">{m.fund_name}</Typography>
          <Typography color="text.secondary">
            Member {m.account_code}
            {m.employer ? ` · ${m.employer}` : ""}
          </Typography>
        </div>
        {many && (
          <TextField select size="small" label="Membership" value={m.member_id} onChange={(e) => navigate(memberPath(e.target.value, tab))} sx={{ minWidth: 240 }}>
            {memberships.data!.map((x) => <MenuItem key={x.member_id} value={x.member_id}>{x.fund_name} ({x.account_code})</MenuItem>)}
          </TextField>
        )}
      </Stack>
      <Tabs value={tab} onChange={(_, v: Section) => navigate(memberPath(m.member_id, v))} variant="scrollable" scrollButtons={false}>
        {SECTIONS.map((s) => <Tab key={s} value={s} label={SECTION_LABELS[s]} />)}
      </Tabs>
      {tab === "overview" && <Overview m={m} />}
      {tab === "transactions" && <Transactions id={m.member_id} />}
      {tab === "statements" && <Statements id={m.member_id} />}
      {tab === "beneficiaries" && <Beneficiaries m={m} />}
      {tab === "details" && <Details m={m} />}
      {tab === "requests" && <Requests id={m.member_id} />}
    </Stack>
  );
}

function MemberLanding() {
  const { user } = useAuth();
  const memberships = useMemberships();
  const firstName = user?.full_name.split(" ")[0] || "there";
  if (memberships.isLoading) return <LoadingState />;
  if (memberships.error) return <Alert severity="error">{memberships.error.message}</Alert>;
  const rows = memberships.data ?? [];
  if (rows.length === 1) return <Navigate to={memberPath(rows[0].member_id)} replace />;
  return (
    <Stack spacing={2} sx={{ maxWidth: 720 }}>
      <Typography variant="h1">Hello, {firstName}</Typography>
      {rows.length === 0 ? (
        <Paper sx={{ p: { xs: 2.5, sm: 3 } }}>
          <Typography color="text.secondary">
            Your sign-in isn't linked to a membership yet. If you were invited by mistake or this doesn't change, contact {BRAND.administrator}.
          </Typography>
        </Paper>
      ) : (
        rows.map((r) => (
          <Paper key={r.member_id} sx={{ p: 2.5 }}>
            <Link component={RouterLink} to={memberPath(r.member_id)} underline="hover" sx={{ fontWeight: 600, fontSize: "1.1rem" }}>
              {r.fund_name}
            </Link>
            <Typography color="text.secondary">Member {r.account_code}{r.employer ? ` · ${r.employer}` : ""}</Typography>
            <Typography sx={money}>{formatMoney(r.balance)}</Typography>
          </Paper>
        ))
      )}
    </Stack>
  );
}

// Member portal (/member; FR-PRT-002): the member's own memberships — savings by
// account, transactions, statements, beneficiaries, details and change requests.
export function MemberPortal() {
  return (
    <Routes>
      <Route index element={<MemberLanding />} />
      <Route path="kyc/:applicationId" element={<MemberKycPage />} />
      <Route path=":memberId" element={<MemberPage />} />
      <Route path=":memberId/:section" element={<MemberPage />} />
    </Routes>
  );
}
