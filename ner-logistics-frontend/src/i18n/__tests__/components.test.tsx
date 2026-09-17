import { render, screen, act } from '@testing-library/react'
import '@testing-library/jest-dom'
import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest'
import { I18nextProvider } from 'react-i18next'
import i18n from '../config'
import { RiskPanel } from '../../components/dashboard/RiskPanel'
import { RoutePlannerPanel } from '../../components/dashboard/RoutePlannerPanel'
import { SavedRoutes } from '../../pages/SavedRoutes'
import * as AuthContext from '../../contexts/AuthContext'

// Mock the API calls for RiskPanel and SavedRoutes so they don't fail during rendering
vi.mock('../../api/risk', () => ({
  riskApi: {
    predictRisk: () => Promise.resolve({ risk_score: 0.5, risk_level: 'medium', prediction_source: 'ML' })
  }
}))
vi.mock('../../api/infrastructure', () => ({
  infrastructureApi: {
    getRoads: () => Promise.resolve({ items: [] })
  }
}))
vi.mock('../../api/routes', () => ({
  routesApi: {}
}))

describe('Phase 8 Targeted Fixes - Multilingual Components', () => {
  beforeEach(async () => {
    localStorage.clear()
    await i18n.changeLanguage('en')
    // Mock user as admin so SavedRoutes renders its content
    vi.spyOn(AuthContext, 'useAuth').mockReturnValue({
      role: 'admin',
      user: { id: 1, username: 'admin', email: 'admin@test.com', role: 'admin', is_active: true },
      isAuthenticated: true,
      isLoading: false,
      login: vi.fn(),
      logout: vi.fn(),
      restoreSession: vi.fn(),
    })
  })

  afterEach(() => {
    vi.restoreAllMocks()
    localStorage.clear()
  })

  it('translates RiskPanel to Assamese', async () => {
    const { unmount } = render(
      <I18nextProvider i18n={i18n}>
        <RiskPanel selectedRoad={null} />
      </I18nextProvider>
    )
    
    // Default English
    expect(screen.getByText('Select a road on the map to view risk prediction.')).toBeInTheDocument()
    
    // Switch to Assamese
    await act(async () => {
      await i18n.changeLanguage('as')
    })
    
    expect(screen.getByText('বিপদৰ পূৰ্বানুমান চাবলৈ মেপত এটা পথ বাছক।')).toBeInTheDocument()
    unmount()
  })

  it('translates RoutePlannerPanel to Assamese', async () => {
    const { unmount } = render(
      <I18nextProvider i18n={i18n}>
        <RoutePlannerPanel 
          origin={null} 
          destination={null} 
          selectingMode={null} 
          setSelectingMode={vi.fn()} 
          onCalculateRoute={vi.fn()} 
          routeLoading={false} 
          routeError={null} 
          routeResult={null} 
        />
      </I18nextProvider>
    )

    // Default English
    expect(screen.getByText('Route Planner')).toBeInTheDocument()
    expect(screen.getByText('Calculate Route')).toBeInTheDocument()

    // Switch to Assamese
    await act(async () => {
      await i18n.changeLanguage('as')
    })

    expect(screen.getByText('পথ পৰিকল্পনাকাৰী')).toBeInTheDocument()
    expect(screen.getByText('পথ গণনা কৰক')).toBeInTheDocument()
    unmount()
  })

  it('translates SavedRoutes to English and Assamese', async () => {
    const { unmount } = render(
      <I18nextProvider i18n={i18n}>
        <SavedRoutes />
      </I18nextProvider>
    )

    // Default English
    expect(screen.getByText('Saved Routes')).toBeInTheDocument()
    expect(screen.getByText('1. Create New Route')).toBeInTheDocument()

    // Switch to Assamese
    await act(async () => {
      await i18n.changeLanguage('as')
    })

    expect(screen.getByText('১. নতুন পথ সৃষ্টি কৰক')).toBeInTheDocument()
    unmount()
  })
})
