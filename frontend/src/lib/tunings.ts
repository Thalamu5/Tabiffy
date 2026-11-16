import type { TuningPreset } from './types'

export const GUITAR_STRING_COUNTS = [6, 7, 8] as const

const FAMILY_ORDER = { standard: 0, drop: 1, open: 2 } as const

/** Presets for an instrument (and string count), in a sensible display order. */
export function presetsFor(tunings: Record<string, TuningPreset>, instrument: 'guitar' | 'bass', strings?: number) {
  return Object.entries(tunings)
    .filter(([, p]) => p.instrument === instrument && (strings === undefined || p.strings === strings))
    .sort(([, a], [, b]) => a.strings - b.strings || FAMILY_ORDER[a.family] - FAMILY_ORDER[b.family])
}

/** The preset key whose notes match a tuning exactly, if any. */
export function findPreset(tunings: Record<string, TuningPreset>, notes: string[]): string | undefined {
  const text = notes.join(' ')
  return Object.entries(tunings).find(([, p]) => p.notes.join(' ') === text)?.[0]
}

/** A short display name for a tuning (preset label, or the notes themselves). */
export function tuningName(tunings: Record<string, TuningPreset>, notes: string[]): string {
  const key = findPreset(tunings, notes)
  return key ? tunings[key].label.replace(/ \(.*\)$/, '') : notes.join(' ')
}
