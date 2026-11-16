import { useState } from 'react'
import { nameToMidi } from '../lib/music'
import { GUITAR_STRING_COUNTS, findPreset, presetsFor } from '../lib/tunings'
import type { CapoSuggestion, SolverSettings, TargetInstrument, Track, TuningPreset, TuningSuggestion } from '../lib/types'

export interface TrackSettings {
  target: TargetInstrument
  tuning: string[]
  capo: number
  transpose: number
  settings: SolverSettings
}

interface Props {
  track: Track
  settings: SolverSettings
  tunings: Record<string, TuningPreset>
  busy: boolean
  suggestion: CapoSuggestion | null
  onApply: (s: TrackSettings) => void
  onSuggestCapo: (s: TrackSettings) => void
  onSuggestTuning: (strings?: number[]) => Promise<TuningSuggestion[]>
}

const DEFAULT_TUNING: Record<'guitar' | 'bass', string[]> = {
  guitar: ['E2', 'A2', 'D3', 'G3', 'B3', 'E4'],
  bass: ['E1', 'A1', 'D2', 'G2'],
}

function validTuning(text: string): string[] | null {
  const notes = text.split(/[\s,]+/).filter(Boolean)
  if (notes.length < 4 || notes.length > 8) return null
  try {
    notes.forEach(nameToMidi)
    return notes
  } catch {
    return null
  }
}

export function SettingsPanel({ track, settings, tunings, busy, suggestion, onApply, onSuggestCapo, onSuggestTuning }: Props) {
  // The parent remounts this panel (via `key`) when the track is re-solved, which resets the form.
  const [target, setTarget] = useState<TargetInstrument>(track.targetInstrument)
  const [tuningText, setTuningText] = useState((track.tuning.length ? track.tuning : DEFAULT_TUNING.guitar).join(' '))
  const [capo, setCapo] = useState(track.capo)
  const [transpose, setTranspose] = useState(track.transposeSemitones)
  const [s, setS] = useState<SolverSettings>(settings)
  const [tuningSuggestions, setTuningSuggestions] = useState<TuningSuggestion[]>(track.tuningSuggestions ?? [])
  const [suggesting, setSuggesting] = useState(false)

  const stringed = target !== 'piano'
  const tuning = validTuning(tuningText)
  const presetKey = findPreset(tunings, tuningText.trim().split(/\s+/)) ?? 'custom'
  const stringCount = tuning?.length ?? tuningText.trim().split(/\s+/).length
  const presets = presetsFor(tunings, target === 'bass' ? 'bass' : 'guitar', target === 'guitar' ? stringCount : undefined)
  const setStrings = (n: number) => {
    const first = presetsFor(tunings, 'guitar', n)[0]
    if (first) setTuningText(first[1].notes.join(' '))
  }
  const suggestTuning = async () => {
    setSuggesting(true)
    try {
      setTuningSuggestions(await onSuggestTuning())
    } finally {
      setSuggesting(false)
    }
  }

  const current = (): TrackSettings => ({ target, tuning: stringed ? (tuning ?? []) : [], capo: stringed ? capo : 0, transpose, settings: s })
  const canApply = !busy && (!stringed || tuning !== null)

  return (
    <aside className="settings">
      <h3>Track settings</h3>
      <label>
        Play it on
        <select value={target} onChange={(e) => {
          const t = e.target.value as TargetInstrument
          setTarget(t)
          if (t !== 'piano') setTuningText(DEFAULT_TUNING[t].join(' '))
        }}>
          <option value="guitar">Guitar</option>
          <option value="bass">Bass</option>
          <option value="piano">Piano</option>
        </select>
      </label>
      {track.sourceInstrument !== target && (
        <p className="hint">Originally {track.sourceInstrument === 'other' ? 'another instrument' : track.sourceInstrument}: notes are moved by octaves into the {target}’s range.</p>
      )}

      {stringed && (
        <>
          {target === 'guitar' && (
            <div className="row">
              <span>Strings</span>
              <div className="segmented" role="group" aria-label="Number of strings">
                {GUITAR_STRING_COUNTS.map((n) => (
                  <button key={n} className={stringCount === n ? 'on' : ''} onClick={() => setStrings(n)}>{n}</button>
                ))}
              </div>
            </div>
          )}
          <label>
            Tuning
            <select value={presetKey} onChange={(e) => {
              const p = tunings[e.target.value]
              if (p) setTuningText(p.notes.join(' '))
            }}>
              {presets.map(([k, p]) => <option key={k} value={k}>{p.label}</option>)}
              <option value="custom">Custom…</option>
            </select>
          </label>
          <label>
            Strings (low → high)
            <input value={tuningText} onChange={(e) => setTuningText(e.target.value)} className={tuning ? '' : 'invalid'} />
          </label>
          {!tuning && <p className="hint warn">Enter 4–8 note names, e.g. “D2 A2 D3 G3 B3 E4”.</p>}
          {target === 'guitar' && (
            <div className="tuning-suggest">
              <button className="wide" disabled={busy || suggesting} onClick={suggestTuning}>
                {suggesting ? 'Listening…' : tuningSuggestions.length ? 'Suggest again' : 'Suggest a tuning'}
              </button>
              {tuningSuggestions.length > 0 && (
                <ol className="suggestions">
                  {tuningSuggestions.map((t, i) => {
                    const active = t.tuning.join(' ') === tuningText.trim()
                    return (
                      <li key={t.key} className={active ? 'active' : ''}>
                        <div>
                          <strong>{t.label.replace(/ \(.*\)$/, '')}</strong>
                          <span className="muted"> · {t.strings} strings{i > 0 ? ` · ${t.relative < 0.15 ? 'nearly as likely' : 'less likely'}` : ' · best fit'}</span>
                          <small className="muted">{t.reason}</small>
                        </div>
                        {active ? <span className="pill">current</span> : (
                          <button disabled={busy} onClick={() => {
                            setTuningText(t.tuning.join(' '))
                            onApply({ target, tuning: t.tuning, capo, transpose, settings: s })
                          }}>Use it</button>
                        )}
                      </li>
                    )
                  })}
                </ol>
              )}
            </div>
          )}
          <label>
            Capo: {capo === 0 ? 'none' : `fret ${capo}`}
            <input type="range" min={0} max={12} value={capo} onChange={(e) => setCapo(Number(e.target.value))} />
          </label>
        </>
      )}
      <label>
        Transpose: {transpose > 0 ? `+${transpose}` : transpose} semitones
        <input type="range" min={-12} max={12} value={transpose} onChange={(e) => setTranspose(Number(e.target.value))} />
      </label>

      {stringed && (
        <>
          <h4>Fingering</h4>
          <label>
            Highest fret: {s.maxFret}
            <input type="range" min={5} max={24} value={s.maxFret} onChange={(e) => setS({ ...s, maxFret: Number(e.target.value) })} />
          </label>
          <label>
            Open strings: {s.openStringPreference === 0 ? 'neutral' : s.openStringPreference < 1 ? 'a little' : s.openStringPreference === 1 ? 'normal' : 'lots'}
            <input type="range" min={0} max={2} step={0.25} value={s.openStringPreference}
              onChange={(e) => setS({ ...s, openStringPreference: Number(e.target.value) })} />
          </label>
          <label className="inline">
            <input type="checkbox" checked={s.simplifyChords} onChange={(e) => setS({ ...s, simplifyChords: e.target.checked })} />
            Simplify chords (max 4 notes)
          </label>
        </>
      )}
      <label>
        Rhythm grid
        <select value={s.quantize} onChange={(e) => setS({ ...s, quantize: e.target.value as SolverSettings['quantize'] })}>
          <option value="off">Off (as played)</option>
          <option value="1/8">1/8 notes</option>
          <option value="1/16">1/16 notes</option>
          <option value="1/16+triplets">1/16 + triplets (default)</option>
          <option value="1/32">1/32 notes</option>
        </select>
      </label>

      <button className="primary wide" disabled={!canApply} onClick={() => onApply(current())}>
        {busy ? 'Working…' : 'Re-calculate tab'}
      </button>
      {stringed && (
        <button className="wide" disabled={!canApply} onClick={() => onSuggestCapo(current())}>Suggest a capo</button>
      )}
      {suggestion && stringed && (
        <div className="suggestion">
          {suggestion.capo === 0
            ? 'Best without a capo.'
            : `Capo ${suggestion.capo}${suggestion.shapesKey ? `, play in ${suggestion.shapesKey.replace(' major', '').replace(' minor', 'm')} shapes` : ''}.`}
          {suggestion.capo !== capo && (
            <button onClick={() => { setCapo(suggestion.capo); onApply({ ...current(), capo: suggestion.capo }) }}>Use it</button>
          )}
        </div>
      )}
      <p className="hint">Changes here only re-run the fast steps (range, rhythm grid, fingering).</p>
    </aside>
  )
}
