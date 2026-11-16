import { useRef, useState } from 'react'
import { GUITAR_STRING_COUNTS, presetsFor } from '../lib/tunings'
import type { UploadOptions } from '../lib/api'
import type { AudioMode, TuningPreset } from '../lib/types'

interface Props {
  onFile: (file: File, opts: UploadOptions) => void
  busy: boolean
  tunings: Record<string, TuningPreset>
}

const SAMPLES = [
  { file: 'demo_band.mp3', label: 'Band recording (audio, full mix)', mode: 'mix' as AudioMode },
  { file: 'chord_progression.mid', label: 'Chord progression (MIDI)' },
  { file: 'pentatonic_riff.mid', label: 'Pentatonic riff (MIDI)' },
  { file: 'flute_melody.mid', label: 'Flute melody → guitar (MIDI)' },
  { file: 'piano_two_hands.mid', label: 'Piano, two hands (MIDI)' },
]

const MODES: { value: AudioMode; label: string; hint: string }[] = [
  { value: 'guitar', label: 'Guitar', hint: 'a guitar recording, or a guitar part you separated from a song' },
  { value: 'bass', label: 'Bass', hint: '' },
  { value: 'piano', label: 'Piano / keys', hint: '' },
  { value: 'vocals', label: 'Vocals', hint: 'becomes a single melody line' },
  { value: 'other', label: 'Another instrument', hint: 'e.g. violin, flute, sax' },
  { value: 'mix', label: 'A full band mix', hint: 'everything together; rough results' },
]

/** The start page: drop a file, say what's in it, pick a tuning and whether it uses tapping. */
export function Upload({ onFile, busy, tunings }: Props) {
  const input = useRef<HTMLInputElement>(null)
  const [over, setOver] = useState(false)
  const [mode, setMode] = useState<AudioMode>('guitar')
  const [tuning, setTuning] = useState('auto')
  const [tapping, setTapping] = useState(false)
  const opts = (m: AudioMode = mode): UploadOptions => ({ mode: m, tuning, tapping })

  const loadSample = async (name: string, sampleMode?: AudioMode) => {
    const res = await fetch(`/samples/${name}`)
    const blob = await res.blob()
    onFile(new File([blob], name, { type: blob.type }), opts(sampleMode))
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
          if (f) onFile(f, opts())
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
          onChange={(e) => { const f = e.target.files?.[0]; if (f) onFile(f, opts()); e.target.value = '' }} />
      </div>

      <fieldset className="modes">
        <legend>For audio: what's in the file?</legend>
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

      <label className="tuning-choice">
        Guitar tuning
        <select value={tuning} onChange={(e) => setTuning(e.target.value)}>
          <option value="auto">Detect it from the notes (recommended)</option>
          {GUITAR_STRING_COUNTS.map((n) => (
            <optgroup key={n} label={`${n}-string`}>
              {presetsFor(tunings, 'guitar', n).map(([k, p]) => <option key={k} value={k}>{p.label}</option>)}
            </optgroup>
          ))}
        </select>
        <small className="muted">
          {tuning === 'auto'
            ? 'Tabiffy suggests a tuning (6, 7 or 8 strings) from what it hears; detection works best on a guitar-only recording. You can change it afterwards.'
            : 'The tab will be written for this tuning.'}
        </small>
      </label>

      <label className="inline tapping-choice">
        <input type="checkbox" checked={tapping} onChange={(e) => setTapping(e.target.checked)} />
        <span>
          This song uses <strong>two-hand tapping</strong>
          <small className="muted"> · lets the tab use tapped notes (marked “T”) for wide jumps on one string. Leave it off otherwise.</small>
        </span>
      </label>

      <p className="hint">
        Each audio file becomes one part. For the best tab from a full song, separate the instrument you want first
        (with a stem-separation tool) and upload that part. Transcription isn't perfect: notes the app is unsure
        about are shown in red so you know where to check.
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
