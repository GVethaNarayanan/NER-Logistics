import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import '@testing-library/jest-dom'
import { RiskPanel } from '../components/dashboard/RiskPanel'
import { RoutePlannerPanel } from '../components/dashboard/RoutePlannerPanel'
import { riskApi } from '../api/risk'
import { RoadOut } from '../api/infrastructure'

vi.mock('../api/risk', () => ({
  riskApi: { predictRisk: vi.fn() }
}))

vi.mock('../api/routing', () => ({
  routingApi: { computeRoute: vi.fn() }
}))

describe('Phase 4: Risk Prediction & Routing', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  const dummyRoad: RoadOut = { id: 10, name: 'Test Road', start_lat: 26, start_lon: 92, end_lat: 27, end_lon: 93, status: 'open', district: 'Test' }

  describe('Risk Panel', () => {
    it('1. Risk panel renders', () => {
      render(<RiskPanel selectedRoad={null} />)
      expect(screen.getByText(/Select a road on the map to view risk prediction/i)).toBeInTheDocument()
    })

    it('2-6. Displays risk score, level, factors, ml and tier1_fallback prediction sources', async () => {
      vi.mocked(riskApi.predictRisk).mockResolvedValueOnce({
        risk_score: 85.5,
        risk_level: 'HIGH',
        factors: ['Steep terrain', 'Heavy rainfall'],
        prediction_source: 'ml'
      })

      const { rerender } = render(<RiskPanel selectedRoad={dummyRoad} />)

      await waitFor(() => {
        expect(screen.getByText('85.5')).toBeInTheDocument()
        expect(screen.getByText('HIGH')).toBeInTheDocument()
        expect(screen.getByText('Steep terrain')).toBeInTheDocument()
        expect(screen.getByText('AI / ML Prediction')).toBeInTheDocument()
      })

      vi.mocked(riskApi.predictRisk).mockResolvedValueOnce({
        risk_score: 20.0,
        risk_level: 'LOW',
        factors: ['Clear weather'],
        prediction_source: 'tier1_fallback'
      })

      rerender(<RiskPanel selectedRoad={{...dummyRoad, id: 11}} />)

      await waitFor(() => {
        expect(screen.getByText('20.0')).toBeInTheDocument()
        expect(screen.getByText('Tier-1 Rule-Based Fallback')).toBeInTheDocument()
      })
    })

    it('7. Risk API error is handled', async () => {
      vi.mocked(riskApi.predictRisk).mockRejectedValueOnce(new Error('Risk network error'))
      render(<RiskPanel selectedRoad={dummyRoad} />)

      await waitFor(() => {
        expect(screen.getByText('Risk network error')).toBeInTheDocument()
      })
    })
  })

  describe('Route Planner Panel', () => {
    it('8-11. Origin/Dest selection works and Shortest/Safest preference is sent correctly', async () => {
      const setSelectingMode = vi.fn()
      const onCalculateRoute = vi.fn()
      render(
        <RoutePlannerPanel 
          origin={[26.1, 92.1]} 
          destination={[26.2, 92.2]} 
          selectingMode={null} 
          setSelectingMode={setSelectingMode}
          onCalculateRoute={onCalculateRoute}
          routeLoading={false}
          routeError={null}
          routeResult={null}
        />
      )

      fireEvent.click(screen.getByText(/Origin/i).closest('button')!)
      expect(setSelectingMode).toHaveBeenCalledWith('origin')

      fireEvent.click(screen.getByText('Lowest available route risk (Safest)'))
      fireEvent.click(screen.getByText('Calculate Route'))
      expect(onCalculateRoute).toHaveBeenCalledWith('safest')
    })

    it('14. Route metadata is displayed', () => {
      const result = {
        type: 'Feature',
        geometry: { type: 'LineString', coordinates: [[92.1, 26.1], [92.2, 26.2]] },
        properties: { total_distance_km: 15.5, average_risk_score: 30.2, max_risk_score: 45.1, risk_level: 'MEDIUM' }
      }
      render(
        <RoutePlannerPanel 
          origin={[26.1, 92.1]} 
          destination={[26.2, 92.2]} 
          selectingMode={null} 
          setSelectingMode={vi.fn()}
          onCalculateRoute={vi.fn()}
          routeLoading={false}
          routeError={null}
          routeResult={result as any}
        />
      )
      
      expect(screen.getByText('15.50 km')).toBeInTheDocument()
      expect(screen.getByText('30.2')).toBeInTheDocument()
      expect(screen.getByText('45.1')).toBeInTheDocument()
      expect(screen.getByText('MEDIUM')).toBeInTheDocument()
    })

    it('15-17. No-route error is displayed correctly', () => {
      render(
        <RoutePlannerPanel 
          origin={[26.1, 92.1]} 
          destination={[26.2, 92.2]} 
          selectingMode={null} 
          setSelectingMode={vi.fn()}
          onCalculateRoute={vi.fn()}
          routeLoading={false}
          routeError="SNAP_FAILED: Coordinates too far from nearest road"
          routeResult={null}
        />
      )
      
      expect(screen.getByText(/SNAP_FAILED: Coordinates too far from nearest road/i)).toBeInTheDocument()
    })

    it('18. Loading state prevents duplicate requests', () => {
      render(
        <RoutePlannerPanel 
          origin={[26.1, 92.1]} 
          destination={[26.2, 92.2]} 
          selectingMode={null} 
          setSelectingMode={vi.fn()}
          onCalculateRoute={vi.fn()}
          routeLoading={true}
          routeError={null}
          routeResult={null}
        />
      )
      
      const calcBtn = screen.getByText('Calculating...').closest('button')!
      expect(calcBtn).toBeDisabled()
    })
  })
})
