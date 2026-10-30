/** Load complete offset-paginated collections without silently dropping later pages. */
export async function fetchAllPages<T>(
  fetchPage: (offset: number, limit: number) => Promise<T[]>,
  collection: string,
  pageSize = 100,
  maxPages = 50,
  getId?: (item: T) => string,
): Promise<T[]> {
  const items: T[] = [];
  const seen = new Set<string>();
  for (let page = 0; page < maxPages; page++) {
    const batch = await fetchPage(page * pageSize, pageSize);
    if (!Array.isArray(batch) || batch.length > pageSize) {
      throw new Error(`Invalid ${collection} page received.`);
    }
    // Offset pages can shift after a concurrent edit. Reject overlapping
    // identities rather than render duplicates and hide missing records.
    if (getId) {
      for (const item of batch) {
        const id = item && getId(item);
        if (typeof id !== "string" || !id) {
          throw new Error(`Invalid ${collection} record received.`);
        }
        if (seen.has(id)) {
          throw new Error(`Overlapping ${collection} pages received. Retry to load a consistent list.`);
        }
        seen.add(id);
      }
    }
    items.push(...batch);
    if (batch.length < pageSize) return items;
  }
  // The next page may be empty when the total is an exact multiple of the limit.
  const next = await fetchPage(maxPages * pageSize, 1);
  if (!Array.isArray(next)) throw new Error(`Invalid ${collection} page received.`);
  if (next.length === 0) return items;
  throw new Error(`More than ${maxPages * pageSize} ${collection} exist. The full list could not be loaded safely.`);
}
