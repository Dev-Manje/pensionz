import { useState } from "react";
import { Link as RouterLink, useNavigate, useParams } from "react-router-dom";
import Alert from "@mui/material/Alert";
import Breadcrumbs from "@mui/material/Breadcrumbs";
import Button from "@mui/material/Button";
import Link from "@mui/material/Link";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";
import { LoadingState } from "../../components/LoadingState";
import { ResponsiveTable } from "../../components/ResponsiveTable";
import { useFeedback } from "../../components/feedback/FeedbackProvider";
import { downloadImportErrors, submitPortalImport } from "../../api/po";
import { usePortalImport, usePortalMemberRequest } from "../../queries/po";
import { schemePath } from "./PoSchemePage";

// A checked bulk upload of new members: every row's problems, the errors spreadsheet
// to fix and upload again, and sending the valid rows for approval.
export function PoImportPage() {
  const { importId } = useParams();
  const navigate = useNavigate();
  const feedback = useFeedback();
  const query = usePortalImport(importId);
  const send = usePortalMemberRequest((id: string) => submitPortalImport(id));
  const [problemsOnly, setProblemsOnly] = useState(true);
  if (query.isLoading) return <LoadingState />;
  if (query.error || !query.data) return <Alert severity="error">{query.error?.message ?? "Upload not found"}</Alert>;
  const b = query.data;
  const bad = b.total_rows - b.valid_rows;
  const rows = problemsOnly ? b.rows.filter((r) => r.errors.length || r.warnings.length) : b.rows;
  const back = b.scheme_id ? schemePath(b.scheme_id, "members") : "/po";

  async function go() {
    try {
      await send.mutateAsync(b.id);
      feedback.success(`${b.valid_rows} new member${b.valid_rows === 1 ? "" : "s"} sent for approval.`);
      navigate(b.scheme_id ? schemePath(b.scheme_id, "requests") : "/po");
    } catch (e) {
      feedback.error(e instanceof Error ? e.message : "Couldn't send.");
    }
  }

  return (
    <Stack spacing={2} sx={{ maxWidth: 1240 }}>
      <Breadcrumbs>
        <Link component={RouterLink} to="/po" underline="hover" color="inherit">My schemes</Link>
        <Link component={RouterLink} to={back} underline="hover" color="inherit">{b.employer ?? "Members"}</Link>
        <Typography color="text.primary">{b.filename}</Typography>
      </Breadcrumbs>
      <Typography variant="h1">New members from {b.filename}</Typography>
      {b.status === "validated" ? (
        <Alert severity={bad ? "warning" : "success"}>
          {b.valid_rows} of {b.total_rows} row{b.total_rows === 1 ? "" : "s"} can be added.
          {bad > 0 && ` ${bad} need${bad === 1 ? "s" : ""} fixing — download them, fix and upload again; send the good rows now or after.`}
        </Alert>
      ) : (
        <Alert severity="info">This upload has been sent ({b.status.replace("_", " ")}). See Requests for the outcome.</Alert>
      )}
      <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
        {b.can_submit && (
          <Button variant="contained" onClick={go} disabled={send.isPending}>
            {send.isPending ? "Sending…" : `Send ${b.valid_rows} for approval`}
          </Button>
        )}
        {bad > 0 && <Button variant="outlined" onClick={() => downloadImportErrors(b.id).catch((e) => feedback.error(e.message))}>Download the rows to fix</Button>}
        <Button onClick={() => setProblemsOnly(!problemsOnly)}>{problemsOnly ? "Show every row" : "Only rows with problems"}</Button>
      </Stack>
      <TableContainer component={Paper}>
        <ResponsiveTable size="small">
          <TableHead>
            <TableRow>
              <TableCell>Row</TableCell>
              <TableCell>Name</TableCell>
              <TableCell>Checks</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.length === 0 && (
              <TableRow><TableCell colSpan={3}><Typography color="text.secondary">No problems — every row checks out.</Typography></TableCell></TableRow>
            )}
            {rows.map((r) => (
              <TableRow key={r.row} sx={r.errors.length ? { bgcolor: "rgba(211, 47, 47, 0.04)" } : undefined}>
                <TableCell>{r.row}</TableCell>
                <TableCell sx={{ fontWeight: 600 }}>{r.name}</TableCell>
                <TableCell>
                  {r.errors.map((m) => <Typography key={m} variant="body2" color="error.main">{m}</Typography>)}
                  {r.warnings.map((m) => <Typography key={m} variant="body2" color="warning.dark">{m}</Typography>)}
                  {!r.errors.length && !r.warnings.length && <Typography variant="body2" color="success.main">OK</Typography>}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </ResponsiveTable>
      </TableContainer>
    </Stack>
  );
}
