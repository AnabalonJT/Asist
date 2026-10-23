import { ChallengeList } from '../components/ChallengeList'
import { GoalList } from '../components/GoalList'

export function GoalsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-2xl font-semibold text-text-primary leading-none">Metas y Desafíos</h1>
        <p className="text-sm text-text-secondary mt-1">Crea metas desde Telegram: "quiero correr 3 veces por semana"</p>
      </div>

      <ChallengeList />
      <GoalList />
    </div>
  )
}
