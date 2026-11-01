import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
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
import { PageHeader } from "../../../components/PageHeader";
import { ResponsiveTable } from "../../../components/ResponsiveTable";
import { StatusChip } from "../../../components/StatusChip";
import { TableStateRow } from "../../../components/TableStateRow";
import { DiffView } from "../../../components/DiffView";
import { useFeedback } from "../../../components/feedback/FeedbackProvider";
import { useUrlTab } from "../../../hooks/useUrlState";
import { useApproval, useApprovals, useDecideApproval } from "../../../queries/approvals";
import { formatDate, formatDateTime, MONTH_NAMES } from "../../../utils/date";
import { statusLabel } from "../../../utils/labels";
import {
  BANK_PURPOSE_LABELS,
  BILLING_FREQUENCY_LABELS,
  FUND_TYPE_LABELS,
  PRICING_METHOD_LABELS,
  ROLE_LABELS,
  type Approval,
  type BankAccountPurpose,
  type BillingFrequency,
  type FundType,
  type PricingMethod,
  type UserRole,
} from "../../../api/types";
import { dueDayLabel } from "../funds/schemes/schemeLabels";

const VIEWS = ["review", "mine", "history"] as const;
type View = (typeof VIEWS)[number];

const EMPTY: Record<View, string> = {
  review: "Nothing is waiting for your approval. Requests from colleagues appear here.",
  mine: "You have no requests waiting. Changes you propose appear here until someone approves them.",
  history: "No decided requests yet.",
};

type Row = Record<string, unknown>;

// One line per trustee / bank account in a fund change.
function describeRow(key: string, row: Row): string {
  const parts =
    key === "bank_accounts"
      ? [row.bank_name, row.branch_name, row.account_number, row.account_name, BANK_PURPOSE_LABELS[row.purpose as BankAccountPurpose], row.currency]
      : [row.full_name, row.designation, row.email, row.phone, row.appointed_on ? `appointed ${formatDate(row.appointed_on as string)}` : null];
  return parts.filter(Boolean).join(" · ");
}

// Readable values for known payload fields (roles, status, fund type…) in the diff.
function formatValue(key: string, value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (key === "roles" && Array.isArray(value)) return value.map((r) => ROLE_LABELS[r as UserRole] ?? r).join(", ");
  if (key === "fund_type") return FUND_TYPE_LABELS[value as FundType] ?? String(value);
  if (key === "financial_year_end_month") return MONTH_NAMES[Number(value) - 1] ?? String(value);
  if (key === "contribution_day") return dueDayLabel(Number(value));
  if (key === "pricing_method") return PRICING_METHOD_LABELS[value as PricingMethod] ?? String(value);
  if (key === "billing_frequency") return BILLING_FREQUENCY_LABELS[value as BillingFrequency] ?? String(value);
  if ((key.endsWith("_date") || key === "effective_from") && typeof value === "string") return formatDate(value);
  if (key === "status") return statusLabel(String(value));
  if (Array.isArray(value)) {
    if (value.length === 0) return "—";
    if (typeof value[0] === "object") return value.map((row) => describeRow(key, row as Row)).join("\n");
    if (key === "bands") return value.join("\n");
    return value.join(", ");
  }
  return String(value);
}

function ApprovalDialog({ approval, onClose }: { approval: Approval; onClose: () => void }) {
  const decide = useDecideApproval();
  const feedback = useFeedback();
  const [comment, setComment] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function act(action: "approve" | "reject" | "cancel") {
    setError(null);
    if (action === "reject" && !comment.trim()) {
      setError("Give a reason so the person who asked knows what to fix.");
      return;
    }
    try {
      await decide.mutateAsync({ id: approval.id, action, comment });
      feedback.success(action === "approve" ? "Approved — the change has been applied." : action === "reject" ? "Rejected." : "Request withdrawn.");
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
    }
  }

  return (
    <Dialog open onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle>{approval.kind_label}</DialogTitle>
      <DialogContent>
        <Stack spacing={2}>
          <Typography>{approval.summary}</Typography>
          <Typography variant="body2" color="text.secondary">
            Requested by {approval.initiated_by} on {formatDateTime(approval.created_at)}
          </Typography>
          <DiffView after={approval.payload} before={approval.previous} hide={["action", "fund_id"]} format={formatValue} />
          {approval.status !== "pending" && (
            <Alert severity={approval.status === "approved" ? "success" : "info"}>
              {approval.status === "cancelled" ? "Withdrawn by the requester" : `${approval.status === "approved" ? "Approved" : "Rejected"} by ${approval.reviewed_by ?? "—"}`}
              {approval.reviewed_at ? ` on ${formatDateTime(approval.reviewed_at)}` : ""}
              {approval.review_comment ? ` — “${approval.review_comment}”` : ""}
            </Alert>
          )}
          {approval.status === "pending" && !approval.can_review && !approval.can_cancel && (
            <Alert severity="info">Waiting for a checker. You can't decide this one.</Alert>
          )}
          {approval.can_cancel && (
            <Alert severity="info">You made this request, so another person must approve it.</Alert>
          )}
          {approval.can_review && (
            <TextField
              label="Comment"
              helperText="Required when rejecting"
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              multiline
              minRows={2}
              fullWidth
            />
          )}
          {error && <Alert severity="error">{error}</Alert>}
        </Stack>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2, gap: 1, flexWrap: "wrap" }}>
        <Button onClick={onClose}>Close</Button>
        {approval.can_cancel && (
          <Button color="warning" onClick={() => act("cancel")} disabled={decide.isPending}>
            Withdraw request
          </Button>
        )}
        {approval.can_review && (
          <>
            <Button color="error" variant="outlined" onClick={() => act("reject")} disabled={decide.isPending}>
              Reject
            </Button>
            <Button variant="contained" onClick={() => act("approve")} disabled={decide.isPending}>
              {decide.isPending ? "Saving…" : "Approve"}
            </Button>
          </>
        )}
      </DialogActions>
    </Dialog>
  );
}

// Opens /approvals/<id> (the link in "Approval needed" notifications).
function LinkedApproval({ id }: { id: string }) {
  const navigate = useNavigate();
  const query = useApproval(id);
  const close = () => navigate("/approvals", { replace: true });
  if (query.error) {
    return (
      <Alert severity="error" onClose={close} sx={{ mb: 2 }}>
        {query.error.message}
      </Alert>
    );
  }
  return query.data ? <ApprovalDialog approval={query.data} onClose={close} /> : null;
}

// Every maker-checker request in one queue (FR-SEC-002).
export function ApprovalsPage() {
  const linkedId = useParams()["*"] || null;
  const [view, setView] = useUrlTab(VIEWS);
  const query = useApprovals(view === "history" ? "all" : "pending");
  const [open, setOpen] = useState<Approval | null>(null);

  const rows = (query.data ?? []).filter((a) =>
    view === "review" ? a.can_review : view === "mine" ? a.can_cancel : a.status !== "pending",
  );

  return (
    <>
      <PageHeader title="Approvals" description="Changes that need a second person before they take effect." />
      <Tabs value={view} onChange={(_, v: View) => setView(v)} sx={{ mb: 2 }}>
        <Tab value="review" label="To review" />
        <Tab value="mine" label="My requests" />
        <Tab value="history" label="History" />
      </Tabs>
      <TableContainer component={Paper}>
        <ResponsiveTable size="small">
          <TableHead>
            <TableRow>
              <TableCell>Request</TableCell>
              <TableCell>Type</TableCell>
              <TableCell>Requested by</TableCell>
              <TableCell>When</TableCell>
              <TableCell>Status</TableCell>
              <TableCell align="right">Actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            <TableStateRow
              colSpan={6}
              loading={query.isLoading}
              error={query.error?.message ?? null}
              onRetry={() => query.refetch()}
              empty={EMPTY[view]}
              count={rows.length}
            />
            {rows.map((a) => (
              <TableRow key={a.id} hover>
                <TableCell>{a.summary}</TableCell>
                <TableCell>{a.kind_label}</TableCell>
                <TableCell>{a.initiated_by}</TableCell>
                <TableCell sx={{ whiteSpace: "nowrap" }}>{formatDateTime(a.created_at)}</TableCell>
                <TableCell>
                  <StatusChip status={a.status} />
                </TableCell>
                <TableCell align="right">
                  <Button size="small" variant={a.can_review ? "contained" : "text"} onClick={() => setOpen(a)}>
                    {a.can_review ? "Review" : "View"}
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </ResponsiveTable>
      </TableContainer>
      {open && <ApprovalDialog approval={open} onClose={() => setOpen(null)} />}
      {linkedId && !open && <LinkedApproval id={linkedId} />}
    </>
  );
}
