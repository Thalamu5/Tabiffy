import * as alphaTab from '@coderline/alphatab'
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { decompose, toAlphaTex } from './toAlphaTex'
import type { Note, TabiffyScore } from './types'

function note(p: Partial<Note> & { tick: number; durationTicks: number; midi: number }): Note {
  return { id: `n${p.tick}-${p.midi}`, velocity: 90, techniques: [], confidence: 1, userEdited: false, flags: [], ...p }
}

function score(notes: Note[], extra: Partial<TabiffyScore> = {}): TabiffyScore {
  return {
    version: 1,
    meta: { title: 'Test', artist: '', sourceFile: '', bpm: 100, timeSignature: [4, 4], key: '' },
    tempoMap: [{ tick: 0, bpm: 100 }],
    ticksPerQuarter: 960,
    chords: [],
    settings: { maxFret: 22, openStringPreference: 1, simplifyChords: false, quantize: '1/16' },
    tracks: [{
      id: 't1', name: 'Guitar', sourceInstrument: 'guitar', targetInstrument: 'guitar',
      tuning: ['E2', 'A2', 'D3', 'G3', 'B3', 'E4'], capo: 0, transposeSemitones: 0, program: 25, notes,
    }],
    ...extra,
  }
}

function load(tex: string): alphaTab.model.Score {
  const settings = new alphaTab.Settings()
  const importer = new alphaTab.importer.AlphaTexImporter()
  importer.initFromString(tex, settings)
  return importer.readScore()
}

/** All sounding notes as [tick, midi] pairs, from the alphaTab model (ties merged). */
function soundingNotes(s: alphaTab.model.Score, trackIndex = 0): [number, number][] {
  const out: [number, number][] = []
  for (const staff of s.tracks[trackIndex].staves)
    for (const bar of staff.bars)
      for (const voice of bar.voices)
        for (const beat of voice.beats)
          for (const n of beat.notes)
            if (!n.isTieDestination) out.push([beat.absolutePlaybackStart, n.realValue])
  return out.sort((a, b) => a[0] - b[0] || a[1] - b[1])
}

describe('decompose', () => {
  it('splits lengths into note values', () => {
    expect(decompose(960).map((p) => p.dur)).toEqual([4])
    expect(decompose(1440)).toMatchObject([{ dur: 4, dotted: true }])
    expect(decompose(1200).map((p) => p.dur)).toEqual([4, 16])
    expect(decompose(320)).toMatchObject([{ dur: 8, triplet: true }])
  })
})

describe('toAlphaTex', () => {
  it('writes frets, strings and finger numbers that alphaTab understands', () => {
    const tex = toAlphaTex(score([
      note({ tick: 0, durationTicks: 960, midi: 48, string: 5, fret: 3, finger: 3 }),
      note({ tick: 0, durationTicks: 960, midi: 52, string: 4, fret: 2, finger: 2 }),
      note({ tick: 0, durationTicks: 960, midi: 60, string: 2, fret: 1, finger: 1 }),
      note({ tick: 960, durationTicks: 480, midi: 64, string: 1, fret: 0, finger: 0 }),
    ]))
    const s = load(tex)
    const beats = s.tracks[0].staves[0].bars[0].voices[0].beats
    const first = beats[0].notes.map((n) => [n.string, n.fret, n.leftHandFinger]).sort()
    // alphaTab numbers strings from the lowest (1) up; LeftHandFingers: 1 = index
    expect(first).toEqual([[2, 3, 3], [3, 2, 2], [5, 1, 1]].sort())
    expect(soundingNotes(s)).toEqual([[0, 48], [0, 52], [0, 60], [960, 64]])
  })

  it('fills bars exactly and ties notes across barlines', () => {
    const s = load(toAlphaTex(score([note({ tick: 2880, durationTicks: 1920, midi: 64, string: 1, fret: 0 })])))
    const bars = s.tracks[0].staves[0].bars
    expect(bars.length).toBe(2)
    const tied = bars[1].voices[0].beats[0].notes[0]
    expect(tied.isTieDestination).toBe(true)
    expect(soundingNotes(s)).toEqual([[2880, 64]])
  })

  it('keeps capo, tuning, tempo changes and chord names', () => {
    const s = load(toAlphaTex(score(
      [note({ tick: 0, durationTicks: 3840, midi: 50, string: 4, fret: 0 }),
       note({ tick: 3840, durationTicks: 3840, midi: 52, string: 4, fret: 2 })],
      {
        tempoMap: [{ tick: 0, bpm: 100 }, { tick: 3840, bpm: 140 }],
        chords: [{ tick: 0, durationTicks: 3840, symbol: 'D', pcs: [2, 6, 9], confidence: 1 }],
      },
    )).replace('\\tuning (E4 B3 G3 D3 A2 E2)', '\\tuning (D4 A3 F#3 D3 A2 D2)\n\\capo 2'))
    const staff = s.tracks[0].staves[0]
    expect(staff.capo).toBe(2)
    expect(staff.tuning).toEqual([62, 57, 54, 50, 45, 38])
    expect(staff.bars[1].masterBar.tempoAutomations[0].value).toBe(140)
    expect(staff.bars[0].voices[0].beats[0].chord?.name).toBe('D')
  })

  it('renders piano tracks on two staves by hand', () => {
    const base = score([])
    base.tracks[0] = {
      ...base.tracks[0], targetInstrument: 'piano', tuning: [], program: 0, notes: [
        note({ tick: 0, durationTicks: 960, midi: 72, hand: 'R' }),
        note({ tick: 0, durationTicks: 1920, midi: 48, hand: 'L' }),
      ],
    }
    const s = load(toAlphaTex(base))
    expect(s.tracks[0].staves.length).toBe(2)
    expect(soundingNotes(s)).toEqual([[0, 48], [0, 72]])
  })

  it.each([
    [7, ['B1', 'E2', 'A2', 'D3', 'G3', 'B3', 'E4']],
    [8, ['F#1', 'B1', 'E2', 'A2', 'D3', 'G3', 'B3', 'E4']],
  ])('renders %i-string tunings with notes on the lowest string', (strings, tuning) => {
    const base = score([
      note({ tick: 0, durationTicks: 960, midi: strings === 7 ? 35 : 30, string: strings, fret: 0 }),
      note({ tick: 960, durationTicks: 960, midi: strings === 7 ? 38 : 33, string: strings, fret: 3, finger: 3 }),
    ])
    base.tracks[0].tuning = tuning
    const s = load(toAlphaTex(base))
    const staff = s.tracks[0].staves[0]
    expect(staff.tuning.length).toBe(strings)
    const beats = staff.bars[0].voices[0].beats
    // alphaTab numbers strings from the lowest (1)
    expect(beats[0].notes[0].string).toBe(1)
    expect(soundingNotes(s).map((n) => n[1])).toEqual(strings === 7 ? [35, 38] : [30, 33])
  })

  it('handles triplets', () => {
    const s = load(toAlphaTex(score([0, 320, 640].map((t) => note({ tick: t, durationTicks: 320, midi: 64, string: 1, fret: 0 })))))
    const beats = s.tracks[0].staves[0].bars[0].voices[0].beats
    expect(beats[0].tupletNumerator).toBe(3)
    expect(soundingNotes(s).map((n) => n[0])).toEqual([0, 320, 640])
  })

  it('round-trips through Guitar Pro (.gp) export and import', () => {
    const notes = [45, 48, 50, 52, 55, 57, 60, 62].map((m, i) =>
      note({ tick: i * 240, durationTicks: 240, midi: m, string: 6 - Math.floor(i / 2), fret: [5, 8, 5, 7, 5, 7, 5, 7][i], finger: 1 }))
    const original = load(toAlphaTex(score(notes)))
    const settings = new alphaTab.Settings()
    const gp = new alphaTab.exporter.Gp7Exporter().export(original, settings)
    const reloaded = alphaTab.importer.ScoreLoader.loadScoreFromBytes(gp, settings)
    expect(soundingNotes(reloaded)).toEqual(soundingNotes(original))
    const frets = (sc: alphaTab.model.Score) => sc.tracks[0].staves[0].bars[0].voices[0].beats.flatMap((b) => b.notes.map((n) => [n.string, n.fret]))
    expect(frets(reloaded)).toEqual(frets(original))
  })

  it('converts a real pipeline output fixture', () => {
    const fixture = JSON.parse(readFileSync(new URL('../../test-fixtures/chord_progression.score.json', import.meta.url), 'utf8'))
    const s = load(toAlphaTex(fixture))
    const expected = fixture.tracks[0].notes.map((n: Note) => [n.tick, n.midi]).sort((a: number[], b: number[]) => a[0] - b[0] || a[1] - b[1])
    expect(soundingNotes(s)).toEqual(expected)
  })
})
