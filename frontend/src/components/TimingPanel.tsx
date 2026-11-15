import { useState } from 'react'
import type { TimingRequest } from '../lib/api'
import type { TabiffyScore } from '../lib/types'

interface Props {
  score: TabiffyScore
  busy: boolean
  onApply: (req: TimingRequest) => void
}

const AUDIO_SIGNATURES: [number, number][] = [[2, 4], [3, 4], [4, 4], [5, 4], [6, 4], [7, 4]]
const MIDI_SIGNATURES: [number, number][] = [...AUDIO_SIGNATURES, [3, 8], [6, 8], [9, 8], [12, 8]]

/** Fix the detected tempo, time signature and bar lines. Re-solves all tracks. */
export function TimingPanel({ score, busy, onApply }: Props) {
  const audio = score.audio
  const [sig, setSig] = useState(score.meta.timeSignature.join('/'))
  const [bpm, setBpm] = useState(String(Math.round(score.tempoMap[0]?.bpm ?? score.meta.bpm)))
  const signatures = audio ? AUDIO_SIGNATURES : MIDI_SIGNATURES
  const [num, den] = sig.split('/').map(Number) as [number, number]

  const apply = (extra: Partial<TimingRequest> = {}) => {
    const req: TimingRequest = { timeSignature: [num, den] }
    if (audio) {
      req.tempoFactor = audio.tempoFactor
      req.downbeatShift = audio.downbeatShift
    } else if (Number(bpm) >= 20) {
      req.bpm = Number(bpm)
    }
    onApply({ ...req, ...extra })
  }

  return (
    <section className="timing">
      <h3>Song timing</h3>
      {audio && (
        <p className="hint">
          Detected {Math.round(audio.detectedBpm)} BPM{audio.tempoFactor !== 1 ? `, shown at ${audio.tempoFactor === 2 ? 'double' : 'half'} time` : ''}.
          If the bars look wrong, try these:
        </p>
      )}
      <label>
        Time signature
        <select value={sig} onChange={(e) => setSig(e.target.value)}>
          {signatures.map(([n, d]) => <option key={`${n}/${d}`} value={`${n}/${d}`}>{n}/{d}</option>)}
        </select>
      </label>
      {audio ? (
        <>
          <div className="row">
            <span>Tempo</span>
            <div className="segmented">
              {[0.5, 1, 2].map((f) => (
                <button key={f} className={audio.tempoFactor === f ? 'on' : ''} disabled={busy}
                  onClick={() => apply({ tempoFactor: f, downbeatShift: 0 })}>
                  {f === 0.5 ? 'Half' : f === 1 ? 'As detected' : 'Double'}
                </button>
              ))}
            </div>
          </div>
          <div className="row">
            <span>Bar lines</span>
            <div className="segmented">
              <button disabled={busy} onClick={() => apply({ downbeatShift: (audio.downbeatShift + num - 1) % num })}>◀ 1 beat</button>
              <button disabled={busy} onClick={() => apply({ downbeatShift: (audio.downbeatShift + 1) % num })}>1 beat ▶</button>
            </div>
          </div>
        </>
      ) : (
        <label>
          Tempo (BPM)
          <input type="number" min={20} max={400} value={bpm} onChange={(e) => setBpm(e.target.value)} />
        </label>
      )}
      <button className="wide" disabled={busy} onClick={() => apply()}>Apply timing</button>
    </section>
  )
}
