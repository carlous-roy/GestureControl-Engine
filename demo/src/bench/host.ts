// The host process on the bench: the control loop of gesturecontrol/app.py and its heartbeat
// thread, around the ported controller and the modelled board. Each frame result goes to the
// controller the way the loop does it (a new confirmed count requests relays, a pending change is
// applied once its interval has passed); heartbeats go out every 250 ms; a HardwareError ends the
// run through cleanup with the exit codes the program uses. The bench adds the faults a visitor
// can inject: a stalled host, a pulled cable, a Ctrl-C, a power cut on the board, and a restart.

import type { FrameResult } from '../engine.ts'
import { Board, SerialError, SerialLink } from './board.ts'
import { HEARTBEAT_INTERVAL_S, HardwareError, RelayController } from './controller.ts'
import type { BenchLog } from './log.ts'

export const EXIT_OK = 0
export const EXIT_RUNTIME = 1
export const EXIT_SETUP = 2
export const EXIT_UNSAFE = 3

/** The port the host opens; the usual name of an UNO on Linux. */
export const PORT = '/dev/ttyACM0'

export type HostState = 'running' | 'stalled' | 'exited'

export class Host {
  readonly link = new SerialLink()
  readonly board: Board
  controller: RelayController
  state: HostState = 'exited'
  exitCode: number | null = null
  stopReason = ''
  /** Bench seconds at which a stalled host wakes up. */
  stalledUntil = 0
  private stallSeconds = 0
  private nextHeartbeatAt = 0
  private changes = 0
  private readonly clock: () => number
  /** While a heartbeat is being sent for an earlier instant, the time the thread would have seen. */
  private heartbeatAt: number | null = null
  private readonly log: BenchLog

  constructor(clock: () => number, log: BenchLog) {
    this.clock = clock
    this.log = log
    this.board = new Board(this.link, log)
    this.controller = this.newController()
  }

  /** The controller's clock: the bench clock, except inside a backdated heartbeat. */
  private readonly threadClock = (): number => this.heartbeatAt ?? this.clock()

  get revision(): number {
    return this.changes
  }

  private changed(): void {
    this.changes++
  }

  private newController(): RelayController {
    return new RelayController(this.threadClock, this.log, (port) => {
      // Opening the port resets an UNO, which is why the sketch sets the safe level in setup().
      if (!this.link.up) throw new SerialError(`could not open port ${port}: no such device`)
      if (!this.board.powered) throw new SerialError(`${port} does not answer`)
      this.board.reset()
      return this.board
    })
  }

  /** The program starts: connect, start the heartbeat, open the camera, run. */
  start(): void {
    if (this.state !== 'exited') return
    this.controller = this.newController()
    this.exitCode = null
    this.stopReason = ''
    this.log.info('host', `Connecting to the board on ${PORT}`)
    try {
      this.controller.connect(PORT)
    } catch (e) {
      this.log.error('host', `Board failure: ${messageOf(e)}`)
      this.finish(EXIT_SETUP, '')
      return
    }
    this.nextHeartbeatAt = this.clock() + HEARTBEAT_INTERVAL_S
    this.log.info('host', 'Opening frame source 0')
    this.log.info('host', 'Ready. Show 0-5 fingers. Press Q to exit.')
    this.state = 'running'
    this.changed()
  }

  /**
   * Runs the heartbeat thread and the board's loop up to now, and wakes a stalled host when due.
   * The heartbeat thread is not held up by the frame loop, so every beat that fell due while the
   * page was busy (a long inference, say) is sent as of its own instant, before the board checks.
   */
  tick(): void {
    const now = this.clock()
    if (this.state === 'stalled' && now >= this.stalledUntil) {
      this.state = 'running'
      // Nothing was sent during the stall; the thread beats again as soon as it is scheduled.
      this.nextHeartbeatAt = now
      this.log.warn('host', `Resumed after a ${this.stallSeconds.toFixed(1)} s stall`)
      this.changed()
    }
    if (this.state === 'running') {
      while (this.nextHeartbeatAt <= now) {
        const at = this.nextHeartbeatAt
        this.nextHeartbeatAt += HEARTBEAT_INTERVAL_S
        this.heartbeatAt = at
        try {
          this.controller.heartbeat()
        } catch (e) {
          this.heartbeatAt = null
          this.log.error('host', `Heartbeat stopped: ${messageOf(e)}`)
          this.log.error('host', `Board failure: ${messageOf(e)}`)
          this.finish(EXIT_RUNTIME, '')
          return
        } finally {
          this.heartbeatAt = null
        }
      }
    }
    this.board.tick(now * 1000)
  }

  /** One frame's result, handled as the loop handles it. */
  onFrame(result: FrameResult): void {
    if (this.state !== 'running') return
    try {
      if (result.changed) {
        this.controller.setFromFingerCount(result.confirmedCount)
        this.log.info(
          'host',
          `Gesture: ${result.confirmedCount} finger(s) -> relays ${this.controller.states.map((s) => (s ? '1' : '0')).join('')}`
        )
      } else if (this.controller.pending) {
        this.controller.apply()
      }
    } catch (e) {
      this.log.error('host', `Board failure: ${messageOf(e)}`)
      this.finish(EXIT_RUNTIME, '')
    }
  }

  // Faults ----------------------------------------------------------------------

  /** The process stops making progress for `seconds`: no frames, no heartbeats, then carries on. */
  stall(seconds: number): void {
    if (this.state !== 'running') return
    this.state = 'stalled'
    this.stallSeconds = seconds
    this.stalledUntil = this.clock() + seconds
    this.log.warn('bench', `Host stalled for ${seconds.toFixed(1)} s: no frames, no heartbeats`)
    this.changed()
  }

  /** The USB cable comes out: every serial write from now on fails. */
  pullCable(): void {
    if (!this.link.up) return
    this.link.up = false
    this.log.warn('bench', 'USB cable pulled: the serial port is gone')
    this.changed()
  }

  plugCable(): void {
    if (this.link.up) return
    this.link.up = true
    this.log.info('bench', `USB cable back in: ${PORT} is available again`)
    this.changed()
  }

  /** The module loses power: the relays drop and the board forgets everything. */
  cutPower(): void {
    if (!this.board.powered) return
    this.board.powerOff()
    this.log.warn('bench', 'Power cut to the board and the module: every relay drops')
    this.changed()
  }

  restorePower(): void {
    if (this.board.powered) return
    this.board.powerOn()
    this.log.info('bench', 'Power restored: the board boots with every relay released')
    this.changed()
  }

  /** Ctrl-C: the signal handler requests a stop and the loop ends through cleanup. */
  interrupt(): void {
    if (this.state === 'exited') return
    this.log.info('host', 'Received SIGINT, shutting down')
    this.finish(EXIT_OK, 'SIGINT')
  }

  /** The program is started again on the same port. */
  restart(): void {
    if (this.state !== 'exited') return
    this.start()
  }

  private finish(code: number, reason: string): void {
    let exitCode = code
    if (!this.controller.cleanup()) exitCode = EXIT_UNSAFE
    if (reason) this.log.info('host', `Stopped: ${reason}`)
    this.log.info('host', `Done (exit code ${exitCode}).`)
    this.state = 'exited'
    this.exitCode = exitCode
    this.stopReason = reason
    this.changed()
  }
}

function messageOf(e: unknown): string {
  if (e instanceof HardwareError || e instanceof Error) return e.message
  return String(e)
}
