interface WeightChartProps {
  series: { date: string; weight_kg: number }[]
  targetWeight?: number | null
}

export function WeightChart({ series, targetWeight }: WeightChartProps) {
  if (series.length === 0) {
    return (
      <div className="flex items-center justify-center h-40 text-sm text-text-dim">
        Aún no hay registros de peso
      </div>
    )
  }

  // ViewBox coordinate space (responsive via preserveAspectRatio).
  const width = 320
  const height = 160
  const padL = 36
  const padR = 12
  const padT = 12
  const padB = 24
  const plotW = width - padL - padR
  const plotH = height - padT - padB

  const weights = series.map((p) => p.weight_kg)
  const values = [...weights]
  if (targetWeight != null) values.push(targetWeight)
  let min = Math.min(...values)
  let max = Math.max(...values)
  if (min === max) {
    // Avoid a flat line hugging an edge: pad the range.
    min -= 1
    max += 1
  }
  const range = max - min

  const x = (i: number) =>
    series.length === 1 ? padL + plotW / 2 : padL + (i / (series.length - 1)) * plotW
  const y = (w: number) => padT + (1 - (w - min) / range) * plotH

  const points = series.map((p, i) => `${x(i)},${y(p.weight_kg)}`).join(' ')
  const targetY = targetWeight != null ? y(targetWeight) : null

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      className="w-full h-auto text-accent"
      preserveAspectRatio="xMidYMid meet"
      role="img"
      aria-label="Gráfico de progreso de peso"
    >
      {/* Axes */}
      <line
        x1={padL}
        y1={padT}
        x2={padL}
        y2={padT + plotH}
        className="text-bg-border"
        stroke="currentColor"
        strokeWidth={1}
      />
      <line
        x1={padL}
        y1={padT + plotH}
        x2={padL + plotW}
        y2={padT + plotH}
        className="text-bg-border"
        stroke="currentColor"
        strokeWidth={1}
      />

      {/* Min / max labels */}
      <text x={4} y={padT + 4} className="fill-text-dim" fontSize={9}>
        {max.toFixed(1)}
      </text>
      <text x={4} y={padT + plotH} className="fill-text-dim" fontSize={9}>
        {min.toFixed(1)}
      </text>

      {/* Target line */}
      {targetY != null && (
        <>
          <line
            x1={padL}
            y1={targetY}
            x2={padL + plotW}
            y2={targetY}
            className="text-success"
            stroke="currentColor"
            strokeWidth={1}
            strokeDasharray="4 3"
          />
          <text
            x={padL + plotW}
            y={targetY - 3}
            textAnchor="end"
            className="fill-success"
            fontSize={9}
          >
            Objetivo {targetWeight?.toFixed(1)}
          </text>
        </>
      )}

      {/* Weight line */}
      <polyline
        points={points}
        fill="none"
        stroke="currentColor"
        strokeWidth={2}
        strokeLinejoin="round"
        strokeLinecap="round"
      />

      {/* Points */}
      {series.map((p, i) => (
        <circle key={i} cx={x(i)} cy={y(p.weight_kg)} r={2.5} fill="currentColor" />
      ))}
    </svg>
  )
}
