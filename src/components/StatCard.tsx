interface Props {
  label: string
  value: string | number
  sub?: string
  icon: string
}

export function StatCard({ label, value, sub, icon }: Props) {
  return (
    <div className="card flex items-center gap-4">
      <div className="w-10 h-10 rounded-xl bg-accent-glow flex items-center justify-center text-xl flex-shrink-0">
        {icon}
      </div>
      <div>
        <p className="text-xs text-text-secondary mb-0.5">{label}</p>
        <p className="text-xl font-semibold text-text-primary font-mono">{value}</p>
        {sub && <p className="text-xs text-text-dim mt-0.5">{sub}</p>}
      </div>
    </div>
  )
}
