import { useRef, useState } from "react";
import { Link as RouterLink, useNavigate, useParams } from "react-router-dom";
import Alert from "@mui/material/Alert";
import Breadcrumbs from "@mui/material/Breadcrumbs";
import Button from "@mui/material/Button";
import Link from "@mui/material/Link";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { BRAND } from "../../brand";
import { LoadingState } from "../../components/LoadingState";
import { StatusChip } from "../../components/StatusChip";
import { useFeedback } from "../../components/feedback/FeedbackProvider";
import {
  cancelPortalSchedule, downloadPortalTemplate, fillPortalSchedule, removePortalLine, savePortalLine, submitPortalSchedule, uploadPortalSchedule,
} from "../../api/po";
import type { ScheduleLine, ScheduleLineInput } from "../../api/schedules";
import { useMySchemes, usePortalSchedule, usePortalScheduleChange } from "../../queries/po";
import { formatDateTime, formatPeriod } from "../../utils/date";
import { formatMoney } from "../../utils/format";
import { LineDialog, ScheduleLines, Totals } from "../staff/contributions/ScheduleParts";
import { SCHEDULE_TEXT } from "./poLabels";
import { schemePath } from "./PoSchemePage";
import { RemitCodeDialog } from "./RemitCodeDialog";

type Change =
  | { kind: "upload"; file: File }
  | { kind: "fill" }
  | { kind: "save"; lineId: string | null; body: ScheduleLineInput }
  | { kind: "remove"; lineId: string }
  | { kind: "submit"; code: string }
  | { kind: "cancel" };

// One contribution schedule in the portal: built and checked row by row while it's
// a draft, then sent (with a one-time code) to the administrator for allocation.
export function PoSchedulePage() {
  const { scheduleId = "" } = useParams();
  const navigate = useNavigate();
  const feedback = useFeedback();
  const query = usePortalSchedule(scheduleId);
  const schemes = useMySchemes();
  const fileInput = useRef<HTMLInputElement>(null);
  const [editing, setEditing] = useState<ScheduleLine | "new" | null>(null);
  const [sending, setSending] = useState(false);
  const change = usePortalScheduleChange(scheduleId, (a: Change) => {
    switch (a.kind) {
      case "upload":
        return uploadPortalSchedule(scheduleId, a.file);
      case "fill":
        return fillPortalSchedule(scheduleId);
      case "save":
        return savePortalLine(scheduleId, a.lineId, a.body);
      case "remove":
        return removePortalLine(scheduleId, a.lineId);
      case "submit":
        return submitPortalSchedule(scheduleId, a.code);
      case "cancel":
        return cancelPortalSchedule(scheduleId);
    }
  });

  if (query.isLoading) return <LoadingState />;
  if (query.error || !query.data) {
    return <Alert severity="error" action={<Button color="inherit" onClick={() => query.refetch()}>Try again</Button>}>{query.error?.message ?? "Couldn't load the schedule."}</Alert>;
  }
  const s = query.data;
  const scheme = schemes.data?.find((x) => x.id === s.scheme_id);
  const back = scheme ? schemePath(scheme.id) : "/po";
  const status = SCHEDULE_TEXT[s.status];

  async function run(a: Change, done: string) {
    try {
      await change.mutateAsync(a);
      feedback.success(done);
    } catch (e) {
      feedback.error(e instanceof Error ? e.message : "That didn't work.");
    }
  }

  return (
    <Stack spacing={2} sx={{ maxWidth: 1240 }}>
      <Breadcrumbs>
        <Link component={RouterLink} to="/po" underline="hover" color="inherit">My schemes</Link>
        {scheme && <Link component={RouterLink} to={back} underline="hover" color="inherit">{scheme.name}</Link>}
        <Typography color="text.primary">{s.reference}</Typography>
      </Breadcrumbs>
      <Stack direction={{ xs: "column", md: "row" }} spacing={2} sx={{ justifyContent: "space-between", alignItems: { md: "flex-start" } }}>
        <div>
          <Typography variant="h1">
            {formatPeriod(s.contribution_month)} schedule{s.supplementary ? " (supplementary)" : ""}
          </Typography>
          <Stack direction="row" spacing={1} sx={{ alignItems: "center", mt: 0.5, flexWrap: "wrap" }} useFlexGap>
            <Typography color="text.secondary">
              {s.reference}
              {s.filename ? ` · from ${s.filename}` : ""}
            </Typography>
            <StatusChip status={s.status} label={status.label} tone={status.tone} />
          </Stack>
        </div>
        {s.can_edit && (
          <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: "wrap" }}>
            <Button variant="contained" disabled={!!s.error_count || !s.line_count || change.isPending} onClick={() => setSending(true)}>
              Send schedule
            </Button>
            <Button onClick={() => setEditing("new")}>Add member</Button>
            <Button onClick={() => fileInput.current?.click()}>Upload spreadsheet</Button>
            <Button onClick={() => downloadPortalTemplate(s.scheme_id, s.contribution_month).catch((e) => feedback.error(e.message))}>
              Download spreadsheet
            </Button>
            <input ref={fileInput} type="file" hidden accept=".xlsx,.csv"
              onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) run({ kind: "upload", file: f }, "Spreadsheet checked — the rows were replaced."); }} />
          </Stack>
        )}
      </Stack>

      {!s.can_edit && s.status === "draft" && (
        <Alert severity="info">This schedule is being prepared by {BRAND.administrator}. You'll see it here once it's sent.</Alert>
      )}
      {s.can_edit && s.error_count > 0 && (
        <Alert severity="error">
          {s.error_count} row{s.error_count === 1 ? " has" : "s have"} errors — fix or remove {s.error_count === 1 ? "it" : "them"} before sending. Each row says what's wrong.
        </Alert>
      )}
      {s.can_edit && !s.error_count && s.warning_count > 0 && (
        <Alert severity="warning">
          {s.warning_count} row{s.warning_count === 1 ? " has" : "s have"} warnings — check them; they don't stop the schedule.
        </Alert>
      )}
      {s.can_edit && !s.error_count && !s.warning_count && s.line_count > 0 && (
        <Alert severity="success">Every row checks out. Send the schedule when it matches what you are paying.</Alert>
      )}
      {s.status === "ready" && (
        <Alert severity="info">
          Sent {s.submitted_at ? formatDateTime(s.submitted_at) : ""}. Next, {BRAND.administrator} matches it to your payment and credits the members —
          usually within 5 working days.
        </Alert>
      )}
      {s.status === "allocated" && <Alert severity="success">Done — the contributions have been credited to the members.</Alert>}

      <Totals s={s} />
      <ScheduleLines s={s} editable={s.can_edit} memberLinks={false} onEdit={(l) => setEditing(l)}
        onRemove={(l) => run({ kind: "remove", lineId: l.id }, `Row ${l.row_no} removed.`)} />
      {s.can_edit && (
        <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: "wrap", pb: 2 }}>
          <Button onClick={() => run({ kind: "fill" }, "Members missing from the schedule were added at their expected amounts.")}>
            Add missing members
          </Button>
          <Button color="error" onClick={async () => {
            if (!window.confirm("Throw this draft away? Nothing has been sent.")) return;
            try {
              await change.mutateAsync({ kind: "cancel" });
              feedback.success("Draft thrown away.");
              navigate(back);
            } catch (e) {
              feedback.error(e instanceof Error ? e.message : "That didn't work.");
            }
          }}>
            Throw away draft
          </Button>
        </Stack>
      )}
      {editing && (
        <LineDialog line={editing === "new" ? null : editing} onClose={() => setEditing(null)}
          onSave={(lineId, body) => change.mutateAsync({ kind: "save", lineId, body })} />
      )}
      {sending && (
        <RemitCodeDialog title="Send the schedule" confirmLabel="Send schedule" onClose={() => setSending(false)}
          onConfirm={async (code) => {
            await change.mutateAsync({ kind: "submit", code });
            setSending(false);
            feedback.success(`Schedule ${s.reference} sent for processing.`);
          }}>
          <Typography>
            {formatPeriod(s.contribution_month)}: {s.line_count} member{s.line_count === 1 ? "" : "s"}, {formatMoney(s.total)}. Once sent it can't be changed here.
          </Typography>
        </RemitCodeDialog>
      )}
    </Stack>
  );
}
