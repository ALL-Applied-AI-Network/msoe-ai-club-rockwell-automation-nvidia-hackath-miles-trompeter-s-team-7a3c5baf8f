import type { Assessment } from './App'

export function verdict(item?: Assessment, reference = false) {
  if (!item) return { tone: 'uncertain', label: 'Waiting for capture' }
  const finding = item.sequence?.third_vial_comparison
  if (finding?.decision === 'appearance deviation - review' || item.fill?.status === 'possible low fill - review') return { tone: 'bad', label: 'Review needed' }
  if (item.status === 'error') return { tone: 'uncertain', label: 'Assessment error' }
  if (reference) return { tone: 'uncertain', label: 'Reference / not scored' }
  if (finding?.decision === 'no clear appearance deviation') return { tone: 'good', label: 'No clear deviation' }
  return { tone: 'uncertain', label: 'Awaiting comparison' }
}

export function batchExplanation(items: (Assessment | undefined)[]) {
  const first = items[0]?.sequence?.third_vial_comparison
  const second = items[1]?.sequence?.third_vial_comparison
  if (!first || !second) return 'Waiting for all three measured vials. No future reference is used until it is available.'
  const firstFlagged = first.distance > first.tolerance
  const secondFlagged = second.distance > second.tolerance
  if (firstFlagged && !secondFlagged) return `First vial differs from the third-vial reference (distance ${first.distance.toFixed(1)}); the second is within its tolerance (${second.distance.toFixed(1)}). This supports a transient appearance change, not proof of carryover.`
  if (firstFlagged && secondFlagged) return `Both first and second vials differ from the reference (${first.distance.toFixed(1)} and ${second.distance.toFixed(1)}). The evidence does not show a clean second fill under this measurement rule.`
  if (!firstFlagged && secondFlagged) return 'Only the second vial exceeds its comparison tolerance. This does not follow the expected first-vial carryover pattern.'
  return 'Both first and second vials are within their comparison tolerances. No clear appearance deviation was measured.'
}

export function buildBatches(assessments: Assessment[]) {
  const byVial = new Map(assessments.filter(item => item.recipe).map(item => [item.recipe!.vial, item]))
  // Explicit video-5 protocol: 30 labeled vials in consecutive groups of three.
  const starts = [...new Set([...byVial.keys()].map(vial => Math.floor((vial - 1) / 3) * 3 + 1))].sort((a, b) => b - a)
  return starts.map(start => {
    const items = [0, 1, 2].map(offset => byVial.get(start + offset))
    const checks = items.slice(0, 2).map(item => verdict(item))
    const tone = items.some(item => item && verdict(item).tone === 'bad') ? 'bad'
      : checks.every(check => check.tone === 'good') && items.every(item => item && item.status !== 'error') ? 'good' : 'uncertain'
    return { start, items, previous: byVial.get(start - 1), tone, recipe: items.find(item => item?.recipe)?.recipe }
  })
}


