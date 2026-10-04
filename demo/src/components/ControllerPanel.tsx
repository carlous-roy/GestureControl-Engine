import { memo } from 'react'
import { FIRMWARE_NAME } from '../bench/board.ts'
import { HEARTBEAT_INTERVAL_S } from '../bench/controller.ts'
import {
  EXIT_OK,
  EXIT_RUNTIME,
  EXIT_SETUP,
  EXIT_UNSAFE,
  PORT,
  type HostState,
} from '../bench/host.ts'
import type { Bench, BenchView } from '../hooks/useBench.ts'
import Led from './Led.tsx'

interface Props {
  host: BenchView['host']
  faults: Bench['faults']
}

const EXIT_TEXT: Record<number, string> = {
  [EXIT_OK]: 'clean exit, every relay off',
  [EXIT_RUNTIME]: 'runtime failure',
  [EXIT_SETUP]: 'could not start',
  [EXIT_UNSAFE]: 'a relay may be left on',
}

const STATE_TEXT: Record<HostState, string> = {
  running: 'running',
  stalled: 'stalled',
  exited: 'exited',
}

export const STALL_SECONDS = 2

/** The host process and the board, their link, and the faults a visitor can throw at them. */
const ControllerPanel = memo(function ControllerPanel({ host, faults }: Props) {
  const beat = host.sinceHeartbeatMs >= 0 && host.sinceHeartbeatMs < 90 && host.state === 'running'
  const remaining = Math.max(0, host.timeoutMs - host.sinceHeartbeatMs)
  const watchdogFraction = host.armed ? remaining / host.timeoutMs : 1
  const hostTone = host.state === 'running' ? 'green' : host.state === 'stalled' ? 'amber' : 'red'

  return (
    <section className="panel controller" aria-label="Host and board">
      <div className="faceplate">
        <h2>Host and board</h2>
        <span className="spacer" />
        <span className="small muted mono">{PORT}</span>
      </div>

      <div className="units">
        <div className="unit">
          <div className="unit-head">
            <Led on tone={hostTone} label="Host" />
            <span className="unit-name">gesturecontrol</span>
            <span className={`small state state-${host.state}`}>
              {STATE_TEXT[host.state]}
              {host.state === 'stalled' ? ` ${host.stallRemainingS.toFixed(1)} s` : ''}
              {host.state === 'exited' && host.exitCode !== null
                ? `, code ${host.exitCode}: ${EXIT_TEXT[host.exitCode] ?? ''}`
                : ''}
            </span>
          </div>
          <div className="unit-row">
            <Led on={beat} tone="cyan" label="Heartbeat" />
            <span className="small muted">heartbeat every {HEARTBEAT_INTERVAL_S * 1000} ms</span>
          </div>
        </div>

        <div className="cable" aria-hidden="true">
          <span className={`wire ${host.linkUp ? '' : 'cut'}`} />
          <span className="small muted">{host.linkUp ? 'USB' : 'USB out'}</span>
        </div>

        <div className="unit">
          <div className="unit-head">
            <Led on={host.powered} tone="green" label="Board power" />
            <span className="unit-name">Arduino UNO</span>
            <span className="small muted">{FIRMWARE_NAME}</span>
          </div>
          <div
            className="unit-row watchdog"
            title="The sketch releases every relay when no heartbeat arrives for the timeout"
          >
            <span className="small muted">watchdog</span>
            <span className="spacer" />
            <span className="small num">
              {!host.powered
                ? 'off'
                : host.tripped
                  ? 'TRIPPED'
                  : host.armed
                    ? `${Math.round(remaining)} ms`
                    : 'not armed'}
            </span>
          </div>
          <div className={`meter ${host.tripped ? 'tripped' : ''}`}>
            <div
              className="meter-fill"
              style={{ width: `${Math.round(watchdogFraction * 100)}%` }}
            />
          </div>
        </div>
      </div>

      <div className="faults" role="group" aria-label="Faults">
        <button
          type="button"
          className="btn btn-sm"
          disabled={host.state !== 'running'}
          onClick={() => faults.stall(STALL_SECONDS)}
          title="The process hangs for two seconds: no frames, no heartbeats. The board's watchdog releases the relays after one second; when the host wakes up its heartbeat notices the gap and restates them."
        >
          Stall host {STALL_SECONDS} s
        </button>
        {host.linkUp ? (
          <button
            type="button"
            className="btn btn-sm btn-danger"
            onClick={faults.pullCable}
            title="The next serial write fails; the host reconnects once, fails again and exits through cleanup. The board, cut off, releases the relays by itself."
          >
            Pull USB
          </button>
        ) : (
          <button type="button" className="btn btn-sm" onClick={faults.plugCable}>
            Plug USB back
          </button>
        )}
        {host.powered ? (
          <button
            type="button"
            className="btn btn-sm btn-danger"
            onClick={faults.cutPower}
            title="The board and the module lose power: every relay drops at once and the board forgets its state."
          >
            Cut power
          </button>
        ) : (
          <button type="button" className="btn btn-sm" onClick={faults.restorePower}>
            Restore power
          </button>
        )}
        {host.state === 'exited' ? (
          <button type="button" className="btn btn-sm btn-primary" onClick={faults.restart}>
            Restart host
          </button>
        ) : (
          <button
            type="button"
            className="btn btn-sm"
            onClick={faults.interrupt}
            title="SIGINT: the loop stops, every relay is de-energised, the board is closed, exit code 0."
          >
            Ctrl-C
          </button>
        )}
      </div>
    </section>
  )
})

export default ControllerPanel
