import { memo } from 'react'
import { FINGERS, RULES, type Measurement } from '../engine.ts'
import Led from './Led.tsx'

interface Props {
  measurement: Measurement | null
  states: boolean[] | null
}

/** The bar spans this range of palm widths. */
const RANGE: [number, number] = [-0.3, 1.0]

function position(value: number): number {
  const [lo, hi] = RANGE
  return Math.min(100, Math.max(0, ((value - lo) / (hi - lo)) * 100))
}

/** One channel per finger: the measurement against its hysteresis band, and the latch. */
const FingerStrip = memo(function FingerStrip({ measurement, states }: Props) {
  return (
    <section className="panel fingers" aria-label="Finger channels">
      <div className="faceplate">
        <h2>Fingers</h2>
        <span className="spacer" />
        <span className="small muted">
          {measurement === null ? 'no measurement' : `palm ${measurement.palmWidth.toFixed(0)} px`}
        </span>
      </div>
      <div className="channels">
        {FINGERS.map((name, i) => {
          const band = i === 0 ? RULES.thumb : RULES.finger
          const value =
            measurement === null
              ? null
              : i === 0
                ? measurement.thumb
                : (measurement.fingers[i - 1] ?? null)
          const on = states !== null && states[i] === true
          return (
            <div key={name} className={`channel ${on ? 'on' : ''}`}>
              <span className="name">{name}</span>
              <div
                className="band"
                title={`${name}: raises above ${band.raise_threshold}, lowers below ${band.lower_threshold} palm widths`}
              >
                <span
                  className="hysteresis"
                  style={{
                    left: `${position(band.lower_threshold)}%`,
                    width: `${position(band.raise_threshold) - position(band.lower_threshold)}%`,
                  }}
                />
                <span className="zero" style={{ left: `${position(0)}%` }} />
                {value !== null && (
                  <span className="marker" style={{ left: `${position(value)}%` }} />
                )}
              </div>
              <span className="num value">{value === null ? '' : value.toFixed(2)}</span>
              <Led on={on} tone="green" label={name} />
            </div>
          )
        })}
      </div>
      <p className="panel-note">
        Tip beyond the PIP joint along the hand's up axis, in palm widths (the thumb: tip beyond the
        index MCP along the side axis). The shaded band is the hysteresis: a finger latches above
        the right edge and releases below the left one.
      </p>
    </section>
  )
})

export default FingerStrip
