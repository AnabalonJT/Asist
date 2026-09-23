import { useEffect, useState, FormEvent } from 'react'
import {
  fitnessApi,
  FitnessProfile,
  GoalResult,
  WorkoutPlan,
  Progress,
  Adherence,
} from '../lib/api'
import { WeightChart } from '../components/WeightChart'

const EQUIPMENT_CATALOG = [
  'mancuernas',
  'barra',
  'banco',
  'kettlebell',
  'bandas',
  'peso corporal',
  'acceso a gimnasio',
  'máquinas',
]

const GOAL_TYPES: { value: string; label: string }[] = [
  { value: 'weight_target', label: 'Peso objetivo (A → B)' },
  { value: 'lose_weight', label: 'Adelgazar' },
  { value: 'gain_muscle', label: 'Ganar músculo' },
  { value: 'maintain', label: 'Mantener' },
  { value: 'improve_endurance', label: 'Mejorar resistencia' },
  { value: 'performance', label: 'Marca de rendimiento' },
]

type ProfileForm = {
  weight_kg: string
  height_cm: string
  age: string
  sex: string
  level: string
  equipment: string[]
  days_per_week: string
  minutes_per_session: string
}

const EMPTY_PROFILE: ProfileForm = {
  weight_kg: '',
  height_cm: '',
  age: '',
  sex: '',
  level: 'principiante',
  equipment: [],
  days_per_week: '3',
  minutes_per_session: '45',
}

function todayISO(): string {
  return new Date().toISOString().slice(0, 10)
}

function apiError(err: any, fallback: string): string {
  const detail = err?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail) && detail.length > 0 && detail[0]?.msg) return detail[0].msg
  return fallback
}

export function FitnessPage() {
  // ── Profile state ──
  const [profile, setProfile] = useState<ProfileForm>(EMPTY_PROFILE)
  const [profileMsg, setProfileMsg] = useState('')
  const [profileErr, setProfileErr] = useState('')
  const [savingProfile, setSavingProfile] = useState(false)

  // ── Goal state ──
  const [goalType, setGoalType] = useState('lose_weight')
  const [targetWeight, setTargetWeight] = useState('')
  const [targetDate, setTargetDate] = useState('')
  const [performanceTarget, setPerformanceTarget] = useState('')
  const [goalResult, setGoalResult] = useState<GoalResult | null>(null)
  const [goalMsg, setGoalMsg] = useState('')
  const [goalErr, setGoalErr] = useState('')
  const [savingGoal, setSavingGoal] = useState(false)

  // ── Plan state ──
  const [plan, setPlan] = useState<WorkoutPlan | null>(null)
  const [planMessage, setPlanMessage] = useState('')
  const [planErr, setPlanErr] = useState('')
  const [generating, setGenerating] = useState(false)

  // ── Weight / progress state ──
  const [weightVal, setWeightVal] = useState('')
  const [weightDate, setWeightDate] = useState(todayISO())
  const [weightErr, setWeightErr] = useState('')
  const [savingWeight, setSavingWeight] = useState(false)
  const [progress, setProgress] = useState<Progress | null>(null)

  // ── Adherence state ──
  const [adherence, setAdherence] = useState<Adherence | null>(null)

  // ── Loading ──
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadProfile()
    loadPlan()
    loadProgress()
    loadAdherence()
  }, [])

  async function loadProfile() {
    try {
      const { data } = await fitnessApi.getProfile()
      setProfile({
        weight_kg: data.weight_kg != null ? String(data.weight_kg) : '',
        height_cm: data.height_cm != null ? String(data.height_cm) : '',
        age: data.age != null ? String(data.age) : '',
        sex: data.sex ?? '',
        level: data.level ?? 'principiante',
        equipment: Array.isArray(data.equipment) ? data.equipment : [],
        days_per_week: data.days_per_week != null ? String(data.days_per_week) : '3',
        minutes_per_session:
          data.minutes_per_session != null ? String(data.minutes_per_session) : '45',
      })
      if (data.goal_type) setGoalType(data.goal_type)
      if (data.target_weight_kg != null) setTargetWeight(String(data.target_weight_kg))
      if (data.target_date) setTargetDate(data.target_date)
      if (data.performance_target) setPerformanceTarget(data.performance_target)
    } catch (err: any) {
      // 404 = perfil aún no creado, no es error.
      if (err?.response?.status !== 404) {
        setProfileErr(apiError(err, 'No se pudo cargar el perfil.'))
      }
    } finally {
      setLoading(false)
    }
  }

  async function loadPlan() {
    try {
      const { data } = await fitnessApi.getPlan()
      if ('structure' in data) {
        setPlan(data)
        setPlanMessage('')
      } else {
        setPlan(null)
        setPlanMessage(data.message)
      }
    } catch {
      setPlan(null)
    }
  }

  async function loadProgress() {
    try {
      const { data } = await fitnessApi.getProgress()
      setProgress(data)
    } catch {
      setProgress(null)
    }
  }

  async function loadAdherence() {
    try {
      const { data } = await fitnessApi.getAdherence()
      setAdherence(data)
    } catch {
      setAdherence(null)
    }
  }

  function toggleEquipment(item: string) {
    setProfile((p) => ({
      ...p,
      equipment: p.equipment.includes(item)
        ? p.equipment.filter((e) => e !== item)
        : [...p.equipment, item],
    }))
  }

  async function saveProfile(e: FormEvent) {
    e.preventDefault()
    setSavingProfile(true)
    setProfileMsg('')
    setProfileErr('')
    try {
      const payload: Partial<FitnessProfile> = {
        weight_kg: Number(profile.weight_kg),
        height_cm: Number(profile.height_cm),
        age: Number(profile.age),
        sex: profile.sex ? profile.sex : null,
        level: profile.level,
        equipment: profile.equipment,
        days_per_week: Number(profile.days_per_week),
        minutes_per_session: Number(profile.minutes_per_session),
      }
      await fitnessApi.putProfile(payload)
      setProfileMsg('✅ Perfil guardado')
    } catch (err: any) {
      setProfileErr(apiError(err, 'No se pudo guardar el perfil.'))
    } finally {
      setSavingProfile(false)
    }
  }

  async function saveGoal(e: FormEvent) {
    e.preventDefault()
    setSavingGoal(true)
    setGoalMsg('')
    setGoalErr('')
    try {
      const payload: Record<string, unknown> = { goal_type: goalType }
      if (goalType === 'weight_target') {
        payload.target_weight_kg = targetWeight ? Number(targetWeight) : null
        payload.target_date = targetDate || null
      }
      if (goalType === 'performance') {
        payload.performance_target = performanceTarget
      }
      const { data } = await fitnessApi.putGoal(payload)
      setGoalResult(data)
      setGoalMsg('✅ Objetivo guardado')
      loadProgress()
    } catch (err: any) {
      setGoalErr(apiError(err, 'No se pudo guardar el objetivo.'))
    } finally {
      setSavingGoal(false)
    }
  }

  async function generatePlan() {
    setGenerating(true)
    setPlanErr('')
    try {
      const { data } = await fitnessApi.generatePlan()
      setPlan(data)
      setPlanMessage('')
      loadAdherence()
    } catch (err: any) {
      setPlanErr(apiError(err, 'No se pudo generar la rutina. Intenta de nuevo.'))
    } finally {
      setGenerating(false)
    }
  }

  async function saveWeight(e: FormEvent) {
    e.preventDefault()
    setSavingWeight(true)
    setWeightErr('')
    try {
      await fitnessApi.postWeight({
        weight_kg: Number(weightVal),
        entry_date: weightDate,
      })
      setWeightVal('')
      loadProgress()
    } catch (err: any) {
      setWeightErr(apiError(err, 'No se pudo registrar el peso.'))
    } finally {
      setSavingWeight(false)
    }
  }

  if (loading) {
    return <div className="text-sm text-text-dim py-8 text-center">Cargando...</div>
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-lg font-semibold text-text-primary">🏋️ Coach de fitness</h1>
        <p className="text-xs text-text-dim mt-1">
          Configura tu perfil y objetivo para generar rutinas adaptadas a ti.
        </p>
      </div>

      {/* ── Perfil ── */}
      <div className="card">
        <h2 className="text-sm font-semibold text-text-primary mb-3">👤 Perfil</h2>
        <form onSubmit={saveProfile} className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-text-secondary">Peso (kg)</label>
              <input
                type="number"
                step="0.1"
                className="input"
                value={profile.weight_kg}
                onChange={(e) => setProfile({ ...profile, weight_kg: e.target.value })}
                required
              />
            </div>
            <div>
              <label className="text-xs text-text-secondary">Altura (cm)</label>
              <input
                type="number"
                step="0.1"
                className="input"
                value={profile.height_cm}
                onChange={(e) => setProfile({ ...profile, height_cm: e.target.value })}
                required
              />
            </div>
            <div>
              <label className="text-xs text-text-secondary">Edad</label>
              <input
                type="number"
                className="input"
                value={profile.age}
                onChange={(e) => setProfile({ ...profile, age: e.target.value })}
                required
              />
            </div>
            <div>
              <label className="text-xs text-text-secondary">Sexo</label>
              <select
                className="input"
                value={profile.sex}
                onChange={(e) => setProfile({ ...profile, sex: e.target.value })}
              >
                <option value="">Sin especificar</option>
                <option value="male">Masculino</option>
                <option value="female">Femenino</option>
                <option value="other">Otro</option>
              </select>
            </div>
            <div>
              <label className="text-xs text-text-secondary">Nivel</label>
              <select
                className="input"
                value={profile.level}
                onChange={(e) => setProfile({ ...profile, level: e.target.value })}
              >
                <option value="principiante">Principiante</option>
                <option value="intermedio">Intermedio</option>
                <option value="avanzado">Avanzado</option>
              </select>
            </div>
            <div>
              <label className="text-xs text-text-secondary">Días/semana</label>
              <input
                type="number"
                min={1}
                max={7}
                className="input"
                value={profile.days_per_week}
                onChange={(e) => setProfile({ ...profile, days_per_week: e.target.value })}
                required
              />
            </div>
            <div>
              <label className="text-xs text-text-secondary">Minutos/sesión</label>
              <input
                type="number"
                min={10}
                max={240}
                className="input"
                value={profile.minutes_per_session}
                onChange={(e) =>
                  setProfile({ ...profile, minutes_per_session: e.target.value })
                }
                required
              />
            </div>
          </div>

          <div>
            <label className="text-xs text-text-secondary">Equipo disponible</label>
            <div className="grid grid-cols-2 gap-2 mt-1">
              {EQUIPMENT_CATALOG.map((item) => (
                <label
                  key={item}
                  className="flex items-center gap-2 text-sm text-text-primary cursor-pointer"
                >
                  <input
                    type="checkbox"
                    checked={profile.equipment.includes(item)}
                    onChange={() => toggleEquipment(item)}
                  />
                  <span className="capitalize">{item}</span>
                </label>
              ))}
            </div>
          </div>

          {profileErr && <p className="text-xs text-danger">{profileErr}</p>}
          {profileMsg && <p className="text-xs text-success">{profileMsg}</p>}

          <button type="submit" className="btn-primary w-full text-sm" disabled={savingProfile}>
            {savingProfile ? 'Guardando...' : 'Guardar perfil'}
          </button>
        </form>
      </div>

      {/* ── Objetivo ── */}
      <div className="card">
        <h2 className="text-sm font-semibold text-text-primary mb-3">🎯 Objetivo</h2>
        <form onSubmit={saveGoal} className="space-y-3">
          <div>
            <label className="text-xs text-text-secondary">Tipo de objetivo</label>
            <select
              className="input"
              value={goalType}
              onChange={(e) => setGoalType(e.target.value)}
            >
              {GOAL_TYPES.map((g) => (
                <option key={g.value} value={g.value}>
                  {g.label}
                </option>
              ))}
            </select>
          </div>

          {goalType === 'weight_target' && (
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs text-text-secondary">Peso objetivo (kg)</label>
                <input
                  type="number"
                  step="0.1"
                  className="input"
                  value={targetWeight}
                  onChange={(e) => setTargetWeight(e.target.value)}
                />
              </div>
              <div>
                <label className="text-xs text-text-secondary">Fecha objetivo</label>
                <input
                  type="date"
                  className="input"
                  value={targetDate}
                  onChange={(e) => setTargetDate(e.target.value)}
                />
              </div>
            </div>
          )}

          {goalType === 'performance' && (
            <div>
              <label className="text-xs text-text-secondary">Descripción de la marca</label>
              <input
                type="text"
                maxLength={200}
                className="input"
                placeholder="Ej. correr 10 km en 50 min"
                value={performanceTarget}
                onChange={(e) => setPerformanceTarget(e.target.value)}
              />
            </div>
          )}

          {goalErr && <p className="text-xs text-danger">{goalErr}</p>}
          {goalMsg && <p className="text-xs text-success">{goalMsg}</p>}

          <button type="submit" className="btn-primary w-full text-sm" disabled={savingGoal}>
            {savingGoal ? 'Guardando...' : 'Guardar objetivo'}
          </button>
        </form>

        {goalResult?.target_rate && (
          <div className="mt-4 space-y-1 border-t border-bg-border pt-3">
            <p className="text-sm text-text-primary">
              Ritmo: {goalResult.target_rate.rate_kg_per_week} kg/semana (
              {goalResult.target_rate.direction})
            </p>
            <p className="text-sm text-text-secondary">
              {goalResult.target_rate.daily_kcal_delta} kcal/día
            </p>
            {goalResult.target_rate.warning && goalResult.target_rate.warning_message && (
              <p className="text-xs text-danger">{goalResult.target_rate.warning_message}</p>
            )}
            <p className="text-xs text-text-dim">{goalResult.target_rate.disclaimer}</p>
          </div>
        )}
      </div>

      {/* ── Rutina ── */}
      <div className="card">
        <h2 className="text-sm font-semibold text-text-primary mb-3">📅 Rutina</h2>
        <button
          onClick={generatePlan}
          className="btn-primary w-full text-sm mb-3"
          disabled={generating}
        >
          {generating ? 'Generando...' : 'Generar rutina'}
        </button>

        {planErr && (
          <div className="mb-3">
            <p className="text-xs text-danger">{planErr}</p>
            <button
              onClick={generatePlan}
              className="btn-ghost text-xs mt-1"
              disabled={generating}
            >
              Reintentar
            </button>
          </div>
        )}

        {planMessage && !plan && <p className="text-sm text-text-dim">{planMessage}</p>}

        {plan && (
          <div className="space-y-4">
            {plan.structure.map((day, di) => (
              <div key={di} className="border border-bg-border rounded-lg p-3">
                <h3 className="text-sm font-semibold text-accent mb-2">{day.day}</h3>
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
            {plan.disclaimer && <p className="text-xs text-text-dim">{plan.disclaimer}</p>}
          </div>
        )}
      </div>

      {/* ── Peso y progreso ── */}
      <div className="card">
        <h2 className="text-sm font-semibold text-text-primary mb-3">⚖️ Peso y progreso</h2>
        <form onSubmit={saveWeight} className="flex gap-2 items-end mb-4">
          <div className="flex-1">
            <label className="text-xs text-text-secondary">Peso (kg)</label>
            <input
              type="number"
              step="0.1"
              className="input"
              value={weightVal}
              onChange={(e) => setWeightVal(e.target.value)}
              required
            />
          </div>
          <div className="flex-1">
            <label className="text-xs text-text-secondary">Fecha</label>
            <input
              type="date"
              className="input"
              value={weightDate}
              onChange={(e) => setWeightDate(e.target.value)}
              required
            />
          </div>
          <button type="submit" className="btn-primary text-sm" disabled={savingWeight}>
            {savingWeight ? '...' : 'Registrar'}
          </button>
        </form>

        {weightErr && <p className="text-xs text-danger mb-2">{weightErr}</p>}

        <WeightChart
          series={progress?.series ?? []}
          targetWeight={progress?.target_weight_kg}
        />
      </div>

      {/* ── Adherencia ── */}
      <div className="card">
        <h2 className="text-sm font-semibold text-text-primary mb-3">📊 Adherencia</h2>
        {adherence == null ? (
          <p className="text-sm text-text-dim">No disponible.</p>
        ) : adherence.available ? (
          <div className="space-y-1">
            <p className="text-sm text-text-primary">
              {adherence.completed ?? 0} de {adherence.planned ?? 0} sesiones
            </p>
            <p className="text-sm text-text-secondary">
              {Math.round((adherence.ratio ?? 0) * 100)}% de adherencia
            </p>
          </div>
        ) : (
          <p className="text-sm text-text-dim">
            {adherence.message ?? 'No hay adherencia calculable todavía.'}
          </p>
        )}
      </div>
    </div>
  )
}
