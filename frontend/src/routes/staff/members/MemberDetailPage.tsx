import { useState } from "react";
import { Link as RouterLink, useParams } from "react-router-dom";
import Alert from "@mui/material/Alert";
import Breadcrumbs from "@mui/material/Breadcrumbs";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Link from "@mui/material/Link";
import MenuItem from "@mui/material/MenuItem";
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
import { DetailField, DetailSection } from "../../../components/DetailSection";
import { LoadingState } from "../../../components/LoadingState";
import { PageHeader } from "../../../components/PageHeader";
import { ResponsiveTable } from "../../../components/ResponsiveTable";
import { StatusChip } from "../../../components/StatusChip";
import { TableStateRow } from "../../../components/TableStateRow";
import { useFeedback } from "../../../components/feedback/FeedbackProvider";
import { useUrlTab } from "../../../hooks/useUrlState";
import { useKycOptions } from "../../../queries/kyc";
import { useMember, useMemberProposal } from "../../../queries/members";
import { proposeMove, proposeStatusChange } from "../../../api/members";
import { useSchemes } from "../../../queries/schemes";
import { CategorySelect } from "./MemberFormPage";
import { MEMBER_STATUS_LABELS, type KycStanding, type Member, type MemberStatus } from "../../../api/types";
import { formatDate } from "../../../utils/date";
import { MemberBeneficiariesTab } from "./MemberBeneficiariesTab";
import { MemberEmploymentTab } from "./MemberEmploymentTab";
import { MemberTransactionsTab } from "./MemberTransactionsTab";

const TABS = ["main", "member", "beneficiaries", "salary", "company", "kyc", "regulatory", "transactions", "history"] as const;
type MemberTab = (typeof TABS)[number];

const STATUS_HELP: Record<MemberStatus, string> = {
  active: "Employed and contributing.",
  inactive: "Still employed but not contributing (e.g. unpaid leave).",
  deferred: "Left employment; the benefit stays in the fund. The exit date is set to the effective date.",
  pensioner: "Retired and drawing a pension from the fund.",
  exited: "Benefit paid out or transferred. This is final.",
  deceased: "The member has died. This is final; the death claim follows.",
};

const KYC_TONE: Record<KycStanding["state"], "success" | "warning" | "error" | "default"> = {
  current: "success",
  none: "default",
  review_overdue: "error",
  document_expired: "error",
};

function useOptionLabel() {
  const options = useKycOptions();
  return (key: "genders" | "marital_statuses" | "contact_modes", value: unknown) =>
    (options.data?.[key] ?? []).find((o) => o.value === value)?.label ?? (value as string | null);
}

function MainInformation({ m }: { m: Member }) {
  const f = m.fields as Record<string, string | null>;
  const l = m.labels;
  const optionLabel = useOptionLabel();
  return (
    <Stack spacing={2}>
      <DetailSection title="Account">
        <DetailField label="Account code">{f.account_code}</DetailField>
        <DetailField label="Old member no.">{f.old_member_no}</DetailField>
        <DetailField label="Employee no.">{f.employee_no}</DetailField>
        <DetailField label="Group account">{m.fields.is_group_account ? "Yes — this is a group account" : l.group_account_id ? `Part of ${l.group_account_id}` : "No"}</DetailField>
      </DetailSection>
      <DetailSection title="Name and identity">
        <DetailField label="First name">{f.first_name}</DetailField>
        <DetailField label="Other names">{f.other_names}</DetailField>
        <DetailField label="Last name">{f.last_name}</DetailField>
        <DetailField label="Maiden name">{f.maiden_name}</DetailField>
        <DetailField label="Nationality">{l.nationality}</DetailField>
        <DetailField label="ID">{f.id_number ? `${l.id_type ?? ""} ${f.id_number}`.trim() : null}</DetailField>
      </DetailSection>
      <DetailSection title="Addresses">
        <DetailField label="Physical address">{f.physical_address}</DetailField>
        <DetailField label="Postal address">{f.postal_address}</DetailField>
        <DetailField label="Postal district / village">{[l.postal_district_id, f.postal_village].filter(Boolean).join(" / ")}</DetailField>
        <DetailField label="Home district">{l.home_district_id}</DetailField>
        <DetailField label="Home TA">{l.home_ta_id}</DetailField>
        <DetailField label="Home village">{l.home_village_id}</DetailField>
      </DetailSection>
      <DetailSection title="Contact">
        <DetailField label="Mobile">{f.mobile}</DetailField>
        <DetailField label="Telephone">{f.telephone}</DetailField>
        <DetailField label="Fax">{f.fax}</DetailField>
        <DetailField label="Email">{f.email}</DetailField>
        <DetailField label="Preferred contact">{optionLabel("contact_modes", f.preferred_contact)}</DetailField>
      </DetailSection>
      <DetailSection title="Bank">
        <DetailField label="Bank">{l.bank_id}</DetailField>
        <DetailField label="Branch">{l.bank_branch_id}</DetailField>
        <DetailField label="Account name">{f.bank_account_name}</DetailField>
        <DetailField label="Account number">{f.bank_account_number}</DetailField>
      </DetailSection>
      <DetailSection title="Next of kin">
        <DetailField label="Name">{f.next_of_kin_name}</DetailField>
        <DetailField label="Relationship">{l.next_of_kin_relationship}</DetailField>
        <DetailField label="Telephone">{f.next_of_kin_phone}</DetailField>
        <DetailField label="Email">{f.next_of_kin_email}</DetailField>
      </DetailSection>
    </Stack>
  );
}

function MemberInformation({ m }: { m: Member }) {
  const f = m.fields as Record<string, string | null>;
  const l = m.labels;
  const optionLabel = useOptionLabel();
  return (
    <Stack spacing={2}>
      <DetailSection title="Membership">
        <DetailField label="Fund">{`${m.fund.code} — ${m.fund.name}`}</DetailField>
        <DetailField label="Employer">{l.scheme_id}</DetailField>
        <DetailField label="Benefit category">{l.category_id}</DetailField>
        <DetailField label="Account type">{f.account_type_code === "MEM" ? "Member Account" : f.account_type_code}</DetailField>
        <DetailField label="Status">{`${MEMBER_STATUS_LABELS[m.status]}${f.status_effective ? ` since ${formatDate(f.status_effective)}` : ""}`}</DetailField>
        <DetailField label="Joined the fund">{f.date_joined_fund && formatDate(f.date_joined_fund)}</DetailField>
        <DetailField label="Joined the employer">{f.date_joined_employer && formatDate(f.date_joined_employer)}</DetailField>
        <DetailField label="Exit date">{f.exit_date && formatDate(f.exit_date)}</DetailField>
        {f.date_of_death && <DetailField label="Date of death">{formatDate(f.date_of_death)}</DetailField>}
      </DetailSection>
      <DetailSection title="Personal">
        <DetailField label="Title">{l.salutation}</DetailField>
        <DetailField label="Date of birth">{f.date_of_birth && formatDate(f.date_of_birth)}</DetailField>
        <DetailField label="Gender">{optionLabel("genders", f.gender)}</DetailField>
        <DetailField label="Nationality code">{f.nationality}</DetailField>
        <DetailField label="Civil status on entry">{optionLabel("marital_statuses", f.civil_status_on_entry)}</DetailField>
        <DetailField label="Current civil status">{optionLabel("marital_statuses", f.civil_status_current)}</DetailField>
        <DetailField label="Civil status (foreign)">{f.civil_status_foreign}</DetailField>
        <DetailField label="Place of birth">{[l.birth_district_id, f.birth_village].filter(Boolean).join(" / ")}</DetailField>
      </DetailSection>
      <DetailSection title="Pension identifiers">
        <DetailField label="UPID">{f.upid}</DetailField>
        <DetailField label="BI UPID">{f.bi_upid}</DetailField>
      </DetailSection>
    </Stack>
  );
}

function CompanyInfo({ m }: { m: Member }) {
  const c = m.company;
  return (
    <DetailSection title="Company information">
      <DetailField label="Owner name">{c.owner_name ? `${c.employer_code} — ${c.owner_name}` : m.fund.fund_type === "personal_pension" ? "Personal pension (no employer)" : null}</DetailField>
      <DetailField label="Corporate form">{c.corporate_form}</DetailField>
      <DetailField label="TPIN">{c.tpin}</DetailField>
      <DetailField label="Registration number">{c.registration_number}</DetailField>
      <DetailField label="Employer KYC">{c.employer_kyc}</DetailField>
      <DetailField label="Fund name">{`${c.fund_code} — ${c.fund_name}`}</DetailField>
    </DetailSection>
  );
}

function KycTab({ m }: { m: Member }) {
  const k = m.kyc;
  return (
    <Stack spacing={2}>
      {k.payment_block && <Alert severity={k.state === "none" ? "info" : "error"}>Benefit payments blocked: {k.payment_block}.</Alert>}
      <DetailSection title="KYC">
        <DetailField label="Standing">
          <StatusChip status={k.state} tone={KYC_TONE[k.state]} label={k.label} />
        </DetailField>
        <DetailField label="KYC client">{k.party_name}</DetailField>
        <DetailField label="Risk rating">{k.risk_rating && <StatusChip status={k.risk_rating} />}</DetailField>
        <DetailField label="Review due">{k.review_due && formatDate(k.review_due)}</DetailField>
        <DetailField label="Latest application">
          {k.application_id && (
            <Link component={RouterLink} to={`/kyc/${k.application_id}`}>
              {k.application_reference}
            </Link>
          )}
        </DetailField>
      </DetailSection>
      {k.state === "none" && (
        <Typography color="text.secondary">Link an approved individual KYC client with “Correct details”, or capture the member's KYC under KYC first.</Typography>
      )}
    </Stack>
  );
}

function RegulatoryTab({ m }: { m: Member }) {
  const data = Object.entries((m.fields.regulatory_data as Record<string, string>) ?? {});
  return (
    <Stack spacing={2}>
      <DetailSection title="Regulatory Authority Data">
        <DetailField label="UPID">{m.fields.upid as string | null}</DetailField>
        <DetailField label="BI UPID">{m.fields.bi_upid as string | null}</DetailField>
        {data.map(([k, v]) => (
          <DetailField key={k} label={k}>
            {v}
          </DetailField>
        ))}
      </DetailSection>
      {data.length === 0 && <Typography color="text.secondary">No other regulatory values recorded. Add them with “Correct details” (Regulatory data step).</Typography>}
    </Stack>
  );
}

function History({ m }: { m: Member }) {
  return (
    <Stack spacing={3}>
      <div>
        <Typography variant="subtitle1" component="h2" sx={{ fontWeight: 600, mb: 1 }}>
          Status history
        </Typography>
        <TableContainer component={Paper}>
          <ResponsiveTable size="small">
            <TableHead>
              <TableRow>
                <TableCell>Effective</TableCell>
                <TableCell>Change</TableCell>
                <TableCell>Reason</TableCell>
                <TableCell>Requested / approved by</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              <TableStateRow colSpan={4} empty="No status changes yet." count={m.status_history.length} />
              {m.status_history.map((c) => (
                <TableRow key={c.id}>
                  <TableCell sx={{ whiteSpace: "nowrap" }}>{formatDate(c.effective_date)}</TableCell>
                  <TableCell>{c.from_status ? `${MEMBER_STATUS_LABELS[c.from_status]} → ${MEMBER_STATUS_LABELS[c.to_status]}` : MEMBER_STATUS_LABELS[c.to_status]}</TableCell>
                  <TableCell>{c.reason}</TableCell>
                  <TableCell>{[c.requested_by, c.approved_by].filter(Boolean).join(" / ")}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </ResponsiveTable>
        </TableContainer>
      </div>
      <div>
        <Typography variant="subtitle1" component="h2" sx={{ fontWeight: 600, mb: 1 }}>
          Employer and category history
        </Typography>
        <TableContainer component={Paper}>
          <ResponsiveTable size="small">
            <TableHead>
              <TableRow>
                <TableCell>From</TableCell>
                <TableCell>To</TableCell>
                <TableCell>Employer</TableCell>
                <TableCell>Category</TableCell>
                <TableCell>Why</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              <TableStateRow colSpan={5} empty="Members of this fund have no employer." count={m.assignments.length} />
              {m.assignments.map((a) => (
                <TableRow key={a.id}>
                  <TableCell sx={{ whiteSpace: "nowrap" }}>{formatDate(a.effective_from)}</TableCell>
                  <TableCell sx={{ whiteSpace: "nowrap" }}>{a.effective_to ? formatDate(a.effective_to) : "Current"}</TableCell>
                  <TableCell>{a.employer ?? "—"}</TableCell>
                  <TableCell>{a.category ?? "—"}</TableCell>
                  <TableCell>{{ joined: "Joined", category_move: "Category move", employer_transfer: "Employer transfer" }[a.reason]}{a.note ? ` — ${a.note}` : ""}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </ResponsiveTable>
        </TableContainer>
      </div>
    </Stack>
  );
}

function StatusDialog({ m, open, onClose }: { m: Member; open: boolean; onClose: () => void }) {
  const feedback = useFeedback();
  const submit = useMemberProposal((body: { to_status: MemberStatus; effective_date: string; reason: string }) => proposeStatusChange(m.id, body));
  const [to, setTo] = useState<MemberStatus | "">("");
  const [date, setDate] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function send() {
    setError(null);
    try {
      await submit.mutateAsync({ to_status: to as MemberStatus, effective_date: date, reason });
      feedback.success(`Status change sent for approval — ${String(m.fields.account_code)} becomes ${MEMBER_STATUS_LABELS[to as MemberStatus].toLowerCase()} once a member checker approves it.`);
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
    }
  }

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>Change status of {String(m.fields.full_name)}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <Typography color="text.secondary">Currently {MEMBER_STATUS_LABELS[m.status].toLowerCase()}. A member checker approves the change.</Typography>
          <TextField select label="New status" value={to} onChange={(e) => setTo(e.target.value as MemberStatus)} helperText={to ? STATUS_HELP[to] : undefined} required>
            {m.allowed_transitions.map((s) => (
              <MenuItem key={s} value={s}>
                {MEMBER_STATUS_LABELS[s]}
              </MenuItem>
            ))}
          </TextField>
          <TextField label={to === "deceased" ? "Date of death" : "Effective date"} type="date" value={date} onChange={(e) => setDate(e.target.value)} required slotProps={{ inputLabel: { shrink: true } }} />
          <TextField label="Reason" value={reason} onChange={(e) => setReason(e.target.value)} required multiline minRows={2} helperText="E.g. resignation letter dated 30 June, death certificate number." />
          {error && <Alert severity="error">{error}</Alert>}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" onClick={send} disabled={!to || !date || reason.trim().length < 3 || submit.isPending}>
          {submit.isPending ? "Sending…" : "Submit for approval"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

function MoveDialog({ m, onClose }: { m: Member; onClose: () => void }) {
  const feedback = useFeedback();
  const umbrella = m.fund.fund_type === "umbrella_dc";
  const schemes = useSchemes(m.fund.id);
  const submit = useMemberProposal((body: Parameters<typeof proposeMove>[1]) => proposeMove(m.id, body));
  const [schemeId, setSchemeId] = useState(String(m.fields.scheme_id ?? ""));
  const [categoryId, setCategoryId] = useState<string | null>(null);
  const [date, setDate] = useState("");
  const [employeeNo, setEmployeeNo] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const transfer = schemeId !== m.fields.scheme_id;

  async function send() {
    setError(null);
    try {
      await submit.mutateAsync({ scheme_id: schemeId, category_id: categoryId!, effective_date: date, employee_no: employeeNo.trim() || null, reason });
      feedback.success(`${transfer ? "Transfer" : "Category move"} sent for approval.`);
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
    }
  }

  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>{umbrella ? "Move or transfer" : "Move category"} — {String(m.fields.full_name)}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <Typography color="text.secondary">
            Now in {m.labels.scheme_id}, category {m.labels.category_id}. The history keeps both; a member checker approves the change.
          </Typography>
          {umbrella && (
            <TextField select label="Employer" value={schemeId} onChange={(e) => { setSchemeId(e.target.value); setCategoryId(null); }} helperText="Another employer in this umbrella fund is a transfer.">
              {(schemes.data ?? []).filter((s) => s.status === "active" || s.id === schemeId).map((s) => (
                <MenuItem key={s.id} value={s.id}>
                  {s.code} — {s.name}
                </MenuItem>
              ))}
            </TextField>
          )}
          {schemeId && <CategorySelect key={schemeId} schemeId={schemeId} value={categoryId} onChange={setCategoryId} />}
          <TextField label="Takes effect" type="date" value={date} onChange={(e) => setDate(e.target.value)} required slotProps={{ inputLabel: { shrink: true } }} />
          {transfer && <TextField label="Employee number at the new employer" value={employeeNo} onChange={(e) => setEmployeeNo(e.target.value)} />}
          <TextField label="Reason" value={reason} onChange={(e) => setReason(e.target.value)} required multiline minRows={2} helperText="E.g. promotion letter dated 1 July." />
          {error && <Alert severity="error">{error}</Alert>}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" onClick={send} disabled={!categoryId || !date || reason.trim().length < 3 || submit.isPending}>
          {submit.isPending ? "Sending…" : "Submit for approval"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

export function MemberDetailPage() {
  const { memberId } = useParams();
  const query = useMember(memberId);
  const [tab, setTab] = useUrlTab(TABS);
  const [statusOpen, setStatusOpen] = useState(false);
  const [moveOpen, setMoveOpen] = useState(false);

  if (query.isLoading) return <LoadingState />;
  if (query.error || !query.data) {
    return (
      <Alert severity="error" action={<Button component={RouterLink} to="/members">Back to members</Button>}>
        {query.error?.message ?? "Member not found"}
      </Alert>
    );
  }
  const m = query.data;
  const locked = !!m.pending_approval_id;

  return (
    <>
      <Breadcrumbs sx={{ mb: 1 }}>
        <Link component={RouterLink} to="/members" underline="hover" color="inherit">
          Members
        </Link>
        <Typography color="text.primary">{String(m.fields.account_code)}</Typography>
      </Breadcrumbs>
      <PageHeader
        title={String(m.fields.full_name)}
        description={`${String(m.fields.account_code)} · ${m.fund.code}${m.labels.scheme_id ? ` · ${m.labels.scheme_id}` : ""}`}
        action={
          m.can_edit && (
            <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: "wrap" }}>
              {!!m.fields.scheme_id && (m.status === "active" || m.status === "inactive") && (
                <Button variant="outlined" onClick={() => setMoveOpen(true)} disabled={locked}>
                  {m.fund.fund_type === "umbrella_dc" ? "Move / transfer" : "Move category"}
                </Button>
              )}
              {m.allowed_transitions.length > 0 && (
                <Button variant="outlined" onClick={() => setStatusOpen(true)} disabled={locked}>
                  Change status
                </Button>
              )}
              <Button variant="contained" component={RouterLink} to={`/members/${m.id}/edit`} disabled={locked}>
                Correct details
              </Button>
            </Stack>
          )
        }
      />
      <Stack direction="row" spacing={1} sx={{ mb: 2, mt: -1.5 }} useFlexGap>
        <StatusChip status={m.status} label={MEMBER_STATUS_LABELS[m.status]} />
        <StatusChip status={m.kyc.state} tone={KYC_TONE[m.kyc.state]} label={m.kyc.label} variant="outlined" />
      </Stack>
      {locked && (
        <Alert severity="warning" sx={{ mb: 2 }} action={<Button color="inherit" size="small" component={RouterLink} to={`/approvals/${m.pending_approval_id}`}>View request</Button>}>
          A change to this member is waiting for approval. Other changes can be made once it is decided.
        </Alert>
      )}
      <Tabs value={tab} onChange={(_, v: MemberTab) => setTab(v)} sx={{ mb: 2 }} variant="scrollable">
        <Tab value="main" label="Main information" />
        <Tab value="member" label="Member information" />
        <Tab value="beneficiaries" label="Beneficiaries" />
        <Tab value="salary" label="Salary & service" />
        <Tab value="company" label="Company info" />
        <Tab value="kyc" label="KYC" />
        <Tab value="regulatory" label="Regulatory Authority Data" />
        <Tab value="transactions" label="Transactions" />
        <Tab value="history" label="History" />
      </Tabs>
      {tab === "main" && <MainInformation m={m} />}
      {tab === "member" && <MemberInformation m={m} />}
      {tab === "beneficiaries" && <MemberBeneficiariesTab member={m} />}
      {tab === "salary" && <MemberEmploymentTab member={m} />}
      {tab === "company" && <CompanyInfo m={m} />}
      {tab === "kyc" && <KycTab m={m} />}
      {tab === "regulatory" && <RegulatoryTab m={m} />}
      {tab === "transactions" && <MemberTransactionsTab member={m} />}
      {tab === "history" && <History m={m} />}
      {statusOpen && <StatusDialog m={m} open onClose={() => setStatusOpen(false)} />}
      {moveOpen && <MoveDialog m={m} onClose={() => setMoveOpen(false)} />}
    </>
  );
}
