import { render, screen } from '@testing-library/react'
import '@testing-library/jest-dom'
import { describe, it, expect, vi } from 'vitest'
import { LoadingState } from '../components/shared/LoadingState'
import { ErrorState } from '../components/shared/ErrorState'
import { EmptyState } from '../components/shared/EmptyState'
import { ApiError } from '../api/client'

// Mock Lucide icons
vi.mock('lucide-react', () => ({
  Loader2: () => <div data-testid="loader-icon" />,
  AlertCircle: () => <div data-testid="alert-icon" />,
  Inbox: () => <div data-testid="inbox-icon" />,
  RefreshCw: () => <div data-testid="refresh-icon" />,
  FolderOpen: () => <div data-testid="folder-icon" />,
  FileWarning: () => <div data-testid="filewarning-icon" />
}))

describe('UX Hardening Shared Components', () => {
  describe('LoadingState', () => {
    it('renders default loading message', () => {
      render(<LoadingState />)
      expect(screen.getByText('Loading...')).toBeInTheDocument()
      expect(screen.getByTestId('loader-icon')).toBeInTheDocument()
    })

    it('renders custom loading message', () => {
      render(<LoadingState message="Fetching data..." />)
      expect(screen.getByText('Fetching data...')).toBeInTheDocument()
    })
  })

  describe('ErrorState', () => {
    it('renders simple string error', () => {
      render(<ErrorState error="Network disconnected" />)
      expect(screen.getByText('Network disconnected')).toBeInTheDocument()
    })

    it('renders ApiError with status code', () => {
      const err = new ApiError({ error: { code: 404, message: 'Not Found', path: '/test' } })
      render(<ErrorState error={err} />)
      expect(screen.getByText('Not Found')).toBeInTheDocument()
    })

    it('renders ApiError with 422 validation details', () => {
      const err = new ApiError({ 
        error: { 
          code: 422, 
          message: 'Validation Error', 
          path: '/test',
          detail: [
            { loc: ['body', 'email'], msg: 'invalid email' },
            { loc: ['body', 'password'], msg: 'too short' }
          ]
        } 
      })
      render(<ErrorState error={err} />)
      expect(screen.getByText('Validation Error')).toBeInTheDocument()
      expect(screen.getByText('body.email')).toBeInTheDocument()
      expect(screen.getByText(/invalid email/)).toBeInTheDocument()
      expect(screen.getByText('body.password')).toBeInTheDocument()
      expect(screen.getByText(/too short/)).toBeInTheDocument()
    })

    it('renders retry button when onRetry is provided', () => {
      const onRetry = vi.fn()
      render(<ErrorState error="Failed" onRetry={onRetry} />)
      const button = screen.getByRole('button', { name: /Retry/i })
      expect(button).toBeInTheDocument()
      button.click()
      expect(onRetry).toHaveBeenCalled()
    })
  })

  describe('EmptyState', () => {
    it('renders with default props', () => {
      render(<EmptyState title="No items" />)
      expect(screen.getByText('No items')).toBeInTheDocument()
      expect(screen.getByTestId('folder-icon')).toBeInTheDocument()
    })

    it('renders with description and custom icon', () => {
      render(
        <EmptyState 
          title="Custom Title" 
          description="Custom description text" 
          icon={<div data-testid="custom-icon" />} 
        />
      )
      expect(screen.getByText('Custom Title')).toBeInTheDocument()
      expect(screen.getByText('Custom description text')).toBeInTheDocument()
      expect(screen.getByTestId('custom-icon')).toBeInTheDocument()
    })
  })
})
