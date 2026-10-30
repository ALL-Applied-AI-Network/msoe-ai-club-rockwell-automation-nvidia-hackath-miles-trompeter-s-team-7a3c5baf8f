import { expect, test } from 'bun:test'
import { batchExplanation, buildBatches } from '../src/batchEvidence'
import type { Assessment } from '../src/App'

function vial(number: number, distance?: number): Assessment {
  return { id: `v${number}`, image: 'crop', seconds: number * 10, number, status: 'complete', text: '', error: null,
    recipe: { vial: number, recipe_id: 5 + Math.floor((number - 1) / 3), tanks: { '100': 10 } },
    ...(distance != null ? { sequence: { decision: 'measured', reason: '', third_vial_comparison: { reference_vial: Math.ceil(number / 3) * 3, distance, tolerance: 3, decision: number % 3 === 0 ? 'reference only - not scored' : distance > 3 ? 'appearance deviation - review' : 'no clear appearance deviation' } } } : {}) }
}
test('missing captures retain positions; previous context must be the actual final vial', () => {
  const [batch] = buildBatches([vial(2), vial(5)])
  expect(batch.start).toBe(4)
  expect(batch.items.map(item => item?.recipe?.vial)).toEqual([undefined, 5, undefined])
  expect(batch.previous).toBeUndefined()
  expect(batch.tone).toBe('uncertain')
})
test('complete measured batch is green; reference is not scored as a defect', () => {
  expect(buildBatches([vial(1, 1), vial(2, 2), vial(3, 0)])[0].tone).toBe('good')
})
test('measured deviation makes batch red and includes actual previous output', () => {
  const [batch] = buildBatches([vial(3, 0), vial(4, 10), vial(5, 2), vial(6, 0)])
  expect(batch.previous?.recipe?.vial).toBe(3)
  expect(batch.tone).toBe('bad')
  expect(batchExplanation(batch.items)).toContain('second is within its tolerance')
})
test('errors cannot appear green; missing evidence cannot produce a summary', () => {
  const failed = { ...vial(2, 1), status: 'error' as const }
  expect(buildBatches([vial(1, 1), failed, vial(3, 0)])[0].tone).toBe('uncertain')
  expect(batchExplanation([vial(1), undefined, undefined])).toContain('Waiting')
})

