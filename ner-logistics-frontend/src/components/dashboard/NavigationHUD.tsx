import React from 'react'
import { NavigationProgress, ManeuverStep } from '../../lib/navigation'
import { 
  Navigation, 
  Volume2, 
  VolumeX, 
  Compass, 
  LocateFixed, 
  X, 
  AlertTriangle, 
  Clock, 
  Gauge, 
  Route as RouteIcon,
  Play,
  Pause
} from 'lucide-react'

interface NavigationHUDProps {
  progress: NavigationProgress
  isNavigating: boolean
  onStopNavigation: () => void
  isVoiceMuted: boolean
  onToggleVoice: () => void
  isSimulationMode: boolean
  onToggleSimulationMode: () => void
  isSimulationPaused?: boolean
  onToggleSimulationPause?: () => void
  onRecenter: () => void
  isAutoFollow: boolean
}

function getManeuverIcon(type?: string) {
  switch (type) {
    case 'left':
      return <span className="text-3xl font-black">⬅️</span>
    case 'slight-left':
      return <span className="text-3xl font-black">↖️</span>
    case 'right':
      return <span className="text-3xl font-black">➡️</span>
    case 'slight-right':
      return <span className="text-3xl font-black">↗️</span>
    case 'u-turn':
      return <span className="text-3xl font-black">↩️</span>
    case 'destination':
      return <span className="text-3xl font-black">🏁</span>
    default:
      return <span className="text-3xl font-black">⬆️</span>
  }
}

export const NavigationHUD: React.FC<NavigationHUDProps> = ({
  progress,
  isNavigating,
  onStopNavigation,
  isVoiceMuted,
  onToggleVoice,
  isSimulationMode,
  onToggleSimulationMode,
  isSimulationPaused = false,
  onToggleSimulationPause,
  onRecenter,
  isAutoFollow,
}) => {
  if (!isNavigating) return null

  const next = progress.nextManeuver
  const isArrived = next?.type === 'destination' || (progress.totalDistanceRemainingKm <= 0.0 && progress.distanceToNextTurnMeters <= 20)
  const isImminent = !isArrived && progress.distanceToNextTurnMeters <= 45 && next?.type !== 'straight'
  const distFormatted =
    progress.distanceToNextTurnMeters >= 1000
      ? `${(progress.distanceToNextTurnMeters / 1000).toFixed(1)} km`
      : `${progress.distanceToNextTurnMeters} m`

  return (
    <div className="pointer-events-none absolute inset-0 z-[500] flex flex-col justify-between p-3 sm:p-5">
      
      {/* ── TOP MANEUVER / INSTRUCTION BANNER ───────────────────────────── */}
      <div className="pointer-events-auto flex flex-col gap-2 max-w-lg w-full mx-auto">
        <div className="bg-slate-900/95 text-white backdrop-blur-md rounded-2xl p-4 shadow-2xl border border-slate-700/80 flex items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            <div className={`flex items-center justify-center w-14 h-14 rounded-xl border text-white shadow-inner shrink-0 transition-all ${
              isArrived
                ? 'bg-emerald-500/30 border-emerald-400 scale-105 shadow-emerald-500/30 shadow-lg'
                : isImminent
                  ? 'bg-amber-500/30 border-amber-400 scale-105 shadow-amber-500/30 shadow-lg'
                  : 'bg-emerald-600/30 border-emerald-500/40'
            }`}>
              {getManeuverIcon(next?.type)}
            </div>
            <div>
              <div className="text-2xl font-black tracking-tight text-white flex items-baseline gap-2">
                <span>
                  {isArrived
                    ? 'Destination Arrived'
                    : isImminent
                      ? 'Turn Now'
                      : `In ${distFormatted}`}
                </span>
                <span className={`text-xs px-2 py-0.5 rounded-full font-semibold border ${
                  isArrived
                    ? 'bg-emerald-500/30 text-emerald-300 border-emerald-400'
                    : isImminent
                      ? 'bg-amber-500/30 text-amber-300 border-amber-400 animate-pulse'
                      : 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30'
                }`}>
                  {isArrived ? 'ARRIVED' : (next?.type?.replace('-', ' ').toUpperCase() || 'STRAIGHT')}
                </span>
              </div>
              <p className="text-sm font-semibold text-slate-200 mt-0.5 line-clamp-1">
                {isArrived
                  ? 'You have safely reached your destination.'
                  : isImminent
                    ? `${next?.instruction} now`
                    : (next?.instruction || 'Follow the highlighted corridor')}
              </p>
              <p className="text-xs text-slate-400 flex items-center gap-1.5 mt-0.5">
                <Compass className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                <span>Heading: {Math.round(progress.heading)}°</span>
                <span className="opacity-40">•</span>
                <span>{next?.roadName || 'NER Highway'}</span>
              </p>
            </div>
          </div>

          {/* Quick action buttons */}
          <div className="flex flex-col gap-1.5 shrink-0">
            <button
              onClick={onToggleVoice}
              title={isVoiceMuted ? 'Unmute voice guidance' : 'Mute voice guidance'}
              className="p-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 transition-colors border border-slate-700"
            >
              {isVoiceMuted ? <VolumeX className="w-4 h-4 text-red-400" /> : <Volume2 className="w-4 h-4 text-emerald-400" />}
            </button>
            <button
              onClick={onStopNavigation}
              title="Exit navigation"
              className="p-2 rounded-lg bg-red-600/80 hover:bg-red-600 text-white transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* ── PROXIMITY HAZARD WARNING CHIME (BRIDGE / LANDSLIDE) ───────── */}
        {progress.upcomingBridgeAlert && (
          <div className="animate-bounce bg-amber-500 text-slate-950 font-bold p-3 rounded-xl shadow-xl border-2 border-amber-300 flex items-center justify-between gap-3 text-xs sm:text-sm">
            <div className="flex items-center gap-2.5">
              <AlertTriangle className="w-5 h-5 shrink-0 text-slate-950 fill-amber-300" />
              <div>
                <span className="uppercase tracking-wider font-black">
                  Hazard Ahead in {progress.upcomingBridgeAlert.distanceMeters} m:
                </span>{' '}
                <span>
                  {progress.upcomingBridgeAlert.bridgeName} —{' '}
                  {progress.upcomingBridgeAlert.cause || progress.upcomingBridgeAlert.condition}
                </span>
              </div>
            </div>
            <span className="bg-slate-950 text-amber-400 px-2 py-0.5 rounded text-[11px] shrink-0 font-bold">
              SLOW DOWN
            </span>
          </div>
        )}

        {/* Off Route Warning */}
        {progress.isOffRoute && (
          <div className="bg-red-600 text-white font-semibold p-2.5 rounded-xl shadow-lg border border-red-400 flex items-center gap-2 text-xs">
            <AlertTriangle className="w-4 h-4 shrink-0" />
            <span>Off designated safe corridor. Re-centering on route...</span>
          </div>
        )}
      </div>

      {/* ── BOTTOM HUD TELEMETRY BAR ────────────────────────────────────── */}
      <div className="pointer-events-auto max-w-2xl w-full mx-auto">
        <div className="bg-slate-900/95 text-white backdrop-blur-md rounded-2xl p-3.5 shadow-2xl border border-slate-700/80 flex flex-wrap items-center justify-between gap-3 text-xs">
          
          {/* Speed & Direction */}
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2 bg-slate-800/80 px-3 py-1.5 rounded-xl border border-slate-700">
              <Gauge className="w-4 h-4 text-emerald-400" />
              <div>
                <span className="text-base font-black text-white">{Math.round(progress.speedKmh)}</span>
                <span className="text-[10px] text-slate-400 ml-1">km/h</span>
              </div>
            </div>

            <div className="flex items-center gap-2 bg-slate-800/80 px-3 py-1.5 rounded-xl border border-slate-700">
              <RouteIcon className="w-4 h-4 text-blue-400" />
              <div>
                <span className="text-base font-black text-white">{progress.totalDistanceRemainingKm}</span>
                <span className="text-[10px] text-slate-400 ml-1">km left</span>
              </div>
            </div>

            <div className="flex items-center gap-2 bg-slate-800/80 px-3 py-1.5 rounded-xl border border-slate-700">
              <Clock className="w-4 h-4 text-amber-400" />
              <div>
                <span className="text-base font-black text-white">{progress.estimatedTimeRemainingMinutes}</span>
                <span className="text-[10px] text-slate-400 ml-1">min</span>
              </div>
            </div>
          </div>

          {/* Controls: Mode Toggle, Recenter, End */}
          <div className="flex items-center gap-2">
            {/* Simulation Play/Pause (only in sim mode) */}
            {isSimulationMode && onToggleSimulationPause && (
              <button
                onClick={onToggleSimulationPause}
                className="px-2.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 flex items-center gap-1 font-medium transition-colors"
                title={isSimulationPaused ? 'Resume simulated driving' : 'Pause simulated driving'}
              >
                {isSimulationPaused ? <Play className="w-3.5 h-3.5 text-emerald-400" /> : <Pause className="w-3.5 h-3.5 text-amber-400" />}
                <span className="text-[11px]">{isSimulationPaused ? 'Resume' : 'Pause'}</span>
              </button>
            )}

            {/* GPS Source Toggle */}
            <button
              onClick={onToggleSimulationMode}
              className={`px-3 py-1.5 rounded-lg font-semibold flex items-center gap-1.5 transition-all text-[11px] ${
                isSimulationMode
                  ? 'bg-purple-600/30 text-purple-300 border border-purple-500/50 hover:bg-purple-600/40'
                  : 'bg-emerald-600/30 text-emerald-300 border border-emerald-500/50 hover:bg-emerald-600/40'
              }`}
            >
              <span className={`w-2 h-2 rounded-full ${isSimulationMode ? 'bg-purple-400' : 'bg-emerald-400 animate-ping'}`} />
              <span>{isSimulationMode ? '🎮 Sim Drive' : '📡 Device GPS'}</span>
            </button>

            {/* Recenter / Auto-follow toggle */}
            <button
              onClick={onRecenter}
              className={`p-2 rounded-lg border transition-colors ${
                isAutoFollow
                  ? 'bg-emerald-600 text-white border-emerald-500'
                  : 'bg-slate-800 text-slate-300 border-slate-700 hover:bg-slate-700'
              }`}
              title="Keep map centered on vehicle"
            >
              <LocateFixed className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>

    </div>
  )
}
