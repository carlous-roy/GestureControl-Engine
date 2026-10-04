// The Arduino on the bench: a model of firmware/RelayWatchdogFirmata.ino. Four relay pins start
// at their de-energised level, a heartbeat SysEx arms the watchdog, a configuration SysEx sets the
// polarity and the timeout and is acknowledged, and when the heartbeat stops for longer than the
// timeout every relay pin is driven to the safe level and writes to those pins are ignored until a
// heartbeat arrives again. The strings the sketch sends with Firmata.sendString go to `onString`.

import type { BenchLog } from './log.ts'

/** Pins 7, 6, 5 and 4 drive IN1 to IN4 of the module, as config.py and the sketch agree. */
export const RELAY_PINS: readonly number[] = [7, 6, 5, 4]
export const DEFAULT_TIMEOUT_MS = 1000
export const FIRMWARE_NAME = 'RelayWatchdogFirmata.ino'
export const FIRMWARE_VERSION: readonly [number, number] = [1, 0]

/** Thrown by a serial operation when the cable is out or the board is unpowered. */
export class SerialError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'SerialError'
  }
}

/** The USB cable between host and board; the host's writes fail while it is out. */
export class SerialLink {
  up = true
}

export class Board {
  activeLow = true
  timeoutMs = DEFAULT_TIMEOUT_MS
  /** Pin levels for the four relay pins, 0 or 1. */
  levels: number[] = [1, 1, 1, 1]
  private lastHeartbeat = 0
  armed = false
  tripped = false
  powered = true
  private changes = 0
  private readonly link: SerialLink
  private readonly log: BenchLog

  constructor(link: SerialLink, log: BenchLog) {
    this.link = link
    this.log = log
    this.reset()
  }

  /** Counts every change so a renderer can tell when the board moved. */
  get revision(): number {
    return this.changes
  }

  /** The level that leaves a relay de-energised under the current polarity. */
  safeLevel(): number {
    return this.activeLow ? 1 : 0
  }

  /** The relay a pin level produces: on when the level is the energised one. */
  relayStates(): boolean[] {
    const onLevel = this.activeLow ? 0 : 1
    return this.levels.map((level) => level === onLevel)
  }

  /** millis() since the last heartbeat, for the countdown on the panel. */
  sinceHeartbeat(nowMs: number): number {
    return nowMs - this.lastHeartbeat
  }

  private changed(): void {
    this.changes++
  }

  private string(message: string): void {
    this.log.info('board', message)
  }

  private requireSerial(): void {
    if (!this.link.up) throw new SerialError('the serial port is gone')
    if (!this.powered) throw new SerialError('the board does not answer')
  }

  /** Power-up or SYSTEM_RESET: every relay pin at the safe level before it becomes an output. */
  reset(): void {
    this.levels = [this.safeLevel(), this.safeLevel(), this.safeLevel(), this.safeLevel()]
    this.armed = false
    this.tripped = false
    this.changed()
  }

  /** Cuts the power: everything releases and the state is forgotten. */
  powerOff(): void {
    this.powered = false
    this.levels = [this.safeLevel(), this.safeLevel(), this.safeLevel(), this.safeLevel()]
    this.armed = false
    this.tripped = false
    this.changed()
  }

  powerOn(): void {
    this.powered = true
    this.reset()
  }

  /** SysEx 0x79: the firmware name and version the sketch announces. */
  reportFirmware(): { name: string; version: readonly [number, number] } {
    this.requireSerial()
    return { name: FIRMWARE_NAME, version: FIRMWARE_VERSION }
  }

  /** SysEx 0x01 from the host. */
  heartbeat(nowMs: number): void {
    this.requireSerial()
    this.lastHeartbeat = nowMs
    this.armed = true
    if (this.tripped) {
      this.tripped = false
      this.string('watchdog: heartbeat resumed')
    }
    this.changed()
  }

  /** SysEx 0x02 from the host; answered with an acknowledgement. */
  configure(activeLow: boolean, timeoutMs: number, nowMs: number): boolean {
    this.requireSerial()
    this.activeLow = activeLow
    this.timeoutMs = timeoutMs === 0 ? DEFAULT_TIMEOUT_MS : timeoutMs
    this.lastHeartbeat = nowMs
    this.armed = true
    this.tripped = false
    this.changed()
    return true
  }

  /** A digital write to a relay pin; ignored while the watchdog has tripped. */
  write(index: number, level: number): void {
    this.requireSerial()
    if (this.tripped) return
    if (this.levels[index] !== level) {
      this.levels[index] = level
      this.changed()
    }
  }

  /** The sketch's loop(): trip when the heartbeat is overdue. */
  tick(nowMs: number): void {
    if (!this.powered) return
    if (this.armed && !this.tripped && nowMs - this.lastHeartbeat > this.timeoutMs) {
      this.tripped = true
      this.levels = [this.safeLevel(), this.safeLevel(), this.safeLevel(), this.safeLevel()]
      this.string('watchdog: no heartbeat, relays released')
      this.changed()
    }
  }
}
