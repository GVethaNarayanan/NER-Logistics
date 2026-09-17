export interface PaginatedData<T> {
  items: T[]
  total: number
  skip: number
  limit: number
}

// Type guard to check if a response matches the backend pagination structure
export function isPaginated(response: any): response is PaginatedData<any> {
  return (
    response !== null &&
    typeof response === 'object' &&
    Array.isArray(response.items) &&
    typeof response.total === 'number' &&
    typeof response.skip === 'number' &&
    typeof response.limit === 'number'
  )
}

/**
 * Normalizes an API response into a consistent PaginatedData structure.
 * This guarantees components always deal with a uniform data shape,
 * even if a non-paginated endpoint is wrapped.
 */
export function normalizePagination<T>(data: any): PaginatedData<T> {
  if (isPaginated(data)) {
    return {
      items: data.items,
      total: data.total,
      skip: data.skip,
      limit: data.limit
    }
  }

  // Graceful fallback for non-paginated arrays
  if (Array.isArray(data)) {
    return {
      items: data,
      total: data.length,
      skip: 0,
      limit: 0
    }
  }

  // Graceful fallback for completely unknown structures
  return {
    items: data ? [data] : [],
    total: data ? 1 : 0,
    skip: 0,
    limit: 0
  }
}

/**
 * Helper to fetch all pages from a paginated endpoint.
 * Issues requests with limit=100 until all items are collected.
 */
export async function fetchAllPaginated<T>(
  fetcher: (skip: number, limit: number) => Promise<PaginatedData<T>>,
  maxLimit: number = 100
): Promise<PaginatedData<T>> {
  let skip = 0;
  // Fetch the first page
  const initialPage = await fetcher(skip, maxLimit);
  
  const combined: PaginatedData<T> = {
    items: [...initialPage.items],
    total: initialPage.total,
    skip: 0,
    limit: maxLimit
  };

  let collected = initialPage.items.length;
  let safetyCounter = 0;
  const MAX_PAGES = 1000; // prevent absolute infinite loops

  // Continue fetching if we have fewer items than the reported total
  while (collected < initialPage.total && safetyCounter < MAX_PAGES) {
    skip += maxLimit;
    const nextPage = await fetcher(skip, maxLimit);
    
    // Safety check: if an empty array is returned prematurely, break
    if (!nextPage.items || nextPage.items.length === 0) {
      break;
    }
    
    combined.items.push(...nextPage.items);
    collected += nextPage.items.length;
    safetyCounter++;
  }

  // Update total to actual length in case backend total was inaccurate
  combined.total = combined.items.length;
  return combined;
}
