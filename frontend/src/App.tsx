import { useCallback, useEffect, useMemo, useState } from 'react'
import { Fretboard } from './components/Fretboard'
import { KeyModal } from './components/KeyModal'
import { Piano } from './components/Piano'
import { ScoreView } from './components/ScoreView'
import { SettingsPanel, type TrackSettings } from './components/SettingsPanel'
import { TimingPanel } from './components/TimingPanel'
import { Upload } from './components/Upload'
import { getScore, getTunings, isAudioFile, resolveTrack, setTiming, suggestCapo, suggestTuning, uploadFile, watchJob, type ResolveRequest, type TimingRequest, type UploadOptions } from './lib/api'
import { tuningName } from './lib/tunings'
import { isSuggestedTechnique, isUncertain } from './lib/alphaTabScore'
import type { CapoSuggestion, Job, TabiffyScore, TuningPreset } from './lib/types'

const LOOKAHEAD_TICKS = 480

/** Read a saved on/off preference (browser storage can be unavailable, e.g. private mode). */
function readPref(key: string): boolean {
  try {
    return localStorage.getItem(key) === '1'
  } catch {
    return false
  }
}
/** Save an on/off preference; silently skipped if browser storage is unavailable. */
function writePref(key: string, v: boolean) {
  try {
    localStorage.setItem(key, v ? '1' : '0')
  } catch {
    /* storage unavailable */
  }
}

/** The score id from the page address (?score=...), so a score can be reopened or shared. */
function scoreIdFromUrl(): string | null {
  return new URLSearchParams(window.location.search).get('score')
}

export default function App() {
  const [scoreId, setScoreId] = useState<string | null>(scoreIdFromUrl())
  const [score, setScore] = useState<TabiffyScore | null>(null)
  const [job, setJob] = useState<Job | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [trackIndex, setTrackIndex] = useState(0)
  const [tick, setTick] = useState(0)
  const [busy, setBusy] = useState(false)
  const [tunings, setTunings] = useState<Record<string, TuningPreset>>({})
  const [suggestion, setSuggestion] = useState<CapoSuggestion | null>(null)
  const [leftHanded, setLeftHanded] = useState(readPref('tabiffy.leftHanded'))
  const [seek, setSeek] = useState<{ tick: number; n: number } | null>(null)
  const [keyOpen, setKeyOpen] = useState(false) // the key/scale window

  useEffect(() => {
    getTunings().then(setTunings).catch(() => {})
    const onPop = () => setScoreId(scoreIdFromUrl())
    window.addEventListener('popstate', onPop)
    return () => window.removeEventListener('popstate', onPop)
  }, [])

  useEffect(() => {
    if (!scoreId) return
    let cancelled = false
    getScore(scoreId)
      .then((s) => {
        if (cancelled) return
        setScore(s)
        setTrackIndex(0)
        setTick(0)
      })
      .catch((e) => !cancelled && setError(`Could not open the score: ${e.message}`))
    return () => {
      cancelled = true
    }
  }, [scoreId])

  const openScore = (id: string) => {
    window.history.pushState({}, '', `?score=${id}`)
    setScoreId(id)
  }

  const onFile = async (file: File, opts: UploadOptions) => {
    setError(null)
    setBusy(true)
    setJob({ id: '', filename: file.name, status: 'queued', stage: 'upload', stageLabel: 'Uploading', progress: 0, error: null,
      options: { mode: opts.mode, kind: isAudioFile(file.name) ? 'audio' : 'midi' } })
    try {
      const jobId = await uploadFile(file, opts)
      watchJob(jobId, (j) => {
        setJob(j)
        if (j.status === 'done') {
          setBusy(false)
          setJob(null)
          openScore(j.scoreId ?? j.id)
        } else if (j.status === 'error') {
          setBusy(false)
          setJob(null)
          setError(j.error ?? 'Processing failed')
        }
      })
    } catch (e) {
      setBusy(false)
      setJob(null)
      setError((e as Error).message)
    }
  }

  // Only show the score that belongs to the current URL.
  const shown = scoreId ? score : null
  const track = shown?.tracks[trackIndex]

  const request = (s: TrackSettings): ResolveRequest => ({
    trackId: track!.id,
    target: s.target,
    tuning: s.target === 'piano' ? undefined : s.tuning,
    capo: s.capo,
    transpose: s.transpose,
    settings: s.settings,
  })

  const onApply = async (s: TrackSettings) => {
    if (!scoreId || !track) return
    setBusy(true)
    setError(null)
    try {
      setScore(await resolveTrack(scoreId, request(s)))
      setSuggestion(null)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const onSuggestCapo = async (s: TrackSettings) => {
    if (!scoreId || !track) return
    setBusy(true)
    try {
      setSuggestion(await suggestCapo(scoreId, request(s)))
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const onSuggestTuning = async (strings?: number[]) => {
    if (!scoreId || !track) return []
    try {
      return await suggestTuning(scoreId, track.id, strings)
    } catch (e) {
      setError((e as Error).message)
      return []
    }
  }

  const onTiming = async (req: TimingRequest) => {
    if (!scoreId) return
    setBusy(true)
    setError(null)
    try {
      setScore(await setTiming(scoreId, req))
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const onTick = useCallback((t: number) => setTick(t), [])

  const { active, upcoming } = useMemo(() => {
    if (!track) return { active: [], upcoming: [] }
    const active = track.notes.filter((n) => n.tick <= tick && tick < n.tick + n.durationTicks)
    const ids = new Set(active.map((n) => n.id))
    const upcoming = track.notes.filter((n) => n.tick > tick && n.tick <= tick + LOOKAHEAD_TICKS && !ids.has(n.id))
    return { active, upcoming }
  }, [track, tick])

  const uncertain = useMemo(() => (track ? track.notes.filter(isUncertain) : []), [track])
  const suggestedTechniques = useMemo(() => (track ? track.notes.filter(isSuggestedTechnique).length : 0), [track])
  const reviewNext = () => {
    if (!uncertain.length) return
    const next = uncertain.find((n) => n.tick > tick) ?? uncertain[0]
    setSeek({ tick: next.tick, n: (seek?.n ?? 0) + 1 })
  }
  const currentChord = shown?.chords.find((c) => c.tick <= tick && tick < c.tick + c.durationTicks)

  return (
    <div className="app">
      <header className="topbar">
        <a className="logo" href="/" onClick={(e) => { e.preventDefault(); window.history.pushState({}, '', '/'); setScoreId(null) }}>
          Tabiffy
        </a>
        {shown && (
          <div className="meta">
            <strong>{shown.meta.title || 'Untitled'}</strong>
            {shown.meta.key && (shown.keyAnalysis ? (
              <button className="pill key" onClick={() => setKeyOpen(true)} title="Why this key? Which scale?">
                {/* Plain major/minor shows as the key; any other scale shows its full name. */}
                {['major', 'natural minor'].includes(shown.keyAnalysis.scale.name) ? shown.meta.key : shown.keyAnalysis.scale.label} ⓘ
              </button>
            ) : <span className="pill">{shown.meta.key}</span>)}
            <span className="pill">{Math.round(shown.meta.bpm)} BPM</span>
            <span className="pill">{shown.meta.timeSignature.join('/')}</span>
          </div>
        )}
        <span className="spacer" />
        {shown && <button onClick={() => { window.history.pushState({}, '', '/'); setScoreId(null) }}>New upload</button>}
      </header>

      {error && <div className="error banner">{error}</div>}
      {keyOpen && shown?.keyAnalysis && (
        <KeyModal
          analysis={shown.keyAnalysis}
          tuning={track && track.targetInstrument !== 'piano' ? track.tuning : []}
          capo={track?.capo ?? 0}
          onClose={() => setKeyOpen(false)}
        />
      )}

      {!scoreId && !job && <Upload onFile={onFile} busy={busy} tunings={tunings} />}
      {job && (
        <div className="job">
          <p>Working on <strong>{job.filename}</strong></p>
          <p className="muted">{job.stageLabel ?? job.stage}…</p>
          <div className="progress"><div style={{ width: `${Math.round(job.progress * 100)}%` }} /></div>
        </div>
      )}

      {shown && track && (
        <div className="workspace">
          <main>
            <div className="tracks">
              {shown.tracks.map((t, i) => (
                <button key={t.id} className={i === trackIndex ? 'tab active' : 'tab'} onClick={() => { setTrackIndex(i); setSuggestion(null) }}>
                  {t.name}
                  <span className="muted"> · {t.targetInstrument}{t.capo ? ` · capo ${t.capo}` : ''}</span>
                </button>
              ))}
            </div>
            {shown.audio?.warnings.map((w) => <div key={w} className="notice">{w}</div>)}
            {track.tuningDetected && track.targetInstrument === 'guitar' && (
              <div className="notice">
                Tuning detected from the notes: <strong>{tuningName(tunings, track.tuning)}</strong> ({track.tuning.length} strings)
                {(track.tuningSuggestions?.length ?? 0) > 1 && <>; also possible: {track.tuningSuggestions!.slice(1).map((t) => t.label.replace(/ \(.*\)$/, '')).join(', ')}</>}.
                {' '}Change it under Track settings → Tuning.
              </div>
            )}
            {uncertain.length > 0 && (
              <div className="notice review">
                <span>
                  <strong className="warn-text">{uncertain.length}</strong> note{uncertain.length > 1 ? 's' : ''} in this track
                  {shown.audio ? ' may be wrong (the transcription was unsure) or' : ''} couldn’t be placed comfortably. They’re shown in red.
                </span>
                <button onClick={reviewNext}>Review next uncertain note ▶</button>
              </div>
            )}
            {suggestedTechniques > 0 && (
              <div className="notice">
                <strong className="suggest-text">{suggestedTechniques}</strong> slide{suggestedTechniques > 1 ? 's' : ''} / hammer-ons /
                pull-offs are only suggested from the sound. They’re shown in blue: listen and keep the ones that feel right.
              </div>
            )}
            <ScoreView score={shown} scoreId={scoreId!} trackIndex={trackIndex} onTick={onTick} seek={seek} />
            <section className="visualizer">
              <div className="viz-head">
                <span>
                  {track.targetInstrument === 'piano' ? 'Piano' : `${track.tuning.join(' ')}${track.capo ? ` · capo ${track.capo}` : ''}`}
                  {currentChord && <span className="pill chord">{currentChord.symbol}</span>}
                </span>
                {track.targetInstrument !== 'piano' && (
                  <label className="inline">
                    <input type="checkbox" checked={leftHanded} onChange={(e) => { setLeftHanded(e.target.checked); writePref('tabiffy.leftHanded', e.target.checked) }} />
                    Left-handed
                  </label>
                )}
              </div>
              <div className="viz-scroll">
                {track.targetInstrument === 'piano'
                  ? <Piano track={track} active={active} upcoming={upcoming} />
                  : <Fretboard track={track} active={active} upcoming={upcoming} leftHanded={leftHanded} />}
              </div>
              <p className="legend muted">
                {track.targetInstrument === 'piano'
                  ? 'Blue = left hand, orange = right hand. Faded keys are coming up next.'
                  : 'Numbers are fingers: 1 index · 2 middle · 3 ring · 4 pinky · 0 open string. Red = worth checking. Faded dots are coming up next.'}
              </p>
            </section>
          </main>
          <div className="sidebar">
          <SettingsPanel
            key={`${track.id}|${track.targetInstrument}|${track.tuning.join(',')}|${track.capo}|${track.transposeSemitones}|${JSON.stringify(shown.settings)}`}
            track={track}
            settings={shown.settings}
            tunings={tunings}
            busy={busy}
            suggestion={suggestion}
            onApply={onApply}
            onSuggestCapo={onSuggestCapo}
            onSuggestTuning={onSuggestTuning}
          />
          <TimingPanel
            key={`${shown.meta.timeSignature.join('/')}|${shown.tempoMap[0]?.bpm}|${shown.audio?.tempoFactor}|${shown.audio?.downbeatShift}`}
            score={shown}
            busy={busy}
            onApply={onTiming}
          />
          </div>
        </div>
      )}
    </div>
  )
}
