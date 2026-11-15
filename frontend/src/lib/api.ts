import type { CapoSuggestion, Job, SolverSettings, TabiffyScore, TargetInstrument, TuningPreset } from './types'

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

export async function uploadFile(file: File): Promise<string> {
  const form = new FormData()
  form.append('file', file)
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

export async function getScore(id: string): Promise<TabiffyScore> {
  return json(await fetch(`/api/scores/${id}`))
}

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

export async function resolveTrack(id: string, req: ResolveRequest): Promise<TabiffyScore> {
  return json(await fetch(`/api/scores/${id}/resolve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  }))
}

export async function suggestCapo(id: string, req: ResolveRequest): Promise<CapoSuggestion> {
  return json(await fetch(`/api/scores/${id}/suggest-capo`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  }))
}

export async function getTunings(): Promise<Record<string, TuningPreset>> {
  return json(await fetch('/api/tunings'))
}
