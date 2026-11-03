import { useRef, useState } from "react";
import { Link as RouterLink, useNavigate } from "react-router-dom";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import FormControlLabel from "@mui/material/FormControlLabel";
import Link from "@mui/material/Link";
import MenuItem from "@mui/material/MenuItem";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Switch from "@mui/material/Switch";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import useMediaQuery from "@mui/material/useMediaQuery";
import type { Theme } from "@mui/material/styles";
import { ResponsiveTable } from "../../components/ResponsiveTable";
import { StatusChip } from "../../components/StatusChip";
import { TableStateRow } from "../../components/TableStateRow";
import { useFeedback } from "../../components/feedback/FeedbackProvider";
import { applyNewMember, downloadMemberTemplate, openApplicationForm, uploadMemberList } from "../../api/po";
import type { NewMemberInput } from "../../api/types";
import { usePortalCategories, usePortalMemberRequest, usePortalMembers } from "../../queries/po";
import { useListRows } from "../../queries/setup";
import { formatDate, todayIso } from "../../utils/date";
import { formatMoney } from "../../utils/format";
import { schemePath } from "./PoSchemePage";

const blank = {
  first_name: "", other_names: "", last_name: "", gender: "", date_of_birth: "", nationality: "MW", id_type: "", id_number: "",
  employee_no: "", category_id: "", date_joined_employer: todayIso().slice(0, 8) + "01", date_joined_fund: todayIso().slice(0, 8) + "01",
  mobile: "", email: "", physical_address: "", basic_salary: "",
};

function NewMemberDialog({ schemeId, onClose }: { schemeId: string; onClose: () => void }) {
  const fullScreen = useMediaQuery((t: Theme) => t.breakpoints.down("sm"));
  const navigate = useNavigate();
  const feedback = useFeedback();
  const categories = usePortalCategories(schemeId);
  const idTypes = useListRows("id_types");
  const countries = useListRows("countries");
  const send = usePortalMemberRequest((body: NewMemberInput) => applyNewMember(schemeId, body));
  const [v, setV] = useState({ ...blank, category_id: "" });
  const [error, setError] = useState<string | null>(null);
  const set = (k: keyof typeof v) => (e: { target: { value: string } }) => setV({ ...v, [k]: e.target.value });
  const category = v.category_id || (categories.data?.length === 1 ? categories.data[0].id : "");
  const ready = v.first_name.trim() && v.last_name.trim() && v.gender && v.date_of_birth && category && v.date_joined_employer &&
    v.date_joined_fund && Number(v.basic_salary.replace(/,/g, "")) > 0;

  async function go() {
    setError(null);
    const opt = (s: string) => s.trim() || null;
    try {
      await send.mutateAsync({
        first_name: v.first_name.trim(), other_names: opt(v.other_names), last_name: v.last_name.trim(), gender: v.gender, date_of_birth: v.date_of_birth,
        nationality: opt(v.nationality), id_type: opt(v.id_type), id_number: opt(v.id_number), employee_no: opt(v.employee_no), category_id: category,
        date_joined_employer: v.date_joined_employer, date_joined_fund: v.date_joined_fund, mobile: opt(v.mobile), email: opt(v.email),
        physical_address: opt(v.physical_address), basic_salary: v.basic_salary.replace(/,/g, "").trim(),
      });
      feedback.success(`${v.first_name} ${v.last_name} sent for approval — you'll be told when the member is added.`);
      navigate(schemePath(schemeId, "requests"));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't send the application.");
    }
  }

  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="md" fullScreen={fullScreen}>
      <DialogTitle>Add a new member</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <Typography color="text.secondary">
            For an employee joining the scheme. We check the details and add the member; you get an email when it's done.
          </Typography>
          <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
            <TextField label="First name" value={v.first_name} onChange={set("first_name")} required fullWidth autoFocus />
            <TextField label="Other names" value={v.other_names} onChange={set("other_names")} fullWidth />
            <TextField label="Surname" value={v.last_name} onChange={set("last_name")} required fullWidth />
          </Stack>
          <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
            <TextField select label="Gender" value={v.gender} onChange={set("gender")} required fullWidth>
              <MenuItem value="female">Female</MenuItem>
              <MenuItem value="male">Male</MenuItem>
            </TextField>
            <TextField label="Date of birth" type="date" value={v.date_of_birth} onChange={set("date_of_birth")} required fullWidth
              slotProps={{ inputLabel: { shrink: true } }} />
            <TextField select label="Nationality" value={v.nationality} onChange={set("nationality")} fullWidth>
              {(countries.data ?? []).map((c) => (
                <MenuItem key={String(c.code)} value={String(c.code)}>{String(c.name)}</MenuItem>
              ))}
            </TextField>
          </Stack>
          <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
            <TextField select label="ID type" value={v.id_type} onChange={set("id_type")} fullWidth>
              <MenuItem value="">Not given</MenuItem>
              {(idTypes.data ?? []).map((t) => (
                <MenuItem key={String(t.code)} value={String(t.code)}>{String(t.name)}</MenuItem>
              ))}
            </TextField>
            <TextField label="ID number" value={v.id_number} onChange={set("id_number")} fullWidth />
            <TextField label="Employee number" value={v.employee_no} onChange={set("employee_no")} fullWidth />
          </Stack>
          <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
            <TextField select label="Category" value={category} onChange={set("category_id")} required fullWidth
              helperText={categories.data?.length === 0 ? "No categories set up — ask your administrator" : undefined}>
              {(categories.data ?? []).map((c) => (
                <MenuItem key={c.id} value={c.id}>{c.name}</MenuItem>
              ))}
            </TextField>
            <TextField label="Started with you on" type="date" value={v.date_joined_employer} onChange={set("date_joined_employer")} required fullWidth
              slotProps={{ inputLabel: { shrink: true } }} />
            <TextField label="Joins the fund on" type="date" value={v.date_joined_fund} onChange={set("date_joined_fund")} required fullWidth
              slotProps={{ inputLabel: { shrink: true } }} helperText="Usually the first day of the month" />
          </Stack>
          <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
            <TextField label="Monthly basic salary (MWK)" value={v.basic_salary} onChange={set("basic_salary")} inputMode="decimal" required fullWidth />
            <TextField label="Mobile" value={v.mobile} onChange={set("mobile")} type="tel" fullWidth />
            <TextField label="Email" value={v.email} onChange={set("email")} type="email" fullWidth />
          </Stack>
          <TextField label="Physical address" value={v.physical_address} onChange={set("physical_address")} />
          <Typography variant="body2" color="text.secondary">
            Beneficiaries and bank details come on the signed application form —{" "}
            <Link component="button" type="button" onClick={() => openApplicationForm(schemeId).catch((e) => feedback.error(e.message))}>
              print it here
            </Link>{" "}
            and send it to us.
          </Typography>
          {error && <Alert severity="error">{error}</Alert>}
        </Stack>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" onClick={go} disabled={!ready || send.isPending}>
          {send.isPending ? "Sending…" : "Send for approval"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

function UploadDialog({ schemeId, onClose }: { schemeId: string; onClose: () => void }) {
  const navigate = useNavigate();
  const feedback = useFeedback();
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function upload(file: File) {
    setBusy(true);
    setError(null);
    try {
      const batch = await uploadMemberList(schemeId, file);
      navigate(`/po/member-imports/${batch.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't read the file.");
      setBusy(false);
    }
  }

  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="xs">
      <DialogTitle>Upload several new members</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 0.5 }}>
          <Typography>1. Download the spreadsheet — it lists your categories and the codes each column accepts.</Typography>
          <Button variant="outlined" onClick={() => downloadMemberTemplate(schemeId).catch((e) => feedback.error(e.message))} sx={{ alignSelf: "flex-start" }}>
            Download spreadsheet
          </Button>
          <Typography>2. Fill in one row per new member, then upload it. Every row is checked; you'll see what to fix before anything is sent.</Typography>
          <Button variant="contained" onClick={() => input.current?.click()} disabled={busy} sx={{ alignSelf: "flex-start" }}>
            {busy ? "Checking…" : "Upload the filled spreadsheet"}
          </Button>
          <input ref={input} type="file" hidden accept=".xlsx,.csv"
            onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) void upload(f); }} />
          {error && <Alert severity="error">{error}</Alert>}
        </Stack>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onClose}>Close</Button>
      </DialogActions>
    </Dialog>
  );
}

// The employer's members (HR-level facts only) and new-member applications.
export function PoMembers({ schemeId }: { schemeId: string }) {
  const [q, setQ] = useState("");
  const [former, setFormer] = useState(false);
  const [dialog, setDialog] = useState<"new" | "upload" | null>(null);
  const query = usePortalMembers(schemeId, q, !former);
  const rows = query.data ?? [];

  return (
    <Stack spacing={2}>
      <Paper sx={{ p: { xs: 2, sm: 2.5 } }}>
        <Stack direction={{ xs: "column", md: "row" }} spacing={1.5} sx={{ justifyContent: "space-between", alignItems: { md: "center" } }}>
          <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} sx={{ alignItems: { sm: "center" } }}>
            <TextField size="small" label="Search name, account or employee no." value={q} onChange={(e) => setQ(e.target.value)} sx={{ minWidth: { sm: 300 } }} />
            <FormControlLabel control={<Switch checked={former} onChange={(e) => setFormer(e.target.checked)} />} label="Include former members" />
          </Stack>
          <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
            <Button variant="contained" onClick={() => setDialog("new")}>Add a member</Button>
            <Button variant="outlined" onClick={() => setDialog("upload")}>Upload several</Button>
          </Stack>
        </Stack>
      </Paper>
      <TableContainer component={Paper}>
        <ResponsiveTable size="small">
          <TableHead>
            <TableRow>
              <TableCell>Member</TableCell>
              <TableCell>Employee no.</TableCell>
              <TableCell>Category</TableCell>
              <TableCell>Joined</TableCell>
              <TableCell align="right">Salary</TableCell>
              <TableCell>Status</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            <TableStateRow colSpan={6} loading={query.isLoading} error={query.error?.message ?? null} onRetry={() => query.refetch()}
              empty={q ? "No members match." : "No members yet — add them above."} count={rows.length} />
            {rows.map((m) => (
              <TableRow key={m.id} hover>
                <TableCell>
                  <Link component={RouterLink} to={`/po/members/${m.id}`} underline="hover" sx={{ fontWeight: 600 }}>
                    {m.full_name}
                  </Link>
                  <Typography variant="body2" color="text.secondary">{m.account_code}</Typography>
                </TableCell>
                <TableCell>{m.employee_no ?? "—"}</TableCell>
                <TableCell>{m.category ?? "—"}</TableCell>
                <TableCell>{formatDate(m.date_joined_employer ?? m.date_joined_fund)}</TableCell>
                <TableCell align="right">{m.salary ? formatMoney(m.salary) : "Not on record"}</TableCell>
                <TableCell>
                  <Stack direction="row" spacing={0.5} useFlexGap sx={{ flexWrap: "wrap" }}>
                    <StatusChip status={m.status} label={m.status_label} />
                    {m.has_pending_request && <StatusChip status="pending" label="Change waiting" tone="info" />}
                  </Stack>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </ResponsiveTable>
      </TableContainer>
      {dialog === "new" && <NewMemberDialog schemeId={schemeId} onClose={() => setDialog(null)} />}
      {dialog === "upload" && <UploadDialog schemeId={schemeId} onClose={() => setDialog(null)} />}
    </Stack>
  );
}
