import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL ?? '/api',
  headers: { 'Content-Type': 'application/json' },
})

// Attach JWT on every request
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// On 401 → clear token and redirect to login
api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('token')
      window.location.href = '/login'
    }
    return Promise.reject(err)
  }
)

export default api

// ── Auth ──────────────────────────────────────────────────────────────────────
export interface UserMe {
  id: number
  email: string
  is_admin: boolean
  telegram_linked: boolean
}

export interface TokenResponse {
  access_token: string
  token_type: string
}

export interface GenericMessageResponse {
  message: string
}

export const authApi = {
  register: (email: string, password: string) =>
    api.post<TokenResponse>('/auth/register', {
      email,
      password,
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    }),

  login: (email: string, password: string) =>
    api.post<TokenResponse>('/auth/login', { email, password }),

  me: () => api.get<UserMe>('/auth/me'),

  linkingToken: () =>
    api.post<{ token: string; bot_url: string; expires_at: string }>('/auth/linking-token'),

  forgotPassword: (email: string) =>
    api.post<GenericMessageResponse>('/auth/forgot-password', { email }),

  resetPassword: (email: string, code: string, new_password: string) =>
    api.post<GenericMessageResponse>('/auth/reset-password', { email, code, new_password }),
}

// ── Dashboard ─────────────────────────────────────────────────────────────────
export interface Activity {
  id: number
  activity_type: string
  duration_minutes: number | null
  distance_km: number | null
  calories: number
  timestamp: string
}

export interface ActivityBreakdown {
  activity_type: string
  count: number
  total_minutes: number
  total_calories: number
}

export interface WeekComparison {
  this_week: number
  last_week: number
  change_pct: number
}

export interface DashboardStats {
  total_activities: number
  total_calories: number
  total_minutes: number
  total_distance_km: number
  current_streak: number
  telegram_linked: boolean
  timezone: string
  recent_activities: Activity[]
  breakdown: ActivityBreakdown[]
  week_comparison: WeekComparison
}

export const dashboardApi = {
  stats: () => api.get<DashboardStats>('/dashboard/stats'),
}

// ── Reminders ─────────────────────────────────────────────────────────────────
export interface ReminderItem {
  id: number
  schedule: string
  frequency: string
  message: string
  active: boolean
  schedule_days: string | null
  schedule_date: string | null
}

export const remindersApi = {
  list: () => api.get<ReminderItem[]>('/reminders'),
  delete: (id: number) => api.delete(`/reminders/${id}`),
  toggle: (id: number, active: boolean) => api.put(`/reminders/${id}`, { active }),
}

// ── Goals ─────────────────────────────────────────────────────────────────────
export interface GoalItem {
  id: number
  activity_type: string
  description: string
  target_count: number
  period: string
  active: boolean
  current_progress: number
  ends_at: string | null
}

export const goalsApi = {
  list: () => api.get<GoalItem[]>('/goals'),
  delete: (id: number) => api.delete(`/goals/${id}`),
}

// ── Challenges ────────────────────────────────────────────────────────────────
export interface ChallengeGoal {
  id: number
  activity_type: string
  description: string
  target_count: number
  period: string
  current_progress: number
  completed: boolean
}

export interface ChallengeItem {
  id: number
  name: string
  ends_at: string | null
  active: boolean
  all_completed: boolean
  goals: ChallengeGoal[]
}

export const challengesApi = {
  list: () => api.get<ChallengeItem[]>('/challenges'),
  delete: (id: number) => api.delete(`/challenges/${id}`),
}

// ── Settings ──────────────────────────────────────────────────────────────────
export interface UserSettings {
  show_calories: boolean
  timezone: string
}

export const settingsApi = {
  get: () => api.get<UserSettings>('/settings'),
  update: (data: Partial<UserSettings>) => api.put<UserSettings>('/settings', data),
}

// ── Admin ─────────────────────────────────────────────────────────────────────
export interface AdminOverview {
  total_users: number
  telegram_linked_users: number
  total_activities: number
  total_goals: number
  total_reminders: number
  total_challenges: number
  active_users_7d: number
  active_users_30d: number
}

export interface AdminUserSummary {
  id: number
  email: string
  telegram_linked: boolean
  created_at: string
  activity_count: number
  goal_count: number
  reminder_count: number
  challenge_count: number
}

export interface AdminUserDetail extends AdminUserSummary {
  activities_7d: number
  activities_30d: number
  last_activity_at: string | null
}

export const adminApi = {
  overview: () => api.get<AdminOverview>('/admin/overview'),
  users: () => api.get<AdminUserSummary[]>('/admin/users'),
  userDetail: (id: number) => api.get<AdminUserDetail>(`/admin/users/${id}`),
}

// ── Fitness ───────────────────────────────────────────────────────────────────
export interface FitnessProfile {
  weight_kg: number
  height_cm: number
  age: number
  sex: string | null
  level: string
  equipment: string[]
  days_per_week: number
  minutes_per_session: number
  goal_type: string | null
  target_weight_kg: number | null
  target_date: string | null
  performance_target: string | null
}

export interface TargetRate {
  rate_kg_per_week: number
  daily_kcal_delta: number
  direction: string
  warning: boolean
  warning_message: string | null
  disclaimer: string
}

export interface WorkoutExercise {
  name: string
  sets: number | null
  reps: number | null
  duration_seconds: number | null
  rest_seconds: number
  equipment: string
}

export interface WorkoutDay {
  day: string
  exercises: WorkoutExercise[]
}

export interface WorkoutPlan {
  id: number
  goal_type: string
  structure: WorkoutDay[]
  disclaimer: string
}

export interface WeightEntry {
  id: number
  weight_kg: number
  entry_date: string
}

export interface Progress {
  series: { date: string; weight_kg: number }[]
  target_weight_kg: number | null
}

export interface Adherence {
  available: boolean
  completed?: number
  planned?: number
  ratio?: number
  message?: string
}

export interface GoalResult {
  goal_type: string
  target_weight_kg: number | null
  target_date: string | null
  performance_target: string | null
  target_rate: TargetRate | null
  disclaimer: string
}

export const fitnessApi = {
  getProfile: () => api.get<FitnessProfile>('/fitness/profile'),
  putProfile: (d: Partial<FitnessProfile>) => api.put<FitnessProfile>('/fitness/profile', d),
  putGoal: (d: object) => api.put<GoalResult>('/fitness/goal', d),
  postWeight: (d: { weight_kg: number; entry_date: string }) =>
    api.post<WeightEntry>('/fitness/weight', d),
  getWeight: () => api.get<WeightEntry[]>('/fitness/weight'),
  generatePlan: () => api.post<WorkoutPlan>('/fitness/plan/generate'),
  getPlan: () => api.get<WorkoutPlan | { message: string }>('/fitness/plan'),
  getProgress: () => api.get<Progress>('/fitness/progress'),
  getAdherence: () => api.get<Adherence>('/fitness/adherence'),
}
