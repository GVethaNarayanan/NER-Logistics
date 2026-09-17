import { describe, it, expect } from 'vitest'
import { normalizePagination, isPaginated, fetchAllPaginated, PaginatedData } from './pagination'

describe('Pagination Normalization', () => {
  it('correctly identifies a paginated backend response', () => {
    expect(isPaginated({ items: [], total: 0, skip: 0, limit: 10 })).toBe(true)
    expect(isPaginated({ items: [] })).toBe(false)
    expect(isPaginated(null)).toBe(false)
    expect(isPaginated([])).toBe(false)
  })

  it('normalizes paginated responses correctly', () => {
    const rawBackendResponse = {
      items: [{ id: 1, name: 'Test' }],
      total: 100,
      skip: 10,
      limit: 10
    }

    const normalized = normalizePagination(rawBackendResponse)
    expect(normalized.items).toEqual([{ id: 1, name: 'Test' }])
    expect(normalized.total).toBe(100)
    expect(normalized.skip).toBe(10)
    expect(normalized.limit).toBe(10)
  })

  it('handles non-paginated responses gracefully by treating them as items', () => {
    const arrayResponse = [{ id: 1 }]
    const normalized = normalizePagination(arrayResponse as any)
    
    // In our implementation, we want to ensure down-stream consumers always get a uniform shape
    // even if a non-paginated endpoint was accidentally passed.
    expect(normalized.items).toEqual([{ id: 1 }])
    expect(normalized.total).toBe(1)
    expect(normalized.skip).toBe(0)
    expect(normalized.limit).toBe(0)
  })
})

describe('fetchAllPaginated Helper', () => {
  it('<=100 records -> issues exactly one request', async () => {
    let callCount = 0
    const mockFetcher = async (skip: number, limit: number): Promise<PaginatedData<any>> => {
      callCount++
      const items = Array.from({ length: 80 }, (_, i) => i)
      return { items, total: 80, skip, limit }
    }
    
    const result = await fetchAllPaginated(mockFetcher, 100)
    expect(callCount).toBe(1)
    expect(result.items.length).toBe(80)
    expect(result.total).toBe(80)
  })

  it('>100 records -> issues multiple requests with correct skip progression', async () => {
    const skips: number[] = []
    const mockFetcher = async (skip: number, limit: number): Promise<PaginatedData<any>> => {
      skips.push(skip)
      // Simulate 250 total items
      const items = Array.from({ length: skip === 200 ? 50 : 100 }, (_, i) => skip + i)
      return { items, total: 250, skip, limit }
    }
    
    const result = await fetchAllPaginated(mockFetcher, 100)
    
    // Should call with skip=0, skip=100, skip=200
    expect(skips).toEqual([0, 100, 200])
    expect(result.items.length).toBe(250) // combined result contains all items
    expect(result.total).toBe(250)
  })

  it('handles completely empty results cleanly', async () => {
    const mockFetcher = async (skip: number, limit: number): Promise<PaginatedData<any>> => {
      return { items: [], total: 0, skip, limit }
    }
    
    const result = await fetchAllPaginated(mockFetcher, 100)
    expect(result.items).toEqual([])
    expect(result.total).toBe(0)
  })

  it('rejects completely if a page fails (surfaces backend error)', async () => {
    let callCount = 0
    const mockFetcher = async (skip: number, limit: number): Promise<PaginatedData<any>> => {
      callCount++
      if (skip === 100) {
        throw new Error('Backend Validation Failed')
      }
      return { items: Array.from({ length: 100 }), total: 200, skip, limit }
    }
    
    await expect(fetchAllPaginated(mockFetcher, 100)).rejects.toThrow('Backend Validation Failed')
    expect(callCount).toBe(2) // failed on second page
  })

  it('prevents infinite loops if backend total is infinitely large but items stop', async () => {
    let callCount = 0
    const mockFetcher = async (skip: number, limit: number): Promise<PaginatedData<any>> => {
      callCount++
      // Pretend total is 1 million, but only return items on first 2 pages
      if (skip >= 200) {
        return { items: [], total: 1000000, skip, limit }
      }
      return { items: Array.from({ length: 100 }), total: 1000000, skip, limit }
    }
    
    const result = await fetchAllPaginated(mockFetcher, 100)
    expect(callCount).toBe(3) // 0, 100, and 200 (which returns empty and breaks)
    expect(result.items.length).toBe(200)
    expect(result.total).toBe(200) // Corrected total length
  })
})
