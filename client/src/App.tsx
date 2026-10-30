import { useEffect, useRef, useState } from 'react'
import './App.css'
import BatchComparison from './BatchComparison'
import RunChat from './RunChat'
import { downloadRunCsv } from './exportRun'
type Capture = { image: string; seconds: number; number: number }
type Observation = { status: string; latest: Capture | null; seconds: number; lag_seconds: number; run: string }
export type Assessment = Capture & { process_context?: { explanation: string; dispense_order?: string; previous_dispense_order?: string; warnings: string[]; requested_total_ml: number }; fill?: { status: string; reason: string; surface_y_fraction?: number };  sequence?: { distance_from_previous_output?: number[]; third_vial_comparison?: { decision: string; reference_vial: number; distance: number; tolerance: number }; decision: string; reason: string; available_after_seconds?: number };  color?: { status: string; swatch?: string; overlay?: string; distance?: number; threshold?: number; temporal_spread?: number; reference_vials?: number[]; reason?: string }; hybrid?: { decision: string; visual_status: string };  id: string; status: 'queued' | 'running' | 'complete' | 'error'; text: string | null; error: string | null; recipe: { vial: number; recipe_id: number; tanks: Record<string, number> } | null }
const time = (s: number) => `${Math.floor(s / 60)}:${Math.floor(s % 60).toString().padStart(2, '0')}`

function vialVerdict(item: Assessment) {
  const retrospective = item.sequence?.third_vial_comparison
  const finding = retrospective?.decision || item.hybrid?.decision || item.color?.status
  const source = retrospective ? 'Retrospective appearance check' : 'Current appearance check'
  if (finding === 'appearance deviation - review' || item.fill?.status === 'possible low fill - review') {
    return { tone: 'bad', label: 'Review needed', detail: item.fill?.status === 'possible low fill - review' ? 'Possible low fill' : source }
  }
  if (item.status === 'error') return { tone: 'uncertain', label: 'Uncertain', detail: 'Assessment error; inspect the details below' }
  if (item.status !== 'complete') return { tone: 'uncertain', label: 'Pending', detail: 'Assessment in progress' }
  if (finding === 'no clear appearance deviation') return { tone: 'good', label: 'Looks good', detail: `${source}: no clear color deviation. Fill volume is not verified.` }
  return { tone: 'uncertain', label: 'Uncertain', detail: finding === 'reference only - not scored' ? 'Reference vial; not independently scored' : 'Not enough evidence for an appearance judgment' }
}
export default function App() {
  const vial = useRef<HTMLVideoElement>(null)
  const tank = useRef<HTMLVideoElement>(null)
  const [observation, setObservation] = useState<Observation | null>(null)
  const [error, setError] = useState('')
  const [videoError, setVideoError] = useState('')
  const [playing, setPlaying] = useState(false)
  const [assessmentBatch, setAssessmentBatch] = useState<{ run: string; items: Assessment[] }>({ run: '', items: [] })
  const [assessmentError, setAssessmentError] = useState('')
  const [exportNotice, setExportNotice] = useState<{ run: string; text: string } | null>(null)
  const run = observation?.run
  const assessments = assessmentBatch.run === run ? assessmentBatch.items : []
  useEffect(() => {
    if (!run) return
    let stopped = false
    let timer: ReturnType<typeof setTimeout>
    const controller = new AbortController()
    const poll = async () => {
      try {
        const response = await fetch(`/api/assessments/${run}`, { signal: controller.signal })
        if (!response.ok) throw new Error('Cannot load assessments')
        const results: Assessment[] = await response.json()
        if (!stopped) { setAssessmentBatch({ run, items: results }); setAssessmentError('') }
      } catch (err) {
        if (!stopped) setAssessmentError(err instanceof Error ? err.message : 'Cannot load assessments')
      }
      if (!stopped) timer = setTimeout(poll, 1500)
    }
    void poll()
    return () => { stopped = true; clearTimeout(timer); controller.abort() }
  }, [run])
  function exportRun() {
    if (!run || !assessments.length) return
    try {
      downloadRunCsv(run, assessments)
      const pending = assessments.filter(item => item.status === 'queued' || item.status === 'running').length
      setExportNotice({ run, text: `CSV download started: ${assessments.length} captures${pending > 0 ? ' (some are still processing)' : ''}. This is a snapshot; export again after later fills for updated retrospective results.` })
    } catch {
      setExportNotice({ run, text: 'Could not start CSV download. Please try again.' })
    }
  }
  async function retry(id: string) {
    try {
      const response = await fetch(`/api/assessments/${id}/retry`, { method: 'POST' })
      if (!response.ok) throw new Error('Could not retry assessment')
      setAssessmentError('')
    } catch (err) { setAssessmentError(err instanceof Error ? err.message : 'Could not retry') }
  }
  useEffect(() => {
    let stopped = false
    let timer: ReturnType<typeof setTimeout>
    const controller = new AbortController()
    const session = crypto.randomUUID()
    let lastTime = -1
    const poll = async () => {
      const video = vial.current
      if (video && !video.seeking && video.readyState >= 2 &&
          (video.currentTime - lastTime >= 0.25 || video.currentTime < lastTime)) {
        const seconds = video.currentTime
        try {
          const response = await fetch('/api/vial/observe', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session, seconds }), signal: controller.signal,
          })
          if (!response.ok) {
            const body = await response.json()
            throw new Error(body.detail || 'Vial analysis failed')
          }
          const result: Observation = await response.json()
          if (!stopped) { setObservation(result); setError(''); lastTime = result.seconds }
        } catch (err) {
          if (!stopped) setError(err instanceof Error ? err.message : 'Cannot reach camera API')
        }
      }
      if (!stopped) timer = setTimeout(poll, 150)
    }
    void poll()
    return () => { stopped = true; clearTimeout(timer); controller.abort() }
  }, [])
  async function togglePlayback() {
    if (!vial.current || !tank.current) return
    if (playing) { vial.current.pause(); tank.current.pause(); setPlaying(false); return }
    tank.current.currentTime = vial.current.currentTime
    try {
      await Promise.all([vial.current.play(), tank.current.play()])
      setPlaying(true); setVideoError('')
    } catch {
      vial.current.pause(); tank.current.pause(); setPlaying(false)
      setVideoError('Unable to play recordings. Check that the API is running.')
    }
  }
  return <main>
    {videoError && <p className="error" role="alert">{videoError}</p>}
    <div className="layout"><section className="feeds" aria-label="Camera feeds"><div className="camera-controls"><span>Recorded camera feeds</span><button onClick={() => void togglePlayback()}>{playing ? 'Pause cameras' : 'Start cameras'}</button></div>
      {(['vial', 'tank'] as const).map((camera, index) => <article className="panel" key={camera}>
        <div className="panel-title"><h2>{index === 0 ? 'Vial filling station' : 'Source tanks'}</h2><span className="badge">{playing ? 'REPLAYING' : 'PAUSED'} / CAM 0{index + 1}</span></div>
        <video ref={camera === 'vial' ? vial : tank} src={`/api/cameras/${camera}/video`} muted playsInline preload="auto"
          onEnded={camera === 'vial' ? () => { tank.current?.pause(); setPlaying(false) } : undefined}
          onError={() => setVideoError(`Cannot load the ${camera} recording. Check the API and sample files.`)}
          onTimeUpdate={camera === 'vial' ? () => {
            if (vial.current && tank.current && Math.abs(vial.current.currentTime - tank.current.currentTime) > 0.75) tank.current.currentTime = vial.current.currentTime
          } : undefined} />
        <p className="caption">{camera === 'vial' ? 'Raw camera view / fixed filling nozzle' : 'Raw camera view / tank levels'}</p>
      </article>)}
    </section><div className="sidebar"><aside className="panel capture"><div className="panel-title"><h2>Latest completed vial</h2></div>
      <p className="status" aria-live="polite">{error ? 'Analysis unavailable' : observation?.status.replace(/jar/gi, 'vial') || 'Start cameras to begin detection'}</p>
      {observation && observation.lag_seconds > 1 && <p className="note">Analysis is catching up ({Math.ceil(observation.lag_seconds)}s behind playback). Captures will appear as frames are processed.</p>}
      {error && <p className="error" role="alert">{error}</p>}
      {observation?.latest ? <><div className="crop"><img src={observation.latest.image} alt="Most recent vial captured before leaving the filling station" /></div>
        <div className="capture-meta"><strong>Vial {observation.latest.number.toString().padStart(3, '0')}</strong><span>Video time {time(observation.latest.seconds)}</span></div></>
        : <div className="empty"><span>?</span><p>Waiting for the first completed vial</p><small>The crop appears after a vial leaves the filling station.</small></div>}
      <p className="note">Completion is estimated from a vial moving left after stopping under the nozzle. The last crop at the station stays here until the next completion.</p>
    </aside>
    <RunChat key={run || 'no-run'} run={run} />
    <BatchComparison assessments={assessments} />
    <section className="panel assessments" aria-label="Vial assessments">
      <div className="panel-title"><h2>Assessment results</h2><div className="assessment-actions"><span className="badge">{assessments.length} CAPTURED</span><button className="export-button" disabled={!run || !assessments.length} onClick={exportRun}>Export run CSV</button></div></div>
      {exportNotice?.run === run && <p className="note" role="status">{exportNotice?.text}</p>}
      <p className="note">Export downloads the current run snapshot, including pending/error rows and separate immediate/retrospective measurements. No images or model descriptions are included.</p>
      <p className="note">The intended recipe stays fixed. Measurements compare observed appearances; Cosmos describes visible differences. Sequence findings appear retrospectively after all three fills, and do not prove contamination.</p>
      <div className="verdict-legend"><span className="verdict-badge verdict-good">Looks good</span><span className="verdict-badge verdict-bad">Review needed</span><span className="verdict-badge verdict-uncertain">Uncertain / pending</span><small>Appearance indicators, not chemical-quality certification.</small></div>
      {assessmentError && <p className="error" role="alert">{assessmentError}</p>}
      {!assessments.length && <p className="note">Start the cameras. The first assessment will queue after the first vial leaves the station.</p>}
      {[...assessments].reverse().map(item => { const verdict = vialVerdict(item); return <article className={`assessment verdict-${verdict.tone}`} key={item.id}>
        <img src={item.color?.overlay || item.image} alt={`Captured vial ${item.recipe?.vial ?? item.number}`} />
        <div><div className="verdict-banner" role="status"><span className={`verdict-badge verdict-${verdict.tone}`}>{verdict.label}</span><span>{verdict.detail}</span></div><h3>{item.recipe ? `Vial ${item.recipe.vial} / Recipe ${item.recipe.recipe_id}` : `Capture ${item.number}`} <small>{time(item.seconds)}</small><span className={`assessment-state ${item.status}`}>{item.status}</span></h3>
          {item.recipe && <p className="recipe">{Object.entries(item.recipe.tanks).map(([tankId, amount]) => `Tank ${tankId}: ${amount} mL`).join(' + ')}</p>}
          {item.color && <div className="color-check">
            <strong>{item.hybrid?.decision || 'Measuring appearance'}</strong>
            <p>{item.color.swatch && <span className="color-swatch" style={{ backgroundColor: item.color.swatch }} aria-label={`Measured color ${item.color.swatch}`} />}
              Color check: {item.color.status}{item.color.distance != null && ` / distance ${item.color.distance.toFixed(1)} / exploratory tolerance ${item.color.threshold?.toFixed(1)}`}</p>
            <small>{item.color.reference_vials ? `Earlier comparison vials: ${item.color.reference_vials.join(', ')}. Outline marks sampled liquid. Uses earlier documented-clean second/third fills only.` : item.color.reason}</small>
          </div>}
          {item.sequence && <div className="color-check"><strong>Retrospective: {item.sequence.third_vial_comparison?.decision || item.sequence.decision}</strong><p>Sequence: {item.sequence.decision}. {item.sequence.reason}</p>{item.sequence.third_vial_comparison && <small>Clean reference: vial {item.sequence.third_vial_comparison.reference_vial}; color distance {item.sequence.third_vial_comparison.distance.toFixed(1)} / tolerance {item.sequence.third_vial_comparison.tolerance.toFixed(1)}.</small>}{item.sequence.available_after_seconds != null && <small>Available after video time {time(item.sequence.available_after_seconds)}. Uses later fills.</small>}</div>}
          {item.process_context && <div className="color-check"><strong>Recipe and carryover context</strong><p>{item.process_context.explanation}</p><small>Current order: {item.process_context.dispense_order || 'unknown'}; previous order: {item.process_context.previous_dispense_order || 'unknown'}. Requested total: {item.process_context.requested_total_ml} mL (not measured).</small>{item.process_context.warnings.map(w => <p key={w} className="error">{w}</p>)}</div>}
          {item.fill && <div className="color-check"><strong>Visual fill check: {item.fill.status}</strong><p>{item.fill.reason}</p></div>}
          <p className="visual-label">Cosmos appearance description</p>
          <p className="assessment-text" aria-live="polite">{item.status === 'complete' ? (item.text?.trim() || 'Assessment completed without result text.') : item.status === 'running' ? 'Cosmos is inspecting this vial...' : item.status === 'queued' ? 'Queued for Cosmos...' : item.error}</p>
          {item.status === 'error' && item.recipe && <button onClick={() => void retry(item.id)}>Retry assessment</button>}
        </div>
      </article>})}
    </section></div></div>
  </main>
}












