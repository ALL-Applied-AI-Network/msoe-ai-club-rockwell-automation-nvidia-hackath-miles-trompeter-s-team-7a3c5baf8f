import { useEffect, useRef, useState } from 'react'

type Reply = { answer: string; source: string; snapshot: { at: string; total: number; counts: { review: number; uncertain: number; pending: number; no_clear_deviation: number } } }
type Turn = { question: string; reply?: Reply; error?: string }
const suggestions = ['How many vials need checking?', 'Which vials are uncertain?', 'Which batches show possible carryover?', 'Explain the latest flagged vial.']

export default function RunChat({ run }: { run?: string }) {
  const [question, setQuestion] = useState('')
  const [turns, setTurns] = useState<Turn[]>([])
  const [busy, setBusy] = useState(false)
  const request = useRef<AbortController | null>(null)
  useEffect(() => () => request.current?.abort(), [])
  async function send(value: string) {
    const text = value.trim()
    if (!run || !text || busy) return
    const controller = new AbortController()
    request.current = controller
    const history = turns.flatMap(turn => turn.reply ? [{ role: 'user', content: turn.question }, { role: 'assistant', content: turn.reply.answer.slice(0, 2000) }] : []).slice(-4)
    setTurns(previous => [...previous.slice(-9), { question: text }]); setQuestion(''); setBusy(true)
    const timer = setTimeout(() => controller.abort(), 75000)
    try {
      const response = await fetch(`/api/assessments/${encodeURIComponent(run)}/chat`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question: text, history }), signal: controller.signal })
      if (!response.ok) throw new Error(`Question failed (HTTP ${response.status}). Check the API and try again.`)
      const reply: Reply = await response.json()
      if (!controller.signal.aborted) setTurns(previous => previous.map((turn, index) => index === previous.length - 1 ? { ...turn, reply } : turn))
    } catch (error) {
      setTurns(previous => previous.map((turn, index) => index === previous.length - 1 ? { ...turn, error: controller.signal.aborted ? 'Question timed out or was cancelled. Try again.' : error instanceof Error ? error.message : 'Could not ask this run.' } : turn))
    } finally { clearTimeout(timer); setBusy(false) }
  }
  return <section className="panel run-chat" aria-label="Ask this run">
    <div className="panel-title"><h2>Ask this run</h2><span className="badge">READ ONLY</span></div>
    <p className="note">Counts come directly from run data. Cosmos explains saved findings; it does not inspect new images or control the station. Answers are snapshots, not live counts.</p>
    <div className="chat-suggestions">{suggestions.map(text => <button key={text} disabled={!run || busy} onClick={() => void send(text)}>{text}</button>)}</div>
    {!run && <p className="note">Start the cameras to create a run.</p>}
    <div className="chat-turns" role="log" aria-label="Run questions and answers" aria-live="polite">
      {turns.map((turn, index) => <article className="chat-turn" key={index}>
        <p className="chat-question">{turn.question}</p>
        {turn.reply ? <><div className="chat-facts"><strong>Verified snapshot · {new Date(turn.reply.snapshot.at).toLocaleTimeString()}</strong><p>{turn.reply.snapshot.total} unique captures · {turn.reply.snapshot.counts.review} need review · {turn.reply.snapshot.counts.uncertain} uncertain · {turn.reply.snapshot.counts.pending} pending · {turn.reply.snapshot.counts.no_clear_deviation} without clear deviation</p></div><p className="chat-source">{turn.reply.source}</p><p className="chat-answer">{turn.reply.answer}</p></> : turn.error ? <p className="error" role="alert">{turn.error}</p> : <p className="note">Checking this run…</p>}
      </article>)}
    </div>
    <form className="chat-form" onSubmit={event => { event.preventDefault(); void send(question) }}>
      <label htmlFor="run-question">Question about this run</label>
      <div><input id="run-question" value={question} onChange={event => setQuestion(event.target.value)} maxLength={500} disabled={!run || busy} placeholder="Why was vial 7 flagged?" /><button disabled={!run || busy || !question.trim()} type="submit">{busy ? 'Asking…' : 'Ask'}</button></div>
    </form>
  </section>
}
