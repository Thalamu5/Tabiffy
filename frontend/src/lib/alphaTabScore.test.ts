import * as alphaTab from '@coderline/alphatab'
import { describe, expect, it } from 'vitest'
import { attachRecording, buildAlphaTabScore, flatSyncPoints, isUncertain } from './alphaTabScore'
import type { Note, TabiffyScore } from './types'

function note(p: Partial<Note> & { tick: number; midi: number }): Note {
  return { id: `n${p.tick}-${p.midi}`, durationTicks: 960, velocity: 90, techniques: [], confidence: 1, userEdited: false, flags: [], ...p }
}

const score: TabiffyScore = {
  version: 1,
  meta: { title: 'T', artist: '', sourceFile: '', bpm: 100, timeSignature: [4, 4], key: '' },
  tempoMap: [{ tick: 0, bpm: 100 }],
  ticksPerQuarter: 960,
  chords: [],
  settings: { maxFret: 22, openStringPreference: 1, simplifyChords: false, quantize: '1/16' },
  tracks: [{
    id: 't1', name: 'Guitar', sourceInstrument: 'guitar', targetInstrument: 'guitar',
    tuning: ['E2', 'A2', 'D3', 'G3', 'B3', 'E4'], capo: 0, transposeSemitones: 0, program: 25,
    notes: [
      note({ tick: 0, midi: 64, string: 1, fret: 0, confidence: 0.9 }),
      note({ tick: 960, midi: 67, string: 1, fret: 3, finger: 3, confidence: 0.2 }),
    ],
  }],
  audio: {
    durationSeconds: 5, separated: true, mode: 'full', detectedBpm: 100, tempoFactor: 1, downbeatShift: 0, warnings: [],
    syncPoints: [{ tick: 0, seconds: 0.1 }, { tick: 960, seconds: 0.7 }, { tick: 3840, seconds: 2.5 }],
  },
}

describe('alphaTab score extras', () => {
  it('flags low-confidence notes', () => {
    expect(score.tracks[0].notes.map(isUncertain)).toEqual([false, true])
  })

  it('colors uncertain notes red and leaves the rest alone', () => {
    const at = buildAlphaTabScore(score, new alphaTab.Settings())
    const beats = at.tracks[0].staves[0].bars[0].voices[0].beats
    expect(beats[0].notes[0].style).toBeUndefined()
    const styled = beats[1].notes[0].style
    expect(styled?.colors.get(alphaTab.model.NoteSubElement.GuitarTabFretNumber)?.rgba).toMatch(/211|D32F2F/i)
  })

  it('converts sync points to bar positions', () => {
    expect(flatSyncPoints(score, 10)).toEqual([
      { barIndex: 0, barPosition: 0, barOccurence: 0, millisecondOffset: 100 },
      { barIndex: 0, barPosition: 0.25, barOccurence: 0, millisecondOffset: 700 },
      { barIndex: 1, barPosition: 0, barOccurence: 0, millisecondOffset: 2500 },
    ])
  })

  it('attaches the recording and sync points to the alphaTab score', () => {
    const at = buildAlphaTabScore(score, new alphaTab.Settings())
    attachRecording(at, score, new Uint8Array([1, 2, 3]))
    expect(at.backingTrack?.rawAudioFile?.length).toBe(3)
    expect(at.exportFlatSyncPoints().length).toBeGreaterThan(0)
  })
})
