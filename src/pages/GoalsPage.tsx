import { ChallengeList } from '../components/ChallengeList'
import { GoalList } from '../components/GoalList'

export function GoalsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-lg font-semibold text-text-primary">🎯 Metas y Desafíos</h1>
        <p className="text-xs text-text-secondary mt-0.5">Crea metas desde Telegram: "quiero correr 3 veces por semana"</p>
      </div>

      <ChallengeList />
      <GoalList />
    </div>
  )
}
