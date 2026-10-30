import { useEffect, useRef, useState } from 'react'
import './App.css'
type Capture = { image: string; seconds: number; number: number }
type Observation = { status: string; latest: Capture | null; seconds: number; lag_seconds: number; run: string }
type Assessment = Capture & { id: string; status: 'queued' | 'running' | 'complete' | 'error'; text: string | null; error: string | null; recipe: { vial: number; recipe_id: number; tanks: Record<string, number> } | null }
const time = (s: number) => `${Math.floor(s / 60)}:${Math.floor(s % 60).toString().padStart(2, '0')}`

export default function App() {
  const vial = useRef<HTMLVideoElement>(null)
  const tank = useRef<HTMLVideoElement>(null)
  const [observation, setObservation] = useState<Observation | null>(null)
  const [error, setError] = useState('')
  const [videoError, setVideoError] = useState('')
  const [playing, setPlaying] = useState(false)
  const [assessmentBatch, setAssessmentBatch] = useState<{ run: string; items: Assessment[] }>({ run: '', items: [] })
  const [assessmentError, setAssessmentError] = useState('')
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
    <section className="panel assessments" aria-label="Vial assessments">
      <div className="panel-title"><h2>Assessment results</h2><span className="badge">{assessments.length} CAPTURED</span></div>
      <p className="note">Each crop is matched to the video 5 recipe by timestamp and compared with a tank video frame from the same playback time. Appearance checks are provisional; possible causes are suggestions.</p>
      {assessmentError && <p className="error" role="alert">{assessmentError}</p>}
      {!assessments.length && <p className="note">Start the cameras. The first assessment will queue after the first vial leaves the station.</p>}
      {[...assessments].reverse().map(item => <article className="assessment" key={item.id}>
        <img src={item.image} alt={`Captured vial ${item.recipe?.vial ?? item.number}`} />
        <div><h3>{item.recipe ? `Vial ${item.recipe.vial} / Recipe ${item.recipe.recipe_id}` : `Capture ${item.number}`} <small>{time(item.seconds)}</small><span className={`assessment-state ${item.status}`}>{item.status}</span></h3>
          {item.recipe && <p className="recipe">{Object.entries(item.recipe.tanks).map(([tankId, amount]) => `Tank ${tankId}: ${amount} mL`).join(' + ')}</p>}
          <p className="assessment-text" aria-live="polite">{item.status === 'complete' ? (item.text?.trim() || 'Assessment completed without result text.') : item.status === 'running' ? 'Cosmos is inspecting this vial...' : item.status === 'queued' ? 'Queued for Cosmos...' : item.error}</p>
          {item.status === 'error' && item.recipe && <button onClick={() => void retry(item.id)}>Retry assessment</button>}
        </div>
      </article>)}
    </section></div></div>
  </main>
}



