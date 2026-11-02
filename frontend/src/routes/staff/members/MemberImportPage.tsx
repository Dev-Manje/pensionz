import { useState, type ChangeEvent } from "react";
import { Link as RouterLink } from "react-router-dom";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Breadcrumbs from "@mui/material/Breadcrumbs";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
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
import UploadFileIcon from "@mui/icons-material/UploadFileOutlined";
import DownloadIcon from "@mui/icons-material/DownloadOutlined";
import PrintIcon from "@mui/icons-material/PrintOutlined";
import { useQueryClient } from "@tanstack/react-query";
import { PageHeader } from "../../../components/PageHeader";
import { ResponsiveTable } from "../../../components/ResponsiveTable";
import { StatusChip } from "../../../components/StatusChip";
import { TableStateRow } from "../../../components/TableStateRow";
import { useFeedback } from "../../../components/feedback/FeedbackProvider";
import { useAuth } from "../../../auth/AuthContext";
import { useUrlParam } from "../../../hooks/useUrlState";
import { useFunds } from "../../../queries/funds";
import { useSchemes } from "../../../queries/schemes";
import { useImport, useImports, useMemberProposal } from "../../../queries/members";
import { cancelImport, downloadImportErrors, downloadImportTemplate, openApplicationForm, submitImport, uploadImport } from "../../../api/members";
import type { MemberImport } from "../../../api/types";
import { formatDateTime } from "../../../utils/date";
import { NO_EMPLOYER_FUNDS } from "./memberSchema";

function Results({ batch }: { batch: MemberImport }) {
  const feedback = useFeedback();
  const queryClient = useQueryClient();
  const [onlyProblems, setOnlyProblems] = useState(batch.valid_rows < batch.total_rows);
  const submit = useMemberProposal(() => submitImport(batch.id));
  const withdraw = useMemberProposal(() => cancelImport(batch.id));
  const errors = batch.total_rows - batch.valid_rows;
  const warned = batch.rows.filter((r) => !r.errors.length && r.warnings.length).length;
  const rows = onlyProblems ? batch.rows.filter((r) => r.errors.length || r.warnings.length) : batch.rows;
  const run = async (fn: () => Promise<unknown>, done: string) => {
    try {
      await fn();
      feedback.success(done);
      queryClient.invalidateQueries({ queryKey: ["members", "import", batch.id] });
    } catch (e) {
      feedback.error(e instanceof Error ? e.message : "Something went wrong.");
    }
  };

  return (
    <Paper sx={{ p: { xs: 2, sm: 3 } }}>
      <Stack direction={{ xs: "column", md: "row" }} spacing={2} sx={{ justifyContent: "space-between", alignItems: { md: "flex-start" }, mb: 2 }}>
        <Box>
          <Typography variant="subtitle1" component="h2" sx={{ fontWeight: 600 }}>
            {batch.filename}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {batch.employer} · uploaded {formatDateTime(batch.created_at)} by {batch.uploaded_by}
          </Typography>
          <Stack direction="row" spacing={1} useFlexGap sx={{ mt: 1, flexWrap: "wrap" }}>
            <StatusChip status={batch.status} />
            <Chip size="small" label={`${batch.total_rows} rows`} />
            <Chip size="small" color="success" variant="outlined" label={`${batch.valid_rows} ready`} />
            {errors > 0 && <Chip size="small" color="error" variant="outlined" label={`${errors} with errors`} />}
            {warned > 0 && <Chip size="small" color="warning" variant="outlined" label={`${warned} possible duplicate${warned === 1 ? "" : "s"}`} />}
            {batch.status === "imported" && <Chip size="small" color="success" label={`${batch.imported_rows} imported`} />}
          </Stack>
        </Box>
        <Stack direction={{ xs: "column", sm: "row" }} spacing={1} useFlexGap sx={{ flexWrap: "wrap" }}>
          {errors > 0 && (
            <Button startIcon={<DownloadIcon />} variant="outlined" onClick={() => downloadImportErrors(batch.id).catch((e) => feedback.error(e.message))}>
              Download rows with errors
            </Button>
          )}
          {batch.status === "validated" && (
            <Button color="inherit" onClick={() => run(() => withdraw.mutateAsync(undefined), "Upload withdrawn.")} disabled={withdraw.isPending}>
              Withdraw
            </Button>
          )}
          {batch.can_submit && (
            <Button variant="contained" onClick={() => run(() => submit.mutateAsync(undefined), `${batch.valid_rows} member${batch.valid_rows === 1 ? "" : "s"} sent for approval.`)} disabled={submit.isPending}>
              {submit.isPending ? "Sending…" : `Submit ${batch.valid_rows} member${batch.valid_rows === 1 ? "" : "s"} for approval`}
            </Button>
          )}
          {batch.approval_request_id && (
            <Button component={RouterLink} to={`/approvals/${batch.approval_request_id}`} variant="outlined">
              View approval
            </Button>
          )}
        </Stack>
      </Stack>
      {batch.status === "validated" && errors > 0 && batch.valid_rows > 0 && (
        <Alert severity="info" sx={{ mb: 2 }}>
          Only the {batch.valid_rows} ready rows are submitted. Fix the others in the error file (it has the reason on each row) and upload it as a new file.
        </Alert>
      )}
      {batch.status === "validated" && batch.valid_rows === 0 && (
        <Alert severity="error" sx={{ mb: 2 }}>No rows can be imported. Download the rows with errors, fix them and upload again.</Alert>
      )}
      <FormControlLabel control={<Switch checked={onlyProblems} onChange={(e) => setOnlyProblems(e.target.checked)} />} label="Only rows with problems" sx={{ mb: 1 }} />
      <TableContainer>
        <ResponsiveTable size="small">
          <TableHead>
            <TableRow>
              <TableCell>Row</TableCell>
              <TableCell>Member</TableCell>
              <TableCell>Category</TableCell>
              <TableCell>Result</TableCell>
              <TableCell>Problems</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            <TableStateRow colSpan={5} empty="No rows with problems." count={rows.length} />
            {rows.map((r) => (
              <TableRow key={r.row}>
                <TableCell sx={{ fontVariantNumeric: "tabular-nums" }}>{r.row}</TableCell>
                <TableCell sx={{ fontWeight: 500 }}>
                  {r.member_id ? (
                    <Link component={RouterLink} to={`/members/${r.member_id}`}>
                      {r.name}
                    </Link>
                  ) : (
                    r.name
                  )}
                </TableCell>
                <TableCell>{r.raw.category_code ?? "—"}</TableCell>
                <TableCell>
                  {r.errors.length ? (
                    <Chip size="small" color="error" label="Error" />
                  ) : r.member_id ? (
                    <Chip size="small" color="success" label="Imported" />
                  ) : r.warnings.length ? (
                    <Chip size="small" color="warning" label="Check" />
                  ) : (
                    <Chip size="small" color="success" variant="outlined" label="Ready" />
                  )}
                </TableCell>
                <TableCell>
                  {[...r.errors, ...r.warnings].length ? (
                    <Box component="ul" sx={{ m: 0, pl: 2 }}>
                      {r.errors.map((e) => (
                        <li key={e}>{e}</li>
                      ))}
                      {r.warnings.map((w) => (
                        <Typography component="li" key={w} variant="body2" color="warning.dark">
                          Possible duplicate — {w}
                        </Typography>
                      ))}
                    </Box>
                  ) : (
                    "—"
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </ResponsiveTable>
      </TableContainer>
    </Paper>
  );
}

// Members → Bulk upload (FR-MEM-006) and the printable application form (FR-MEM-007).
export function MemberImportPage() {
  const { user } = useAuth();
  const feedback = useFeedback();
  const queryClient = useQueryClient();
  const canUpload = user?.roles.includes("member_admin") ?? false;
  const funds = useFunds();
  const [fundId, setFundId] = useUrlParam("fund");
  const [schemeId, setSchemeId] = useUrlParam("employer");
  const [uploadId, setUploadId] = useUrlParam("upload");
  const schemes = useSchemes(fundId ?? "");
  const batch = useImport(uploadId);
  const recent = useImports(fundId);
  const [busy, setBusy] = useState(false);
  const employerFunds = (funds.data ?? []).filter((f) => !NO_EMPLOYER_FUNDS.includes(f.fund_type));

  async function onFile(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file || !schemeId) return;
    setBusy(true);
    try {
      const result = await uploadImport(schemeId, file);
      queryClient.setQueryData(["members", "import", result.id], result);
      queryClient.invalidateQueries({ queryKey: ["members", "imports"] });
      setUploadId(result.id);
      feedback.success(`Checked ${result.total_rows} rows: ${result.valid_rows} ready.`);
    } catch (err) {
      feedback.error(err instanceof Error ? err.message : "Couldn't read the file.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Breadcrumbs sx={{ mb: 1 }}>
        <Link component={RouterLink} to="/members" underline="hover" color="inherit">
          Members
        </Link>
        <Typography color="text.primary">Bulk upload</Typography>
      </Breadcrumbs>
      <PageHeader
        title="Bulk upload members"
        description="Download the employer's template, fill one row per member, upload it to check every row, then send the ready rows to a member checker. Nothing is created until they approve."
      />
      <Stack spacing={2}>
        <Paper sx={{ p: { xs: 2, sm: 3 } }}>
          <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "1fr 1fr" }, gap: 2, mb: 2 }}>
            <TextField select label="Fund" value={fundId ?? ""} onChange={(e) => { setFundId(e.target.value || null); setSchemeId(null); }} fullWidth>
              {employerFunds.map((f) => (
                <MenuItem key={f.id} value={f.id}>
                  {f.code} — {f.name}
                </MenuItem>
              ))}
            </TextField>
            <TextField select label="Employer" value={schemeId ?? ""} onChange={(e) => setSchemeId(e.target.value || null)} disabled={!fundId} fullWidth helperText={fundId ? undefined : "Choose the fund first."}>
              {(schemes.data ?? []).filter((s) => s.status === "active").map((s) => (
                <MenuItem key={s.id} value={s.id}>
                  {s.code} — {s.name}
                </MenuItem>
              ))}
            </TextField>
          </Box>
          <Stack direction={{ xs: "column", sm: "row" }} spacing={1} useFlexGap sx={{ flexWrap: "wrap" }}>
            <Button startIcon={<DownloadIcon />} variant="outlined" disabled={!schemeId} onClick={() => downloadImportTemplate(schemeId!).catch((e) => feedback.error(e.message))}>
              Download template
            </Button>
            <Button startIcon={<PrintIcon />} variant="outlined" onClick={() => openApplicationForm(schemeId).catch((e) => feedback.error(e.message))}>
              Printable application form
            </Button>
            {canUpload && (
              <Button startIcon={<UploadFileIcon />} variant="contained" component="label" disabled={!schemeId || busy}>
                {busy ? "Checking…" : "Upload filled template"}
                <input hidden type="file" accept=".xlsx,.csv" onChange={onFile} />
              </Button>
            )}
          </Stack>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 1.5 }}>
            Excel (.xlsx) or CSV with the template's headings, up to 2,000 members and 5 MB. The application form is for members who join on paper — key it in
            with “Add member”.
          </Typography>
        </Paper>

        {uploadId && batch.isLoading && <Typography color="text.secondary">Loading the upload…</Typography>}
        {batch.error && <Alert severity="error">{batch.error.message}</Alert>}
        {batch.data && <Results key={batch.data.id} batch={batch.data} />}

        <Box>
          <Typography variant="subtitle1" component="h2" sx={{ fontWeight: 600, mb: 1 }}>
            Recent uploads
          </Typography>
          <TableContainer component={Paper}>
            <ResponsiveTable size="small">
              <TableHead>
                <TableRow>
                  <TableCell>When</TableCell>
                  <TableCell>File</TableCell>
                  <TableCell>Employer</TableCell>
                  <TableCell align="right">Rows</TableCell>
                  <TableCell align="right">Ready</TableCell>
                  <TableCell align="right">Imported</TableCell>
                  <TableCell>Status</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                <TableStateRow colSpan={7} loading={recent.isLoading} error={recent.error?.message ?? null} empty="No uploads yet." count={recent.data?.length ?? 0} />
                {(recent.data ?? []).map((b) => (
                  <TableRow key={b.id} hover selected={b.id === uploadId}>
                    <TableCell sx={{ whiteSpace: "nowrap" }}>{formatDateTime(b.created_at)}</TableCell>
                    <TableCell>
                      <Link component="button" onClick={() => setUploadId(b.id)} underline="hover">
                        {b.filename}
                      </Link>
                    </TableCell>
                    <TableCell>{b.employer}</TableCell>
                    <TableCell align="right">{b.total_rows}</TableCell>
                    <TableCell align="right">{b.valid_rows}</TableCell>
                    <TableCell align="right">{b.imported_rows}</TableCell>
                    <TableCell>
                      <StatusChip status={b.status} />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </ResponsiveTable>
          </TableContainer>
        </Box>
      </Stack>
    </>
  );
}
