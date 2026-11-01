import { Link } from "react-router-dom";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Grid from "@mui/material/Grid";
import Paper from "@mui/material/Paper";
import Skeleton from "@mui/material/Skeleton";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { useAuth } from "../../auth/AuthContext";
import { useApprovals } from "../../queries/approvals";
import { useUnreadCount } from "../../queries/notifications";

function Tile({ label, value, loading, to, action }: { label: string; value: number | undefined; loading: boolean; to: string; action: string }) {
  return (
    <Paper sx={{ p: 2.5, height: "100%" }}>
      <Stack spacing={1} sx={{ height: "100%" }}>
        <Typography variant="body2" color="text.secondary">
          {label}
        </Typography>
        {loading ? (
          <Skeleton width={60} height={40} />
        ) : (
          <Typography variant="h4" component="p" sx={{ fontSize: "2rem", fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>
            {value ?? "—"}
          </Typography>
        )}
        <Button component={Link} to={to} size="small" sx={{ alignSelf: "flex-start", mt: "auto" }}>
          {action}
        </Button>
      </Stack>
    </Paper>
  );
}

// Staff landing page: what needs this person's attention. Fund, contribution
// and claim queues join here as those phases are built.
export function StaffHome() {
  const { user } = useAuth();
  const approvals = useApprovals("pending");
  const unread = useUnreadCount();
  const toReview = approvals.data?.filter((a) => a.can_review).length;
  const mine = approvals.data?.filter((a) => a.can_cancel).length;
  const firstName = user?.full_name.split(" ")[0] || "there";

  return (
    <Stack spacing={3}>
      <div>
        <Typography variant="h1" sx={{ mb: 0.5 }}>
          Hello, {firstName}
        </Typography>
        <Typography color="text.secondary">Here is what is waiting for you today.</Typography>
      </div>
      {approvals.error && <Alert severity="error">{approvals.error.message}</Alert>}
      <Grid container spacing={2}>
        <Grid size={{ xs: 12, sm: 6, md: 4 }}>
          <Tile label="Waiting for your approval" value={toReview} loading={approvals.isLoading} to="/approvals" action="Review requests" />
        </Grid>
        <Grid size={{ xs: 12, sm: 6, md: 4 }}>
          <Tile label="Your requests awaiting a checker" value={mine} loading={approvals.isLoading} to="/approvals?tab=mine" action="View your requests" />
        </Grid>
        <Grid size={{ xs: 12, sm: 6, md: 4 }}>
          <Tile label="Unread notifications" value={unread.data?.unread} loading={unread.isLoading} to="/notifications" action="Open notifications" />
        </Grid>
      </Grid>
    </Stack>
  );
}
