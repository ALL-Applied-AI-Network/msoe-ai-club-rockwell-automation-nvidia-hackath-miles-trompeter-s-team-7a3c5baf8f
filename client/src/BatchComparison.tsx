import { useState } from 'react'
import type { Assessment } from './App'
import { verdict, batchExplanation, buildBatches } from './batchEvidence'

function VialTile({ item, number, title, reference = false }: { item?: Assessment; number: number; title: string; reference?: boolean }) {
  const state = verdict(item, reference)
  const comparison = item?.sequence?.third_vial_comparison
  return <figure className={`batch-vial batch-${state.tone}`}>
    <figcaption><strong>{title}</strong><span>Vial {number}{item?.recipe && ` / Recipe ${item.recipe.recipe_id}`}</span></figcaption>
    <div className="batch-image">{item ? <img src={item.image} alt={`Vial ${number}, ${title.toLowerCase()}`} loading="lazy" /> : <span>No capture yet</span>}</div>
    <span className={`verdict-badge verdict-${state.tone}`}>{state.label}</span>
    <p className="batch-swatch">{item?.color?.swatch ? <><span className="color-swatch" style={{ backgroundColor: item.color.swatch }} />Measured color <code>{item.color.swatch}</code></> : 'Color measurement pending'}</p>
    {!reference && comparison && <p className="batch-distance">Distance <strong>{comparison.distance.toFixed(1)}</strong> / tolerance {comparison.tolerance.toFixed(1)}</p>}
    {reference && <p className="batch-distance">Documented-clean reference; not independently scored.</p>}
  </figure>
}

export default function BatchComparison({ assessments }: { assessments: Assessment[] }) {
  const [reviewOnly, setReviewOnly] = useState(false)
  const batches = buildBatches(assessments)
  const shown = batches.filter(batch => !reviewOnly || batch.tone !== 'good')
  const unmatched = assessments.filter(item => !item.recipe).length
  return <section className="panel batch-comparison" aria-label="Batch comparisons">
    <div className="panel-title"><div><h2>Batch comparisons</h2><p className="batch-subtitle">Video 5 / three-vial batches / retrospective</p></div>
      <label className="review-filter"><input type="checkbox" checked={reviewOnly} onChange={event => setReviewOnly(event.target.checked)} />Review only</label></div>
    <div className="batch-counts"><span>{batches.filter(batch => batch.tone === 'bad').length} flagged</span><span>{batches.filter(batch => batch.tone === 'uncertain').length} pending / uncertain</span><span>{batches.filter(batch => batch.tone === 'good').length} without clear deviation</span></div>
    <p className="note">Review only includes flagged, incomplete and uncertain batches. The third vial is the documented-clean color reference. These comparisons use later fills; they do not verify chemical quality.</p>
    {unmatched > 0 && <p className="note">{unmatched} capture(s) have no matched recipe; inspect their individual assessment errors below.</p>}
    {!batches.length && <div className="batch-placeholder">Start the cameras. Batches appear as recipe-matched vials are captured.</div>}
    {batches.length > 0 && !shown.length && <div className="batch-placeholder">No batches currently need review. Uncheck Review only to see all batches.</div>}
    {shown.map(batch => {
      const sequence = batch.items.find(item => item?.sequence?.available_after_seconds != null)?.sequence
      return <article className={`batch-card batch-${batch.tone}`} key={batch.start}>
        <div className="batch-heading"><h3>Recipe {batch.recipe?.recipe_id} <small>Vials {batch.start}–{batch.start + 2}</small></h3><span className={`verdict-badge verdict-${batch.tone}`}>{batch.tone === 'bad' ? 'Review needed' : batch.tone === 'good' ? 'No clear deviation' : 'Pending / uncertain'}</span></div>
        <p className="recipe">{Object.entries(batch.recipe?.tanks || {}).map(([tank, ml]) => `T-${tank}: ${ml} mL`).join(' + ')}</p>
        <div className="batch-grid">
          {batch.start > 1 ? <VialTile item={batch.previous} number={batch.start - 1} title="Previous recipe / final vial" reference /> : <div className="batch-placeholder">Previous recipe is outside this recording. Carryover source is unknown.</div>}
          {batch.items.map((item, index) => <VialTile key={batch.start + index} item={item} number={batch.start + index} title={['First fill', 'Second fill', 'Third fill / reference'][index]} reference={index === 2} />)}
        </div>
        <div className="batch-evidence"><strong>Measured evidence</strong><p>{batchExplanation(batch.items)}</p>
          {sequence?.distance_from_previous_output && <p>Distance from the previous output: {sequence.distance_from_previous_output.map(value => value.toFixed(1)).join(' → ')} (first → second → third). Smaller means more similar; this is not a mixture model.</p>}
          {sequence?.available_after_seconds != null && <small>Retrospective evidence available at {(sequence.available_after_seconds / 60).toFixed(1)} minutes of video. Exploratory color tolerances; not a validated contamination threshold.</small>}
        </div>
      </article>
    })}
  </section>
}

