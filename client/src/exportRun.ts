import type { Assessment } from './App'

type Cell = string | number | null | undefined

export function csvCell(value: Cell): string {
  if (value == null) return '""'
  let text = String(value)
  // Keep spreadsheet applications from executing exported text as formulas.
  if (typeof value === 'string' && /^[\s]*[=+\-@]/.test(text)) text = `'${text}`
  return `"${text.replaceAll('"', '""')}"`
}

export function buildRunCsv(run: string, assessments: Assessment[], exportedAt = new Date().toISOString()): string {
  const headers = ['export_version', 'run_id', 'exported_at_utc', 'assessment_id', 'capture_number', 'vial_id', 'recipe_id', 'crop_video_seconds', 'processing_status',
    'immediate_finding', 'immediate_color_distance', 'immediate_tolerance', 'earlier_comparison_vials', 'temporal_color_spread', 'measured_color_hex',
    'retrospective_finding', 'retrospective_reference_vial', 'retrospective_color_distance', 'retrospective_tolerance', 'retrospective_available_after_seconds',
    'sequence_finding', 'sequence_reason', 'fill_finding', 'fill_reason', 'requested_total_ml_not_measured', 'recipe_volumes_ml', 'dispense_order', 'recipe_warnings', 'measurement_note', 'processing_error']
  const rows = [...assessments].sort((a, b) => a.seconds - b.seconds || a.number - b.number).map(item => {
    const comparison = item.sequence?.third_vial_comparison
    const values: Cell[] = [1, run, exportedAt, item.id, item.number, item.recipe?.vial, item.recipe?.recipe_id, item.seconds, item.status,
      item.hybrid?.decision || item.color?.status, item.color?.distance, item.color?.threshold, item.color?.reference_vials?.join('; '), item.color?.temporal_spread, item.color?.swatch,
      comparison?.decision, comparison?.reference_vial, comparison?.distance, comparison?.tolerance, item.sequence?.available_after_seconds,
      item.sequence?.decision, item.sequence?.reason, item.fill?.status, item.fill?.reason, item.process_context?.requested_total_ml,
      item.recipe ? Object.entries(item.recipe.tanks).map(([tank, ml]) => `T${tank}: ${ml}`).join('; ') : null,
      item.process_context?.dispense_order, item.process_context?.warnings.join('; '), item.color?.reason, item.error]
    return values.map(csvCell).join(',')
  })
  // BOM for Excel UTF-8; quote every field and preserve embedded newlines.
  return '\uFEFF' + [headers.map(csvCell).join(','), ...rows].join('\r\n') + '\r\n'
}

export function downloadRunCsv(run: string, assessments: Assessment[]) {
  const stamp = new Date().toISOString()
  const blob = new Blob([buildRunCsv(run, assessments, stamp)], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `vial-run-${run.replace(/[^a-zA-Z0-9_-]/g, '_')}-${stamp.replace(/[:.]/g, '-')}.csv`
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
