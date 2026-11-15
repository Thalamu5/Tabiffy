import { isBlackKey } from '../lib/music'
import type { Note, Track } from '../lib/types'

interface Props {
  track: Track
  active: Note[]
  upcoming: Note[]
}

/** 88-key keyboard that zooms to the range the track uses. Colors show the hand. */
export function Piano({ track, active, upcoming }: Props) {
  const used = track.notes.map((n) => n.midi)
  let lo = used.length ? Math.min(...used) : 48
  let hi = used.length ? Math.max(...used) : 72
  lo = Math.max(21, lo - (lo % 12)) // start on a C
  hi = Math.min(108, hi + (11 - (hi % 12)))
  if (hi - lo < 24) hi = Math.min(108, lo + 35)

  const whites: number[] = []
  for (let m = lo; m <= hi; m++) if (!isBlackKey(m)) whites.push(m)
  const keyW = 1000 / whites.length
  const height = 130
  const whiteIndex = new Map(whites.map((m, i) => [m, i]))

  const activeBy = new Map(active.map((n) => [n.midi, n]))
  const upcomingSet = new Set(upcoming.map((n) => n.midi))
  const cls = (m: number) => {
    const n = activeBy.get(m)
    if (n) return n.hand === 'L' ? 'pk-left' : 'pk-right'
    if (upcomingSet.has(m)) return 'pk-next'
    return ''
  }

  const label = (m: number, x: number, y: number, light: boolean) => {
    const n = activeBy.get(m)
    if (!n) return null
    const text = typeof n.finger === 'number' && n.finger > 0 ? String(n.finger) : (n.hand ?? '')
    return <text x={x} y={y} className={light ? 'pk-label pk-label-light' : 'pk-label'}>{text}</text>
  }

  return (
    <svg viewBox={`0 0 1000 ${height + 4}`} className="piano" role="img" aria-label="Piano keyboard">
      {whites.map((m, i) => (
        <g key={m}>
          <rect x={i * keyW} y={0} width={keyW} height={height} className={`pk-white ${cls(m)}`} />
          {m % 12 === 0 && <text x={i * keyW + keyW / 2} y={height - 6} className="pk-c">C{m / 12 - 1}</text>}
          {label(m, i * keyW + keyW / 2, height - 24, false)}
        </g>
      ))}
      {Array.from({ length: hi - lo + 1 }, (_, k) => lo + k).filter(isBlackKey).map((m) => {
        const left = whiteIndex.get(m - 1)
        if (left === undefined) return null
        const x = (left + 1) * keyW - keyW * 0.3
        return (
          <g key={m}>
            <rect x={x} y={0} width={keyW * 0.6} height={height * 0.62} className={`pk-black ${cls(m)}`} />
            {label(m, x + keyW * 0.3, height * 0.62 - 10, true)}
          </g>
        )
      })}
    </svg>
  )
}
