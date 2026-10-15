import {
  useEffect,
  useReducer,
  useRef,
  useState,
  Dispatch,
  FormEvent,
  ReactNode,
} from 'react'
import {
  goalPlanApi,
  DietPhase,
  PhasePlan,
  TargetRate,
  WizardState,
  WorkoutPlan,
} from '../lib/api'
import { CookingAnimation } from '../components/CookingAnimation'

// User-facing copy is Spanish; identifiers and comments are English.

// ── Equipment catalog ─────────────────────────────────────────────────────────
// Redefined locally (same ids/labels/hints as FitnessPage) so this component does
// not depend on an export that may not exist. ids must match the backend
// EQUIPMENT_CATALOG exactly.
type EquipmentItem = { id: string; label: string; hint: string }

const EQUIPMENT_CATALOG: EquipmentItem[] = [
  { id: 'mancuernas', label: 'Mancuernas', hint: 'Pesas de mano ajustables o fijas' },
  { id: 'barra', label: 'Barra + discos', hint: 'Barra olímpica con discos (peso muerto, remo)' },
  { id: 'banco', label: 'Banco', hint: 'Banco plano o ajustable (press banca)' },
  { id: 'rack', label: 'Rack / jaula', hint: 'Para sentadillas y press con barra pesada' },
  { id: 'barra de dominadas', label: 'Barra de dominadas', hint: 'Pull-ups, chin-ups, colgado' },
  { id: 'barras paralelas', label: 'Barras paralelas', hint: 'Fondos / dips' },
  { id: 'poleas', label: 'Poleas / cable', hint: 'Torre de poleas: jalón, cruces, tríceps' },
  { id: 'kettlebell', label: 'Kettlebell', hint: 'Pesa rusa (swings, goblet)' },
  { id: 'bandas', label: 'Bandas elásticas', hint: 'Bandas de resistencia' },
  { id: 'peso corporal', label: 'Peso corporal', hint: 'Sin equipo: flexiones, plancha, sentadilla libre' },
  { id: 'gimnasio completo', label: 'Gimnasio completo', hint: 'Tengo acceso a todo el equipo de un gimnasio' },
]

// ── Step metadata ──────────────────────────────────────────────────────────────
type Step = WizardState['step']

const STEPS: Step[] = [
  'profile',
  'goal',
  'equipment',
  'diet',
  'training_days',
  'routine',
  'summary',
]

const STEP_LABELS: Record<Step, string> = {
  profile: 'Perfil',
  goal: 'Objetivo',
  equipment: 'Equipo',
  diet: 'Dieta',
  training_days: 'Días',
  routine: 'Rutina',
  summary: 'Resumen',
}

// ── Helpers ──────────────────────────────────────────────────────────────────
function apiError(err: any, fallback: string): string {
  const detail = err?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail) && detail.length > 0 && detail[0]?.msg) return detail[0].msg
  return fallback
}

/**
 * Tracks the user's `prefers-reduced-motion` setting so motion we add here (the
 * routine progress bar) can be disabled. CookingAnimation handles its own.
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
    if (mql.addEventListener) {
      mql.addEventListener('change', onChange)
      return () => mql.removeEventListener('change', onChange)
    }
    mql.addListener(onChange)
    return () => mql.removeListener(onChange)
  }, [])
  return reduced
}

function round(value: number | null | undefined, digits = 0): string {
  if (value == null || Number.isNaN(value)) return '—'
  const factor = 10 ** digits
  return String(Math.round(value * factor) / factor)
}

// The /goal-plan/goal endpoint returns an untyped body; model the shape we read.
interface GoalResponse {
  target_rate: TargetRate | null
  disclaimer: string
}

// ── Captured form data ─────────────────────────────────────────────────────────
// Kept in reducer state so going back to a previous step never discards what the
// user already entered (Req 1.4). Strings mirror the inputs; numbers are parsed
// only on submit.
interface ProfileForm {
  weight_kg: string
  height_cm: string
  age: string
  sex: string
  level: string
  days_per_week: string
  minutes_per_session: string
}

interface GoalForm {
  target_weight_kg: string
  target_date: string
}

const EMPTY_PROFILE: ProfileForm = {
  weight_kg: '',
  height_cm: '',
  age: '',
  sex: '',
  level: 'principiante',
  days_per_week: '3',
  minutes_per_session: '45',
}

// ── Reducer ──────────────────────────────────────────────────────────────────
interface WizardData {
  step: Step
  profileForm: ProfileForm
  goalForm: GoalForm
  equipment: string[]
  trainingDays: string
  // Server-derived results captured as the user progresses.
  targetRate: TargetRate | null
  phasePlan: PhasePlan | null
  routine: WorkoutPlan | null
}

const INITIAL_DATA: WizardData = {
  step: 'profile',
  profileForm: EMPTY_PROFILE,
  goalForm: { target_weight_kg: '', target_date: '' },
  equipment: [],
  trainingDays: '3',
  targetRate: null,
  phasePlan: null,
  routine: null,
}

type Action =
  | { type: 'goto'; step: Step }
  | { type: 'setProfile'; patch: Partial<ProfileForm> }
  | { type: 'setGoal'; patch: Partial<GoalForm> }
  | { type: 'toggleEquipment'; id: string }
  | { type: 'setEquipment'; equipment: string[] }
  | { type: 'setTrainingDays'; value: string }
  | { type: 'setTargetRate'; rate: TargetRate | null }
  | { type: 'setPhasePlan'; plan: PhasePlan | null }
  | { type: 'setRoutine'; routine: WorkoutPlan | null }
  | { type: 'hydrate'; patch: Partial<WizardData> }

function reducer(state: WizardData, action: Action): WizardData {
  switch (action.type) {
    case 'goto':
      return { ...state, step: action.step }
    case 'setProfile':
      return { ...state, profileForm: { ...state.profileForm, ...action.patch } }
    case 'setGoal':
      return { ...state, goalForm: { ...state.goalForm, ...action.patch } }
    case 'toggleEquipment': {
      const equipment = state.equipment.includes(action.id)
        ? state.equipment.filter((e) => e !== action.id)
        : [...state.equipment, action.id]
      return { ...state, equipment }
    }
    case 'setEquipment':
      return { ...state, equipment: action.equipment }
    case 'setTrainingDays':
      return { ...state, trainingDays: action.value }
    case 'setTargetRate':
      return { ...state, targetRate: action.rate }
    case 'setPhasePlan':
      return { ...state, phasePlan: action.plan }
    case 'setRoutine':
      return { ...state, routine: action.routine }
    case 'hydrate':
      return { ...state, ...action.patch }
    default:
      return state
  }
}

// ── Shared UI primitives ─────────────────────────────────────────────────────
function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <label className="text-xs text-text-secondary">{label}</label>
      {children}
    </div>
  )
}

function StepNav({
  onBack,
  nextLabel = 'Continuar',
  busy = false,
  canBack = true,
  nextType = 'submit',
  onNextClick,
}: {
  onBack: () => void
  nextLabel?: string
  busy?: boolean
  canBack?: boolean
  nextType?: 'submit' | 'button'
  onNextClick?: () => void
}) {
  return (
    <div className="flex items-center gap-3 pt-1">
      {canBack && (
        <button type="button" className="btn-ghost text-sm" onClick={onBack} disabled={busy}>
          Atrás
        </button>
      )}
      <button
        type={nextType}
        className="btn-primary text-sm flex-1"
        disabled={busy}
        onClick={nextType === 'button' ? onNextClick : undefined}
      >
        {busy ? 'Guardando...' : nextLabel}
      </button>
    </div>
  )
}

const PHASE_STATUS_LABEL: Record<DietPhase['status'], string> = {
  active: 'Activa',
  completed: 'Completada',
  pending: 'Pendiente',
}

const PHASE_STATUS_STYLE: Record<DietPhase['status'], string> = {
  active: 'border-accent/60 bg-accent/10',
  completed: 'border-success/50 bg-success/10',
  pending: 'border-bg-border bg-transparent',
}

function PhaseCard({ phase }: { phase: DietPhase }) {
  return (
    <div className={`rounded-lg border p-3 ${PHASE_STATUS_STYLE[phase.status]}`}>
      <div className="flex items-center justify-between gap-2">
        <h4 className="font-display text-sm font-semibold text-text-primary">
          {phase.maintenance
            ? 'Mantenimiento'
            : `Fase ${phase.index + 1}`}
        </h4>
        <span
          className={`text-[11px] font-medium ${
            phase.status === 'active'
              ? 'text-accent'
              : phase.status === 'completed'
              ? 'text-success'
              : 'text-text-dim'
          }`}
        >
          {PHASE_STATUS_LABEL[phase.status]}
        </span>
      </div>

      <p className="text-xs text-text-secondary mt-1">
        {round(phase.start_weight, 1)} → {round(phase.end_weight, 1)} kg
        <span className="text-text-dim"> · {round(phase.weeks, 1)} sem</span>
      </p>

      <div className="mt-2 flex items-baseline gap-1.5">
        <span className="display text-2xl text-accent leading-none">{round(phase.kcal)}</span>
        <span className="text-xs text-text-secondary">kcal/día</span>
      </div>
      <p className="text-[11px] text-text-dim mt-1">
        P {round(phase.protein_g)}g · G {round(phase.fat_g)}g · C {round(phase.carbs_g)}g
      </p>
    </div>
  )
}

// ── Main component ──────────────────────────────────────────────────────────────
export function GoalWizard({ onClose }: { onClose: () => void }) {
  const [data, dispatch] = useReducer(reducer, INITIAL_DATA)
  const [loading, setLoading] = useState(true)
  const [bootError, setBootError] = useState('')

  // On mount: resume at the first incomplete step across sessions (Req 1.6).
  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const { data: s } = await goalPlanApi.getState()
        if (cancelled) return
        dispatch({ type: 'goto', step: s.step })
      } catch (err: any) {
        if (!cancelled) setBootError(apiError(err, 'No se pudo iniciar el asistente.'))
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  const activeIndex = STEPS.indexOf(data.step)

  function goTo(step: Step) {
    dispatch({ type: 'goto', step })
  }

  function back() {
    const idx = STEPS.indexOf(data.step)
    if (idx > 0) goTo(STEPS[idx - 1])
  }

  return (
    <div
      className="fixed inset-0 z-50 flex flex-col bg-bg-base/95 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-label="Asistente de objetivo"
    >
      {/* Header + step indicator */}
      <header className="shrink-0 border-b border-bg-border px-4 py-3 sm:px-6">
        <div className="mx-auto flex max-w-xl items-center justify-between gap-3">
          <div>
            <h1 className="font-display text-xl font-semibold text-text-primary leading-none">
              Realizar objetivo
            </h1>
            <p className="text-xs text-text-dim mt-1">
              Paso {Math.max(activeIndex + 1, 1)} de {STEPS.length} ·{' '}
              {STEP_LABELS[data.step]}
            </p>
          </div>
          <button type="button" className="btn-ghost text-sm" onClick={onClose}>
            Cerrar
          </button>
        </div>

        <div className="mx-auto mt-3 flex max-w-xl gap-1.5" aria-hidden="true">
          {STEPS.map((step, i) => (
            <span
              key={step}
              className={`h-1 flex-1 rounded-full transition-colors ${
                i < activeIndex
                  ? 'bg-success'
                  : i === activeIndex
                  ? 'bg-accent'
                  : 'bg-bg-elevated'
              }`}
            />
          ))}
        </div>
      </header>

      {/* Body */}
      <div className="flex-1 overflow-y-auto px-4 py-6 sm:px-6">
        <div className="mx-auto max-w-xl">
          {loading ? (
            <p className="py-10 text-center text-sm text-text-dim">Cargando asistente...</p>
          ) : bootError ? (
            <div className="card">
              <p className="text-sm text-danger">{bootError}</p>
              <button
                type="button"
                className="btn-ghost text-sm mt-3"
                onClick={() => window.location.reload()}
              >
                Reintentar
              </button>
            </div>
          ) : (
            <>
              {data.step === 'profile' && (
                <ProfileStep data={data} dispatch={dispatch} onDone={() => goTo('goal')} />
              )}
              {data.step === 'goal' && (
                <GoalStep
                  data={data}
                  dispatch={dispatch}
                  onBack={back}
                  onDone={() => goTo('equipment')}
                />
              )}
              {data.step === 'equipment' && (
                <EquipmentStep
                  data={data}
                  dispatch={dispatch}
                  onBack={back}
                  onDone={() => goTo('diet')}
                />
              )}
              {data.step === 'diet' && (
                <DietStep
                  data={data}
                  dispatch={dispatch}
                  onBack={back}
                  onDone={() => goTo('training_days')}
                />
              )}
              {data.step === 'training_days' && (
                <TrainingDaysStep
                  data={data}
                  dispatch={dispatch}
                  onBack={back}
                  onDone={() => goTo('routine')}
                />
              )}
              {data.step === 'routine' && (
                <RoutineStep
                  data={data}
                  dispatch={dispatch}
                  onBack={back}
                  onDone={() => goTo('summary')}
                />
              )}
              {data.step === 'summary' && (
                <SummaryStep data={data} dispatch={dispatch} onBack={back} onClose={onClose} />
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Step: Profile ─────────────────────────────────────────────────────────────
interface StepProps {
  data: WizardData
  dispatch: Dispatch<Action>
  onDone: () => void
  onBack?: () => void
}

function ProfileStep({ data, dispatch, onDone }: StepProps) {
  const [err, setErr] = useState('')
  const [saving, setSaving] = useState(false)
  const form = data.profileForm

  async function submit(e: FormEvent) {
    e.preventDefault()
    setSaving(true)
    setErr('')
    try {
      await goalPlanApi.putProfile({
        weight_kg: Number(form.weight_kg),
        height_cm: Number(form.height_cm),
        age: Number(form.age),
        sex: form.sex ? form.sex : null,
        level: form.level,
        days_per_week: Number(form.days_per_week),
        minutes_per_session: Number(form.minutes_per_session),
      })
      onDone()
    } catch (error: any) {
      // Preserve the form; just surface the Spanish detail.
      setErr(apiError(error, 'No se pudo guardar el perfil.'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={submit} className="card space-y-4">
      <div>
        <h2 className="font-display text-lg font-semibold text-text-primary">Tu perfil</h2>
        <p className="text-sm text-text-secondary mt-1">
          Con estos datos calculamos tus necesidades por fase.
        </p>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <Field label="Peso actual (kg)">
          <input
            type="number"
            step="0.1"
            className="input"
            value={form.weight_kg}
            onChange={(e) => dispatch({ type: 'setProfile', patch: { weight_kg: e.target.value } })}
            required
          />
        </Field>
        <Field label="Altura (cm)">
          <input
            type="number"
            step="0.1"
            className="input"
            value={form.height_cm}
            onChange={(e) => dispatch({ type: 'setProfile', patch: { height_cm: e.target.value } })}
            required
          />
        </Field>
        <Field label="Edad">
          <input
            type="number"
            className="input"
            value={form.age}
            onChange={(e) => dispatch({ type: 'setProfile', patch: { age: e.target.value } })}
            required
          />
        </Field>
        <Field label="Sexo (opcional)">
          <select
            className="input"
            value={form.sex}
            onChange={(e) => dispatch({ type: 'setProfile', patch: { sex: e.target.value } })}
          >
            <option value="">Sin especificar</option>
            <option value="male">Masculino</option>
            <option value="female">Femenino</option>
            <option value="other">Otro</option>
          </select>
        </Field>
        <Field label="Nivel">
          <select
            className="input"
            value={form.level}
            onChange={(e) => dispatch({ type: 'setProfile', patch: { level: e.target.value } })}
          >
            <option value="principiante">Principiante</option>
            <option value="intermedio">Intermedio</option>
            <option value="avanzado">Avanzado</option>
          </select>
        </Field>
        <Field label="Días/semana">
          <input
            type="number"
            min={1}
            max={7}
            className="input"
            value={form.days_per_week}
            onChange={(e) =>
              dispatch({ type: 'setProfile', patch: { days_per_week: e.target.value } })
            }
            required
          />
        </Field>
        <Field label="Minutos/sesión">
          <input
            type="number"
            min={10}
            max={240}
            className="input"
            value={form.minutes_per_session}
            onChange={(e) =>
              dispatch({ type: 'setProfile', patch: { minutes_per_session: e.target.value } })
            }
            required
          />
        </Field>
      </div>

      {err && <p className="text-xs text-danger">{err}</p>}

      {/* First step: no Back. */}
      <StepNav onBack={() => {}} canBack={false} busy={saving} nextLabel="Continuar" />
    </form>
  )
}

// ── Step: Goal ──────────────────────────────────────────────────────────────────
function GoalStep({ data, dispatch, onDone, onBack }: StepProps) {
  const [err, setErr] = useState('')
  const [saving, setSaving] = useState(false)
  const form = data.goalForm
  const rate = data.targetRate

  async function submit(e: FormEvent) {
    e.preventDefault()
    setSaving(true)
    setErr('')
    try {
      const { data: res } = await goalPlanApi.putGoal({
        target_weight_kg: Number(form.target_weight_kg),
        target_date: form.target_date,
      })
      const body = res as GoalResponse
      dispatch({ type: 'setTargetRate', rate: body.target_rate ?? null })
      // Stay on this step so the user can read the rate before continuing.
    } catch (error: any) {
      setErr(apiError(error, 'No se pudo guardar el objetivo.'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="card space-y-4">
      <div>
        <h2 className="font-display text-lg font-semibold text-text-primary">Tu objetivo</h2>
        <p className="text-sm text-text-secondary mt-1">
          ¿A qué peso quieres llegar y para cuándo?
        </p>
      </div>

      <form onSubmit={submit} className="space-y-4">
        <div className="grid grid-cols-2 gap-3">
          <Field label="Peso objetivo (kg)">
            <input
              type="number"
              step="0.1"
              className="input"
              value={form.target_weight_kg}
              onChange={(e) =>
                dispatch({ type: 'setGoal', patch: { target_weight_kg: e.target.value } })
              }
              required
            />
          </Field>
          <Field label="Fecha objetivo">
            <input
              type="date"
              className="input"
              value={form.target_date}
              onChange={(e) => dispatch({ type: 'setGoal', patch: { target_date: e.target.value } })}
              required
            />
          </Field>
        </div>

        {err && <p className="text-xs text-danger">{err}</p>}

        <div className="flex items-center gap-3 pt-1">
          <button type="button" className="btn-ghost text-sm" onClick={onBack} disabled={saving}>
            Atrás
          </button>
          <button type="submit" className="btn-primary text-sm flex-1" disabled={saving}>
            {saving ? 'Calculando...' : rate ? 'Recalcular ritmo' : 'Calcular ritmo'}
          </button>
        </div>
      </form>

      {rate && (
        <div className="border-t border-bg-border pt-4">
          <div className="flex items-baseline gap-2">
            <span className="display text-4xl text-accent leading-none">
              {round(rate.rate_kg_per_week, 2)}
            </span>
            <span className="text-sm text-text-secondary">kg/semana ({rate.direction})</span>
          </div>
          <p className="text-sm text-text-secondary mt-1">
            {round(rate.daily_kcal_delta)} kcal/día de ajuste
          </p>
          {rate.warning && rate.warning_message && (
            <p className="text-xs text-danger mt-1">{rate.warning_message}</p>
          )}
          <p className="text-xs text-text-dim mt-2">{rate.disclaimer}</p>

          <button type="button" className="btn-primary text-sm w-full mt-4" onClick={onDone}>
            Continuar
          </button>
        </div>
      )}
    </div>
  )
}

// ── Step: Equipment ─────────────────────────────────────────────────────────────
function EquipmentStep({ data, dispatch, onDone, onBack }: StepProps) {
  const [err, setErr] = useState('')
  const [saving, setSaving] = useState(false)

  async function submit(e: FormEvent) {
    e.preventDefault()
    setSaving(true)
    setErr('')
    try {
      await goalPlanApi.putEquipment({ equipment: data.equipment })
      onDone()
    } catch (error: any) {
      setErr(apiError(error, 'No se pudo guardar el equipo.'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={submit} className="card space-y-4">
      <div>
        <h2 className="font-display text-lg font-semibold text-text-primary">Tu equipo</h2>
        <p className="text-sm text-text-secondary mt-1">
          Marca solo lo que tienes. Si entrenas en un gimnasio con todo, marca "Gimnasio completo".
        </p>
      </div>

      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {EQUIPMENT_CATALOG.map((item) => {
          const checked = data.equipment.includes(item.id)
          return (
            <label
              key={item.id}
              className={`flex cursor-pointer items-start gap-2 rounded-lg border p-2.5 transition-colors ${
                checked ? 'border-accent/60 bg-accent/10' : 'border-bg-border'
              }`}
            >
              <input
                type="checkbox"
                className="mt-0.5"
                checked={checked}
                onChange={() => dispatch({ type: 'toggleEquipment', id: item.id })}
              />
              <span>
                <span className="block text-sm leading-tight text-text-primary">{item.label}</span>
                <span className="block text-[11px] leading-tight text-text-dim">{item.hint}</span>
              </span>
            </label>
          )
        })}
      </div>

      {err && <p className="text-xs text-danger">{err}</p>}

      <StepNav onBack={onBack ?? (() => {})} busy={saving} nextLabel="Continuar" />
    </form>
  )
}

// ── Step: Diet (derive phases) ───────────────────────────────────────────────────
function DietStep({ data, dispatch, onDone, onBack }: StepProps) {
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState('')
  const plan = data.phasePlan

  async function derive() {
    setLoading(true)
    setErr('')
    try {
      const { data: res } = await goalPlanApi.derivePhases()
      dispatch({ type: 'setPhasePlan', plan: res })
    } catch (error: any) {
      setErr(apiError(error, 'No se pudo calcular tu plan de fases.'))
    } finally {
      setLoading(false)
    }
  }

  // Auto-run on entering the step when no plan is captured yet.
  useEffect(() => {
    if (!data.phasePlan) {
      derive()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div className="card space-y-4">
      <div>
        <h2 className="font-display text-lg font-semibold text-text-primary">
          Tu dieta por fases
        </h2>
        <p className="text-sm text-text-secondary mt-1">
          Dividimos el trayecto en fases sostenibles con metas propias para cada una.
        </p>
      </div>

      {loading ? (
        <CookingAnimation label="Calculando tus fases..." />
      ) : err ? (
        <div className="space-y-3">
          <p className="text-sm text-danger">{err}</p>
          <div className="flex items-center gap-3">
            <button type="button" className="btn-ghost text-sm" onClick={onBack}>
              Atrás
            </button>
            <button type="button" className="btn-primary text-sm flex-1" onClick={derive}>
              Reintentar
            </button>
          </div>
        </div>
      ) : plan ? (
        <>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {plan.phases.map((phase) => (
              <PhaseCard key={phase.index} phase={phase} />
            ))}
          </div>
          {plan.disclaimer && <p className="text-xs text-text-dim">{plan.disclaimer}</p>}
          <StepNav
            onBack={onBack ?? (() => {})}
            nextType="button"
            onNextClick={onDone}
            nextLabel="Continuar"
          />
        </>
      ) : (
        <p className="text-sm text-text-dim">Preparando el cálculo...</p>
      )}
    </div>
  )
}

// ── Step: Training days ──────────────────────────────────────────────────────────
function TrainingDaysStep({ data, dispatch, onDone, onBack }: StepProps) {
  const [err, setErr] = useState('')
  const [saving, setSaving] = useState(false)

  async function submit(e: FormEvent) {
    e.preventDefault()
    setSaving(true)
    setErr('')
    try {
      await goalPlanApi.putTrainingDays({ days_per_week: Number(data.trainingDays) })
      onDone()
    } catch (error: any) {
      setErr(apiError(error, 'No se pudieron guardar los días de entrenamiento.'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={submit} className="card space-y-4">
      <div>
        <h2 className="font-display text-lg font-semibold text-text-primary">
          Días de entrenamiento
        </h2>
        <p className="text-sm text-text-secondary mt-1">
          ¿Cuántos días a la semana quieres entrenar?
        </p>
      </div>

      <div className="flex flex-wrap gap-2">
        {[1, 2, 3, 4, 5, 6, 7].map((n) => {
          const selected = Number(data.trainingDays) === n
          return (
            <button
              key={n}
              type="button"
              onClick={() => dispatch({ type: 'setTrainingDays', value: String(n) })}
              className={`h-12 w-12 rounded-lg border font-display text-lg font-semibold transition-colors ${
                selected
                  ? 'border-accent bg-accent/15 text-accent'
                  : 'border-bg-border text-text-secondary hover:border-text-dim'
              }`}
              aria-pressed={selected}
            >
              {n}
            </button>
          )
        })}
      </div>

      {err && <p className="text-xs text-danger">{err}</p>}

      <StepNav onBack={onBack ?? (() => {})} busy={saving} nextLabel="Continuar" />
    </form>
  )
}

// ── Step: Routine (LLM generation with incremental progress) ─────────────────────
const ROUTINE_PROGRESS_STAGES = [
  'Generando rutina...',
  'Seleccionando ejercicios...',
  'Día 1...',
  'Día 2...',
  'Día 3...',
  'Ajustando series y descansos...',
  'Casi listo...',
]

function RoutineStep({ data, dispatch, onDone, onBack }: StepProps) {
  const [generating, setGenerating] = useState(false)
  const [err, setErr] = useState('')
  const [stage, setStage] = useState(0)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const reducedMotion = usePrefersReducedMotion()
  const routine = data.routine

  function clearTimer() {
    if (timerRef.current != null) {
      clearInterval(timerRef.current)
      timerRef.current = null
    }
  }

  // Always clear the simulated-progress interval on unmount.
  useEffect(() => clearTimer, [])

  async function generate() {
    setGenerating(true)
    setErr('')
    setStage(0)

    // Simulate staged progress while the (slow) LLM request is in flight.
    clearTimer()
    timerRef.current = setInterval(() => {
      setStage((s) => (s < ROUTINE_PROGRESS_STAGES.length - 1 ? s + 1 : s))
    }, 1400)

    try {
      const { data: res } = await goalPlanApi.generateRoutine()
      dispatch({ type: 'setRoutine', routine: res })
    } catch (error: any) {
      // Keep wizard state intact; just offer a retry (Req 9.3).
      setErr(apiError(error, 'No se pudo generar la rutina. Intenta de nuevo.'))
    } finally {
      clearTimer()
      setGenerating(false)
    }
  }

  return (
    <div className="card space-y-4">
      <div>
        <h2 className="font-display text-lg font-semibold text-text-primary">Tu rutina</h2>
        <p className="text-sm text-text-secondary mt-1">
          Generamos una rutina adaptada a tus días y a tu equipo.
        </p>
      </div>

      {generating ? (
        <div className="py-6 text-center" role="status" aria-live="polite">
          <p className="display text-2xl text-accent">{ROUTINE_PROGRESS_STAGES[stage]}</p>
          <p className="text-xs text-text-dim mt-2">
            Esto puede tardar hasta dos minutos. No cierres el asistente.
          </p>
          <div className="mx-auto mt-4 h-1.5 w-48 overflow-hidden rounded-full bg-bg-elevated">
            <span
              className={`block h-full rounded-full bg-accent ${
                reducedMotion ? '' : 'transition-all duration-700'
              }`}
              style={{
                width: `${((stage + 1) / ROUTINE_PROGRESS_STAGES.length) * 100}%`,
              }}
            />
          </div>
        </div>
      ) : err ? (
        <div className="space-y-3">
          <p className="text-sm text-danger">{err}</p>
          <div className="flex items-center gap-3">
            <button type="button" className="btn-ghost text-sm" onClick={onBack}>
              Atrás
            </button>
            <button type="button" className="btn-primary text-sm flex-1" onClick={generate}>
              Reintentar
            </button>
          </div>
        </div>
      ) : routine ? (
        <>
          <RoutineView routine={routine} />
          <div className="flex items-center gap-3 pt-1">
            <button type="button" className="btn-ghost text-sm" onClick={onBack}>
              Atrás
            </button>
            <button type="button" className="btn-ghost text-sm" onClick={generate}>
              Regenerar
            </button>
            <button type="button" className="btn-primary text-sm flex-1" onClick={onDone}>
              Continuar
            </button>
          </div>
        </>
      ) : (
        <div className="flex items-center gap-3">
          <button type="button" className="btn-ghost text-sm" onClick={onBack}>
            Atrás
          </button>
          <button type="button" className="btn-primary text-sm flex-1" onClick={generate}>
            Generar rutina
          </button>
        </div>
      )}
    </div>
  )
}

function RoutineView({ routine }: { routine: WorkoutPlan }) {
  return (
    <div className="space-y-3">
      {routine.structure.map((day, di) => (
        <div key={di} className="rounded-lg border border-bg-border p-3">
          <h3 className="font-display text-base font-semibold text-accent mb-2">{day.day}</h3>
          <ul className="space-y-1">
            {day.exercises.map((ex, ei) => (
              <li key={ei} className="text-sm text-text-secondary">
                <span className="text-text-primary">{ex.name}</span>
                {' — '}
                {ex.duration_seconds != null
                  ? `${ex.duration_seconds}s`
                  : `${ex.sets ?? '-'}×${ex.reps ?? '-'}`}
                {`, descanso ${ex.rest_seconds}s`}
              </li>
            ))}
          </ul>
        </div>
      ))}
      {routine.disclaimer && <p className="text-xs text-text-dim">{routine.disclaimer}</p>}
    </div>
  )
}

// ── Step: Summary (edit active-phase targets, show routine) ─────────────────────
interface SummaryProps {
  data: WizardData
  dispatch: Dispatch<Action>
  onBack: () => void
  onClose: () => void
}

function SummaryStep({ data, dispatch, onBack, onClose }: SummaryProps) {
  const plan = data.phasePlan
  const routine = data.routine
  const active = plan?.active_phase ?? null

  const [editing, setEditing] = useState(false)
  const [targets, setTargets] = useState({
    kcal: active?.kcal != null ? String(active.kcal) : '',
    protein_g: active?.protein_g != null ? String(active.protein_g) : '',
    fat_g: active?.fat_g != null ? String(active.fat_g) : '',
    carbs_g: active?.carbs_g != null ? String(active.carbs_g) : '',
  })
  const [err, setErr] = useState('')
  const [msg, setMsg] = useState('')
  const [saving, setSaving] = useState(false)

  function startEditing() {
    setErr('')
    setMsg('')
    setTargets({
      kcal: active?.kcal != null ? String(active.kcal) : '',
      protein_g: active?.protein_g != null ? String(active.protein_g) : '',
      fat_g: active?.fat_g != null ? String(active.fat_g) : '',
      carbs_g: active?.carbs_g != null ? String(active.carbs_g) : '',
    })
    setEditing(true)
  }

  async function saveTargets(e: FormEvent) {
    e.preventDefault()
    setSaving(true)
    setErr('')
    setMsg('')
    try {
      const { data: res } = await goalPlanApi.putActiveTargets({
        kcal: Number(targets.kcal),
        protein_g: Number(targets.protein_g),
        fat_g: Number(targets.fat_g),
        carbs_g: Number(targets.carbs_g),
      })
      dispatch({ type: 'setPhasePlan', plan: res })
      setMsg('✅ Metas actualizadas')
      setEditing(false)
    } catch (error: any) {
      // Preserve the form so invalid values are not lost (Req 10.2, 10.3).
      setErr(apiError(error, 'No se pudieron actualizar las metas.'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-5">
      <div>
        <h2 className="font-display text-lg font-semibold text-text-primary">Resumen</h2>
        <p className="text-sm text-text-secondary mt-1">
          Tu plan está listo. Puedes ajustar las metas de la fase activa.
        </p>
      </div>

      {/* Active phase + edit */}
      <div className="card space-y-3">
        <div className="flex items-center justify-between gap-2">
          <h3 className="font-display text-base font-semibold text-text-primary">
            Fase activa
          </h3>
          {active && !editing && (
            <button type="button" className="btn-ghost text-xs" onClick={startEditing}>
              Editar metas
            </button>
          )}
        </div>

        {!active ? (
          <p className="text-sm text-text-dim">
            No hay una fase activa. Vuelve al paso de dieta para calcular tu plan.
          </p>
        ) : editing ? (
          <form onSubmit={saveTargets} className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <Field label="Calorías (kcal)">
                <input
                  type="number"
                  className="input"
                  value={targets.kcal}
                  onChange={(e) => setTargets({ ...targets, kcal: e.target.value })}
                  required
                />
              </Field>
              <Field label="Proteína (g)">
                <input
                  type="number"
                  className="input"
                  value={targets.protein_g}
                  onChange={(e) => setTargets({ ...targets, protein_g: e.target.value })}
                  required
                />
              </Field>
              <Field label="Grasa (g)">
                <input
                  type="number"
                  className="input"
                  value={targets.fat_g}
                  onChange={(e) => setTargets({ ...targets, fat_g: e.target.value })}
                  required
                />
              </Field>
              <Field label="Carbohidratos (g)">
                <input
                  type="number"
                  className="input"
                  value={targets.carbs_g}
                  onChange={(e) => setTargets({ ...targets, carbs_g: e.target.value })}
                  required
                />
              </Field>
            </div>

            {err && <p className="text-xs text-danger">{err}</p>}

            <div className="flex items-center gap-3">
              <button
                type="button"
                className="btn-ghost text-sm"
                onClick={() => setEditing(false)}
                disabled={saving}
              >
                Cancelar
              </button>
              <button type="submit" className="btn-primary text-sm flex-1" disabled={saving}>
                {saving ? 'Guardando...' : 'Guardar metas'}
              </button>
            </div>
          </form>
        ) : (
          <>
            <PhaseCard phase={active} />
            {msg && <p className="text-xs text-success">{msg}</p>}
          </>
        )}
      </div>

      {/* All phases overview */}
      {plan && plan.phases.length > 0 && (
        <div className="card space-y-3">
          <h3 className="font-display text-base font-semibold text-text-primary">
            Todas las fases
          </h3>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {plan.phases.map((phase) => (
              <PhaseCard key={phase.index} phase={phase} />
            ))}
          </div>
          {plan.disclaimer && <p className="text-xs text-text-dim">{plan.disclaimer}</p>}
        </div>
      )}

      {/* Routine (read-only here) */}
      {routine && (
        <div className="card space-y-3">
          <h3 className="font-display text-base font-semibold text-text-primary">
            Rutina semanal
          </h3>
          <RoutineView routine={routine} />
        </div>
      )}

      <div className="flex items-center gap-3">
        <button type="button" className="btn-ghost text-sm" onClick={onBack}>
          Atrás
        </button>
        <button type="button" className="btn-primary text-sm flex-1" onClick={onClose}>
          Finalizar
        </button>
      </div>
    </div>
  )
}
