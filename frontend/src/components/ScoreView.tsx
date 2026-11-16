import * as alphaTab from '@coderline/alphatab'
import { useEffect, useMemo, useRef, useState } from 'react'
import { getAudio } from '../lib/api'
import { attachRecording, buildAlphaTabScore } from '../lib/alphaTabScore'
import type { TabiffyScore } from '../lib/types'

interface Props {
  score: TabiffyScore
  scoreId: string
  trackIndex: number
  onTick: (tick: number) => void
  /** Move the cursor here (the `n` counter lets the same tick be requested twice). */
  seek?: { tick: number; n: number } | null
  /** Draw the music in light-on-dark colors. */
  dark?: boolean
}

// alphaTab draws the music itself, so its colors are set here rather than in CSS. Print/PDF always uses LIGHT.
const LIGHT = { staffLineColor: '#a5a5a5', barSeparatorColor: '#222222', barNumberColor: '#c80000', mainGlyphColor: '#000000', secondaryGlyphColor: '#00000066', scoreInfoColor: '#000000' }
const DARK = { staffLineColor: '#6b665e', barSeparatorColor: '#cfc8bd', barNumberColor: '#ee7448', mainGlyphColor: '#efebe4', secondaryGlyphColor: '#efebe499', scoreInfoColor: '#efebe4' }

/** Save bytes as a file through a temporary link. */
function download(bytes: Uint8Array, filename: string, type: string) {
  const url = URL.createObjectURL(new Blob([bytes as BlobPart], { type }))
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

/** A file name made only of safe characters, from the song title. */
function safeName(s: string) {
  return (s || 'tabiffy').replace(/[^\w\- ]+/g, '').trim() || 'tabiffy'
}

/** alphaTab score view + player controls + exports. */
export function ScoreView({ score, scoreId, trackIndex, onTick, seek, dark = false }: Props) {
  const hostRef = useRef<HTMLDivElement>(null)
  const viewportRef = useRef<HTMLDivElement>(null)
  const apiRef = useRef<alphaTab.AlphaTabApi | null>(null)
  const onTickRef = useRef(onTick)
  useEffect(() => {
    onTickRef.current = onTick
  }, [onTick])

  const [ready, setReady] = useState(false)
  const [loading, setLoading] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [speed, setSpeed] = useState(100)
  const [looping, setLooping] = useState(false)
  const [metronome, setMetronome] = useState(false)
  const [countIn, setCountIn] = useState(false)
  const [muted, setMuted] = useState<Set<number>>(new Set())
  const [solo, setSolo] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [source, setSource] = useState<'synth' | 'original'>('synth')
  const [recording, setRecording] = useState<{ id: string; bytes: Uint8Array } | null>(null)
  const hasAudio = !!score.audio

  // Create the alphaTab instance once.
  useEffect(() => {
    if (!hostRef.current) return
    const api = new alphaTab.AlphaTabApi(hostRef.current, {
      core: { fontDirectory: '/font/' },
      display: { layoutMode: alphaTab.LayoutMode.Page, scale: 0.95 },
      player: {
        // Automatic: plays the original recording when one is attached, else the synthesizer.
        playerMode: alphaTab.PlayerMode.EnabledAutomatic,
        soundFont: '/soundfont/sonivox.sf2',
        scrollElement: viewportRef.current ?? undefined,
        enableUserInteraction: true,
      },
    } as alphaTab.json.SettingsJson)
    apiRef.current = api
    api.playerReady.on(() => setReady(true))
    api.soundFontLoad.on((e) => setLoading(Math.round((e.loaded / Math.max(1, e.total)) * 100)))
    api.playerStateChanged.on((e) => setPlaying(e.state === alphaTab.synth.PlayerState.Playing))
    api.playerPositionChanged.on((e) => onTickRef.current(e.currentTick))
    api.error.on((e) => setError(`Could not render this score: ${String(e?.message ?? e)}`))
    api.scoreLoaded.on(() => setError(null))
    return () => {
      api.destroy()
      apiRef.current = null
    }
  }, [])

  // Switch the music's colors when light/dark mode changes (re-draws only; playback is untouched).
  useEffect(() => {
    const api = apiRef.current
    if (!api) return
    const res = api.settings.display.resources
    for (const [k, v] of Object.entries(dark ? DARK : LIGHT)) {
      ;(res as unknown as Record<string, alphaTab.model.Color>)[k] = alphaTab.model.Color.fromJson(v)!
    }
    api.updateSettings()
    if (api.score) api.render()
  }, [dark])

  // Fetch the original recording the first time it's needed.
  useEffect(() => {
    if (source !== 'original' || !hasAudio || recording?.id === scoreId) return
    let cancelled = false
    getAudio(scoreId)
      .then((bytes) => !cancelled && setRecording({ id: scoreId, bytes }))
      .catch((e) => {
        if (cancelled) return
        setError((e as Error).message)
        setSource('synth')
      })
    return () => {
      cancelled = true
    }
  }, [source, hasAudio, scoreId, recording])

  const audioBytes = source === 'original' && recording?.id === scoreId ? recording.bytes : null

  const converted = useMemo(() => {
    try {
      const at = buildAlphaTabScore(score, new alphaTab.Settings())
      if (audioBytes) attachRecording(at, score, audioBytes)
      return { at, error: null }
    } catch (e) {
      return { at: null, error: `Could not convert this score: ${(e as Error).message}` }
    }
  }, [score, audioBytes])

  // (Re)load the score whenever it, the shown track, or the sound source changes.
  useEffect(() => {
    const api = apiRef.current
    if (api && converted.at) api.renderScore(converted.at, [trackIndex])
  }, [converted, trackIndex])

  useEffect(() => {
    const api = apiRef.current
    if (api && seek) {
      api.tickPosition = seek.tick
      onTickRef.current(seek.tick)
    }
  }, [seek])

  const api = () => apiRef.current
  const tracks = () => api()?.score?.tracks ?? []

  const setTrackMute = (i: number) => {
    const next = new Set(muted)
    if (next.has(i)) next.delete(i)
    else next.add(i)
    setMuted(next)
    const t = tracks()[i]
    if (t) api()?.changeTrackMute([t], next.has(i))
  }
  const setTrackSolo = (i: number) => {
    const next = solo === i ? null : i
    setSolo(next)
    api()?.changeTrackSolo(tracks(), false)
    if (next !== null && tracks()[next]) api()?.changeTrackSolo([tracks()[next]], true)
  }

  const exportGp = () => {
    const a = api()
    if (!a?.score) return
    const bytes = new alphaTab.exporter.Gp7Exporter().export(a.score, a.settings)
    download(bytes, `${safeName(score.meta.title)}.gp`, 'application/octet-stream')
  }
  const exportMidi = () => {
    const a = api()
    if (!a?.score) return
    const midi = new alphaTab.midi.MidiFile()
    const handler = new alphaTab.midi.AlphaSynthMidiFileHandler(midi, true)
    new alphaTab.midi.MidiFileGenerator(a.score, a.settings, handler).generate()
    download(midi.toBinary(), `${safeName(score.meta.title)}.mid`, 'audio/midi')
  }
  const exportPdf = () => api()?.print(undefined, { display: { scale: 0.9, resources: LIGHT } })

  return (
    <div className="score-view">
      <div className="player-bar">
        <button className="primary" disabled={!ready} onClick={() => api()?.playPause()}>
          {playing ? '❚❚ Pause' : '▶ Play'}
        </button>
        <button disabled={!ready} onClick={() => api()?.stop()}>■ Stop</button>
        {!ready && <span className="muted">{source === 'original' ? 'Loading recording…' : `Loading sounds… ${loading}%`}</span>}
        {hasAudio && (
          <div className="segmented" role="group" aria-label="Sound">
            <button className={source === 'synth' ? 'on' : ''} onClick={() => { api()?.stop(); setSource('synth') }}>Synth</button>
            <button className={source === 'original' ? 'on' : ''} onClick={() => { api()?.stop(); setReady(false); setSource('original') }}>
              Original recording
            </button>
          </div>
        )}
        <label className="inline" title="Playback speed">
          Speed {speed}%
          <input type="range" min={25} max={150} step={5} value={speed}
            onChange={(e) => {
              const v = Number(e.target.value)
              setSpeed(v)
              const a = api()
              if (a) a.playbackSpeed = v / 100
            }} />
        </label>
        <label className="inline" title="Loop: drag across the score to select a range, then play">
          <input type="checkbox" checked={looping} onChange={(e) => {
            setLooping(e.target.checked)
            const a = api()
            if (a) a.isLooping = e.target.checked
          }} /> Loop
        </label>
        <label className="inline">
          <input type="checkbox" checked={metronome} onChange={(e) => {
            setMetronome(e.target.checked)
            const a = api()
            if (a) a.metronomeVolume = e.target.checked ? 1 : 0
          }} /> Metronome
        </label>
        <label className="inline">
          <input type="checkbox" checked={countIn} onChange={(e) => {
            setCountIn(e.target.checked)
            const a = api()
            if (a) a.countInVolume = e.target.checked ? 1 : 0
          }} /> Count-in
        </label>
        <span className="spacer" />
        <div className="export">
          <span className="muted">Export</span>
          <button onClick={exportGp} title="Guitar Pro 7/8 (.gp)">.gp</button>
          <button onClick={exportMidi}>.mid</button>
          <button onClick={exportPdf} title="Opens a print view; choose “Save as PDF”">PDF</button>
        </div>
      </div>
      {score.tracks.length > 1 && (
        <div className="mixer">
          {score.tracks.map((t, i) => (
            <span key={t.id} className="mixer-track">
              {t.name}
              <button className={muted.has(i) ? 'toggle on' : 'toggle'} onClick={() => setTrackMute(i)} title="Mute">M</button>
              <button className={solo === i ? 'toggle on' : 'toggle'} onClick={() => setTrackSolo(i)} title="Solo">S</button>
            </span>
          ))}
        </div>
      )}
      {(converted.error ?? error) && <div className="error">{converted.error ?? error}</div>}
      <div className="at-viewport" ref={viewportRef}>
        <div ref={hostRef} />
      </div>
    </div>
  )
}
