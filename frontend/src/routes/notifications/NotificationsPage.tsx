import { Link } from "react-router-dom";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import List from "@mui/material/List";
import Pagination from "@mui/material/Pagination";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import Typography from "@mui/material/Typography";
import SettingsOutlinedIcon from "@mui/icons-material/SettingsOutlined";
import { PageHeader } from "../../components/PageHeader";
import { LoadingState } from "../../components/LoadingState";
import { NotificationItem } from "../../components/notifications/NotificationItem";
import { useUrlParam, useUrlTab } from "../../hooks/useUrlState";
import { useMarkAllNotificationsRead, useNotifications } from "../../queries/notifications";

const PAGE_SIZE = 20;
const FILTERS = ["all", "unread"] as const;

// /notifications — the full inbox for any signed-in user (?tab=unread, ?page=2).
export function NotificationsPage() {
  const [filter, setFilter] = useUrlTab(FILTERS);
  const [pageParam, setPageParam] = useUrlParam("page");
  const page = Math.max(1, Number(pageParam) || 1);
  const list = useNotifications({ unreadOnly: filter === "unread", limit: PAGE_SIZE, offset: (page - 1) * PAGE_SIZE });
  const markAll = useMarkAllNotificationsRead();
  const unread = list.data?.unread ?? 0;
  const pageCount = list.data ? Math.ceil(list.data.total / PAGE_SIZE) : 0;

  return (
    <Stack sx={{ maxWidth: 760 }}>
      <PageHeader
        title="Notifications"
        description="Updates about your account, money movements and anything waiting for you."
        action={
          <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: "wrap" }}>
            <Button variant="outlined" onClick={() => markAll.mutate()} disabled={unread === 0 || markAll.isPending}>
              {markAll.isPending ? "Marking…" : "Mark all as read"}
            </Button>
            <Button component={Link} to="/notifications/settings" startIcon={<SettingsOutlinedIcon />}>
              Settings
            </Button>
          </Stack>
        }
      />
      {markAll.isError && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {markAll.error.message}
        </Alert>
      )}
      <Paper variant="outlined">
        <Tabs
          value={filter}
          onChange={(_, next) => {
            setFilter(next);
            setPageParam(null);
          }}
          sx={{ borderBottom: 1, borderColor: "divider", px: 1 }}
        >
          <Tab value="all" label="All" />
          <Tab value="unread" label={unread ? `Unread (${unread})` : "Unread"} />
        </Tabs>
        {list.isPending ? (
          <LoadingState />
        ) : list.isError ? (
          <Alert severity="error" sx={{ m: 2 }}>
            {list.error.message}
          </Alert>
        ) : list.data.items.length === 0 ? (
          <Typography color="text.secondary" sx={{ p: 4, textAlign: "center" }}>
            {filter === "unread"
              ? "No unread notifications — you're all caught up."
              : "No notifications yet. Updates about your account and approvals will appear here."}
          </Typography>
        ) : (
          <List disablePadding>
            {list.data.items.map((n) => (
              <NotificationItem key={n.id} notification={n} />
            ))}
          </List>
        )}
      </Paper>
      {pageCount > 1 && (
        <Pagination
          count={pageCount}
          page={page}
          onChange={(_, next) => setPageParam(next === 1 ? null : String(next))}
          sx={{ mt: 2, alignSelf: "center" }}
        />
      )}
    </Stack>
  );
}
