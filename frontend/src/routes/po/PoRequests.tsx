import { Link as RouterLink, useParams } from "react-router-dom";
import Alert from "@mui/material/Alert";
import Breadcrumbs from "@mui/material/Breadcrumbs";
import Divider from "@mui/material/Divider";
import Link from "@mui/material/Link";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { LoadingState } from "../../components/LoadingState";
import { StatusChip } from "../../components/StatusChip";
import type { PortalRequest } from "../../api/types";
import { usePortalRequest, usePortalRequests } from "../../queries/po";
import { formatDateTime } from "../../utils/date";
import { REQUEST_TEXT } from "./poLabels";

const NEXT: Record<PortalRequest["status"], string> = {
  pending: "A member checker reviews it. You'll get an email when it's decided.",
  approved: "Done — the change is on the member's record.",
  rejected: "Not made. Fix what the checker says and send it again.",
  withdrawn: "Withdrawn — nothing was changed.",
};

function RequestItem({ r }: { r: PortalRequest }) {
  const text = REQUEST_TEXT[r.status];
  return (
    <Stack spacing={0.5} sx={{ py: 1.25 }}>
      <Stack direction={{ xs: "column", sm: "row" }} spacing={1} sx={{ justifyContent: "space-between" }}>
        <Typography sx={{ fontWeight: 600 }}>
          <Link component={RouterLink} to={`/po/requests/${r.id}`} underline="hover" color="inherit">{r.kind_label}</Link>
        </Typography>
        <StatusChip status={r.status} label={text.label} tone={text.tone} sx={{ alignSelf: { xs: "flex-start", sm: "center" } }} />
      </Stack>
      <Typography variant="body2">{r.summary}</Typography>
      <Typography variant="body2" color="text.secondary">
        Sent {formatDateTime(r.created_at)}{r.requested_by ? ` by ${r.requested_by}` : ""}
        {r.decided_at ? ` · decided ${formatDateTime(r.decided_at)}` : ""}
      </Typography>
      {r.comment && <Typography variant="body2" color={r.status === "rejected" ? "error.main" : "text.secondary"}>Checker's note: {r.comment}</Typography>}
    </Stack>
  );
}

export function RequestList({ rows, title, empty }: { rows: PortalRequest[]; title: string; empty: string }) {
  return (
    <Paper sx={{ p: { xs: 2, sm: 3 } }}>
      <Typography variant="subtitle1" component="h2" sx={{ fontWeight: 600, mb: 0.5 }}>{title}</Typography>
      {rows.length === 0 ? (
        <Typography color="text.secondary">{empty}</Typography>
      ) : (
        <Stack divider={<Divider flexItem />}>
          {rows.map((r) => <RequestItem key={r.id} r={r} />)}
        </Stack>
      )}
    </Paper>
  );
}

// Everything sent from the portal for this employer in the last year and what happened (FR-PRT-005).
export function PoRequests({ schemeId }: { schemeId: string }) {
  const query = usePortalRequests(schemeId);
  if (query.isLoading) return <LoadingState />;
  if (query.error) return <Alert severity="error">{query.error.message}</Alert>;
  const rows = query.data ?? [];
  const pending = rows.filter((r) => r.status === "pending").length;
  return (
    <Stack spacing={2}>
      {pending > 0 && <Alert severity="info">{pending} request{pending === 1 ? " is" : "s are"} waiting for approval.</Alert>}
      <RequestList rows={rows} title="Requests" empty="Nothing sent yet. New members, salary changes and exit notices you send show here with their outcome." />
    </Stack>
  );
}

// /po/requests/<id> — where the "request approved / rejected" email links.
export function PoRequestPage() {
  const { requestId } = useParams();
  const query = usePortalRequest(requestId);
  if (query.isLoading) return <LoadingState />;
  if (query.error || !query.data) return <Alert severity="error">{query.error?.message ?? "Request not found"}</Alert>;
  const r = query.data;
  return (
    <Stack spacing={2} sx={{ maxWidth: 760 }}>
      <Breadcrumbs>
        <Link component={RouterLink} to="/po" underline="hover" color="inherit">My schemes</Link>
        <Typography color="text.primary">{r.kind_label}</Typography>
      </Breadcrumbs>
      <Paper sx={{ px: { xs: 2, sm: 3 }, py: 1 }}>
        <RequestItem r={r} />
      </Paper>
      <Alert severity={r.status === "rejected" ? "warning" : r.status === "approved" ? "success" : "info"}>{NEXT[r.status]}</Alert>
      {r.member_id && (
        <Link component={RouterLink} to={`/po/members/${r.member_id}`}>Open the member</Link>
      )}
    </Stack>
  );
}
