import { useNavigate } from "react-router-dom";
import Box from "@mui/material/Box";
import ListItemButton from "@mui/material/ListItemButton";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import type { UserNotification } from "../../api/types";
import { useMarkNotificationRead } from "../../queries/notifications";
import { formatDateTime, formatRelative } from "../../utils/date";

// One notification row, shared by the bell's dropdown and the full page.
// Clicking marks it read and opens the screen it's about.
export function NotificationItem({ notification, onOpen }: { notification: UserNotification; onOpen?: () => void }) {
  const navigate = useNavigate();
  const markRead = useMarkNotificationRead();
  const unread = notification.read_at === null;

  function open() {
    if (unread) markRead.mutate(notification.id);
    onOpen?.();
    if (notification.link) navigate(notification.link);
  }

  return (
    <ListItemButton
      onClick={open}
      aria-label={`${unread ? "Unread: " : ""}${notification.title}`}
      sx={{
        alignItems: "flex-start",
        gap: 1.5,
        py: 1.5,
        minHeight: 44,
        borderBottom: 1,
        borderColor: "divider",
        bgcolor: unread ? "action.hover" : "transparent",
      }}
    >
      <Box
        aria-hidden
        sx={{ mt: 0.75, width: 8, height: 8, borderRadius: "50%", flexShrink: 0, bgcolor: unread ? "primary.main" : "transparent" }}
      />
      <Stack spacing={0.25} sx={{ minWidth: 0, flex: 1 }}>
        {/* The time drops under the title when there isn't room beside it. */}
        <Stack direction="row" sx={{ justifyContent: "space-between", alignItems: "baseline", flexWrap: "wrap", columnGap: 1 }}>
          <Typography variant="body2" sx={{ fontWeight: unread ? 700 : 500, minWidth: 0, overflowWrap: "anywhere" }}>
            {notification.title}
          </Typography>
          <Typography
            variant="caption"
            color="text.secondary"
            title={formatDateTime(notification.created_at)}
            sx={{ flexShrink: 0, whiteSpace: "nowrap" }}
          >
            {formatRelative(notification.created_at)}
          </Typography>
        </Stack>
        <Typography variant="body2" color="text.secondary">
          {notification.body}
        </Typography>
      </Stack>
    </ListItemButton>
  );
}
