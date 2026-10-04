// The host side of the relays: a port of gesturecontrol/controller.py with the same policies.
// Polarity is active-low by default; a relay is never switched twice within the switching
// interval, a change requested inside the window waits for the next apply; every serial write is
// guarded, with one reconnect that restores the relay states; cleanup de-energises everything and
// never throws; the heartbeat feeds the watchdog and restates the relays after a gap longer than
// its timeout. The clock is in seconds, as time.monotonic is.

import { relaysForCount } from '../engine.ts'
import { Board, SerialError } from './board.ts'
import type { BenchLog } from './log.ts'

export const MIN_SWITCH_INTERVAL_S = 0.5
export const HEARTBEAT_INTERVAL_S = 0.25
export const HEARTBEAT_TIMEOUT_MS = 1000
export const RELAY_ACTIVE_LOW_DEFAULT = true

/** The board is lost even after one reconnect, or a write failed right after connecting. */
export class HardwareError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'HardwareError'
  }
}

export interface ControllerOptions {
  activeLow?: boolean
  minSwitchInterval?: number
  heartbeatTimeoutMs?: number
}

/** Opens the board on a port; throws SerialError when nothing answers there. */
export type BoardFactory = (port: string) => Board

export class RelayController {
  readonly activeLow: boolean
  readonly minSwitchInterval: number
  readonly heartbeatTimeoutMs: number
  private readonly clock: () => number
  private readonly log: BenchLog
  private readonly boardFactory: BoardFactory
  private board: Board | null = null
  private portName: string | null = null
  private desiredStates = [false, false, false, false]
  private physical = [false, false, false, false]
  private lastChange = [-Infinity, -Infinity, -Infinity, -Infinity]
  private lastHeartbeat: number | null = null
  private watchdogAck = false
  private lostBoard = false
  private changes = 0

  constructor(
    clock: () => number,
    log: BenchLog,
    boardFactory: BoardFactory,
    options: ControllerOptions = {}
  ) {
    this.clock = clock
    this.log = log
    this.boardFactory = boardFactory
    this.activeLow = options.activeLow ?? RELAY_ACTIVE_LOW_DEFAULT
    this.minSwitchInterval = options.minSwitchInterval ?? MIN_SWITCH_INTERVAL_S
    this.heartbeatTimeoutMs = options.heartbeatTimeoutMs ?? HEARTBEAT_TIMEOUT_MS
    if (this.minSwitchInterval < 0) throw new RangeError('min_switch_interval must not be negative')
  }

  // Introspection ------------------------------------------------------------

  get revision(): number {
    return this.changes
  }

  get isConnected(): boolean {
    return this.board !== null
  }

  get port(): string | null {
    return this.portName
  }

  /** Relay states as last written (or held in memory in simulation). */
  get states(): boolean[] {
    return [...this.physical]
  }

  /** Requested states, which may still be waiting on the switching interval. */
  get desired(): boolean[] {
    return [...this.desiredStates]
  }

  get pending(): boolean {
    return this.desiredStates.some((state, i) => state !== this.physical[i])
  }

  get watchdogAcknowledged(): boolean {
    return this.watchdogAck
  }

  /** True once a reconnect failed: the relays' real state is unknown. */
  get lost(): boolean {
    return this.lostBoard
  }

  /** Seconds until relay `index` may switch again, zero when it may switch now. */
  holdRemaining(index: number): number {
    const last = this.lastChange[index] ?? -Infinity
    return Math.max(0, last + this.minSwitchInterval - this.clock())
  }

  /** Pin level (0/1) that produces the given relay state under the polarity. */
  levelFor(state: boolean): number {
    const onLevel = this.activeLow ? 0 : 1
    return state ? onLevel : 1 - onLevel
  }

  private changed(): void {
    this.changes++
  }

  // Connection ------------------------------------------------------------------

  /** Opens the board and drives every relay to its de-energised level. */
  connect(port: string): void {
    let board: Board
    try {
      board = this.boardFactory(port)
    } catch (e) {
      throw new HardwareError(`could not claim relay pins on ${port}: ${messageOf(e)}`)
    }
    this.board = board
    this.portName = port
    this.physical = [false, false, false, false]
    this.lastChange = [-Infinity, -Infinity, -Infinity, -Infinity]
    this.lostBoard = false
    try {
      for (let i = 0; i < 4; i++) board.write(i, this.levelFor(false))
      this.configureWatchdog(board)
    } catch (e) {
      this.board = null
      throw new HardwareError(`serial write failed right after connecting: ${messageOf(e)}`)
    }
    this.log.info(
      'host',
      `Connected to Firmata board on ${port} (${this.activeLow ? 'active-low' : 'active-high'} trigger)`
    )
    this.changed()
  }

  private configureWatchdog(board: Board): void {
    this.watchdogAck = false
    const firmware = board.reportFirmware()
    const timeout = this.heartbeatTimeoutMs
    this.watchdogAck = board.configure(this.activeLow, timeout, this.clock() * 1000)
    this.log.info('host', `Firmware: ${firmware.name} (${firmware.version.join(', ')})`)
    if (this.watchdogAck) {
      this.log.info(
        'host',
        `Watchdog firmware acknowledged: relays de-energise if no heartbeat arrives for ${timeout} ms`
      )
    } else {
      this.log.warn(
        'host',
        'No watchdog acknowledgement from the board. With StandardFirmata the relays keep their last state if this program dies; flash firmware/RelayWatchdogFirmata for host-loss protection.'
      )
    }
    this.lastHeartbeat = this.clock()
  }

  /** Closes the board, if any, without touching the relay levels. */
  disconnect(): void {
    this.board = null
    this.changed()
  }

  // Relay commands ----------------------------------------------------------------

  /** Requests one relay state (index 0 to 3) and applies what the interval allows. */
  setRelay(index: number, state: boolean): void {
    if (index < 0 || index > 3) {
      this.log.warn('host', `Ignoring relay index ${index} (valid: 0-3)`)
      return
    }
    this.desiredStates[index] = state
    this.apply()
  }

  /** Requests the state of every relay and applies what the interval allows. */
  setAll(states: readonly boolean[]): void {
    states.slice(0, 4).forEach((state, i) => {
      this.desiredStates[i] = state
    })
    this.apply()
  }

  /** Requests the relay pattern the gesture mapping assigns to `count`. */
  setFromFingerCount(count: number): void {
    this.setAll(relaysForCount(count))
  }

  /**
   * Writes every desired change whose switching interval has passed and returns the (index,
   * state) pairs that were switched. Throws HardwareError if the board is lost after one reconnect.
   */
  apply(): Array<[number, boolean]> {
    const now = this.clock()
    const switched: Array<[number, boolean]> = []
    for (let i = 0; i < 4; i++) {
      const desired = this.desiredStates[i] ?? false
      if (desired === this.physical[i]) continue
      if (now - (this.lastChange[i] ?? -Infinity) < this.minSwitchInterval) continue
      this.write(i, desired)
      this.physical[i] = desired
      this.lastChange[i] = now
      switched.push([i, desired])
    }
    if (switched.length > 0) this.changed()
    return switched
  }

  private write(index: number, state: boolean): void {
    if (this.board === null) return
    const level = this.levelFor(state)
    try {
      this.board.write(index, level)
    } catch (e) {
      this.log.warn(
        'host',
        `Serial write to relay ${index + 1} failed (${messageOf(e)}); reconnecting once`
      )
      this.reconnect()
      try {
        this.board.write(index, level)
      } catch (e2) {
        throw new HardwareError(`serial write failed after reconnect: ${messageOf(e2)}`)
      }
    }
  }

  private reconnect(): void {
    const port = this.portName ?? ''
    this.board = null
    let board: Board
    try {
      board = this.boardFactory(port)
      for (let i = 0; i < 4; i++) board.write(i, this.levelFor(this.physical[i] ?? false))
    } catch (e) {
      this.lostBoard = true
      this.changed()
      throw new HardwareError(
        `lost the board on ${port} and could not reconnect: ${messageOf(e)}; relay states are unknown`
      )
    }
    this.board = board
    this.configureWatchdog(board)
    this.log.info('host', `Reconnected to ${port} and restored relay states`)
    this.changed()
  }

  // Heartbeat ----------------------------------------------------------------------

  /** Sends one heartbeat; after a gap longer than the timeout, re-sends the relay states. */
  heartbeat(): void {
    if (this.board === null) return
    const now = this.clock()
    const gapMs = this.lastHeartbeat === null ? 0 : (now - this.lastHeartbeat) * 1000
    try {
      this.board.heartbeat(now * 1000)
      if (gapMs > this.heartbeatTimeoutMs) {
        this.log.warn(
          'host',
          `Heartbeat gap of ${Math.round(gapMs)} ms exceeded the watchdog timeout; re-sending relay states`
        )
        for (let i = 0; i < 4; i++) this.board.write(i, this.levelFor(this.physical[i] ?? false))
        this.changed()
      }
    } catch (e) {
      throw new HardwareError(`heartbeat write failed: ${messageOf(e)}`)
    }
    this.lastHeartbeat = now
  }

  // Shutdown -------------------------------------------------------------------------

  /** De-energises every relay and closes the board. Never throws; false when a relay may be left on. */
  cleanup(): boolean {
    let ok = true
    this.desiredStates = [false, false, false, false]
    if (this.board !== null) {
      for (let i = 0; i < 4; i++) {
        try {
          this.board.write(i, this.levelFor(false))
          this.physical[i] = false
        } catch (e) {
          ok = false
          this.log.error('host', `Could not de-energise relay ${i + 1}: ${messageOf(e)}`)
        }
      }
      if (!ok) {
        this.log.error(
          'host',
          `Relays may be left energised: ${bits(this.physical)}. Cut power to the module.`
        )
      }
      this.disconnect()
      this.log.info('host', 'Board disconnected.')
    } else if (this.lostBoard) {
      ok = false
      this.log.error(
        'host',
        `The board on ${this.portName ?? '?'} was lost; relays may be left energised: ${bits(this.physical)}. Cut power to the module.`
      )
    } else {
      this.physical = [false, false, false, false]
    }
    this.changed()
    return ok
  }
}

/** The relay states the way the Python prints a list: [True, False, False, False]. */
export function bits(states: readonly boolean[]): string {
  return `[${states.map((s) => (s ? 'True' : 'False')).join(', ')}]`
}

function messageOf(e: unknown): string {
  if (e instanceof SerialError || e instanceof Error) return e.message
  return String(e)
}
