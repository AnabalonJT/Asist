import type { ReactNode } from 'react'

interface Props {
  label: string
  value: string | number
  sub?: string
  icon: ReactNode
}

// A quiet supporting stat (secondary to the Dashboard hero). The value uses the
// condensed display face; the icon is an inline SVG, not an emoji.
export function StatCard({ label, value, sub, icon }: Props) {
  return (
    <div className="card flex items-center gap-3 p-4">
      <div className="w-9 h-9 rounded-lg bg-bg-elevated text-text-secondary flex items-center justify-center flex-shrink-0">
        {icon}
      </div>
      <div className="min-w-0">
        <p className="text-[11px] text-text-secondary mb-0.5 truncate">{label}</p>
        <p className="display text-2xl text-text-primary">{value}</p>
        {sub && <p className="text-[11px] text-text-dim mt-0.5">{sub}</p>}
      </div>
    </div>
  )
}
