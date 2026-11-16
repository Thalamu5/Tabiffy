/**
 * TabiffyScore -> alphaTex (alphaTab's text format), which alphaTab turns into a
 * full Score for rendering, playback and Guitar Pro / MIDI export.
 *
 * Polyphony is flattened into one voice per staff: every note start/end and every
 * barline is a "segment" boundary; notes still sounding across a boundary are tied.
 * Segment lengths are split into standard note values (dotted and triplets included).
 */
import { midiToName } from './music'
import type { ChordLabel, Note, TabiffyScore, Track } from './types'

const TPQ = 960

interface Piece {
  ticks: number
  dur: number // 1, 2, 4, 8, 16, 32, 64
  dotted: boolean
  triplet: boolean
}

const STRAIGHT: Piece[] = [1, 2, 4, 8, 16, 32, 64].flatMap((dur) => {
  const base = (TPQ * 4) / dur
  const out: Piece[] = []
  if (dur <= 32) out.push({ ticks: base * 1.5, dur, dotted: true, triplet: false })
  out.push({ ticks: base, dur, dotted: false, triplet: false })
  return out
})
const TRIPLETS: Piece[] = [2, 4, 8, 16, 32].map((dur) => ({
  ticks: ((TPQ * 4) / dur) * (2 / 3),
  dur,
  dotted: false,
  triplet: true,
}))
const MIN_TICKS = 60 // 64th note

const memo = new Map<number, Piece[] | null>()

/** Split a length in ticks into note values, e.g. 1200 -> [quarter, 16th]. */
export function decompose(ticks: number): Piece[] {
  if (ticks <= 0) return []
  const cached = memo.get(ticks)
  if (cached !== undefined) return cached ?? fallback(ticks)
  const result = decomposeExact(ticks)
  memo.set(ticks, result)
  return result ?? fallback(ticks)
}

function decomposeExact(ticks: number): Piece[] | null {
  if (ticks === 0) return []
  if (ticks % MIN_TICKS === 0) {
    const out: Piece[] = []
    let left = ticks
    while (left > 0) {
      const p = STRAIGHT.find((s) => s.ticks <= left && (left - s.ticks) % MIN_TICKS === 0)!
      out.push(p)
      left -= p.ticks
    }
    return out
  }
  // Needs triplets: take triplet pieces in groups of 3 is not required by alphaTab, but
  // keep it simple: try each triplet value, then solve the remainder.
  for (const t of TRIPLETS) {
    if (t.ticks <= ticks) {
      const rest = decomposeExact(ticks - t.ticks)
      if (rest) return [t, ...rest]
    }
  }
  return null
}

function fallback(ticks: number): Piece[] {
  const rounded = Math.max(MIN_TICKS, Math.round(ticks / MIN_TICKS) * MIN_TICKS)
  return decomposeExact(rounded) ?? []
}

function durationTex(p: Piece): { prefix: string; effects: string[] } {
  const effects: string[] = []
  if (p.dotted) effects.push('d')
  if (p.triplet) effects.push('tu 3')
  return { prefix: `:${p.dur}`, effects }
}

function quote(s: string): string {
  return `"${s.replace(/\\/g, '\\\\').replace(/"/g, '\\"')}"`
}

function sharpName(name: string): string {
  // alphaTex wants sharps (e.g. "Eb2" -> "D#2")
  const flats: Record<string, string> = { Db: 'C#', Eb: 'D#', Gb: 'F#', Ab: 'G#', Bb: 'A#', Cb: 'B', Fb: 'E' }
  const m = /^([A-G]b)(-?\d+)$/.exec(name)
  if (!m) return name
  const oct = m[1] === 'Cb' ? parseInt(m[2], 10) - 1 : parseInt(m[2], 10)
  return `${flats[m[1]]}${oct}`
}

/** alphaTex left-hand finger: 1 = thumb, 2 = index ... 5 = pinky */
function fingerTex(n: Note): string | null {
  if (n.finger === 'T') return 'lf 1'
  if (typeof n.finger === 'number' && n.finger >= 1 && n.finger <= 4 && (n.fret ?? 0) > 0) return `lf ${n.finger + 1}`
  return null
}

/** alphaTex for a note's technique: "h" = hammer-on / pull-off and "sl" = legato slide into the next note. */
function techniqueTex(n: Note): string | null {
  if (!n.legatoTo) return null
  if (n.techniques.includes('slide')) return 'sl'
  if (n.techniques.includes('hammer') || n.techniques.includes('pull')) return 'h'
  return null
}

interface StaffOptions {
  stringed: boolean
  barTicks: number
  totalBars: number
  chords?: Map<number, string>
  tempos?: Map<number, number>
}

/** Build the beats of one staff (a list of bar strings). */
export function staffBars(notes: Note[], opt: StaffOptions): string[] {
  const end = opt.totalBars * opt.barTicks
  const bounds = new Set<number>()
  for (let b = 0; b <= opt.totalBars; b++) bounds.add(b * opt.barTicks)
  for (const n of notes) {
    bounds.add(n.tick)
    bounds.add(Math.min(end, n.tick + n.durationTicks))
  }
  opt.chords?.forEach((_, t) => bounds.add(t))
  opt.tempos?.forEach((_, t) => bounds.add(t))
  const points = [...bounds].filter((t) => t >= 0 && t <= end).sort((a, b) => a - b)

  const sorted = [...notes].sort((a, b) => a.tick - b.tick)
  const bars: string[][] = Array.from({ length: opt.totalBars }, () => [])
  let lastDur = ''
  let active: Note[] = []
  let cursor = 0

  for (let i = 0; i < points.length - 1; i++) {
    const a = points[i]
    const b = points[i + 1]
    if (b <= a) continue
    while (cursor < sorted.length && sorted[cursor].tick <= a) active.push(sorted[cursor++])
    active = active.filter((n) => n.tick + n.durationTicks > a)

    // One note per string (stringed) or per pitch (piano); a new note replaces a ringing one.
    const byKey = new Map<number, Note>()
    for (const n of active) {
      const key = opt.stringed ? (n.string ?? 0) : n.midi
      const prev = byKey.get(key)
      if (!prev || n.tick > prev.tick) byKey.set(key, n)
    }
    const sounding = [...byKey.values()].sort((x, y) => (opt.stringed ? (x.string ?? 0) - (y.string ?? 0) : x.midi - y.midi))

    const pieces = decompose(b - a)
    pieces.forEach((p, pi) => {
      const { prefix, effects } = durationTex(p)
      const beatEffects = [...effects]
      if (pi === 0) {
        const chord = opt.chords?.get(a)
        if (chord) beatEffects.push(`ch ${quote(chord)}`)
        const tempo = opt.tempos?.get(a)
        if (tempo && a > 0) beatEffects.push(`tempo ${Math.round(tempo * 100) / 100}`)
      }
      let body: string
      if (sounding.length === 0) {
        body = 'r'
      } else {
        const parts = sounding.map((n) => {
          const isNew = pi === 0 && n.tick === a
          if (opt.stringed) {
            // A technique goes on the last piece of a tied note, where it leads into the next note.
            const last = pi === pieces.length - 1 && n.tick + n.durationTicks <= b
            const fx = [isNew ? fingerTex(n) : null, last ? techniqueTex(n) : null].filter(Boolean)
            const props = fx.length ? `{${fx.join(' ')}}` : ''
            return isNew ? `${n.fret}.${n.string}${props}` : `-.${n.string}${props}`
          }
          return isNew ? midiToName(n.midi) : `${midiToName(n.midi)}{-}`
        })
        body = parts.length === 1 ? parts[0] : `(${parts.join(' ')})`
      }
      const durPart = prefix !== lastDur ? `${prefix} ` : ''
      lastDur = prefix
      const barIndex = Math.min(opt.totalBars - 1, Math.floor(a / opt.barTicks))
      bars[barIndex].push(`${durPart}${body}${beatEffects.length ? `{${beatEffects.join(' ')}}` : ''}`)
    })
  }
  return bars.map((beats) => beats.join(' '))
}

const DIAGRAM_FRETS = 5 // alphaTab draws 5 frets per chord box

/**
 * Chord box for one chord: the fret most played on each string while the chord lasts, kept within a
 * 5-fret window so every dot fits in the box. `firstfret` moves the box up the neck for high shapes.
 */
export function chordDiagram(track: Track, chord: ChordLabel): string {
  const n = track.tuning.length
  const end = chord.tick + chord.durationTicks
  // weights[string][fret] = how long that fret sounds during the chord
  const weights: Map<number, number>[] = Array.from({ length: n }, () => new Map())
  for (const note of track.notes) {
    if (note.tick < chord.tick || note.tick >= end || !note.string || note.fret === undefined) continue
    const w = weights[note.string - 1]
    if (w) w.set(note.fret, (w.get(note.fret) ?? 0) + note.durationTicks)
  }

  // Try each 5-fret window and keep the one covering the most sound (open strings fit any window).
  const starts = new Set<number>([1])
  weights.forEach((w) => w.forEach((_, f) => f > 0 && starts.add(f)))
  let best: { frets: (number | null)[]; total: number; start: number } = { frets: [], total: -1, start: 1 }
  for (const start of starts) {
    let total = 0
    const frets = weights.map((w) => {
      let pick: number | null = null
      let pickW = 0
      w.forEach((wt, f) => {
        if ((f === 0 || (f >= start && f < start + DIAGRAM_FRETS)) && wt > pickW) {
          pick = f
          pickW = wt
        }
      })
      total += pickW
      return pick
    })
    if (total > best.total) best = { frets, total, start }
  }
  // A single string isn't a chord shape, so it gets no box.
  if (best.frets.filter((f) => f !== null).length < 2) return ''

  // Start the box at fret 1 when the shape fits there; otherwise at the lowest fretted note.
  const fretted = best.frets.filter((f): f is number => f !== null && f > 0)
  const firstFret = fretted.length && Math.max(...fretted) > DIAGRAM_FRETS ? Math.min(...fretted) : 1
  // A barre: the lowest fret is held on 2+ strings by the index finger in the solved tab.
  const low = fretted.length ? Math.min(...fretted) : 0
  const barreStrings = track.notes.filter(
    (x) => x.tick >= chord.tick && x.tick < end && x.fret === low && x.finger === 1 && best.frets[(x.string ?? 0) - 1] === low,
  )
  const barre = low > 0 && new Set(barreStrings.map((x) => x.string)).size >= 2

  const props = [firstFret > 1 ? `firstfret ${firstFret}` : '', barre ? `barre ${low}` : ''].filter(Boolean)
  const body = best.frets.map((f) => (f === null ? 'x' : String(f))).join(' ')
  return props.length ? `${body} {${props.join(' ')}}` : body
}

/** Convert a whole score. Track order is preserved (alphaTab track i = score.tracks[i]). */
export function toAlphaTex(score: TabiffyScore): string {
  const [num, den] = score.meta.timeSignature
  const barTicks = Math.round((num * 4 * score.ticksPerQuarter) / den)
  const lastTick = Math.max(barTicks, ...score.tracks.flatMap((t) => t.notes.map((n) => n.tick + n.durationTicks)))
  const totalBars = Math.max(1, Math.ceil(lastTick / barTicks))
  const tempos = new Map(score.tempoMap.map((t) => [t.tick, t.bpm]))

  const lines: string[] = []
  if (score.meta.title) lines.push(`\\title ${quote(score.meta.title)}`)
  if (score.meta.artist) lines.push(`\\artist ${quote(score.meta.artist)}`)
  lines.push(`\\tempo ${Math.round((score.tempoMap[0]?.bpm ?? score.meta.bpm) * 100) / 100}`)
  lines.push('.')

  const chordTrackIndex = score.tracks.findIndex((t) => t.targetInstrument !== 'piano')
  score.tracks.forEach((track, ti) => {
    lines.push(`\\track ${quote(track.name)}`)
    lines.push(`\\instrument ${track.program}`)
    const withTempo = ti === 0 ? tempos : undefined
    const header = (bars: string[]) => {
      if (bars.length) bars[0] = `\\ts ${num} ${den} ${bars[0]}`
      return bars.join(' |\n')
    }
    if (track.targetInstrument === 'piano') {
      const rh = track.notes.filter((n) => n.hand !== 'L')
      const lh = track.notes.filter((n) => n.hand === 'L')
      lines.push('\\staff {score}')
      lines.push('\\clef G2')
      lines.push(header(staffBars(rh, { stringed: false, barTicks, totalBars, tempos: withTempo })))
      lines.push('\\staff {score}')
      lines.push('\\clef F4')
      lines.push(header(staffBars(lh, { stringed: false, barTicks, totalBars })))
      return
    }
    let chords: Map<number, string> | undefined
    if (ti === chordTrackIndex) {
      chords = new Map()
      // One box per chord name, drawn from its longest occurrence (the most representative shape).
      const longest = new Map<string, ChordLabel>()
      for (const c of score.chords) {
        chords.set(c.tick, c.symbol)
        const prev = longest.get(c.symbol)
        if (!prev || c.durationTicks > prev.durationTicks) longest.set(c.symbol, c)
      }
      for (const [symbol, c] of longest) {
        const diagram = chordDiagram(track, c)
        if (diagram) lines.push(`\\chord ${quote(symbol)} ${diagram}`)
      }
    }
    lines.push(`\\staff {score tabs}`)
    lines.push(`\\tuning (${[...track.tuning].reverse().map(sharpName).join(' ')})`)
    if (track.capo > 0) lines.push(`\\capo ${track.capo}`)
    lines.push(header(staffBars(track.notes, { stringed: true, barTicks, totalBars, chords, tempos: withTempo })))
  })
  return lines.join('\n')
}
