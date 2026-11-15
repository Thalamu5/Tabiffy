// Small pitch helpers shared by the converter and the visualizers.

const PC: Record<string, number> = {
  C: 0, 'C#': 1, DB: 1, D: 2, 'D#': 3, EB: 3, E: 4, F: 5, 'F#': 6, GB: 6,
  G: 7, 'G#': 8, AB: 8, A: 9, 'A#': 10, BB: 10, B: 11, CB: 11, FB: 4, 'E#': 5, 'B#': 0,
}
const SHARPS = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

export function nameToMidi(name: string): number {
  const m = /^([A-Ga-g])([#b]?)(-?\d+)$/.exec(name.trim())
  if (!m) throw new Error(`Not a note name: ${name}`)
  const pc = PC[(m[1] + m[2]).toUpperCase()]
  return pc + (parseInt(m[3], 10) + 1) * 12
}

export function midiToName(midi: number): string {
  return `${SHARPS[midi % 12]}${Math.floor(midi / 12) - 1}`
}

export function pitchClassName(midi: number): string {
  return SHARPS[midi % 12]
}

export function isBlackKey(midi: number): boolean {
  return [1, 3, 6, 8, 10].includes(midi % 12)
}
