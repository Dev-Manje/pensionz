import { apiFetch } from "./client";
import type { UserNotificationPage } from "./types";

export interface NotificationListParams {
  unreadOnly?: boolean;
  limit?: number;
  offset?: number;
}

export function listMyNotifications({ unreadOnly = false, limit = 20, offset = 0 }: NotificationListParams = {}) {
  const query = new URLSearchParams({ unread_only: String(unreadOnly), limit: String(limit), offset: String(offset) });
  return apiFetch<UserNotificationPage>(`/me/notifications?${query}`);
}

export function getUnreadCount() {
  return apiFetch<{ unread: number }>("/me/notifications/unread-count");
}

export function markNotificationRead(id: string) {
  return apiFetch<void>(`/me/notifications/${id}/read`, { method: "POST" });
}

export function markAllNotificationsRead() {
  return apiFetch<void>("/me/notifications/read-all", { method: "POST" });
}
