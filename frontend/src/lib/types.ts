// TypeScript mirror of the backend's TabiffyScore (backend/tabiffy/models.py).

export type Finger = number | 'T'
export type TargetInstrument = 'guitar' | 'bass' | 'piano'

export interface Note {
  id: string
  tick: number
  durationTicks: number
  midi: number
  velocity: number
  /** Guitar/bass: 1 = highest string */
  string?: number
  /** Counted from the capo */
  fret?: number
  hand?: 'L' | 'R'
  /** 0 = open, 1-4 = index..pinky, 'T' = thumb (piano: 1-5) */
  finger?: Finger
  techniques: string[]
  confidence: number
  userEdited: boolean
  flags: string[]
}

export interface Track {
  id: string
  name: string
  sourceInstrument: 'guitar' | 'bass' | 'piano' | 'other'
  targetInstrument: TargetInstrument
  /** low -> high, e.g. ["E2","A2","D3","G3","B3","E4"] */
  tuning: string[]
  capo: number
  transposeSemitones: number
  program: number
  notes: Note[]
  sourceTrackIndex?: number
  capoSuggestion?: CapoSuggestion
}

export interface CapoSuggestion {
  capo: number
  shapesKey: string
  cost: number
}

export interface ChordLabel {
  tick: number
  durationTicks: number
  symbol: string
  pcs: number[]
  confidence: number
}

export interface SolverSettings {
  maxFret: number
  openStringPreference: number
  simplifyChords: boolean
  quantize: 'off' | '1/8' | '1/16' | '1/16+triplets' | '1/32'
}

export interface TabiffyScore {
  version: number
  meta: {
    title: string
    artist: string
    sourceFile: string
    bpm: number
    timeSignature: [number, number]
    key: string
  }
  tempoMap: { tick: number; bpm: number }[]
  ticksPerQuarter: number
  chords: ChordLabel[]
  tracks: Track[]
  settings: SolverSettings
}

export interface Job {
  id: string
  filename: string
  status: 'queued' | 'running' | 'done' | 'error'
  stage: string
  progress: number
  error: string | null
  scoreId?: string
}

export interface TuningPreset {
  label: string
  instrument: 'guitar' | 'bass'
  notes: string[]
}
