import { useEffect, useRef } from 'react'
import { nameToMidi } from '../lib/music'
import type { KeyAnalysis, ScaleMatch } from '../lib/types'

const PC_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
const FRETS = 15 // frets shown on the scale map (plus open strings)

interface Props {
  analysis: KeyAnalysis
  /** Track tuning (low -> high) for the scale map; empty for piano. */
  tuning: string[]
  capo: number
  onClose: () => void
}

/** Pitch class -> the scale's own spelling of it (e.g. 10 -> "Bb" in F major). */
function scaleNames(scale: ScaleMatch): Map<number, string> {
  return new Map(scale.pcs.map((pc, i) => [pc, scale.notes[i]]))
}

/**
 * The "why is it in this key?" window: key, scale, reasons, which notes are played most, the scale on
 * the fretboard and the runner-ups. Uses a native <dialog> so Esc and focus handling work for free.
 */
export function KeyModal({ analysis, tuning, capo, onClose }: Props) {
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    ref.current?.showModal()
  }, [])
  const { scale } = analysis
  const names = scaleNames(scale)
  const inScale = new Set(names.keys())
  const maxShare = Math.max(...analysis.histogram, 0.0001)

  return (
    <dialog ref={ref} className="key-modal" onClose={onClose} onClick={(e) => e.target === ref.current && ref.current?.close()}>
      <header>
        <div>
          <h2>{scale.label}</h2>
          <p className="muted">
            Key: <strong>{analysis.key}</strong> · {scale.family} · confidence: {analysis.confidence}
          </p>
        </div>
        <button onClick={() => ref.current?.close()} aria-label="Close">✕</button>
      </header>

      <section>
        <h3>Why we think so</h3>
        <ul className="reasons">{analysis.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
      </section>

      <section>
        <h3>Notes in the scale</h3>
        <div className="scale-notes">
          {scale.notes.map((n, i) => <span key={n} className={i === 0 ? 'pill tonic' : 'pill'}>{n}</span>)}
        </div>
      </section>

      <section>
        <h3>Which notes the song uses most</h3>
        {/* One bar per note name; notes outside the scale are drawn muted. */}
        <div className="histogram" role="img" aria-label="How much each note is played">
          {analysis.histogram.map((share, pc) => (
            <div key={pc} className={inScale.has(pc) ? 'bar in' : 'bar'} title={`${PC_NAMES[pc]}: ${Math.round(share * 100)}%`}>
              <div style={{ height: `${(share / maxShare) * 100}%` }} />
              <span>{PC_NAMES[pc]}</span>
            </div>
          ))}
        </div>
      </section>

      {tuning.length > 0 && (
        <section>
          <h3>The scale on your fretboard{capo ? ` (frets counted from the capo)` : ''}</h3>
          <div className="scale-map-wrap">
            <ScaleMap tuning={tuning} capo={capo} names={names} tonicPc={scale.tonicPc} />
          </div>
        </section>
      )}

      {analysis.alternatives.length > 0 && (
        <section>
          <h3>Other possibilities</h3>
          <ul className="alternatives">
            {analysis.alternatives.map((a) => (
              <li key={a.label}>
                <strong>{a.label}</strong> <span className="muted">({a.notes.join(' ')}) · {Math.round(a.fit * 100)}% of notes fit</span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </dialog>
  )
}

/** Every fret where a scale note sits, as an SVG fretboard (highest string on top, like tab). */
function ScaleMap({ tuning, capo, names, tonicPc }: { tuning: string[]; capo: number; names: Map<number, string>; tonicPc: number }) {
  const open = tuning.map(nameToMidi).reverse()
  const w = 30
  const h = 18
  const left = 24
  const width = left + (FRETS + 1) * w
  const height = open.length * h + 16
  return (
    <svg className="scale-map" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Scale positions on the fretboard">
      {open.map((_, s) => <line key={`s${s}`} x1={left} x2={width} y1={s * h + h / 2} y2={s * h + h / 2} className="str" />)}
      {Array.from({ length: FRETS + 1 }, (_, f) => (
        <g key={`f${f}`}>
          <line x1={left + f * w + w} x2={left + f * w + w} y1={h / 2} y2={(open.length - 1) * h + h / 2} className={f === 0 ? 'nut' : 'fret'} />
          {[3, 5, 7, 9, 12, 15].includes(f) && <text x={left + f * w + w / 2} y={height - 2} className="fretnum">{f}</text>}
        </g>
      ))}
      {open.map((m, s) =>
        Array.from({ length: FRETS + 1 }, (_, f) => {
          const pc = (m + capo + f) % 12
          const name = names.get(pc)
          if (!name) return null
          return (
            <g key={`${s}-${f}`}>
              <circle cx={left + f * w + w / 2} cy={s * h + h / 2} r={7} className={pc === tonicPc ? 'dot tonic' : 'dot'} />
              <text x={left + f * w + w / 2} y={s * h + h / 2 + 3.5} className="dotname">{name}</text>
            </g>
          )
        }),
      )}
    </svg>
  )
}
