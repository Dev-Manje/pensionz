import { useState } from "react";
import { Link as RouterLink } from "react-router-dom";
import Accordion from "@mui/material/Accordion";
import AccordionDetails from "@mui/material/AccordionDetails";
import AccordionSummary from "@mui/material/AccordionSummary";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import MenuItem from "@mui/material/MenuItem";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import useMediaQuery from "@mui/material/useMediaQuery";
import { useTheme } from "@mui/material/styles";
import AddIcon from "@mui/icons-material/Add";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import { LoadingState } from "../../../components/LoadingState";
import { ResponsiveTable } from "../../../components/ResponsiveTable";
import { TableStateRow } from "../../../components/TableStateRow";
import { RepeatRow } from "../../../components/form/FormLayout";
import { useFeedback } from "../../../components/feedback/FeedbackProvider";
import { useListRows } from "../../../queries/setup";
import { useMemberProposal, useNominations } from "../../../queries/members";
import { proposeNomination } from "../../../api/members";
import type { BeneficiaryInput, Member, Nomination } from "../../../api/types";
import { formatDate, todayIso } from "../../../utils/date";

const EMPTY: BeneficiaryInput = {
  full_name: "", relationship: "", date_of_birth: null, id_number: null, phone: null, email: null, address: null, share_pct: "",
  guardian_name: null, guardian_relationship: null, guardian_phone: null, guardian_id_number: null,
};

function isMinor(dob: string | null) {
  if (!dob) return false;
  const born = new Date(dob);
  const adult = new Date(born.getFullYear() + 18, born.getMonth(), born.getDate());
  return adult > new Date();
}

function total(rows: { share_pct: string }[]) {
  return rows.reduce((sum, r) => sum + (Number(r.share_pct) || 0), 0);
}

function NominationTable({ n, sensitive }: { n: Nomination; sensitive: boolean }) {
  return (
    <TableContainer component={Paper} variant="outlined">
      <ResponsiveTable size="small">
        <TableHead>
          <TableRow>
            <TableCell>Beneficiary</TableCell>
            <TableCell>Relationship</TableCell>
            <TableCell>Born</TableCell>
            <TableCell>ID number</TableCell>
            {sensitive && <TableCell>Contact</TableCell>}
            <TableCell>Guardian</TableCell>
            <TableCell align="right">Share</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {n.beneficiaries.map((b) => (
            <TableRow key={b.full_name}>
              <TableCell sx={{ fontWeight: 500 }}>
                {b.full_name} {b.is_minor && <Chip size="small" label="Minor" color="info" sx={{ ml: 0.5 }} />}
              </TableCell>
              <TableCell>{b.relationship_label ?? b.relationship}</TableCell>
              <TableCell sx={{ whiteSpace: "nowrap" }}>{b.date_of_birth ? formatDate(b.date_of_birth) : "—"}</TableCell>
              <TableCell>{b.id_number ?? "—"}</TableCell>
              {sensitive && <TableCell>{[b.phone, b.email].filter(Boolean).join(" · ") || "—"}</TableCell>}
              <TableCell>{b.guardian_name ? `${b.guardian_name}${b.guardian_relationship_label ? ` (${b.guardian_relationship_label})` : ""}${b.guardian_phone ? `, ${b.guardian_phone}` : ""}` : "—"}</TableCell>
              <TableCell align="right" sx={{ fontVariantNumeric: "tabular-nums", fontWeight: 600 }}>{Number(b.share_pct).toFixed(2)}%</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </ResponsiveTable>
    </TableContainer>
  );
}

function NominationDialog({ member, current, onClose }: { member: Member; current: Nomination | null; onClose: () => void }) {
  const feedback = useFeedback();
  const narrow = useMediaQuery(useTheme().breakpoints.down("sm"));
  const relationships = useListRows("relationships");
  const options = (relationships.data ?? []).filter((r) => r.active !== false);
  const submit = useMemberProposal((body: Parameters<typeof proposeNomination>[1]) => proposeNomination(member.id, body));
  const [signed, setSigned] = useState(todayIso());
  const [note, setNote] = useState("");
  const [rows, setRows] = useState<BeneficiaryInput[]>(() =>
    current ? current.beneficiaries.map((b) => ({ ...EMPTY, ...Object.fromEntries(Object.keys(EMPTY).map((k) => [k, (b as unknown as Record<string, unknown>)[k] ?? null])), share_pct: String(Number(b.share_pct)) }) as BeneficiaryInput) : [{ ...EMPTY, share_pct: "100" }],
  );
  const [error, setError] = useState<string | null>(null);
  const sum = total(rows);
  const set = (i: number, key: keyof BeneficiaryInput, value: string | null) => setRows(rows.map((r, j) => (j === i ? { ...r, [key]: value } : r)));
  const text = (i: number, key: keyof BeneficiaryInput, label: string, extra: Record<string, unknown> = {}) => (
    <TextField label={label} value={rows[i][key] ?? ""} onChange={(e) => set(i, key, e.target.value || null)} fullWidth {...extra} />
  );
  const relation = (i: number, key: "relationship" | "guardian_relationship", label: string, required = true) => (
    <TextField select label={label} required={required} value={rows[i][key] ?? ""} onChange={(e) => set(i, key, e.target.value || null)} fullWidth>
      {options.map((o) => (
        <MenuItem key={o.id} value={String(o.code)}>
          {String(o.name)}
        </MenuItem>
      ))}
    </TextField>
  );

  async function send() {
    setError(null);
    try {
      await submit.mutateAsync({ signed_date: signed, note: note.trim() || null, beneficiaries: rows.map((r) => ({ ...r, share_pct: r.share_pct || "0" })) });
      feedback.success("Nomination sent for approval — it replaces the current one once a member checker approves it.");
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
    }
  }

  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="md" fullScreen={narrow}>
      <DialogTitle>New beneficiary nomination for {String(member.fields.full_name)}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <Typography color="text.secondary">
            Capture the nomination form as the member signed it. It replaces the current nomination, which is kept in the history. The trustees decide who is paid
            on death; the nomination guides them.
          </Typography>
          <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "1fr 2fr" }, gap: 2 }}>
            <TextField label="Signed on" type="date" required value={signed} onChange={(e) => setSigned(e.target.value)} slotProps={{ inputLabel: { shrink: true } }} />
            <TextField label="Note" value={note} onChange={(e) => setNote(e.target.value)} helperText="Optional, e.g. form received by post." />
          </Box>
          {rows.map((r, i) => (
            <RepeatRow key={i} label={`Beneficiary ${i + 1}${r.full_name ? ` — ${r.full_name}` : ""}`} onRemove={() => setRows(rows.filter((_, j) => j !== i))}>
              {text(i, "full_name", "Full name", { required: true })}
              {relation(i, "relationship", "Relationship")}
              {text(i, "share_pct", "Share (%)", { required: true, type: "number", slotProps: { htmlInput: { min: 0.01, max: 100, step: "0.01" } } })}
              {text(i, "date_of_birth", "Date of birth", { type: "date", slotProps: { inputLabel: { shrink: true } }, helperText: isMinor(r.date_of_birth) ? "Under 18 — a guardian is needed." : undefined })}
              {text(i, "id_number", "ID number")}
              {text(i, "phone", "Phone", { type: "tel" })}
              {text(i, "email", "Email", { type: "email" })}
              {text(i, "address", "Address")}
              {isMinor(r.date_of_birth) && (
                <>
                  {text(i, "guardian_name", "Guardian's name", { required: true })}
                  {relation(i, "guardian_relationship", "Guardian's relationship to the child")}
                  {text(i, "guardian_phone", "Guardian's phone", { required: true, type: "tel" })}
                  {text(i, "guardian_id_number", "Guardian's ID number")}
                </>
              )}
            </RepeatRow>
          ))}
          <Stack direction="row" sx={{ justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 1 }}>
            <Button startIcon={<AddIcon />} variant="outlined" onClick={() => setRows([...rows, { ...EMPTY, share_pct: sum < 100 ? String(Math.round((100 - sum) * 100) / 100) : "" }])}>
              Add beneficiary
            </Button>
            <Typography sx={{ fontWeight: 600, color: Math.abs(sum - 100) < 0.005 ? "success.main" : "error.main" }}>
              Shares total {sum.toFixed(2)}%{Math.abs(sum - 100) < 0.005 ? "" : " — must be 100%"}
            </Typography>
          </Stack>
          {error && <Alert severity="error">{error}</Alert>}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" onClick={send} disabled={rows.length === 0 || Math.abs(sum - 100) >= 0.005 || submit.isPending}>
          {submit.isPending ? "Sending…" : "Submit for approval"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

// Beneficiaries tab (FR-MEM-008): the current nomination, earlier versions, and a new nomination.
export function MemberBeneficiariesTab({ member }: { member: Member }) {
  const query = useNominations(member.id);
  const [open, setOpen] = useState(false);
  if (query.isLoading) return <LoadingState />;
  if (query.error || !query.data) return <Alert severity="error">{query.error?.message ?? "Couldn't load the beneficiaries."}</Alert>;
  const { current, history, pending_approval_id, can_edit } = query.data;

  return (
    <Stack spacing={2}>
      {pending_approval_id && (
        <Alert severity="warning" action={<Button color="inherit" size="small" component={RouterLink} to={`/approvals/${pending_approval_id}`}>View request</Button>}>
          A new nomination is waiting for approval.
        </Alert>
      )}
      <Stack direction="row" sx={{ justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 1 }}>
        <Typography color="text.secondary">
          {current ? `Nomination version ${current.version}, signed ${formatDate(current.signed_date)}${current.approved_by ? `, approved by ${current.approved_by}` : ""}.` : "No beneficiaries nominated yet."}
        </Typography>
        {can_edit && !pending_approval_id && (
          <Button variant="contained" onClick={() => setOpen(true)}>
            {current ? "Change nomination" : "Nominate beneficiaries"}
          </Button>
        )}
      </Stack>
      {current ? (
        <NominationTable n={current} sensitive={member.sensitive} />
      ) : (
        <TableContainer component={Paper}>
          <ResponsiveTable size="small">
            <TableBody>
              <TableStateRow colSpan={1} empty="Nominated beneficiaries and their shares appear here once a nomination is approved." count={0} />
            </TableBody>
          </ResponsiveTable>
        </TableContainer>
      )}
      {history.length > 0 && (
        <Box>
          <Typography variant="subtitle1" component="h2" sx={{ fontWeight: 600, mb: 1 }}>
            Earlier nominations
          </Typography>
          {history.map((n) => (
            <Accordion key={n.id} disableGutters>
              <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                Version {n.version} — signed {formatDate(n.signed_date)}, {n.beneficiaries.length} beneficiar{n.beneficiaries.length === 1 ? "y" : "ies"}
              </AccordionSummary>
              <AccordionDetails>
                <NominationTable n={n} sensitive={member.sensitive} />
              </AccordionDetails>
            </Accordion>
          ))}
        </Box>
      )}
      {open && <NominationDialog member={member} current={current} onClose={() => setOpen(false)} />}
    </Stack>
  );
}
