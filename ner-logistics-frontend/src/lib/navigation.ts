/**
 * Navigation & Turn-by-Turn Guidance Engine
 * Provides bearing computation, road-following maneuver extraction,
 * dynamic terrain/turn-based speed modeling with cornering recovery,
 * exact remaining trip metrics, and stutter-free voice guidance.
 */

export interface ManeuverStep {
  id: string
  instruction: string
  type: 'straight' | 'slight-left' | 'left' | 'slight-right' | 'right' | 'u-turn' | 'destination'
  distanceMeters: number
  roadName: string
  lat: number
  lon: number
  bearing: number
  coordIndex: number
  cumulativeDistMeters: number
  bridgeWarning?: string
}

export interface NavigationProgress {
  currentLat: number
  currentLon: number
  heading: number
  speedKmh: number
  currentStepIndex: number
  distanceToNextTurnMeters: number
  nextManeuver: ManeuverStep | null
  totalDistanceRemainingKm: number
  estimatedTimeRemainingMinutes: number
  upcomingBridgeAlert: {
    bridgeName: string
    condition: string
    cause?: string
    distanceMeters: number
  } | null
  isOffRoute: boolean
}

/**
 * Calculate bearing angle in degrees [0, 360) from point A to B
 */
export function calculateBearing(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const toRad = (deg: number) => (deg * Math.PI) / 180
  const toDeg = (rad: number) => (rad * 180) / Math.PI

  const phi1 = toRad(lat1)
  const phi2 = toRad(lat2)
  const deltaLambda = toRad(lon2 - lon1)

  const y = Math.sin(deltaLambda) * Math.cos(phi2)
  const x =
    Math.cos(phi1) * Math.sin(phi2) -
    Math.sin(phi1) * Math.cos(phi2) * Math.cos(deltaLambda)

  const theta = Math.atan2(y, x)
  return (toDeg(theta) + 360) % 360
}

/**
 * Haversine distance in meters between two lat/lon coordinates
 */
export function haversineMeters(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const R = 6371000 // meters
  const dLat = ((lat2 - lat1) * Math.PI) / 180
  const dLon = ((lon2 - lon1) * Math.PI) / 180
  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos((lat1 * Math.PI) / 180) *
      Math.cos((lat2 * Math.PI) / 180) *
      Math.sin(dLon / 2) *
      Math.sin(dLon / 2)
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a))
  return R * c
}

/**
 * Classify turning angle difference into human-friendly maneuver
 */
function classifyTurn(diffAngle: number): 'straight' | 'slight-left' | 'left' | 'slight-right' | 'right' | 'u-turn' {
  let angle = diffAngle
  while (angle > 180) angle -= 360
  while (angle < -180) angle += 360

  if (Math.abs(angle) < 22) return 'straight'
  if (angle >= 22 && angle < 50) return 'slight-right'
  if (angle >= 50 && angle <= 135) return 'right'
  if (angle <= -22 && angle > -50) return 'slight-left'
  if (angle <= -50 && angle >= -135) return 'left'
  return 'u-turn'
}

/**
 * Generate Turn-by-Turn Maneuvers along the road polyline
 */
export function generateManeuvers(
  coordinates: [number, number][], // [lon, lat] from GeoJSON LineString
  bridges: any[] = []
): ManeuverStep[] {
  if (!coordinates || coordinates.length < 2) return []

  const maneuvers: ManeuverStep[] = []
  let cumulativeDist = 0

  // Precompute cumulative distances along polyline
  const cumDists: number[] = [0]
  for (let i = 0; i < coordinates.length - 1; i++) {
    cumulativeDist += haversineMeters(
      coordinates[i][1],
      coordinates[i][0],
      coordinates[i + 1][1],
      coordinates[i + 1][0]
    )
    cumDists.push(cumulativeDist)
  }

  let prevBearing = calculateBearing(
    coordinates[0][1],
    coordinates[0][0],
    coordinates[1][1],
    coordinates[1][0]
  )

  // Initial departure step
  maneuvers.push({
    id: 'step-0',
    instruction: 'Start driving along the route',
    type: 'straight',
    distanceMeters: 0,
    roadName: 'Main Highway Corridor',
    lat: coordinates[0][1],
    lon: coordinates[0][0],
    bearing: prevBearing,
    coordIndex: 0,
    cumulativeDistMeters: 0,
  })

  let lastManeuverCoordIdx = 0

  for (let i = 1; i < coordinates.length - 1; i++) {
    const lat1 = coordinates[i][1]
    const lon1 = coordinates[i][0]
    const lat2 = coordinates[i + 1][1]
    const lon2 = coordinates[i + 1][0]

    const currentBearing = calculateBearing(lat1, lon1, lat2, lon2)
    let turnAngle = currentBearing - prevBearing
    while (turnAngle > 180) turnAngle -= 360
    while (turnAngle < -180) turnAngle += 360

    const distFromLastTurn = cumDists[i] - cumDists[lastManeuverCoordIdx]

    // Trigger turn when angle change is significant and at least 250m has elapsed
    if (Math.abs(turnAngle) >= 28 && distFromLastTurn >= 250) {
      const turnType = classifyTurn(turnAngle)
      let turnText = 'Continue straight'
      if (turnType === 'right') turnText = 'Turn right'
      else if (turnType === 'slight-right') turnText = 'Bear right'
      else if (turnType === 'left') turnText = 'Turn left'
      else if (turnType === 'slight-left') turnText = 'Bear left'
      else if (turnType === 'u-turn') turnText = 'Make a U-turn'

      maneuvers[maneuvers.length - 1].distanceMeters = Math.round(distFromLastTurn)

      const nearbyBridge = bridges.find(
        b => haversineMeters(lat1, lon1, b.latitude, b.longitude) < 500
      )

      maneuvers.push({
        id: `step-${maneuvers.length}`,
        instruction: turnText,
        type: turnType,
        distanceMeters: 0,
        roadName: nearbyBridge?.name ? `Bridge: ${nearbyBridge.name}` : 'Regional Highway',
        lat: lat1,
        lon: lon1,
        bearing: currentBearing,
        coordIndex: i,
        cumulativeDistMeters: cumDists[i],
        bridgeWarning:
          nearbyBridge && nearbyBridge.condition !== 'good'
            ? `Bridge ahead: ${nearbyBridge.name || 'Crossing'} (${nearbyBridge.cause || nearbyBridge.condition})`
            : undefined,
      })

      lastManeuverCoordIdx = i
      prevBearing = currentBearing
    }
  }

  // Final destination step
  const finalCoord = coordinates[coordinates.length - 1]
  const lastDist = cumDists[cumDists.length - 1] - cumDists[lastManeuverCoordIdx]
  if (maneuvers.length > 0) {
    maneuvers[maneuvers.length - 1].distanceMeters = Math.round(lastDist)
  }

  maneuvers.push({
    id: 'step-destination',
    instruction: 'Destination Arrived',
    type: 'destination',
    distanceMeters: 0,
    roadName: 'Destination',
    lat: finalCoord[1],
    lon: finalCoord[0],
    bearing: prevBearing,
    coordIndex: coordinates.length - 1,
    cumulativeDistMeters: cumDists[cumDists.length - 1],
  })

  return maneuvers
}

/**
 * Dynamically computes target driver speed (km/h) based on:
 * - Proximity to upcoming turn (brakes gently down to 18-24 km/h)
 * - Cornering recovery zone (stays slow for 60m after the turn, preventing premature acceleration)
 * - Proximity to bridge hazards (caps at 22-26 km/h)
 * - Open highway cruising (accelerates smoothly to 55-65 km/h)
 */
export function calculateDynamicSpeed(
  distToTurnMeters: number,
  turnType: string,
  isBridgeHazardNear: boolean,
  distSinceLastTurnMeters: number = 999,
  currentSpeedKmh: number = 40
): number {
  let targetSpeed = 58 // Default highway cruising speed

  if (isBridgeHazardNear) {
    targetSpeed = 24 // Safe crawl across hazardous or scour bridges
  } else if (distToTurnMeters <= 40) {
    // Actively entering or inside the turn
    targetSpeed = turnType === 'u-turn' ? 14 : 20
  } else if (distSinceLastTurnMeters < 60) {
    // Post-turn recovery / corner exit: vehicle stays slow (20-25 km/h) and ramps up
    const recoveryProgress = distSinceLastTurnMeters / 60
    targetSpeed = Math.round(20 + recoveryProgress * 15) // 20 km/h -> 35 km/h
  } else if (distSinceLastTurnMeters < 120) {
    // Gradual acceleration back to highway cruise
    const rampProgress = (distSinceLastTurnMeters - 60) / 60
    targetSpeed = Math.round(35 + rampProgress * 23) // 35 km/h -> 58 km/h
  } else if (distToTurnMeters <= 120) {
    targetSpeed = 28 // Approach braking
  } else if (distToTurnMeters <= 280) {
    targetSpeed = 38 // Early deceleration
  } else {
    targetSpeed = 58 // Open highway corridor
  }

  // Smooth acceleration / deceleration (physics smoothing)
  const smoothing = targetSpeed < currentSpeedKmh ? 0.35 : 0.2 // Brakes faster than accelerates
  const smoothed = currentSpeedKmh + (targetSpeed - currentSpeedKmh) * smoothing
  return Math.round(smoothed)
}

/**
 * Calculate dynamic navigation progress given current location and route
 */
export function calculateNavigationProgress(
  currentLat: number,
  currentLon: number,
  coordinates: [number, number][],
  maneuvers: ManeuverStep[],
  bridges: any[] = [],
  currentSpeedKmh: number = 40,
  totalRouteDistanceKm?: number,
  totalRouteDurationMinutes?: number
): NavigationProgress {
  if (!coordinates || coordinates.length === 0) {
    return {
      currentLat,
      currentLon,
      heading: 0,
      speedKmh: currentSpeedKmh,
      currentStepIndex: 0,
      distanceToNextTurnMeters: 0,
      nextManeuver: null,
      totalDistanceRemainingKm: 0,
      estimatedTimeRemainingMinutes: 0,
      upcomingBridgeAlert: null,
      isOffRoute: false,
    }
  }

  // 1. Precompute cumulative distances along polyline
  const cumDists: number[] = [0]
  for (let i = 0; i < coordinates.length - 1; i++) {
    cumDists.push(
      cumDists[i] +
        haversineMeters(
          coordinates[i][1],
          coordinates[i][0],
          coordinates[i + 1][1],
          coordinates[i + 1][0]
        )
    )
  }

  // 2. Find nearest coordinate on route polyline
  let minDistanceMeters = Infinity
  let nearestIdx = 0

  for (let i = 0; i < coordinates.length; i++) {
    const dist = haversineMeters(currentLat, currentLon, coordinates[i][1], coordinates[i][0])
    if (dist < minDistanceMeters) {
      minDistanceMeters = dist
      nearestIdx = i
    }
  }

  const isOffRoute = minDistanceMeters > 350

  // 3. Compute Heading along road direction
  let heading = 0
  if (nearestIdx < coordinates.length - 1) {
    heading = calculateBearing(
      coordinates[nearestIdx][1],
      coordinates[nearestIdx][0],
      coordinates[nearestIdx + 1][1],
      coordinates[nearestIdx + 1][0]
    )
  }

  // 4. Find next active maneuver step ahead of nearestIdx and previous turn
  let nextManeuver: ManeuverStep | null = null
  let activeStepIndex = 0
  let distanceToNextTurnMeters = 0
  let distSinceLastTurnMeters = 999

  for (let m = 0; m < maneuvers.length; m++) {
    const step = maneuvers[m]
    if (step.coordIndex > nearestIdx) {
      nextManeuver = step
      activeStepIndex = m
      // Exact road polyline distance to this turn
      distanceToNextTurnMeters = Math.max(10, Math.round(cumDists[step.coordIndex] - cumDists[nearestIdx]))
      
      // Look at previous turn to check if we are in the cornering recovery zone
      if (m > 0 && maneuvers[m - 1].coordIndex <= nearestIdx) {
        distSinceLastTurnMeters = Math.round(cumDists[nearestIdx] - cumDists[maneuvers[m - 1].coordIndex])
      }
      break
    }
  }

  // If at or past last maneuver, target destination
  if (!nextManeuver && maneuvers.length > 0) {
    nextManeuver = maneuvers[maneuvers.length - 1]
    activeStepIndex = maneuvers.length - 1
    distanceToNextTurnMeters = Math.max(0, Math.round(cumDists[cumDists.length - 1] - cumDists[nearestIdx]))
  }

  // 5. Proximity Hazard Alert Check (within 1.5 km)
  let upcomingBridgeAlert = null
  for (const b of bridges) {
    const bDist = haversineMeters(currentLat, currentLon, b.latitude, b.longitude)
    if (bDist > 30 && bDist <= 1500 && b.condition !== 'good') {
      upcomingBridgeAlert = {
        bridgeName: b.name || 'River Bridge Crossing',
        condition: b.condition,
        cause: b.cause,
        distanceMeters: Math.round(bDist),
      }
      break
    }
  }

  // 6. Dynamic Speed Calculation (with cornering recovery)
  const isHazardNear = upcomingBridgeAlert !== null && upcomingBridgeAlert.distanceMeters < 500
  const speedKmh = calculateDynamicSpeed(
    distanceToNextTurnMeters,
    nextManeuver?.type || 'straight',
    isHazardNear,
    distSinceLastTurnMeters,
    currentSpeedKmh
  )

  // 7. Synchronized Distance Remaining & ETA
  const totalPoints = coordinates.length
  const progressRatio = totalPoints > 1 ? nearestIdx / (totalPoints - 1) : 0
  const remainingRatio = Math.max(0, 1 - progressRatio)

  let remainingKm: number
  let remainingMinutes: number

  if (totalRouteDistanceKm && totalRouteDistanceKm > 0) {
    remainingKm = Math.round(remainingRatio * totalRouteDistanceKm * 10) / 10
    const baseDuration = totalRouteDurationMinutes || Math.round((totalRouteDistanceKm / 40) * 60)
    remainingMinutes = Math.max(0, Math.round(remainingRatio * baseDuration))
  } else {
    const remainingMeters = Math.max(0, cumDists[cumDists.length - 1] - cumDists[nearestIdx])
    remainingKm = Math.round((remainingMeters / 1000) * 10) / 10
    const effectiveSpeed = Math.max(25, speedKmh)
    remainingMinutes = Math.max(0, Math.round((remainingKm / effectiveSpeed) * 60))
  }

  return {
    currentLat,
    currentLon,
    heading,
    speedKmh,
    currentStepIndex: activeStepIndex,
    distanceToNextTurnMeters,
    nextManeuver,
    totalDistanceRemainingKm: remainingKm,
    estimatedTimeRemainingMinutes: remainingMinutes,
    upcomingBridgeAlert,
    isOffRoute,
  }
}

/**
 * Precision GPS Voice Navigation Announcer
 * Prevents mid-sentence cutoff by respecting active audio synthesis.
 * Uses concise driving prompts so sentences finish cleanly and naturally.
 */
class NavigationVoiceAnnouncer {
  private spokenAdvance = new Set<string>()
  private spokenImminent = new Set<string>()
  private spokenHazards = new Set<string>()
  private isSpeaking = false

  public reset() {
    this.spokenAdvance.clear()
    this.spokenImminent.clear()
    this.spokenHazards.clear()
    this.isSpeaking = false
    if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
      window.speechSynthesis.cancel()
    }
  }

  public checkAndSpeak(progress: NavigationProgress, muted: boolean = false) {
    if (muted || typeof window === 'undefined' || !('speechSynthesis' in window)) return

    // Never interrupt an active utterance mid-word to prevent voice cutoff/stutter!
    if (this.isSpeaking || window.speechSynthesis.speaking) return

    const { nextManeuver, distanceToNextTurnMeters, upcomingBridgeAlert } = progress

    // 1. Imminent Turn Alert (20m to 55m before the turn)
    if (nextManeuver && nextManeuver.type !== 'straight') {
      const stepKey = `${nextManeuver.id}-imminent`
      if (distanceToNextTurnMeters <= 55 && distanceToNextTurnMeters >= 15) {
        if (!this.spokenImminent.has(stepKey)) {
          this.spokenImminent.add(stepKey)
          const prompt = nextManeuver.type === 'destination' 
            ? 'Arriving at destination.' 
            : `${nextManeuver.instruction} now.`
          this.speak(prompt)
          return
        }
      }
    }

    // 2. Advance Turn Warning (200m to 350m before the turn)
    if (nextManeuver && nextManeuver.type !== 'straight') {
      const stepKey = `${nextManeuver.id}-advance`
      if (distanceToNextTurnMeters <= 350 && distanceToNextTurnMeters >= 200) {
        if (!this.spokenAdvance.has(stepKey)) {
          this.spokenAdvance.add(stepKey)
          const prompt = `In 300 meters, ${nextManeuver.instruction.toLowerCase()}.`
          this.speak(prompt)
          return
        }
      }
    }

    // 3. Proximity Bridge Hazard Alert (800m to 1200m)
    if (upcomingBridgeAlert) {
      const hazardKey = `${upcomingBridgeAlert.bridgeName}-${upcomingBridgeAlert.condition}`
      if (
        upcomingBridgeAlert.distanceMeters <= 1200 &&
        upcomingBridgeAlert.distanceMeters >= 800
      ) {
        if (!this.spokenHazards.has(hazardKey)) {
          this.spokenHazards.add(hazardKey)
          const prompt = `Caution. Hazard bridge ahead in one kilometer. Reduce speed.`
          this.speak(prompt)
          return
        }
      }
    }
  }

  public speakImmediate(text: string, muted: boolean = false) {
    if (muted || typeof window === 'undefined' || !('speechSynthesis' in window)) return
    this.speak(text)
  }

  private speak(text: string) {
    try {
      this.isSpeaking = true
      const utterance = new SpeechSynthesisUtterance(text)
      utterance.rate = 1.05
      utterance.pitch = 1.0
      utterance.lang = 'en-IN'

      utterance.onend = () => {
        this.isSpeaking = false
      }
      utterance.onerror = () => {
        this.isSpeaking = false
      }

      window.speechSynthesis.speak(utterance)
    } catch (e) {
      console.warn('Speech synthesis error:', e)
      this.isSpeaking = false
    }
  }
}

export const navigationVoice = new NavigationVoiceAnnouncer()
