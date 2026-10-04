import { describe, expect, it } from 'vitest'
import type { FrameResult } from '../../engine.ts'
import { EXIT_OK, EXIT_UNSAFE, Host } from '../host.ts'
import { BenchLog } from '../log.ts'

function result(confirmed: number, changed: boolean): FrameResult {
  return {
    handPresent: true,
    rawCount: confirmed,
    fingerStates: null,
    confirmedCount: confirmed,
    changed,
    relays: [],
    pointsPx: null,
  }
}

function setup() {
  let now = 0
  const log = new BenchLog(() => now * 1000)
  const host = new Host(() => now, log)
  const at = (s: number) => {
    now = s
    host.tick()
  }
  host.start()
  return { host, log, at }
}

describe('Host', () => {
  it('starts connected and drives the relays from confirmed counts', () => {
    const { host, at } = setup()
    expect(host.state).toBe('running')
    at(1)
    host.onFrame(result(2, true))
    expect(host.board.relayStates()).toEqual([false, true, false, false])
    at(1.1)
    host.onFrame(result(4, true))
    expect(host.board.relayStates()).toEqual([false, true, false, true])
    at(1.6)
    host.onFrame(result(4, false))
    expect(host.board.relayStates()).toEqual([false, false, false, true])
  })

  it('keeps the board fed with heartbeats while running', () => {
    const { host, at } = setup()
    for (let t = 0; t < 10; t += 0.016) at(t)
    expect(host.board.tripped).toBe(false)
    expect(host.board.sinceHeartbeat(10_000)).toBeLessThanOrEqual(260)
  })

  it('sends the beats that fell due while the frame loop was busy, as of their own instants', () => {
    const { host, log, at } = setup()
    at(0.5)
    host.onFrame(result(1, true))
    // A 1.1 s block (a slow inference) on the frame loop: the thread kept beating meanwhile.
    at(1.6)
    expect(host.board.tripped).toBe(false)
    expect(host.board.relayStates()).toEqual([true, false, false, false])
    expect(log.snapshot().some((l) => /Heartbeat gap/.test(l.message))).toBe(false)
  })

  it('lets the watchdog release the relays during a stall and restates them after', () => {
    const { host, at } = setup()
    at(1)
    host.onFrame(result(5, true))
    host.stall(2)
    at(1.9)
    expect(host.board.tripped).toBe(false)
    at(2.3)
    expect(host.board.tripped).toBe(true)
    expect(host.board.relayStates()).toEqual([false, false, false, false])
    at(3.05)
    expect(host.state).toBe('running')
    expect(host.board.tripped).toBe(false)
    expect(host.board.relayStates()).toEqual([true, true, true, true])
  })

  it('exits unsafe when the cable is pulled, while the board releases itself', () => {
    const { host, log, at } = setup()
    at(1)
    host.onFrame(result(1, true))
    host.pullCable()
    at(1.3)
    expect(host.state).toBe('exited')
    expect(host.exitCode).toBe(EXIT_UNSAFE)
    expect(log.snapshot().some((l) => /Relays may be left energised/.test(l.message))).toBe(true)
    expect(host.board.relayStates()).toEqual([true, false, false, false])
    at(2.4)
    expect(host.board.relayStates()).toEqual([false, false, false, false])
    host.plugCable()
    host.restart()
    expect(host.state).toBe('running')
    expect(host.exitCode).toBeNull()
  })

  it('exits cleanly on Ctrl-C with every relay off', () => {
    const { host, log, at } = setup()
    at(1)
    host.onFrame(result(3, true))
    host.interrupt()
    expect(host.state).toBe('exited')
    expect(host.exitCode).toBe(EXIT_OK)
    expect(host.board.relayStates()).toEqual([false, false, false, false])
    expect(log.snapshot().at(-1)?.message).toBe('Done (exit code 0).')
    host.onFrame(result(5, true))
    expect(host.board.relayStates()).toEqual([false, false, false, false])
  })

  it('fails setup when the board is unpowered at start, and runs once power is back', () => {
    const { host } = setup()
    host.interrupt()
    host.cutPower()
    host.restart()
    expect(host.state).toBe('exited')
    expect(host.exitCode).toBe(2)
    host.restorePower()
    host.restart()
    expect(host.state).toBe('running')
  })
})
