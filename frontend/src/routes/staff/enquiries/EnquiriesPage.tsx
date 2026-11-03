import { useEffect, useState } from "react";
import { Link as RouterLink, Route, Routes, useNavigate } from "react-router-dom";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
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
import { useAuth } from "../../../auth/AuthContext";
import { PageHeader } from "../../../components/PageHeader";
import { ResponsiveTable } from "../../../components/ResponsiveTable";
import { StatusChip } from "../../../components/StatusChip";
import { TableStateRow } from "../../../components/TableStateRow";
import { useFeedback } from "../../../components/feedback/FeedbackProvider";
import { useUrlParam, useUrlTab } from "../../../hooks/useUrlState";
import { openBulkStatements } from "../../../api/enquiries";
import { usePublishStatements } from "../../../queries/enquiries";
import { useFunds } from "../../../queries/funds";
import { useMembers } from "../../../queries/members";
import { useSchemes } from "../../../queries/schemes";
import { formatDate, todayIso } from "../../../utils/date";
import { EnquiryPage } from "./EnquiryPage";

const TABS = ["members", "statements"] as const;

function FundPicker({ value, onChange }: { value: string | null; onChange: (id: string) => void }) {
  const funds = useFunds();
  const list = funds.data ?? [];
  useEffect(() => {
    if (!value && list.length) onChange(list[0].id);
  }, [value, list.length]); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <TextField select size="small" label="Fund" value={value ?? ""} onChange={(e) => onChange(e.target.value)} sx={{ minWidth: 280 }}>
      {list.map((f) => <MenuItem key={f.id} value={f.id}>{f.code} — {f.name}</MenuItem>)}
    </TextField>
  );
}

function MemberSearch() {
  const [fundId, setFundId] = useUrlParam("fund");
  const [q, setQ] = useState("");
  const members = useMembers({ fund_id: fundId, q: q.trim(), page_size: 25 });
  const navigate = useNavigate();
  const rows = members.data?.items ?? [];
  return (
    <Stack spacing={2}>
      <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5}>
        <FundPicker value={fundId} onChange={setFundId} />
        <TextField size="small" label="Name, member no., employee no. or ID" value={q} onChange={(e) => setQ(e.target.value)} sx={{ minWidth: 320 }} />
      </Stack>
      <TableContainer component={Paper}>
        <ResponsiveTable size="small">
          <TableHead>
            <TableRow>
              <TableCell>Member</TableCell>
              <TableCell>Employer</TableCell>
              <TableCell>Born</TableCell>
              <TableCell>Status</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            <TableStateRow colSpan={4} loading={members.isLoading} error={members.error?.message ?? null} onRetry={() => members.refetch()}
              empty={q ? "No members match." : "No members in this fund."} count={rows.length} />
            {rows.map((m) => (
              <TableRow key={m.id} hover sx={{ cursor: "pointer" }} onClick={() => navigate(`/enquiries/${m.id}`)}>
                <TableCell>
                  <Typography variant="body2" sx={{ fontWeight: 500 }}>{m.full_name}</Typography>
                  <Typography variant="caption" color="text.secondary">{m.account_code}</Typography>
                </TableCell>
                <TableCell>{m.employer_code ?? "—"}</TableCell>
                <TableCell sx={{ whiteSpace: "nowrap" }}>{formatDate(m.date_of_birth)}</TableCell>
                <TableCell><StatusChip status={m.status} /></TableCell>
              </TableRow>
            ))}
          </TableBody>
        </ResponsiveTable>
      </TableContainer>
    </Stack>
  );
}

function BulkStatements() {
  const { user } = useAuth();
  const canPublish = user?.roles.some((r) => r === "member_admin" || r === "admin") ?? false;
  const [fundId, setFundId] = useUrlParam("fund");
  const schemes = useSchemes(fundId ?? "");
  const [schemeId, setSchemeId] = useState("");
  const [asAt, setAsAt] = useState(todayIso());
  const publish = usePublishStatements();
  const feedback = useFeedback();
  const [busy, setBusy] = useState(false);

  async function print() {
    if (!fundId) return;
    setBusy(true);
    try {
      await openBulkStatements(fundId, asAt, schemeId || undefined);
    } catch (e) {
      feedback.error(e instanceof Error ? e.message : "Couldn't print them.");
    } finally {
      setBusy(false);
    }
  }
  async function notify() {
    if (!fundId || !window.confirm("Email the members that their benefit statement is ready? Members with a portal login also see it there.")) return;
    try {
      const r = await publish.mutateAsync({ fundId, asAt, schemeId: schemeId || undefined });
      feedback.success(`${r.notified} of ${r.members} members told (members without an email address on record weren't).`);
    } catch (e) {
      feedback.error(e instanceof Error ? e.message : "Couldn't send them.");
    }
  }
  return (
    <Paper sx={{ p: { xs: 2, sm: 3 } }}>
      <Typography variant="subtitle1" component="h2" sx={{ fontWeight: 600 }}>Member benefit statements in bulk</Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        One page per current member (exited and deceased members are left out), as at the date chosen.
      </Typography>
      <Stack direction={{ xs: "column", md: "row" }} spacing={1.5} sx={{ mb: 2 }}>
        <FundPicker value={fundId} onChange={(id) => { setFundId(id); setSchemeId(""); }} />
        <TextField select size="small" label="Employer" value={schemeId} onChange={(e) => setSchemeId(e.target.value)} sx={{ minWidth: 240 }}>
          <MenuItem value="">All employers</MenuItem>
          {(schemes.data ?? []).map((s) => <MenuItem key={s.id} value={s.id}>{s.code} — {s.name}</MenuItem>)}
        </TextField>
        <TextField size="small" label="As at" type="date" value={asAt} onChange={(e) => setAsAt(e.target.value)} slotProps={{ inputLabel: { shrink: true } }} />
      </Stack>
      <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5}>
        <Button variant="contained" onClick={print} disabled={!fundId || busy}>{busy ? "Preparing…" : "Print statements (PDF)"}</Button>
        {canPublish && <Button variant="outlined" onClick={notify} disabled={!fundId || publish.isPending}>Tell members it's ready</Button>}
      </Stack>
    </Paper>
  );
}

function EnquiriesHome() {
  const [tab, setTab] = useUrlTab(TABS);
  return (
    <>
      <PageHeader title="Enquiries" description="A member's account, statements and trails; benefit statements in bulk." />
      <Stack spacing={2}>
        <Tabs value={tab} onChange={(_, v: (typeof TABS)[number]) => setTab(v)}>
          <Tab value="members" label="Account enquiry" />
          <Tab value="statements" label="Bulk statements" />
        </Tabs>
        {tab === "members" ? <MemberSearch /> : <BulkStatements />}
      </Stack>
    </>
  );
}

export function EnquiriesPage() {
  return (
    <Routes>
      <Route index element={<EnquiriesHome />} />
      <Route path=":memberId" element={<EnquiryPage />} />
      <Route path="*" element={<Alert severity="warning">Page not found. <RouterLink to="/enquiries">Back to enquiries</RouterLink></Alert>} />
    </Routes>
  );
}
