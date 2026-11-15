/**
 * Builds the alphaTab Score for a TabiffyScore, plus the extras alphaTex can't express:
 * red uncertain notes, sync points to the original recording, and the recording itself.
 */
import * as alphaTab from '@coderline/alphatab'
import { toAlphaTex } from './toAlphaTex'
import type { Note, TabiffyScore } from './types'

export const LOW_CONFIDENCE = 0.5
const UNCERTAIN_COLOR = '#D32F2F'

export function isUncertain(n: Note): boolean {
  return n.confidence < LOW_CONFIDENCE || n.flags.includes('outOfRange') || n.flags.includes('hardFingering')
}

export function buildAlphaTabScore(score: TabiffyScore, settings: alphaTab.Settings): alphaTab.model.Score {
  const importer = new alphaTab.importer.AlphaTexImporter()
  importer.initFromString(toAlphaTex(score), settings)
  const at = importer.readScore()
  markUncertainNotes(at, score)
  return at
}

/** Colors notes whose pitch or fingering may be wrong (alphaTab track i = score.tracks[i]). */
export function markUncertainNotes(at: alphaTab.model.Score, score: TabiffyScore): number {
  let marked = 0
  score.tracks.forEach((track, ti) => {
    const flagged = new Set(track.notes.filter(isUncertain).map((n) => `${n.tick}|${n.midi}`))
    if (!flagged.size || !at.tracks[ti]) return
    const color = alphaTab.model.Color.fromJson(UNCERTAIN_COLOR)!
    for (const staff of at.tracks[ti].staves)
      for (const bar of staff.bars)
        for (const voice of bar.voices)
          for (const beat of voice.beats)
            for (const note of beat.notes) {
              if (note.isTieDestination || !flagged.has(`${beat.absolutePlaybackStart}|${note.realValue}`)) continue
              note.style = new alphaTab.model.NoteStyle()
              note.style.colors.set(alphaTab.model.NoteSubElement.GuitarTabFretNumber, color)
              note.style.colors.set(alphaTab.model.NoteSubElement.StandardNotationNoteHead, color)
              marked++
            }
  })
  return marked
}

/** Sync points (score tick -> recording time) as alphaTab expects them: per bar + position. */
export function flatSyncPoints(score: TabiffyScore, barCount: number): alphaTab.model.FlatSyncPoint[] {
  if (!score.audio) return []
  const [num, den] = score.meta.timeSignature
  const barTicks = Math.round((num * 4 * score.ticksPerQuarter) / den)
  return score.audio.syncPoints
    .map((p) => ({
      barIndex: Math.floor(p.tick / barTicks),
      barPosition: (p.tick % barTicks) / barTicks,
      barOccurence: 0,
      millisecondOffset: Math.round(p.seconds * 1000),
    }))
    .filter((p) => p.barIndex < barCount)
}

/** Attach the original recording so alphaTab plays it (with the cursor following) instead of the synth. */
export function attachRecording(at: alphaTab.model.Score, score: TabiffyScore, audio: Uint8Array): void {
  const backing = new alphaTab.model.BackingTrack()
  backing.rawAudioFile = audio
  at.backingTrack = backing
  at.applyFlatSyncPoints(flatSyncPoints(score, at.masterBars.length))
}
