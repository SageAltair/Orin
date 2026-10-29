/** Load complete offset-paginated collections without silently dropping later pages. */
export async function fetchAllPages<T>(
  fetchPage: (offset: number, limit: number) => Promise<T[]>,
  collection: string,
  pageSize = 100,
  maxPages = 50,
): Promise<T[]> {
  const items: T[] = [];
  for (let page = 0; page < maxPages; page++) {
    const batch = await fetchPage(page * pageSize, pageSize);
    if (batch.length > pageSize) throw new Error(`Invalid ${collection} page received.`);
    items.push(...batch);
    if (batch.length < pageSize) return items;
  }
  // The next page may be empty when the total is an exact multiple of the limit.
  const next = await fetchPage(maxPages * pageSize, 1);
  if (next.length === 0) return items;
  throw new Error(`More than ${maxPages * pageSize} ${collection} exist. The full list could not be loaded safely.`);
}
