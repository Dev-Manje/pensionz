import { Link as RouterLink } from "react-router-dom";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Divider from "@mui/material/Divider";
import Link from "@mui/material/Link";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { useAuth } from "../../auth/AuthContext";
import { BRAND } from "../../brand";
import { LoadingState } from "../../components/LoadingState";
import { StatusChip } from "../../components/StatusChip";
import { usePoDashboard } from "../../queries/po";
import { useApplicationFunds, useMyApplications } from "../../queries/employerApplications";
import type { DashboardScheme, PortalActivity } from "../../api/types";
import { formatDate, formatDateTime, formatPeriod } from "../../utils/date";
import { formatMoney } from "../../utils/format";
import { dueDayLabel } from "../staff/funds/schemes/schemeLabels";
import { APPLICATION_STATUS_TEXT, STAGE_TEXT, dueText, isLate } from "./poLabels";
import { schemePath } from "./PoSchemePage";

const SCHEME_STATUS_TEXT: Record<DashboardScheme["status"], string> = {
  active: "Active",
  suspended: "Contributions on hold",
  exited: "Left the fund",
};

const money = { fontVariantNumeric: "tabular-nums", fontWeight: 600 } as const;

function groupByFund(schemes: DashboardScheme[]): [string, DashboardScheme[]][] {
  const groups = new Map<string, DashboardScheme[]>();
  for (const s of schemes) groups.set(s.fund_name, [...(groups.get(s.fund_name) ?? []), s]);
  return [...groups.entries()];
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Box sx={{ flex: 1, minWidth: 0, p: 2, borderRadius: 1, bgcolor: "action.hover" }}>
      <Typography variant="overline" component="h4" color="text.secondary" sx={{ lineHeight: 1.6 }}>
        {title}
      </Typography>
      <Stack spacing={0.75} sx={{ mt: 0.5 }}>
        {children}
      </Stack>
    </Box>
  );
}

function Remittance({ scheme }: { scheme: DashboardScheme }) {
  const c = scheme.current;
  const stage = STAGE_TEXT[c.stage];
  const late = isLate(c.stage, c.days_to_due);
  return (
    <Panel title={`${formatPeriod(c.month)} contributions`}>
      <Box>
        <StatusChip status={c.stage} label={stage.label} tone={stage.tone} />
      </Box>
      <Typography variant="body2" color={late ? "error.main" : "text.secondary"} sx={{ fontWeight: late ? 600 : 400 }}>
        Due by {formatDate(c.due_date)}
        {c.stage !== "allocated" && ` — ${dueText(c.days_to_due)}`}
      </Typography>
      {c.schedule_reference && (
        <Typography variant="body2">
          Schedule{" "}
          <Link component={RouterLink} to={`/po/schedules/${c.schedule_id}`} underline="hover">
            {c.schedule_reference}
          </Link>
          : {c.member_lines} member{c.member_lines === 1 ? "" : "s"},{" "}
          <Box component="span" sx={money}>
            {formatMoney(c.schedule_total)}
          </Box>
        </Typography>
      )}
      {Number(c.confirmed_amount) > 0 && (
        <Typography variant="body2">
          Received:{" "}
          <Box component="span" sx={money}>
            {formatMoney(c.confirmed_amount)}
          </Box>
        </Typography>
      )}
      {Number(c.notified_amount) > 0 && (
        <Typography variant="body2">
          Payment noted, awaiting confirmation:{" "}
          <Box component="span" sx={money}>
            {formatMoney(c.notified_amount)}
          </Box>
        </Typography>
      )}
      <Typography variant="body2" color="text.secondary">
        {stage.next}
      </Typography>
    </Panel>
  );
}

function Arrears({ scheme }: { scheme: DashboardScheme }) {
  const a = scheme.arrears;
  const owing = Number(a.total) > 0;
  return (
    <Panel title="Arrears">
      {owing ? (
        <>
          <Typography variant="h3" component="p" color="error.main" sx={{ ...money, fontSize: "1.25rem" }}>
            {formatMoney(a.total)}
          </Typography>
          <Typography variant="body2">
            {a.overdue_months} month{a.overdue_months === 1 ? "" : "s"} overdue, oldest {formatPeriod(a.oldest_month)} ({a.oldest_days_overdue}{" "}
            days)
          </Typography>
          {a.interest !== null && Number(a.interest) > 0 && (
            <Typography variant="body2">
              Late-payment interest so far:{" "}
              <Box component="span" sx={money}>
                {formatMoney(a.interest)}
              </Box>
            </Typography>
          )}
          <Typography variant="body2" color="text.secondary">
            Worked out from members' salaries on record and the schedules credited so far.
          </Typography>
        </>
      ) : (
        <>
          <Typography variant="h3" component="p" sx={{ ...money, fontSize: "1.25rem" }}>
            {formatMoney(0)}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Nothing overdue.
          </Typography>
        </>
      )}
    </Panel>
  );
}

function SchemeCard({ scheme }: { scheme: DashboardScheme }) {
  return (
    <Paper variant="outlined" sx={{ p: 2 }}>
      <Stack direction={{ xs: "column", sm: "row" }} spacing={1} sx={{ justifyContent: "space-between", alignItems: { sm: "center" }, mb: 1.5 }}>
        <div>
          <Typography variant="subtitle1" component="h3" sx={{ fontWeight: 600 }}>
            {scheme.name}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Employer code {scheme.code} · {scheme.member_count} member{scheme.member_count === 1 ? "" : "s"} · due by the{" "}
            {dueDayLabel(scheme.contribution_day)}
          </Typography>
        </div>
        <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
          {scheme.status !== "active" && <StatusChip status={scheme.status} label={SCHEME_STATUS_TEXT[scheme.status]} />}
          <Button component={RouterLink} to={schemePath(scheme.id)} variant="outlined" size="small">
            Open
          </Button>
        </Stack>
      </Stack>
      <Stack direction={{ xs: "column", md: "row" }} spacing={1.5}>
        <Remittance scheme={scheme} />
        <Arrears scheme={scheme} />
      </Stack>
    </Paper>
  );
}

function Activity({ items, many }: { items: PortalActivity[]; many: boolean }) {
  return (
    <Paper sx={{ p: { xs: 2.5, sm: 3 } }}>
      <Typography variant="h2" sx={{ mb: 1 }}>
        Recent activity
      </Typography>
      {items.length === 0 ? (
        <Typography color="text.secondary">
          Nothing in the last 90 days. Payment notices, schedules you send and contributions credited to members will show here.
        </Typography>
      ) : (
        <Stack divider={<Divider flexItem />} component="ul" sx={{ listStyle: "none", m: 0, p: 0 }}>
          {items.map((a, i) => (
            <Box component="li" key={`${a.kind}-${a.at}-${i}`} sx={{ py: 1.25 }}>
              <Stack direction={{ xs: "column", sm: "row" }} sx={{ justifyContent: "space-between", gap: 0.5 }}>
                <Typography variant="body2" sx={{ fontWeight: 600, color: a.kind === "notice_rejected" || a.kind === "allocation_reversed" ? "error.main" : undefined }}>
                  {a.link ? (
                    <Link component={RouterLink} to={a.link} underline="hover" color="inherit">
                      {a.title}
                    </Link>
                  ) : (
                    a.title
                  )}
                </Typography>
                <Typography variant="caption" color="text.secondary" sx={{ whiteSpace: "nowrap" }}>
                  {formatDateTime(a.at)}
                </Typography>
              </Stack>
              <Typography variant="body2" color="text.secondary">
                {[many ? a.scheme_name : null, a.detail].filter(Boolean).join(" · ")}
              </Typography>
            </Box>
          ))}
        </Stack>
      )}
    </Paper>
  );
}

// The officer's applications for new employers, and the way to start one
// (only when the administrator has given them a fund to apply into).
function Applications() {
  const apps = useMyApplications();
  const funds = useApplicationFunds();
  const open = (apps.data ?? []).filter((a) => a.status !== "withdrawn" && !(a.status === "approved" && a.decided_at && Date.now() - Date.parse(a.decided_at) > 30 * 864e5));
  if (!funds.data?.length && !open.length) return null;
  return (
    <Paper sx={{ p: { xs: 2.5, sm: 3 } }} component="section" aria-label="Employer applications">
      <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} sx={{ justifyContent: "space-between", alignItems: { sm: "center" }, mb: open.length ? 2 : 0 }}>
        <div>
          <Typography variant="h2">Employer applications</Typography>
          <Typography color="text.secondary">Apply for an employer to join a fund; {BRAND.administrator} reviews and sets it up.</Typography>
        </div>
        {!!funds.data?.length && (
          <Button variant="contained" component={RouterLink} to="/po/applications/new" sx={{ whiteSpace: "nowrap" }}>
            Apply for an employer
          </Button>
        )}
      </Stack>
      <Stack divider={<Divider />} spacing={1.25}>
        {open.map((a) => {
          const st = APPLICATION_STATUS_TEXT[a.status];
          return (
            <Stack key={a.id} direction={{ xs: "column", sm: "row" }} spacing={1} sx={{ justifyContent: "space-between", alignItems: { sm: "center" } }}>
              <Box>
                <Link component={RouterLink} to={`/po/applications/${a.id}`} underline="hover" sx={{ fontWeight: 600 }}>
                  {a.details.name}
                </Link>
                <Typography variant="body2" color="text.secondary">
                  {a.fund_name} · {a.reference}
                </Typography>
              </Box>
              <Box>
                <StatusChip status={a.status} label={st.label} tone={st.tone} />
              </Box>
            </Stack>
          );
        })}
      </Stack>
    </Paper>
  );
}

// Principal officer dashboard (FR-PRT-001, FR-PRT-006): every employer the
// officer acts for — possibly several, in several funds — with this month's
// remittance (last month's contributions, due this month), arrears and recent activity.
export function PoHome() {
  const { user } = useAuth();
  const dashboard = usePoDashboard();
  const firstName = user?.full_name.split(" ")[0] || "there";
  const schemes = dashboard.data?.schemes ?? [];
  const groups = groupByFund(schemes);
  const lateCount = schemes.filter((s) => isLate(s.current.stage, s.current.days_to_due)).length;
  const owing = schemes.reduce((sum, s) => sum + Number(s.arrears.total), 0);

  return (
    <Stack spacing={2} sx={{ maxWidth: 1040 }}>
      <Typography variant="h1">Hello, {firstName}</Typography>
      {dashboard.isLoading && <LoadingState />}
      {dashboard.error && (
        <Alert severity="error" action={<Button color="inherit" size="small" onClick={() => dashboard.refetch()}>Try again</Button>}>
          {dashboard.error.message}
        </Alert>
      )}
      {dashboard.data && (
        <>
          <Paper sx={{ p: { xs: 2.5, sm: 3 } }}>
            <Stack spacing={2}>
              <div>
                <Typography variant="h2">Your schemes</Typography>
                {schemes.length > 0 && (
                  <Typography color="text.secondary">
                    You act for {schemes.length} employer{schemes.length === 1 ? "" : "s"}
                    {groups.length > 1 ? ` in ${groups.length} funds` : ""}.
                  </Typography>
                )}
              </div>
              {(lateCount > 0 || owing > 0) && (
                <Alert severity="warning">
                  {[
                    lateCount > 0 ? `${lateCount} employer${lateCount === 1 ? " is" : "s are"} late with this month's remittance.` : null,
                    owing > 0 ? `Arrears across your employers: ${formatMoney(owing)}.` : null,
                  ]
                    .filter(Boolean)
                    .join(" ")}
                </Alert>
              )}
              {schemes.length === 0 && (
                <Typography color="text.secondary">
                  You don't act for an employer yet. Apply for your employer to join a fund below, or ask {BRAND.administrator} to link your
                  sign-in to it. Then you can send monthly contribution schedules, add and update members, and follow each remittance here.
                </Typography>
              )}
              {groups.map(([fundName, list]) => (
                <Stack key={fundName} spacing={1} component="section" aria-label={fundName}>
                  <Typography variant="overline" component="h3" color="text.secondary">
                    {fundName}
                  </Typography>
                  {list.map((s) => (
                    <SchemeCard key={s.id} scheme={s} />
                  ))}
                </Stack>
              ))}
            </Stack>
          </Paper>
          <Applications />
          {schemes.length > 0 && <Activity items={dashboard.data.activity} many={schemes.length > 1} />}
        </>
      )}
    </Stack>
  );
}
