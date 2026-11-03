import { useRef, useState } from "react";
import { Link as RouterLink, useParams } from "react-router-dom";
import Alert from "@mui/material/Alert";
import Breadcrumbs from "@mui/material/Breadcrumbs";
import Button from "@mui/material/Button";
import Link from "@mui/material/Link";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { LoadingState } from "../../../components/LoadingState";
import { StatusChip } from "../../../components/StatusChip";
import { useFeedback } from "../../../components/feedback/FeedbackProvider";
import { useAuth } from "../../../auth/AuthContext";
import { AllocationPanel } from "./AllocationPanel";
import { LineDialog, ScheduleLines, Totals } from "./ScheduleParts";
import { useSchedule, useScheduleChange } from "../../../queries/schedules";
import { downloadScheduleTemplate, type ScheduleLine } from "../../../api/schedules";
import { formatDateTime, formatPeriod } from "../../../utils/date";

export function ScheduleDetailPage() {
  const { scheduleId } = useParams();
  const { user } = useAuth();
  const query = useSchedule(scheduleId);
  const change = useScheduleChange(scheduleId ?? "");
  const feedback = useFeedback();
  const fileInput = useRef<HTMLInputElement>(null);
  const [editing, setEditing] = useState<ScheduleLine | "new" | null>(null);

  if (query.isLoading) return <LoadingState />;
  if (query.error || !query.data) {
    return <Alert severity="error" action={<Button color="inherit" onClick={() => query.refetch()}>Retry</Button>}>{query.error?.message ?? "Couldn't load the schedule."}</Alert>;
  }
  const s = query.data;
  const isMaker = user?.roles.includes("contributions_officer") ?? false;

  async function run(a: Parameters<typeof change.mutateAsync>[0], done: string) {
    try {
      await change.mutateAsync(a);
      feedback.success(done);
    } catch (e) {
      feedback.error(e instanceof Error ? e.message : "That didn't work.");
    }
  }

  return (
    <Stack spacing={2}>
      <Breadcrumbs>
        <Link component={RouterLink} to={`/contributions?fund=${s.fund_id}&tab=schedules`} underline="hover" color="inherit">Contributions</Link>
        <Typography color="text.primary">{s.reference}</Typography>
      </Breadcrumbs>
      <Stack direction={{ xs: "column", md: "row" }} spacing={2} sx={{ justifyContent: "space-between", alignItems: { md: "flex-start" } }}>
        <div>
          <Typography variant="h5" component="h1" sx={{ fontWeight: 600 }}>
            Schedule {s.reference}
          </Typography>
          <Typography color="text.secondary">
            {s.employer} · {formatPeriod(s.contribution_month)}{s.supplementary ? " · supplementary" : ""}
            {s.filename ? ` · from ${s.filename}` : ""}
          </Typography>
          <StatusChip status={s.status} sx={{ mt: 1 }} />
        </div>
        <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: "wrap" }}>
          {s.can_edit && (
            <>
              <Button variant="contained" disabled={!!s.error_count || !s.line_count || change.isPending}
                onClick={() => run({ kind: "action", action: "submit" }, "Schedule handed over for allocation.")}>
                Submit for allocation
              </Button>
              <Button onClick={() => setEditing("new")}>Add member</Button>
              <Button onClick={() => run({ kind: "action", action: "fill-expected" }, "Missing members added at their expected amounts.")}>Add missing members</Button>
              <Button onClick={() => fileInput.current?.click()}>Upload corrected file</Button>
              <Button onClick={() => downloadScheduleTemplate(s.fund_id, s.scheme_id, s.contribution_month)}>Template</Button>
              <input ref={fileInput} type="file" hidden accept=".xlsx,.csv"
                onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) run({ kind: "upload", file: f }, "File checked — the lines were replaced."); }} />
            </>
          )}
          {s.status === "ready" && (
            <Button onClick={() => run({ kind: "action", action: "reopen" }, "Schedule re-opened for changes.")}>Re-open</Button>
          )}
          {(s.can_edit || s.status === "ready") && (
            <Button color="error" onClick={() => run({ kind: "action", action: "cancel" }, "Schedule cancelled.")}>Cancel schedule</Button>
          )}
        </Stack>
      </Stack>

      {s.status === "draft" && s.error_count > 0 && (
        <Alert severity="error">{s.error_count} line{s.error_count === 1 ? " has" : "s have"} errors. Fix or remove them before submitting.</Alert>
      )}
      {s.status === "draft" && !s.error_count && s.warning_count > 0 && (
        <Alert severity="warning">{s.warning_count} line{s.warning_count === 1 ? " has" : "s have"} warnings — check them; they don't stop the schedule.</Alert>
      )}
      {s.status === "ready" && (
        <Alert severity="info">Submitted {s.submitted_at ? formatDateTime(s.submitted_at) : ""}{s.submitted_by ? ` by ${s.submitted_by}` : ""}. Match it to the money received below.</Alert>
      )}

      <Totals s={s} />
      <AllocationPanel schedule={s} canAllocate={isMaker} />

      <ScheduleLines s={s} editable={s.can_edit} memberLinks onEdit={(l) => setEditing(l)}
        onRemove={(l) => run({ kind: "remove", lineId: l.id }, `Row ${l.row_no} removed.`)} />
      {editing && (
        <LineDialog line={editing === "new" ? null : editing} onClose={() => setEditing(null)}
          onSave={(lineId, body) => change.mutateAsync({ kind: "save", lineId, body })} />
      )}
    </Stack>
  );
}
