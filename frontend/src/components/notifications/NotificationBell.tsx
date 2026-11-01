import { useState } from "react";
import { Link } from "react-router-dom";
import Alert from "@mui/material/Alert";
import Badge from "@mui/material/Badge";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import IconButton from "@mui/material/IconButton";
import List from "@mui/material/List";
import Popover from "@mui/material/Popover";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import NotificationsNoneIcon from "@mui/icons-material/NotificationsNone";
import { useMarkAllNotificationsRead, useNotifications, useUnreadCount } from "../../queries/notifications";
import { NotificationItem } from "./NotificationItem";

const DROPDOWN_SIZE = 10;

// App-bar bell for every role, customers included: unread badge (polled),
// dropdown of the latest notifications, link to the full list.
export function NotificationBell() {
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
  const open = anchor !== null;
  const unread = useUnreadCount().data?.unread ?? 0;
  const latest = useNotifications({ limit: DROPDOWN_SIZE }, open);
  const markAll = useMarkAllNotificationsRead();
  const close = () => setAnchor(null);

  return (
    <>
      <IconButton
        onClick={(e) => setAnchor(e.currentTarget)}
        aria-label={unread ? `Notifications, ${unread} unread` : "Notifications"}
        aria-haspopup="true"
        aria-expanded={open}
        sx={{ width: 44, height: 44 }}
      >
        <Badge badgeContent={unread} color="error" max={99}>
          <NotificationsNoneIcon />
        </Badge>
      </IconButton>
      <Popover
        open={open}
        anchorEl={anchor}
        onClose={close}
        anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
        transformOrigin={{ vertical: "top", horizontal: "right" }}
        slotProps={{
          paper: {
            sx: { width: { xs: "calc(100vw - 32px)", sm: 380 }, maxHeight: "min(70vh, 560px)", display: "flex", flexDirection: "column" },
          },
        }}
      >
        <Stack
          direction="row"
          sx={{ px: 2, py: 1, justifyContent: "space-between", alignItems: "center", borderBottom: 1, borderColor: "divider" }}
        >
          <Typography variant="subtitle1" component="h2" sx={{ fontWeight: 600 }}>
            Notifications
          </Typography>
          <Button size="small" onClick={() => markAll.mutate()} disabled={unread === 0 || markAll.isPending}>
            {markAll.isPending ? "Marking…" : "Mark all as read"}
          </Button>
        </Stack>
        <Box sx={{ overflowY: "auto", flex: 1 }}>
          {latest.isPending ? (
            <Box sx={{ display: "flex", justifyContent: "center", py: 4 }}>
              <CircularProgress size={24} />
            </Box>
          ) : latest.isError ? (
            <Alert severity="error" sx={{ m: 2 }}>
              {latest.error.message}
            </Alert>
          ) : latest.data.items.length === 0 ? (
            <Typography color="text.secondary" sx={{ px: 2, py: 4, textAlign: "center" }}>
              You're all caught up. Updates about your account and approvals will appear here.
            </Typography>
          ) : (
            <List disablePadding>
              {latest.data.items.map((n) => (
                <NotificationItem key={n.id} notification={n} onOpen={close} />
              ))}
            </List>
          )}
        </Box>
        <Stack direction="row" sx={{ borderTop: 1, borderColor: "divider", p: 1, alignItems: "center" }}>
          <Button component={Link} to="/notifications" onClick={close} size="small" sx={{ minHeight: 40, flex: 1 }}>
            View all notifications
          </Button>
        </Stack>
      </Popover>
    </>
  );
}
