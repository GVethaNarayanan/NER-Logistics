import React, { createContext, useContext, useState, useEffect, useMemo, useCallback } from 'react'
import { infrastructureApi, StateBase } from '../api/infrastructure'

// ── Types ────────────────────────────────────────────────────────────────────
interface RegionContextType {
  // Registry data
  registryStates: StateBase[]
  registryLoading: boolean
  registryError: string | null

  // Selected IDs
  selectedStateId: number | null
  selectedDistrictId: number | null

  // Derived objects
  activeState: StateBase | undefined
  availableDistricts: { id: number; name: string }[]
  activeDistrict: { id: number; name: string } | undefined

  // Setters
  setSelectedStateId: (id: number | null) => void
  setSelectedDistrictId: (id: number | null) => void
}

const RegionContext = createContext<RegionContextType | null>(null)

// ── Storage helpers ──────────────────────────────────────────────────────────
const STORAGE_KEY_STATE = 'ner_selected_state_id'
const STORAGE_KEY_DISTRICT = 'ner_selected_district_id'

function loadFromStorage(key: string): number | null {
  try {
    const raw = sessionStorage.getItem(key)
    if (raw === null) return null
    const num = parseInt(raw, 10)
    return isNaN(num) ? null : num
  } catch {
    return null
  }
}

function saveToStorage(key: string, value: number | null) {
  try {
    if (value === null) {
      sessionStorage.removeItem(key)
    } else {
      sessionStorage.setItem(key, String(value))
    }
  } catch {
    // sessionStorage unavailable — silently ignore
  }
}

// ── Provider ─────────────────────────────────────────────────────────────────
export const RegionProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [registryStates, setRegistryStates] = useState<StateBase[]>([])
  const [registryLoading, setRegistryLoading] = useState(true)
  const [registryError, setRegistryError] = useState<string | null>(null)

  const [selectedStateId, setSelectedStateIdRaw] = useState<number | null>(null)
  const [selectedDistrictId, setSelectedDistrictIdRaw] = useState<number | null>(null)

  // Clear storage on fresh session so it doesn't force a pre-selected region
  useEffect(() => {
    try {
      sessionStorage.removeItem(STORAGE_KEY_STATE)
      sessionStorage.removeItem(STORAGE_KEY_DISTRICT)
    } catch {
      // ignore
    }
  }, [])

  // Persist to sessionStorage on change
  const setSelectedStateId = useCallback((id: number | null) => {
    setSelectedStateIdRaw(id)
    saveToStorage(STORAGE_KEY_STATE, id)
    // Clear district when state changes
    setSelectedDistrictIdRaw(null)
    saveToStorage(STORAGE_KEY_DISTRICT, null)
  }, [])

  const setSelectedDistrictId = useCallback((id: number | null) => {
    setSelectedDistrictIdRaw(id)
    saveToStorage(STORAGE_KEY_DISTRICT, id)
  }, [])

  // Derived values
  const activeState = useMemo(
    () => registryStates.find(s => s.id === selectedStateId),
    [registryStates, selectedStateId]
  )

  const availableDistricts = useMemo(
    () => (activeState ? activeState.districts : []),
    [activeState]
  )

  const activeDistrict = useMemo(
    () => availableDistricts.find(d => d.id === selectedDistrictId),
    [availableDistricts, selectedDistrictId]
  )

  // Load registry once on mount without auto-selecting any state/district
  useEffect(() => {
    let isMounted = true
    setRegistryLoading(true)

    infrastructureApi.getRegistry()
      .then(res => {
        if (!isMounted) return
        setRegistryStates(res.states)
        // Keep selectedStateId and selectedDistrictId as null on initial entry
      })
      .catch(err => {
        if (isMounted) setRegistryError(err.message || 'Failed to load registry')
      })
      .finally(() => {
        if (isMounted) setRegistryLoading(false)
      })

    return () => { isMounted = false }
  }, [])

  const value: RegionContextType = {
    registryStates,
    registryLoading,
    registryError,
    selectedStateId,
    selectedDistrictId,
    activeState,
    availableDistricts,
    activeDistrict,
    setSelectedStateId,
    setSelectedDistrictId,
  }

  return <RegionContext.Provider value={value}>{children}</RegionContext.Provider>
}

// ── Hook ─────────────────────────────────────────────────────────────────────
export function useRegion(): RegionContextType {
  const ctx = useContext(RegionContext)
  if (!ctx) throw new Error('useRegion must be used within <RegionProvider>')
  return ctx
}
