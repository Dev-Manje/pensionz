import { useEffect, useMemo, useState } from "react";
import { Link as RouterLink, useNavigate, useParams, useSearchParams } from "react-router-dom";
import Alert from "@mui/material/Alert";
import Autocomplete from "@mui/material/Autocomplete";
import Box from "@mui/material/Box";
import Breadcrumbs from "@mui/material/Breadcrumbs";
import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import FormControlLabel from "@mui/material/FormControlLabel";
import IconButton from "@mui/material/IconButton";
import Link from "@mui/material/Link";
import MenuItem from "@mui/material/MenuItem";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Step from "@mui/material/Step";
import StepButton from "@mui/material/StepButton";
import Stepper from "@mui/material/Stepper";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import useMediaQuery from "@mui/material/useMediaQuery";
import { useTheme } from "@mui/material/styles";
import AddIcon from "@mui/icons-material/Add";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutlined";
import { LoadingState } from "../../../components/LoadingState";
import { PageHeader } from "../../../components/PageHeader";
import { useFeedback } from "../../../components/feedback/FeedbackProvider";
import { useBanks, useFunds } from "../../../queries/funds";
import { useSchemes } from "../../../queries/schemes";
import { useCategories } from "../../../queries/categories";
import { useDuplicates, useKycPrefill, useMember, useMemberProposal, useMembers, useParties } from "../../../queries/members";
import { proposeMember, proposeMemberUpdate } from "../../../api/members";
import { MEMBER_STATUS_LABELS, type Member, type MemberValues } from "../../../api/types";
import { formatDate } from "../../../utils/date";
import { KycField } from "../kyc/KycField";
import { isShown, type FieldDef } from "../kyc/kycSchema";
import { CONTACT, DETAIL_KEYS, IDENTIFIERS, NEXT_OF_KIN, NO_EMPLOYER_FUNDS, PERSONAL } from "./memberSchema";

const DRAFT_KEY = "pz_member_draft";
const STEPS = ["Membership", "Personal details", "Address and contact", "Bank and next of kin", "Regulatory data", "Review and submit"];

type Data = MemberValues;

function readDraft(): { fundId: string | null; data: Data } | null {
  try {
    const raw = localStorage.getItem(DRAFT_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function Fields({ fields, data, onChange }: { fields: FieldDef[]; data: Data; onChange: (name: string, value: unknown) => void }) {
  return (
    <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "1fr 1fr" }, gap: 2 }}>
      {fields.filter((f) => isShown(f, data)).map((f) => (
        <Box key={f.name} sx={{ gridColumn: f.type === "textarea" ? "1 / -1" : undefined }}>
          <KycField field={f} data={data} onChange={onChange} />
        </Box>
      ))}
    </Box>
  );
}

export function CategorySelect({ schemeId, value, onChange }: { schemeId: string; value: string | null; onChange: (v: string | null) => void }) {
  const categories = useCategories(schemeId);
  const options = (categories.data ?? []).filter((c) => c.status === "active" || c.id === value);
  return (
    <TextField select label="Benefit category" required value={value ?? ""} onChange={(e) => onChange(e.target.value || null)} fullWidth
      helperText={categories.error ? categories.error.message : !categories.isLoading && options.length === 0 ? "This employer has no active categories yet." : "Sets contribution rates and retirement age."}>
      {options.map((c) => (
        <MenuItem key={c.id} value={c.id}>
          {c.code} — {c.name}
        </MenuItem>
      ))}
    </TextField>
  );
}

function GroupAccountPicker({ fundId, value, onChange }: { fundId: string; value: string | null; onChange: (v: string | null) => void }) {
  const groups = useMembers({ fund_id: fundId, group_accounts: true, page_size: 200 });
  const options = groups.data?.items ?? [];
  return (
    <Autocomplete
      options={options}
      value={options.find((o) => o.id === value) ?? null}
      onChange={(_, o) => onChange(o?.id ?? null)}
      getOptionLabel={(o) => `${o.account_code} — ${o.full_name}`}
      loading={groups.isLoading}
      renderInput={(params) => <TextField {...params} label="Belongs to group account" helperText="Optional — the group account this member is part of." />}
    />
  );
}

function MembershipStep({ member, fundId, setFundId, data, set, merge }: {
  member: Member | null;
  fundId: string | null;
  setFundId: (id: string | null) => void;
  data: Data;
  set: (name: string, value: unknown) => void;
  merge: (values: Data) => void;
}) {
  const funds = useFunds();
  const fund = (funds.data ?? []).find((f) => f.id === fundId);
  const fundType = member?.fund.fund_type ?? fund?.fund_type;
  const noEmployer = !!fundType && NO_EMPLOYER_FUNDS.includes(fundType);
  const schemes = useSchemes(fundId ?? "");
  const parties = useParties("individual");
  const prefill = useKycPrefill();
  const feedback = useFeedback();
  const partyOptions = parties.data ?? [];
  const str = (k: string) => (data[k] as string | null) ?? "";

  async function fillFromKyc() {
    try {
      const values = await prefill.mutateAsync(data.party_id as string);
      merge(Object.fromEntries(Object.entries(values).filter(([, v]) => v !== null && v !== undefined && v !== "")));
      feedback.success("Filled in from the approved KYC — check each step before submitting.");
    } catch (e) {
      feedback.error(e instanceof Error ? e.message : "Couldn't read the KYC answers.");
    }
  }

  return (
    <Stack spacing={2}>
      <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "1fr 1fr" }, gap: 2 }}>
        {member ? (
          <TextField label="Fund" value={`${member.fund.code} — ${member.fund.name}`} disabled fullWidth />
        ) : (
          <TextField select label="Fund" required value={fundId ?? ""} onChange={(e) => { setFundId(e.target.value || null); set("scheme_id", null); set("category_id", null); }} fullWidth>
            {(funds.data ?? []).filter((f) => f.status === "active").map((f) => (
              <MenuItem key={f.id} value={f.id}>
                {f.code} — {f.name}
              </MenuItem>
            ))}
          </TextField>
        )}
        {!member && (
          <TextField label="Account code" value={str("account_code")} onChange={(e) => set("account_code", e.target.value || null)} fullWidth
            helperText="Leave empty to generate one. Give it only when loading an existing member." slotProps={{ htmlInput: { maxLength: 20 } }} />
        )}
        {member && <TextField label="Account code" value={String(member.fields.account_code)} disabled fullWidth />}
      </Box>

      {fundId && !noEmployer && !member && (
        <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "1fr 1fr" }, gap: 2 }}>
          <TextField select label="Employer" required value={str("scheme_id")} onChange={(e) => { set("scheme_id", e.target.value || null); set("category_id", null); }} fullWidth>
            {(schemes.data ?? []).filter((s) => s.status === "active").map((s) => (
              <MenuItem key={s.id} value={s.id}>
                {s.code} — {s.name}
              </MenuItem>
            ))}
          </TextField>
          {data.scheme_id ? (
            <CategorySelect schemeId={data.scheme_id as string} value={(data.category_id as string) ?? null} onChange={(v) => set("category_id", v)} />
          ) : (
            <TextField label="Benefit category" disabled helperText="Choose the employer first." fullWidth />
          )}
        </Box>
      )}
      {member && !noEmployer && (
        <Alert severity="info">
          Employer {member.labels.scheme_id ?? "—"}, category {member.labels.category_id ?? "—"}. To move the member to another category or employer, use
          “Move” on the member's page.
        </Alert>
      )}

      <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "1fr 1fr" }, gap: 2 }}>
        <TextField label="Joined the fund" type="date" required value={str("date_joined_fund")} onChange={(e) => set("date_joined_fund", e.target.value || null)} fullWidth slotProps={{ inputLabel: { shrink: true } }} />
        {!noEmployer && (
          <TextField label="Joined the employer" type="date" value={str("date_joined_employer")} onChange={(e) => set("date_joined_employer", e.target.value || null)} fullWidth slotProps={{ inputLabel: { shrink: true } }} />
        )}
        {IDENTIFIERS.slice(0, 2).map((f) => (
          <KycField key={f.name} field={f} data={data} onChange={set} />
        ))}
      </Box>

      <Paper variant="outlined" sx={{ p: 2 }}>
        <Typography sx={{ fontWeight: 600, mb: 0.5 }}>Approved KYC client{fundType === "personal_pension" ? " (required)" : ""}</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
          {fundType === "personal_pension"
            ? "Personal pension holders must have approved individual KYC."
            : "Optional for employer members — without current KYC, benefits can't be paid until it is completed."}
        </Typography>
        <Stack direction={{ xs: "column", sm: "row" }} spacing={1} sx={{ alignItems: { sm: "flex-start" } }}>
          <Autocomplete
            sx={{ flex: 1 }}
            options={partyOptions}
            value={partyOptions.find((p) => p.id === data.party_id) ?? null}
            onChange={(_, p) => set("party_id", p?.id ?? null)}
            getOptionLabel={(p) => `${p.name}${p.identifier ? ` (${p.identifier})` : ""}`}
            loading={parties.isLoading}
            renderInput={(params) => <TextField {...params} label="KYC client" helperText={parties.error?.message} error={!!parties.error} />}
          />
          {!member && (
            <Button variant="outlined" onClick={fillFromKyc} disabled={!data.party_id || prefill.isPending} sx={{ minHeight: 56, whiteSpace: "nowrap" }}>
              {prefill.isPending ? "Filling in…" : "Fill in from KYC"}
            </Button>
          )}
        </Stack>
      </Paper>

      {fundId && (
        <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "1fr 1fr" }, gap: 2, alignItems: "center" }}>
          <FormControlLabel
            control={<Checkbox checked={!!data.is_group_account} onChange={(e) => { set("is_group_account", e.target.checked); if (e.target.checked) set("group_account_id", null); }} />}
            label="This is a group account"
          />
          {!data.is_group_account && <GroupAccountPicker fundId={fundId} value={(data.group_account_id as string) ?? null} onChange={(v) => set("group_account_id", v)} />}
        </Box>
      )}
    </Stack>
  );
}

function BankStep({ data, set }: { data: Data; set: (name: string, value: unknown) => void }) {
  const banks = useBanks();
  const bank = (banks.data ?? []).find((b) => b.id === data.bank_id);
  return (
    <Stack spacing={3}>
      <Box>
        <Typography sx={{ fontWeight: 600, mb: 1.5 }}>Bank account for benefit payments</Typography>
        <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "1fr 1fr" }, gap: 2 }}>
          <TextField select label="Bank" value={(data.bank_id as string) ?? ""} onChange={(e) => { set("bank_id", e.target.value || null); set("bank_branch_id", null); }} fullWidth>
            <MenuItem value="">
              <em>None</em>
            </MenuItem>
            {(banks.data ?? []).map((b) => (
              <MenuItem key={b.id} value={b.id}>
                {b.name}
              </MenuItem>
            ))}
          </TextField>
          <TextField select label="Branch" value={(data.bank_branch_id as string) ?? ""} onChange={(e) => set("bank_branch_id", e.target.value || null)} disabled={!bank} fullWidth helperText={bank ? undefined : "Choose the bank first."}>
            {(bank?.branches ?? []).map((b) => (
              <MenuItem key={b.id} value={b.id}>
                {b.name}
              </MenuItem>
            ))}
          </TextField>
          <TextField label="Account name" value={(data.bank_account_name as string) ?? ""} onChange={(e) => set("bank_account_name", e.target.value || null)} fullWidth />
          <TextField label="Account number" value={(data.bank_account_number as string) ?? ""} onChange={(e) => set("bank_account_number", e.target.value || null)} fullWidth slotProps={{ htmlInput: { inputMode: "numeric" } }} />
        </Box>
      </Box>
      <Box>
        <Typography sx={{ fontWeight: 600, mb: 1.5 }}>Next of kin</Typography>
        <Fields fields={NEXT_OF_KIN} data={data} onChange={set} />
      </Box>
    </Stack>
  );
}

function RegulatoryStep({ data, set }: { data: Data; set: (name: string, value: unknown) => void }) {
  const pairs = Object.entries((data.regulatory_data as Record<string, string>) ?? {});
  const [rows, setRows] = useState<[string, string][]>(pairs.length ? pairs : []);
  const update = (next: [string, string][]) => {
    setRows(next);
    set("regulatory_data", Object.fromEntries(next.filter(([k]) => k.trim())));
  };
  return (
    <Stack spacing={3}>
      <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "1fr 1fr" }, gap: 2 }}>
        {IDENTIFIERS.slice(2).map((f) => (
          <KycField key={f.name} field={f} data={data} onChange={set} />
        ))}
      </Box>
      <Box>
        <Typography sx={{ fontWeight: 600 }}>Regulatory Authority Data</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
          Other values the regulator's returns need, as name and value, until the regulator's field list is confirmed.
        </Typography>
        <Stack spacing={1.5}>
          {rows.map(([k, v], i) => (
            <Stack key={i} direction="row" spacing={1} sx={{ alignItems: "center" }}>
              <TextField label="Name" value={k} onChange={(e) => update(rows.map((r, j) => (j === i ? [e.target.value, r[1]] : r)))} sx={{ flex: 1 }} slotProps={{ htmlInput: { maxLength: 60 } }} />
              <TextField label="Value" value={v} onChange={(e) => update(rows.map((r, j) => (j === i ? [r[0], e.target.value] : r)))} sx={{ flex: 1 }} slotProps={{ htmlInput: { maxLength: 200 } }} />
              <IconButton aria-label={`Remove ${k || "row"}`} onClick={() => update(rows.filter((_, j) => j !== i))}>
                <DeleteOutlineIcon fontSize="small" />
              </IconButton>
            </Stack>
          ))}
          <Button startIcon={<AddIcon />} variant="outlined" onClick={() => setRows([...rows, ["", ""]])} sx={{ alignSelf: "flex-start" }}>
            Add value
          </Button>
        </Stack>
      </Box>
    </Stack>
  );
}

function DuplicateAlert({ data, excludeId }: { data: Data; excludeId?: string }) {
  const params = {
    id_number: (data.id_number as string) || null,
    first_name: (data.first_name as string) || null,
    last_name: (data.last_name as string) || null,
    date_of_birth: (data.date_of_birth as string) || null,
    exclude: excludeId,
  };
  const ready = !!params.id_number || (!!params.first_name && !!params.last_name && !!params.date_of_birth);
  const [debounced, setDebounced] = useState(params);
  const key = JSON.stringify(params);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(JSON.parse(key)), 500);
    return () => clearTimeout(t);
  }, [key]);
  const dups = useDuplicates(debounced, ready);
  if (!ready || !dups.data?.length) return null;
  return (
    <Alert severity="warning">
      <Typography sx={{ fontWeight: 600, mb: 0.5 }}>Possible duplicate{dups.data.length > 1 ? "s" : ""} — check before submitting:</Typography>
      <Box component="ul" sx={{ m: 0, pl: 2.5 }}>
        {dups.data.map((d) => (
          <li key={d.member_id}>
            {d.match}:{" "}
            <Link component={RouterLink} to={`/members/${d.member_id}`} target="_blank">
              {d.account_code} {d.full_name}
            </Link>{" "}
            (born {formatDate(d.date_of_birth)}, {d.fund_code}
            {d.employer ? ` / ${d.employer}` : ""}, {MEMBER_STATUS_LABELS[d.status]})
          </li>
        ))}
      </Box>
    </Alert>
  );
}

function problems(data: Data, fundId: string | null, needsEmployer: boolean, isNew: boolean): string[] {
  const out: string[] = [];
  if (isNew && !fundId) out.push("Choose the fund");
  if (isNew && needsEmployer && (!data.scheme_id || !data.category_id)) out.push("Choose the employer and benefit category");
  for (const [key, label] of [["first_name", "First name"], ["last_name", "Last name"], ["gender", "Gender"], ["date_of_birth", "Date of birth"], ["date_joined_fund", "Date joined the fund"]] as const) {
    if (!data[key]) out.push(`${label} is required`);
  }
  if (data.id_number && !data.id_type) out.push("Choose the ID type for the ID number");
  if (data.bank_account_number && !data.bank_id) out.push("Choose the bank for the account number");
  return out;
}

export function MemberFormPage() {
  const { memberId } = useParams();
  const existing = useMember(memberId);
  if (memberId && existing.isLoading) return <LoadingState />;
  if (memberId && (existing.error || !existing.data)) return <Alert severity="error">{existing.error?.message ?? "Member not found"}</Alert>;
  return <MemberForm key={memberId ?? "new"} member={existing.data ?? null} />;
}

function initialData(member: Member | null): { fundId: string | null; data: Data; restored: boolean } {
  if (member) {
    const data: Data = {};
    for (const key of DETAIL_KEYS) data[key] = member.fields[key] ?? null;
    return { fundId: member.fund.id, data, restored: false };
  }
  const draft = readDraft();
  if (draft) return { ...draft, restored: true };
  return { fundId: null, data: { regulatory_data: {}, is_group_account: false }, restored: false };
}

function MemberForm({ member }: { member: Member | null }) {
  const navigate = useNavigate();
  const feedback = useFeedback();
  const [search] = useSearchParams();
  const narrow = useMediaQuery(useTheme().breakpoints.down("md"));
  const initial = useMemo(() => initialData(member), [member]);
  const [fundId, setFundId] = useState<string | null>(initial.fundId ?? search.get("fund"));
  const [data, setData] = useState<Data>(initial.data);
  const [restored, setRestored] = useState(initial.restored);
  const [active, setActive] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const funds = useFunds();
  const fundType = member?.fund.fund_type ?? (funds.data ?? []).find((f) => f.id === fundId)?.fund_type;
  const needsEmployer = !!fundType && !NO_EMPLOYER_FUNDS.includes(fundType);
  const submit = useMemberProposal((values: Data) => (member ? proposeMemberUpdate(member.id, values) : proposeMember(fundId!, values)));
  const missing = problems(data, fundId, needsEmployer, !member);

  // New members are kept as a draft in this browser until submitted (FR-MEM-007).
  useEffect(() => {
    if (!member) localStorage.setItem(DRAFT_KEY, JSON.stringify({ fundId, data }));
  }, [member, fundId, data]);

  const set = (name: string, value: unknown) => setData((d) => ({ ...d, [name]: value }));
  const merge = (values: Data) => setData((d) => ({ ...d, ...values }));
  const go = (i: number) => {
    setActive(i);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  function discardDraft() {
    localStorage.removeItem(DRAFT_KEY);
    setData({ regulatory_data: {}, is_group_account: false });
    setFundId(null);
    setRestored(false);
    setActive(0);
  }

  async function send() {
    setError(null);
    const values: Data = {};
    for (const key of DETAIL_KEYS) values[key] = data[key] ?? null;
    if (!member) Object.assign(values, { scheme_id: data.scheme_id ?? null, category_id: data.category_id ?? null, account_code: data.account_code ?? null });
    values.regulatory_data = data.regulatory_data ?? {};
    values.is_group_account = !!data.is_group_account;
    try {
      await submit.mutateAsync(values);
      if (!member) localStorage.removeItem(DRAFT_KEY);
      feedback.success(member ? "Correction sent for approval — it takes effect once a member checker approves it." : "New member sent for approval — the account code is given once a member checker approves it.");
      navigate(member ? `/members/${member.id}` : "/members");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
    }
  }

  const name = [data.first_name, data.last_name].filter(Boolean).join(" ");
  return (
    <>
      <Breadcrumbs sx={{ mb: 1 }}>
        <Link component={RouterLink} to="/members" underline="hover" color="inherit">
          Members
        </Link>
        {member && (
          <Link component={RouterLink} to={`/members/${member.id}`} underline="hover" color="inherit">
            {String(member.fields.account_code)}
          </Link>
        )}
        <Typography color="text.primary">{member ? "Correct details" : "New member"}</Typography>
      </Breadcrumbs>
      <PageHeader
        title={member ? `Correct ${String(member.fields.full_name)}` : "Add a member"}
        description={member ? "A member checker approves the correction before it takes effect; the record's history keeps the old values." : "A member checker approves the new member before it is created. Your answers are kept in this browser until you submit."}
      />
      {restored && (
        <Alert severity="info" sx={{ mb: 2 }} action={<Button color="inherit" size="small" onClick={discardDraft}>Start again</Button>}>
          Your unfinished new member{name ? ` (${name})` : ""} was restored.
        </Alert>
      )}
      <Stack spacing={2}>
        {narrow ? (
          <TextField select label={`Step ${active + 1} of ${STEPS.length}`} value={active} onChange={(e) => go(Number(e.target.value))}>
            {STEPS.map((s, i) => (
              <MenuItem key={s} value={i}>
                {i + 1}. {s}
              </MenuItem>
            ))}
          </TextField>
        ) : (
          <Stepper nonLinear activeStep={active} alternativeLabel>
            {STEPS.map((s, i) => (
              <Step key={s}>
                <StepButton onClick={() => go(i)}>{s}</StepButton>
              </Step>
            ))}
          </Stepper>
        )}
        <Paper component="section" sx={{ p: { xs: 2, sm: 3 } }}>
          <Typography variant="h6" component="h2" sx={{ mb: 2 }}>
            {STEPS[active]}
          </Typography>
          {active === 0 && <MembershipStep member={member} fundId={fundId} setFundId={setFundId} data={data} set={set} merge={merge} />}
          {active === 1 && (
            <Stack spacing={2}>
              <Fields fields={PERSONAL} data={data} onChange={set} />
              <DuplicateAlert data={data} excludeId={member?.id} />
            </Stack>
          )}
          {active === 2 && <Fields fields={CONTACT} data={data} onChange={set} />}
          {active === 3 && <BankStep data={data} set={set} />}
          {active === 4 && <RegulatoryStep data={data} set={set} />}
          {active === 5 && (
            <Stack spacing={2}>
              <DuplicateAlert data={data} excludeId={member?.id} />
              {missing.length > 0 ? (
                <Alert severity="warning">
                  <Typography sx={{ fontWeight: 600, mb: 0.5 }}>Still to do:</Typography>
                  <Box component="ul" sx={{ m: 0, pl: 2.5 }}>
                    {missing.map((p) => (
                      <li key={p}>{p}</li>
                    ))}
                  </Box>
                </Alert>
              ) : (
                <Alert severity="success">Everything required is filled in. The member checker sees the full record before approving.</Alert>
              )}
              {error && <Alert severity="error">{error}</Alert>}
              <Box>
                <Button variant="contained" size="large" onClick={send} disabled={missing.length > 0 || submit.isPending}>
                  {submit.isPending ? "Sending…" : "Submit for approval"}
                </Button>
              </Box>
            </Stack>
          )}
        </Paper>
        <Stack direction="row" spacing={1} sx={{ justifyContent: "space-between", pb: 2 }}>
          <Button onClick={() => (active === 0 ? navigate(member ? `/members/${member.id}` : "/members") : go(active - 1))}>{active === 0 ? "Cancel" : "Back"}</Button>
          {active < STEPS.length - 1 && (
            <Button variant="contained" onClick={() => go(active + 1)}>
              Next
            </Button>
          )}
        </Stack>
      </Stack>
    </>
  );
}
