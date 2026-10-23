import { useEffect, useState } from 'react'

interface CookingAnimationProps {
  /** Optional Spanish caption shown under the pot. */
  label?: string
}

const DEFAULT_LABEL = 'Preparando tu plan de comidas...'

/**
 * Reads the user's `prefers-reduced-motion` system preference and keeps it in
 * sync if it changes while the component is mounted. Returns `true` when the
 * user has asked the OS to minimize non-essential motion.
 */
function usePrefersReducedMotion(): boolean {
  const query = '(prefers-reduced-motion: reduce)'

  const [reduced, setReduced] = useState<boolean>(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return false
    return window.matchMedia(query).matches
  })

  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return
    const mql = window.matchMedia(query)
    const onChange = (e: MediaQueryListEvent) => setReduced(e.matches)
    // addEventListener is the modern API; older Safari only has addListener.
    if (mql.addEventListener) {
      mql.addEventListener('change', onChange)
      return () => mql.removeEventListener('change', onChange)
    }
    mql.addListener(onChange)
    return () => mql.removeListener(onChange)
  }, [])

  return reduced
}

/**
 * Themed "cooking / meal preparation" loading state shown in the Goal Wizard's
 * diet step while the diet phase plan is being derived. One orchestrated moment:
 * steam rising from a healthy-cooking pot over a quiet shimmer progress bar.
 *
 * Accessibility (Req 6.6): when the user prefers reduced motion, a static
 * equivalent is rendered — the same pot icon with a settled caption and a
 * non-animated progress indicator, with no movement at all. The region is
 * announced to assistive tech via role="status" / aria-live="polite".
 */
export function CookingAnimation({ label = DEFAULT_LABEL }: CookingAnimationProps) {
  const reducedMotion = usePrefersReducedMotion()
  const animate = !reducedMotion

  return (
    <div
      role="status"
      aria-live="polite"
      className="flex flex-col items-center justify-center gap-5 py-8 select-none"
    >
      {/* Scoped keyframes. Only referenced when motion is allowed, so the static
          branch below never moves even though the rules exist in the document. */}
      <style>{`
        @keyframes cook-steam {
          0%   { opacity: 0; transform: translateY(4px) scaleX(1); }
          25%  { opacity: 0.75; }
          70%  { opacity: 0.35; }
          100% { opacity: 0; transform: translateY(-16px) scaleX(1.35); }
        }
        @keyframes cook-bob {
          0%, 100% { transform: translateY(0); }
          50%      { transform: translateY(-1.5px); }
        }
        @keyframes cook-shimmer {
          0%   { transform: translateX(-110%); }
          100% { transform: translateX(240%); }
        }
      `}</style>

      <svg
        viewBox="0 0 120 96"
        className="w-28 h-auto"
        role="img"
        aria-hidden="true"
        preserveAspectRatio="xMidYMid meet"
      >
        {/* Steam — three wisps rising on staggered loops. Hidden entirely for
            reduced motion so the icon reads as a calm, static pot. */}
        {animate && (
          <g
            className="text-accent"
            stroke="currentColor"
            strokeWidth={3.2}
            strokeLinecap="round"
            fill="none"
            opacity={0.9}
          >
            <path
              d="M44 34 q-6 -8 0 -16"
              style={{ animation: 'cook-steam 2.4s ease-in-out infinite', transformOrigin: '44px 26px' }}
            />
            <path
              d="M60 32 q6 -9 0 -18"
              style={{ animation: 'cook-steam 2.4s ease-in-out 0.6s infinite', transformOrigin: '60px 23px' }}
            />
            <path
              d="M76 34 q-6 -8 0 -16"
              style={{ animation: 'cook-steam 2.4s ease-in-out 1.2s infinite', transformOrigin: '76px 26px' }}
            />
          </g>
        )}

        {/* Pot — gentle bob while cooking, perfectly still at rest. */}
        <g
          style={animate ? { animation: 'cook-bob 2.4s ease-in-out infinite' } : undefined}
        >
          {/* Lid */}
          <ellipse cx="60" cy="46" rx="30" ry="5.5" className="fill-bg-elevated" />
          <circle cx="60" cy="40.5" r="3.2" className="fill-accent" />
          {/* Body */}
          <path
            d="M30 48 h60 l-4 30 a10 10 0 0 1 -10 9 H44 a10 10 0 0 1 -10 -9 Z"
            className="fill-bg-surface stroke-bg-border"
            strokeWidth={2}
          />
          {/* Fresh-food line inside the pot — the healthy/athletic cue (green). */}
          <path
            d="M38 60 q22 7 44 0"
            className="text-success"
            stroke="currentColor"
            strokeWidth={2.5}
            strokeLinecap="round"
            fill="none"
            opacity={0.85}
          />
          {/* Handles */}
          <path
            d="M30 52 q-9 1 -9 7"
            className="text-text-secondary"
            stroke="currentColor"
            strokeWidth={2.5}
            strokeLinecap="round"
            fill="none"
          />
          <path
            d="M90 52 q9 1 9 7"
            className="text-text-secondary"
            stroke="currentColor"
            strokeWidth={2.5}
            strokeLinecap="round"
            fill="none"
          />
        </g>
      </svg>

      <p className="text-sm text-text-secondary text-center max-w-[14rem] leading-snug">
        {label}
      </p>

      {/* Progress indicator. Motion → an indeterminate shimmer sweeping across the
          track. Reduced motion → a static, settled fill (no movement) that still
          reads as "in progress". */}
      <div
        className="relative h-1.5 w-40 overflow-hidden rounded-full bg-bg-elevated"
        aria-hidden="true"
      >
        {animate ? (
          <span
            className="absolute inset-y-0 left-0 w-1/3 rounded-full bg-accent"
            style={{ animation: 'cook-shimmer 1.6s ease-in-out infinite' }}
          />
        ) : (
          <span className="absolute inset-y-0 left-0 w-2/3 rounded-full bg-accent" />
        )}
      </div>
    </div>
  )
}
