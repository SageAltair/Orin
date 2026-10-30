import { fetchAllPagesWithIdentityCheck } from "./features/focus/taskPagination";

/**
 * The notification API defaults to the 100 latest due dates, which can hide
 * older unread reminders and make the bell's unread count misleading.
 * Confirm the full owner-scoped identity set before publishing a refresh.
 * This is best-effort offset consistency, not an atomic database snapshot.
 */
export function fetchCompleteNotificationInbox<T extends { id: string }>(
  fetchPage: (offset: number, limit: number) => Promise<T[]>,
  pageSize = 200,
  maxPages = 50,
): Promise<T[]> {
  return fetchAllPagesWithIdentityCheck(
    fetchPage, "notifications", (row) => row.id, pageSize, maxPages,
  );
}
