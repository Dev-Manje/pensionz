import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { useAuth } from "../../auth/AuthContext";
import { BRAND } from "../../brand";
import { LoadingState } from "../../components/LoadingState";
import { StatusChip } from "../../components/StatusChip";
import { useMySchemes } from "../../queries/po";
import type { PortalScheme } from "../../api/types";
import { dueDayLabel } from "../staff/funds/schemes/schemeLabels";

const STATUS_TEXT: Record<PortalScheme["status"], string> = {
  active: "Active",
  suspended: "Contributions on hold",
  exited: "Left the fund",
};

function groupByFund(schemes: PortalScheme[]): [string, PortalScheme[]][] {
  const groups = new Map<string, PortalScheme[]>();
  for (const s of schemes) groups.set(s.fund_name, [...(groups.get(s.fund_name) ?? []), s]);
  return [...groups.entries()];
}

function SchemeCard({ scheme }: { scheme: PortalScheme }) {
  return (
    <Paper variant="outlined" sx={{ p: 2 }}>
      <Stack direction={{ xs: "column", sm: "row" }} spacing={1} sx={{ justifyContent: "space-between", alignItems: { sm: "center" } }}>
        <div>
          <Typography variant="subtitle1" component="h3" sx={{ fontWeight: 600 }}>
            {scheme.name}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Employer code {scheme.code} · {scheme.member_count} member{scheme.member_count === 1 ? "" : "s"} · contributions due by the{" "}
            {dueDayLabel(scheme.contribution_day)}
          </Typography>
        </div>
        <StatusChip status={scheme.status} label={STATUS_TEXT[scheme.status]} size="small" sx={{ alignSelf: { xs: "flex-start", sm: "center" } }} />
      </Stack>
    </Paper>
  );
}

// Principal officer portal landing page (FR-PRT-001, FR-PRT-006). Lists every
// employer the officer acts for, grouped by fund — one officer may serve
// several employers in several funds. Remittance status, arrears and members
// per employer come with the dashboard.
export function PoHome() {
  const { user } = useAuth();
  const schemes = useMySchemes();
  const firstName = user?.full_name.split(" ")[0] || "there";
  const groups = groupByFund(schemes.data ?? []);

  return (
    <Stack spacing={2} sx={{ maxWidth: 880 }}>
      <Typography variant="h1">Hello, {firstName}</Typography>
      <Paper sx={{ p: { xs: 2.5, sm: 3 } }}>
        <Stack spacing={2}>
          <div>
            <Typography variant="h2">Your schemes</Typography>
            {!!schemes.data?.length && (
              <Typography color="text.secondary">
                You act for {schemes.data.length} employer{schemes.data.length === 1 ? "" : "s"}
                {groups.length > 1 ? ` in ${groups.length} funds` : ""}.
              </Typography>
            )}
          </div>
          {schemes.isLoading && <LoadingState />}
          {schemes.error && (
            <Alert severity="error" action={<Button color="inherit" size="small" onClick={() => schemes.refetch()}>Try again</Button>}>
              {schemes.error.message}
            </Alert>
          )}
          {schemes.data?.length === 0 && (
            <Typography color="text.secondary">
              Your sign-in has not been linked to a scheme yet. Once {BRAND.administrator} links it, you will be able to send monthly
              contribution schedules, add and update members, and follow each remittance here.
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
    </Stack>
  );
}
