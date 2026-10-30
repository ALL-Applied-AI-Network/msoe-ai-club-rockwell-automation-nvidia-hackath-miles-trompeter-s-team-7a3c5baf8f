import { expect, test } from 'bun:test'
import { buildRunCsv, csvCell } from '../src/exportRun'
import type { Assessment } from '../src/App'

const item: Assessment = { id: 'job-1', image: 'data:image/jpeg;base64,PRIVATE_IMAGE', seconds: 28, number: 1, status: 'error', text: 'PRIVATE_MODEL_TEXT', error: 'Network, "failed"\nretry', recipe: { vial: 1, recipe_id: 5, tanks: { '100': 10 } }, color: { status: 'insufficient evidence', distance: 0 }, sequence: { decision: 'appearance deviation - review', reason: 'sequence evidence', available_after_seconds: 120, third_vial_comparison: { decision: 'appearance deviation - review', distance: 12, tolerance: 3, reference_vial: 3 } } }

test('quotes commas, newlines and quotes and neutralizes spreadsheet formulas', () => {
  expect(csvCell('a,"b"\nc')).toBe('"a,""b""\nc"')
  expect(csvCell('=HYPERLINK("x")')).toBe('"\'=HYPERLINK(""x"")"')
  expect(csvCell('  +1')).toBe('"\'  +1"')
  expect(csvCell(0)).toBe('"0"')
  expect(csvCell(undefined)).toBe('""')
})
test('exports separate time scopes, errors and zeros without images or model output', () => {
  const csv = buildRunCsv('run-1', [item], '2026-10-30T00:00:00Z')
  expect(csv.startsWith('\uFEFF')).toBe(true)
  expect(csv).toContain('"immediate_finding"')
  expect(csv).toContain('"retrospective_available_after_seconds"')
  expect(csv).toContain('"insufficient evidence","0"')
  expect(csv).toContain('"Network, ""failed""\nretry"')
  expect(csv).not.toContain('PRIVATE_IMAGE')
  expect(csv).not.toContain('PRIVATE_MODEL_TEXT')
})
test('retains pending/unmatched captures, sorts chronologically without mutating input', () => {
  const pending: Assessment = { ...item, id: 'pending-2', number: 2, seconds: 74, status: 'queued', recipe: null, sequence: undefined }
  const input = [pending, item]
  const csv = buildRunCsv('run-1', input)
  expect(csv.indexOf('"job-1"')).toBeLessThan(csv.indexOf('"pending-2"'))
  expect(csv).toContain('"queued"')
  expect(input[0].id).toBe('pending-2')
})
