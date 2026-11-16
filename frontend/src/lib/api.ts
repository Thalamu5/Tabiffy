import type { AudioMode, CapoSuggestion, Job, SolverSettings, TabiffyScore, TargetInstrument, TuningPreset, TuningSuggestion } from './types'

/** Parse a JSON response, turning server errors into readable Error messages. */
async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let msg = `${res.status} ${res.statusText}`
    try {
      const body = await res.json()
      if (body.detail) msg = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
    } catch {
      /* not JSON */
    }
    throw new Error(msg)
  }
  return res.json() as Promise<T>
}

/** `tuning`: 'auto' to detect it from the notes, or a guitar preset key from /api/tunings. */
/** What the user told us about an upload. */
export interface UploadOptions {
  mode: AudioMode
  /** "auto" or a tuning preset key */
  tuning: string
  /** the song uses two-hand tapping */
  tapping: boolean
}

/** Upload a song with the user's choices; returns the job id to follow. */
export async function uploadFile(file: File, opts: UploadOptions): Promise<string> {
  const form = new FormData()
  form.append('file', file)
  form.append('mode', opts.mode)
  form.append('tuning', opts.tuning)
  form.append('tapping', opts.tapping ? 'true' : 'false')
  const { jobId } = await json<{ jobId: string }>(await fetch('/api/jobs', { method: 'POST', body: form }))
  return jobId
}

/** Follows job progress over Server-Sent Events, falling back to polling. */
export function watchJob(jobId: string, onUpdate: (job: Job) => void): () => void {
  let stopped = false
  let timer: ReturnType<typeof setTimeout> | undefined
  const poll = async () => {
    if (stopped) return
    try {
      const job = await json<Job>(await fetch(`/api/jobs/${jobId}`))
      onUpdate(job)
      if (job.status === 'done' || job.status === 'error') return
    } catch {
      /* retry */
    }
    timer = setTimeout(poll, 500)
  }
  if (typeof EventSource === 'undefined') {
    poll()
    return () => {
      stopped = true
      clearTimeout(timer)
    }
  }
  const es = new EventSource(`/api/jobs/${jobId}/events`)
  es.onmessage = (e) => {
    const job = JSON.parse(e.data) as Job
    onUpdate(job)
    if (job.status === 'done' || job.status === 'error') es.close()
  }
  es.onerror = () => {
    es.close()
    poll()
  }
  return () => {
    stopped = true
    es.close()
    clearTimeout(timer)
  }
}

/** Load a score by id. */
export async function getScore(id: string): Promise<TabiffyScore> {
  return json(await fetch(`/api/scores/${id}`))
}

/** Save the whole score (e.g. after edits). */
export async function saveScore(id: string, score: TabiffyScore): Promise<void> {
  await json(await fetch(`/api/scores/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(score),
  }))
}

export interface ResolveRequest {
  trackId: string
  tuning?: string[]
  capo: number
  target: TargetInstrument
  transpose: number
  lockedNoteIds?: string[]
  settings?: SolverSettings
}

/** Re-calculate one track's tab with new tuning/capo/settings. */
export async function resolveTrack(id: string, req: ResolveRequest): Promise<TabiffyScore> {
  return json(await fetch(`/api/scores/${id}/resolve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  }))
}

/** Ask the server for the easiest capo position. */
export async function suggestCapo(id: string, req: ResolveRequest): Promise<CapoSuggestion> {
  return json(await fetch(`/api/scores/${id}/suggest-capo`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  }))
}

/** Rank tunings for a track, optionally only for one string count. */
export async function suggestTuning(id: string, trackId: string, strings?: number[]): Promise<TuningSuggestion[]> {
  return json(await fetch(`/api/scores/${id}/suggest-tuning`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ trackId, strings }),
  }))
}

/** The tuning presets (with string counts) offered in the menus. */
export async function getTunings(): Promise<Record<string, TuningPreset>> {
  return json(await fetch('/api/tunings'))
}

export interface TimingRequest {
  timeSignature: [number, number]
  /** MIDI scores */
  bpm?: number
  /** audio scores: 0.5, 1 or 2 */
  tempoFactor?: number
  /** audio scores: move bar lines by N beats */
  downbeatShift?: number
}

/** Fix the timing (tempo, bar lines, meter) and rebuild the score. */
export async function setTiming(id: string, req: TimingRequest): Promise<TabiffyScore> {
  return json(await fetch(`/api/scores/${id}/timing`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  }))
}

/** The uploaded recording as MP3 bytes, for original-audio playback. */
export async function getAudio(id: string): Promise<Uint8Array> {
  const res = await fetch(`/api/scores/${id}/audio`)
  if (!res.ok) throw new Error('The original recording is not available')
  return new Uint8Array(await res.arrayBuffer())
}

/** True for audio file names (anything else is treated as MIDI). */
export function isAudioFile(name: string): boolean {
  return /\.(mp3|wav|flac|ogg|m4a|aac|opus|aiff?)$/i.test(name)
}
