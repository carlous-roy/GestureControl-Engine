import { memo } from 'react'
import { RELAY_PINS } from '../bench/board.ts'
import { MIN_SWITCH_INTERVAL_S } from '../bench/controller.ts'
import Led from './Led.tsx'

interface Props {
  /** What the module's coils are doing, from the board's pin levels. */
  energised: boolean[]
  /** What the host believes it wrote. */
  written: boolean[]
  desired: boolean[]
  holds: number[]
  levels: number[]
  activeLow: boolean
  tripped: boolean
  powered: boolean
  hostRunning: boolean
}

/** The four-channel relay module as it sits on the bench, with the host's view beside each channel. */
const RelayModule = memo(function RelayModule({
  energised,
  written,
  desired,
  holds,
  levels,
  activeLow,
  tripped,
  powered,
  hostRunning,
}: Props) {
  return (
    <section
      className={`panel relays ${tripped ? 'tripped' : ''} ${powered ? '' : 'unpowered'}`}
      aria-label="Relay module"
    >
      <div className="faceplate">
        <h2>Relay module</h2>
        <span className="small muted">4 channel, {activeLow ? 'active-low' : 'active-high'}</span>
        <span className="spacer" />
        <Led on={powered} tone="red" label="Module power" />
        <span className="small muted">{powered ? 'powered' : 'no power'}</span>
      </div>
      <div className="module">
        {energised.map((on, i) => {
          const hold = holds[i] ?? 0
          const pending = (desired[i] ?? false) !== (written[i] ?? false)
          const level = levels[i] ?? 1
          return (
            <div key={i} className={`relay ${on ? 'on' : ''}`}>
              <div className="relay-head">
                <span className="label">
                  IN{i + 1} <span className="muted">pin {RELAY_PINS[i]}</span>
                </span>
                <Led on={on} tone="red" size={12} label={`Relay ${i + 1}`} />
              </div>
              <div className="coil" aria-hidden="true">
                <span className="contact" />
              </div>
              <div className="relay-foot num">
                <span>{on ? 'ON' : 'OFF'}</span>
                <span className="muted">{level === 1 ? 'HIGH' : 'LOW'}</span>
              </div>
              <div
                className="hold"
                title={`A relay never switches twice within ${MIN_SWITCH_INTERVAL_S} s`}
              >
                {!hostRunning ? (
                  <span className="small muted">host down</span>
                ) : pending ? (
                  <>
                    <span
                      className="hold-fill"
                      style={{ width: `${(hold / MIN_SWITCH_INTERVAL_S) * 100}%` }}
                    />
                    <span className="small">
                      {hold > 0
                        ? `${desired[i] ? 'on' : 'off'} in ${hold.toFixed(2)} s`
                        : 'applying'}
                    </span>
                  </>
                ) : (
                  <span className="small muted">
                    {written[i] === on ? 'settled' : 'host differs'}
                  </span>
                )}
              </div>
            </div>
          )
        })}
      </div>
      <p className="panel-note">
        {tripped
          ? 'The watchdog has released every relay: pin writes are ignored until the heartbeat is back.'
          : !powered
            ? 'Without power nothing holds: a mechanical relay keeps its state only while its coil is driven.'
            : `Each channel waits at least ${MIN_SWITCH_INTERVAL_S} s between switches; a change asked for inside that window is applied by the next loop iteration once it has passed.`}
      </p>
    </section>
  )
})

export default RelayModule
