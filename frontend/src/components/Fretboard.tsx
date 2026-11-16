import { isUncertain } from '../lib/alphaTabScore'
import { nameToMidi, pitchClassName } from '../lib/music'
import type { Note, Track } from '../lib/types'

interface Props {
  track: Track
  active: Note[]
  upcoming: Note[]
  leftHanded: boolean
}

const INLAYS = [3, 5, 7, 9, 15, 17, 19, 21]
const DOUBLE_INLAYS = [12, 24]

/**
 * SVG fretboard. String 1 (highest) is drawn at the top, like tab. Frets are drawn in
 * absolute positions (counted from the nut); note frets are relative to the capo.
 */
export function Fretboard({ track, active, upcoming, leftHanded }: Props) {
  const nStrings = track.tuning.length
  const capo = track.capo
  const maxUsed = Math.max(0, ...track.notes.map((n) => (n.fret ?? 0) + capo))
  const frets = Math.min(24, Math.max(12, maxUsed + 1))

  const padL = 60
  const padR = 14
  const padT = 22
  const width = 1000
  const stringGap = 22
  const height = padT * 2 + stringGap * (nStrings - 1)
  const boardW = width - padL - padR

  // Slightly tapered fret spacing (real guitars use a factor of 2^(-1/12)).
  const raw = Array.from({ length: frets + 1 }, (_, i) => 1 - Math.pow(2, -i / 18))
  const scale = boardW / raw[frets]
  const fretX = (f: number) => {
    const x = padL + raw[f] * scale
    return leftHanded ? width - x : x
  }
  const noteX = (absFret: number) => (absFret === 0 ? fretX(0) - (leftHanded ? -16 : 16) : (fretX(absFret - 1) + fretX(absFret)) / 2)
  const stringY = (s: number) => padT + (s - 1) * stringGap

  const barres = new Map<number, number[]>()
  for (const n of active) {
    if (n.flags.includes('barre') && n.fret && n.string) {
      barres.set(n.fret, [...(barres.get(n.fret) ?? []), n.string])
    }
  }

  const dot = (n: Note, ghost: boolean) => {
    if (!n.string || n.fret === undefined) return null
    const abs = n.fret + capo
    const x = n.fret === 0 && capo > 0 ? fretX(capo) + (leftHanded ? -10 : 10) : noteX(abs)
    const y = stringY(n.string)
    const isOpen = n.fret === 0
    // Tapped notes are played by the picking hand: shown as "T" on a different color, not a finger number.
    const tapped = n.techniques.includes('tap')
    const label = isOpen ? '0' : tapped ? 'T' : n.finger !== undefined && n.finger !== 0 ? String(n.finger) : ''
    const cls = isOpen ? 'fb-open' : isUncertain(n) ? 'fb-note fb-warn' : tapped ? 'fb-note fb-tap' : 'fb-note'
    return (
      <g key={`${ghost ? 'g' : 'a'}-${n.id}`} opacity={ghost ? 0.35 : 1}>
        <circle cx={x} cy={y} r={9} className={cls} />
        {!ghost && <text x={x} y={y + 4} className="fb-finger">{label}</text>}
      </g>
    )
  }

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="fretboard" role="img" aria-label="Fretboard">
      <rect x={Math.min(fretX(0), fretX(frets))} y={padT - 8} width={boardW} height={stringGap * (nStrings - 1) + 16} className="fb-wood" />
      {INLAYS.filter((f) => f <= frets).map((f) => (
        <circle key={f} cx={(fretX(f - 1) + fretX(f)) / 2} cy={padT + (stringGap * (nStrings - 1)) / 2} r={5} className="fb-inlay" />
      ))}
      {DOUBLE_INLAYS.filter((f) => f <= frets).map((f) => (
        <g key={f}>
          <circle cx={(fretX(f - 1) + fretX(f)) / 2} cy={padT + stringGap * 0.9} r={5} className="fb-inlay" />
          <circle cx={(fretX(f - 1) + fretX(f)) / 2} cy={padT + stringGap * (nStrings - 1.9)} r={5} className="fb-inlay" />
        </g>
      ))}
      {Array.from({ length: frets + 1 }, (_, f) => (
        <line key={f} x1={fretX(f)} x2={fretX(f)} y1={padT - 8} y2={height - padT + 8} className={f === 0 ? 'fb-nut' : 'fb-fret'} />
      ))}
      {Array.from({ length: frets }, (_, i) => i + 1).filter((f) => [3, 5, 7, 9, 12, 15, 17, 19, 21, 24].includes(f)).map((f) => (
        <text key={f} x={(fretX(f - 1) + fretX(f)) / 2} y={height - 4} className="fb-fretnum">{f}</text>
      ))}
      {track.tuning.map((_, i) => {
        const s = i + 1
        const name = track.tuning[nStrings - 1 - i]
        return (
          <g key={s}>
            <line x1={fretX(0)} x2={fretX(frets)} y1={stringY(s)} y2={stringY(s)} className="fb-string" strokeWidth={0.8 + i * 0.35} />
            <text x={leftHanded ? width - 14 : 14} y={stringY(s) + 4} className="fb-tuning">{pitchClassName(nameToMidi(name))}</text>
          </g>
        )
      })}
      {capo > 0 && (
        <g>
          <rect x={fretX(capo) - (leftHanded ? -2 : 7)} y={padT - 12} width={5} height={stringGap * (nStrings - 1) + 24} rx={2} className="fb-capo" />
          <text x={fretX(capo)} y={padT - 14} className="fb-capo-label">capo {capo}</text>
        </g>
      )}
      {[...barres.entries()].filter(([, strings]) => strings.length >= 2).map(([fret, strings]) => {
        const x = noteX(fret + capo)
        const y1 = stringY(Math.min(...strings))
        const y2 = stringY(Math.max(...strings))
        return <rect key={`barre-${fret}`} x={x - 9} y={y1 - 9} width={18} height={y2 - y1 + 18} rx={9} className="fb-barre" />
      })}
      {upcoming.map((n) => dot(n, true))}
      {active.map((n) => dot(n, false))}
    </svg>
  )
}
