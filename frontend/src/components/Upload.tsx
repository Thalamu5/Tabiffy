import { useRef, useState } from 'react'
import type { AudioMode } from '../lib/types'

interface Props {
  onFile: (file: File, mode: AudioMode) => void
  busy: boolean
}

const SAMPLES = [
  { file: 'demo_band.mp3', label: 'Band recording (audio)', mode: 'full' as AudioMode },
  { file: 'chord_progression.mid', label: 'Chord progression (MIDI)' },
  { file: 'pentatonic_riff.mid', label: 'Pentatonic riff (MIDI)' },
  { file: 'flute_melody.mid', label: 'Flute melody → guitar (MIDI)' },
  { file: 'piano_two_hands.mid', label: 'Piano, two hands (MIDI)' },
]

const MODES: { value: AudioMode; label: string; hint: string }[] = [
  { value: 'full', label: 'A full song', hint: 'Separates the instruments first (takes a few minutes)' },
  { value: 'guitar', label: 'Solo guitar', hint: 'Just one guitar, no band' },
  { value: 'bass', label: 'Solo bass', hint: '' },
  { value: 'piano', label: 'Solo piano', hint: '' },
  { value: 'other', label: 'Another solo instrument', hint: 'e.g. voice, violin, flute' },
]

export function Upload({ onFile, busy }: Props) {
  const input = useRef<HTMLInputElement>(null)
  const [over, setOver] = useState(false)
  const [mode, setMode] = useState<AudioMode>('full')

  const loadSample = async (name: string, sampleMode?: AudioMode) => {
    const res = await fetch(`/samples/${name}`)
    const blob = await res.blob()
    onFile(new File([blob], name, { type: blob.type }), sampleMode ?? mode)
  }

  return (
    <div className="upload-page">
      <div
        className={`dropzone ${over ? 'over' : ''}`}
        onDragOver={(e) => { e.preventDefault(); setOver(true) }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => {
          e.preventDefault()
          setOver(false)
          const f = e.dataTransfer.files[0]
          if (f) onFile(f, mode)
        }}
        onClick={() => input.current?.click()}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') input.current?.click() }}
      >
        <div className="drop-icon">♫</div>
        <p><strong>Drop a song here</strong> or click to choose a file</p>
        <p className="muted">Audio (.mp3, .wav, .flac, .ogg, .m4a, up to 15 minutes) or MIDI (.mid)</p>
        <input ref={input} type="file" accept=".mid,.midi,audio/*,.mp3,.wav,.flac,.ogg,.m4a,.aac,.opus" hidden disabled={busy}
          onChange={(e) => { const f = e.target.files?.[0]; if (f) onFile(f, mode); e.target.value = '' }} />
      </div>

      <fieldset className="modes">
        <legend>For audio: what's in the recording?</legend>
        {MODES.map((m) => (
          <label key={m.value} className={`mode ${mode === m.value ? 'on' : ''}`}>
            <input type="radio" name="mode" value={m.value} checked={mode === m.value} onChange={() => setMode(m.value)} />
            <span>
              {m.label}
              {m.hint && <small className="muted"> · {m.hint}</small>}
            </span>
          </label>
        ))}
      </fieldset>

      <p className="hint">
        Automatic transcription isn't perfect, especially for full songs. Notes the app is unsure about are shown in red
        so you know where to check.
      </p>

      <div className="samples">
        <span className="muted">No file handy? Try a sample:</span>
        {SAMPLES.map((s) => (
          <button key={s.file} disabled={busy} onClick={() => loadSample(s.file, s.mode)}>{s.label}</button>
        ))}
      </div>
    </div>
  )
}
