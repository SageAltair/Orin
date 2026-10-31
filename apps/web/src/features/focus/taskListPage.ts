export function paginateTaskList<T>(items: readonly T[], requestedPage: number, pageSize = 10) {
  if (!Number.isInteger(pageSize) || pageSize < 1) throw new RangeError("pageSize must be positive");
  const pageCount = Math.max(1, Math.ceil(items.length / pageSize));
  const currentPage = Math.min(Math.max(1, Number.isFinite(requestedPage) ? Math.floor(requestedPage) : 1), pageCount);
  return { pageCount, currentPage, pageTasks: items.slice((currentPage - 1) * pageSize, currentPage * pageSize) };
}
