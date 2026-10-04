import { memo } from 'react'
import type { Bench, BenchView, SourceMode } from '../hooks/useBench.ts'
import { SEQUENCES } from '../sources/replay.ts'
import Led from './Led.tsx'

interface Props {
  mode: SourceMode
  replay: BenchView['replay']
  controls: Bench['replay']
  onMode: (mode: SourceMode) => void
}

/** The golden sequences, their parity with the engine, and the transport that plays them. */
const ReplayDeck = memo(function ReplayDeck({ mode, replay, controls, onMode }: Props) {
  const passing = replay.parity.filter((p) => p.mismatches === 0).length
  const active = mode === 'replay'
  const sequence = SEQUENCES[replay.sequenceIndex]
  return (
    <section className="panel deck" aria-label="Golden sequences">
      <div className="faceplate">
        <h2>Golden sequences</h2>
        <span className="small muted num">
          {passing}/{SEQUENCES.length} match the engine
        </span>
        <span className="spacer" />
        {!active && (
          <button type="button" className="btn btn-sm" onClick={() => onMode('replay')}>
            Back to the replay
          </button>
        )}
      </div>
      {active && (
        <div className="transport">
          <button
            type="button"
            className="btn btn-sm"
            onClick={() => controls.play(!replay.playing)}
            aria-pressed={replay.playing}
          >
            {replay.playing ? 'Pause' : 'Play'}
          </button>
          <button
            type="button"
            className="btn btn-sm"
            onClick={() => {
              controls.play(false)
              controls.step()
            }}
            title="One frame"
          >
            Step
          </button>
          <div className="segmented" role="group" aria-label="Speed">
            {[0.25, 1].map((speed) => (
              <button
                key={speed}
                type="button"
                aria-pressed={replay.speed === speed}
                onClick={() => controls.setSpeed(speed)}
              >
                {speed}x
              </button>
            ))}
          </div>
          <label className="option small">
            <input
              type="checkbox"
              checked={replay.continuous}
              onChange={(e) => controls.setContinuous(e.target.checked)}
            />
            play through
          </label>
        </div>
      )}
      <ol className="sequences">
        {SEQUENCES.map((s, i) => {
          const parity = replay.parity[i]
          const current = active && i === replay.sequenceIndex
          return (
            <li key={s.name} className={current ? 'current' : ''}>
              <button type="button" className="sequence" onClick={() => controls.select(i)}>
                <Led
                  on={parity !== undefined && parity.mismatches === 0}
                  tone="green"
                  label={`${s.name} parity`}
                />
                <span className="seq-name mono">{s.name}</span>
                <span className="seq-desc small muted">{s.description}</span>
                <span className="seq-frames small num muted">
                  {current ? `${Math.min(replay.frameIndex + 1, s.frames.length)}/` : ''}
                  {s.frames.length}
                </span>
              </button>
            </li>
          )
        })}
      </ol>
      <p className="panel-note">
        {sequence
          ? `${sequence.width}x${sequence.height} at ${sequence.fps} fps. Every frame's raw count, confirmed count, relays, latches and filtered coordinates are compared with fixtures/golden_vectors.json as it plays; the Python suite checks the same file.`
          : ''}
      </p>
    </section>
  )
})

export default ReplayDeck
