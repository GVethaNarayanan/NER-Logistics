import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest'
import { fetchJson, setAccessToken, setRefreshToken, clearAuth, getAccessToken, getRefreshToken, ApiError, API_BASE_URL } from './client'

const mockFetch = vi.fn()
globalThis.fetch = mockFetch

describe('API Client Foundation', () => {
  beforeEach(() => {
    clearAuth()
    mockFetch.mockReset()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('API base URL comes from environment configuration', () => {
    expect(API_BASE_URL).toBeDefined()
  })

  it('Public requests work without a token', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ status: 'ok' })
    })

    const data = await fetchJson('/')
    expect(data).toEqual({ status: 'ok' })
    expect(mockFetch).toHaveBeenCalledWith(`${API_BASE_URL}/`, expect.objectContaining({
      headers: expect.any(Headers)
    }))
    
    // Check headers directly
    const headers = mockFetch.mock.calls[0][1].headers as Headers
    expect(headers.has('Authorization')).toBe(false)
  })

  it('Authorization header is attached when an access token exists', async () => {
    setAccessToken('test-access-token')
    
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ status: 'ok' })
    })

    await fetchJson('/')
    
    const headers = mockFetch.mock.calls[0][1].headers as Headers
    expect(headers.get('Authorization')).toBe('Bearer test-access-token')
  })

  it('Backend structured error is parsed correctly', async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      status: 400,
      statusText: 'Bad Request',
      json: async () => ({
        error: {
          code: 400,
          message: 'Invalid input',
          path: '/test'
        }
      })
    })

    await expect(fetchJson('/test')).rejects.toThrow(ApiError)
    await expect(fetchJson('/test')).rejects.toThrow('Invalid input')
  })

  it('401 triggers exactly one refresh attempt and retries the original request once', async () => {
    setAccessToken('expired-token')
    setRefreshToken('valid-refresh-token')

    // 1st request: returns 401
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 401,
      json: async () => ({ error: { message: 'Unauthorized' } })
    })

    // 2nd request: refresh token call
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ access_token: 'new-access-token', refresh_token: 'new-refresh-token' })
    })

    // 3rd request: original request retry
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ success: true })
    })

    const data = await fetchJson('/protected')
    expect(data).toEqual({ success: true })
    
    expect(mockFetch).toHaveBeenCalledTimes(3)
    // Verify 2nd call was the refresh call
    expect(mockFetch.mock.calls[1][0]).toBe(`${API_BASE_URL}/auth/refresh`)
    // Verify new token was set
    expect(getAccessToken()).toBe('new-access-token')
    expect(getRefreshToken()).toBe('new-refresh-token')
  })

  it('Failed refresh clears authentication state', async () => {
    setAccessToken('expired-token')
    setRefreshToken('invalid-refresh-token')

    // 1st request: returns 401
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 401,
      json: async () => ({ error: { message: 'Unauthorized' } })
    })

    // 2nd request: refresh token call fails
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 401,
      json: async () => ({ error: { message: 'Refresh token invalid' } })
    })

    await expect(fetchJson('/protected')).rejects.toThrow()
    
    expect(mockFetch).toHaveBeenCalledTimes(2)
    expect(getAccessToken()).toBeNull()
    expect(getRefreshToken()).toBeNull()
  })

  it('Refresh does not loop indefinitely', async () => {
    setAccessToken('expired-token')
    setRefreshToken('valid-refresh-token')

    // 1st request: returns 401
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 401,
      json: async () => ({ error: { message: 'Unauthorized' } })
    })

    // 2nd request: refresh token call
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ access_token: 'new-token-that-is-somehow-also-expired', refresh_token: 'new-refresh-token' })
    })

    // 3rd request: original request retry STILL returns 401
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 401,
      json: async () => ({ error: { message: 'Unauthorized' } })
    })

    // Should throw after one retry
    await expect(fetchJson('/protected')).rejects.toThrow('Unauthorized')
    
    expect(mockFetch).toHaveBeenCalledTimes(3)
  })
})
