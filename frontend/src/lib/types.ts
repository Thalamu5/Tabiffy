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
  /** "slide", "hammer", "pull" (leading into `legatoTo`) or "tap" */
  techniques: string[]
  legatoTo?: string
  confidence: number
  userEdited: boolean
  flags: string[]
}

export interface Track {
  id: string
  name: string
  sourceInstrument: 'guitar' | 'bass' | 'piano' | 'vocals' | 'other'
  targetInstrument: TargetInstrument
  /** low -> high, e.g. ["E2","A2","D3","G3","B3","E4"] */
  tuning: string[]
  capo: number
  transposeSemitones: number
  program: number
  notes: Note[]
  sourceTrackIndex?: number
  capoSuggestion?: CapoSuggestion
  tuningSuggestions?: TuningSuggestion[]
  /** the tuning was picked automatically from the notes heard */
  tuningDetected?: boolean
}

export interface TuningSuggestion {
  key: string
  label: string
  tuning: string[]
  strings: number
  /** lower = better fit */
  score: number
  /** score minus the best score */
  relative: number
  notesBelow: number
  reason: string
}

/** One candidate key/scale, e.g. "F# Phrygian Dominant". */
export interface ScaleMatch {
  tonic: string
  tonicPc: number
  name: string
  label: string
  family: string
  notes: string[]
  /** pitch class (C=0 ... B=11) of each entry in `notes` */
  pcs: number[]
  /** share of played notes inside the scale, 0-1 */
  fit: number
  relative: number
}

/** Key and scale with the reasons behind them (shown when the key is clicked). */
export interface KeyAnalysis {
  key: string
  scale: ScaleMatch
  alternatives: ScaleMatch[]
  confidence: 'high' | 'medium' | 'low'
  /** share of playing time per note, C..B */
  histogram: number[]
  reasons: string[]
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
  /** two-hand tapping: allow notes played by the picking hand */
  tapping?: boolean
}

/** What an audio upload contains. 'mix' = a whole band mix, transcribed as one part. */
export type AudioMode = 'guitar' | 'bass' | 'piano' | 'vocals' | 'other' | 'mix'

/** Present when the score was transcribed from a recording. */
export interface AudioInfo {
  durationSeconds: number
  mode: AudioMode
  detectedBpm: number
  tempoFactor: number
  downbeatShift: number
  /** where score ticks fall in the original recording */
  syncPoints: { tick: number; seconds: number }[]
  warnings: string[]
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
  audio?: AudioInfo
  keyAnalysis?: KeyAnalysis
}

export interface Job {
  id: string
  filename: string
  status: 'queued' | 'running' | 'done' | 'error'
  stage: string
  stageLabel?: string
  progress: number
  error: string | null
  scoreId?: string
  options?: { mode?: AudioMode; kind?: 'midi' | 'audio' }
}

export interface TuningPreset {
  label: string
  instrument: 'guitar' | 'bass'
  notes: string[]
  strings: number
  family: 'standard' | 'drop' | 'open'
}
