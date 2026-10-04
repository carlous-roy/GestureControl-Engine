import { describe, expect, it } from 'vitest'
import { Board, SerialError, SerialLink } from '../board.ts'
import { BenchLog } from '../log.ts'

function setup() {
  let now = 0
  const log = new BenchLog(() => now)
  const link = new SerialLink()
  const board = new Board(link, log)
  return { board, link, log, at: (ms: number) => (now = ms) }
}

describe('Board (RelayWatchdogFirmata)', () => {
  it('boots with every relay released and never trips before the first heartbeat', () => {
    const { board } = setup()
    expect(board.levels).toEqual([1, 1, 1, 1])
    expect(board.relayStates()).toEqual([false, false, false, false])
    board.tick(60_000)
    expect(board.tripped).toBe(false)
  })

  it('switches a relay on a write and reads it back under the polarity', () => {
    const { board } = setup()
    board.configure(true, 1000, 0)
    board.write(2, 0)
    expect(board.relayStates()).toEqual([false, false, true, false])
    board.configure(false, 1000, 0)
    expect(board.relayStates()).toEqual([true, true, false, true])
  })

  it('releases the relays when the heartbeat stops and ignores writes until it resumes', () => {
    const { board, log } = setup()
    board.configure(true, 1000, 0)
    board.write(0, 0)
    board.heartbeat(250)
    board.tick(1_250)
    expect(board.tripped).toBe(false)
    board.tick(1_251)
    expect(board.tripped).toBe(true)
    expect(board.relayStates()).toEqual([false, false, false, false])
    board.write(0, 0)
    expect(board.relayStates()).toEqual([false, false, false, false])
    board.heartbeat(3_000)
    expect(board.tripped).toBe(false)
    board.write(0, 0)
    expect(board.relayStates()).toEqual([true, false, false, false])
    expect(log.snapshot().map((l) => l.message)).toEqual([
      'watchdog: no heartbeat, relays released',
      'watchdog: heartbeat resumed',
    ])
  })

  it('refuses serial traffic while the cable is out or the power is off', () => {
    const { board, link } = setup()
    link.up = false
    expect(() => board.heartbeat(0)).toThrow(SerialError)
    expect(() => board.write(0, 0)).toThrow(SerialError)
    link.up = true
    board.configure(true, 1000, 0)
    board.write(1, 0)
    board.powerOff()
    expect(board.relayStates()).toEqual([false, false, false, false])
    expect(() => board.reportFirmware()).toThrow(SerialError)
    board.powerOn()
    expect(board.armed).toBe(false)
  })
})
