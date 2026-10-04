import { describe, expect, it } from 'vitest'
import { Board, SerialError, SerialLink } from '../board.ts'
import { HardwareError, RelayController } from '../controller.ts'
import { BenchLog } from '../log.ts'

function setup(options = {}) {
  let now = 0
  const log = new BenchLog(() => now * 1000)
  const link = new SerialLink()
  const board = new Board(link, log)
  const controller = new RelayController(
    () => now,
    log,
    (port) => {
      if (!link.up) throw new SerialError(`could not open port ${port}`)
      board.reset()
      return board
    },
    options
  )
  return { controller, board, link, log, at: (s: number) => (now = s) }
}

describe('RelayController', () => {
  it('keeps the switching interval per relay, applying a held change later', () => {
    const { controller, at } = setup()
    at(10)
    controller.setFromFingerCount(1)
    expect(controller.states).toEqual([true, false, false, false])
    at(10.2)
    // Relay 2 has never switched, so it goes on at once; relay 1 waits out its interval.
    controller.setFromFingerCount(2)
    expect(controller.states).toEqual([true, true, false, false])
    expect(controller.desired).toEqual([false, true, false, false])
    expect(controller.pending).toBe(true)
    expect(controller.holdRemaining(0)).toBeCloseTo(0.3)
    at(10.49)
    expect(controller.apply()).toEqual([])
    at(10.5)
    expect(controller.apply()).toEqual([[0, false]])
    expect(controller.states).toEqual([false, true, false, false])
    expect(controller.pending).toBe(false)
  })

  it('connects with every relay released and the watchdog configured', () => {
    const { controller, board, log } = setup()
    controller.connect('/dev/ttyACM0')
    expect(controller.isConnected).toBe(true)
    expect(controller.watchdogAcknowledged).toBe(true)
    expect(board.armed).toBe(true)
    expect(board.timeoutMs).toBe(1000)
    expect(log.snapshot().map((l) => l.message)).toEqual([
      'Firmware: RelayWatchdogFirmata.ino (1, 0)',
      'Watchdog firmware acknowledged: relays de-energise if no heartbeat arrives for 1000 ms',
      'Connected to Firmata board on /dev/ttyACM0 (active-low trigger)',
    ])
    controller.setFromFingerCount(3)
    expect(board.relayStates()).toEqual([false, false, true, false])
    expect(board.levels).toEqual([1, 1, 0, 1])
  })

  it('restates the relays after a heartbeat gap longer than the timeout', () => {
    const { controller, board, log, at } = setup()
    controller.connect('/dev/ttyACM0')
    controller.setFromFingerCount(5)
    at(0.25)
    controller.heartbeat()
    board.tick(1_500)
    expect(board.relayStates()).toEqual([false, false, false, false])
    at(1.6)
    controller.heartbeat()
    expect(board.relayStates()).toEqual([true, true, true, true])
    expect(log.snapshot().at(-1)?.message).toMatch(/Heartbeat gap of 1350 ms exceeded/)
  })

  it('reconnects once after a failed write and raises when the board is gone', () => {
    const { controller, link, log, at } = setup()
    controller.connect('/dev/ttyACM0')
    at(1)
    controller.setFromFingerCount(1)
    link.up = false
    at(2)
    expect(() => controller.setFromFingerCount(2)).toThrow(HardwareError)
    expect(controller.lost).toBe(true)
    expect(controller.isConnected).toBe(false)
    expect(log.snapshot().some((l) => /reconnecting once/.test(l.message))).toBe(true)
    expect(controller.cleanup()).toBe(false)
    expect(log.snapshot().at(-1)?.message).toMatch(/was lost; relays may be left energised/)
  })

  it('cleans up to every relay off and reports success', () => {
    const { controller, board, at } = setup()
    controller.connect('/dev/ttyACM0')
    at(1)
    controller.setFromFingerCount(5)
    expect(controller.cleanup()).toBe(true)
    expect(controller.states).toEqual([false, false, false, false])
    expect(board.relayStates()).toEqual([false, false, false, false])
    expect(controller.isConnected).toBe(false)
  })

  it('works without a board, keeping the states in memory', () => {
    const { controller, at } = setup()
    at(1)
    controller.setRelay(3, true)
    expect(controller.states).toEqual([false, false, false, true])
    controller.heartbeat()
    expect(controller.cleanup()).toBe(true)
    expect(controller.states).toEqual([false, false, false, false])
  })
})
