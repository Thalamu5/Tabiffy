import { useRef, useState } from 'react'

interface Props {
  onFile: (file: File) => void
  busy: boolean
}

const SAMPLES = [
  { file: 'chord_progression.mid', label: 'Chord progression (guitar)' },
  { file: 'pentatonic_riff.mid', label: 'Pentatonic riff (guitar)' },
  { file: 'flute_melody.mid', label: 'Flute melody → guitar' },
  { file: 'piano_two_hands.mid', label: 'Piano, two hands' },
  { file: 'bass_line.mid', label: 'Bass line' },
]

export function Upload({ onFile, busy }: Props) {
  const input = useRef<HTMLInputElement>(null)
  const [over, setOver] = useState(false)

  const loadSample = async (name: string) => {
    const res = await fetch(`/samples/${name}`)
    const blob = await res.blob()
    onFile(new File([blob], name, { type: 'audio/midi' }))
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
          if (f) onFile(f)
        }}
        onClick={() => input.current?.click()}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') input.current?.click() }}
      >
        <div className="drop-icon">♫</div>
        <p><strong>Drop a MIDI file here</strong> or click to choose one</p>
        <p className="muted">.mid / .midi · audio files (mp3, wav…) are coming in the next version</p>
        <input ref={input} type="file" accept=".mid,.midi,audio/midi" hidden disabled={busy}
          onChange={(e) => { const f = e.target.files?.[0]; if (f) onFile(f); e.target.value = '' }} />
      </div>
      <div className="samples">
        <span className="muted">No file handy? Try a sample:</span>
        {SAMPLES.map((s) => (
          <button key={s.file} disabled={busy} onClick={() => loadSample(s.file)}>{s.label}</button>
        ))}
      </div>
    </div>
  )
}
