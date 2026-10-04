import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { RULES } from '../../engine.ts'
import { GOLDEN_RULES, ReplayPlayer, SEQUENCES, checkAllParity } from '../replay.ts'
import { TASKS_VISION_VERSION } from '../camera.ts'

describe('golden replay', () => {
  it('matches the engine on every sequence with the rules the page loads', () => {
    expect(GOLDEN_RULES).toEqual(RULES)
    const results = checkAllParity()
    expect(results).toHaveLength(SEQUENCES.length)
    expect(results.filter((r) => r.mismatches > 0)).toEqual([])
  })

  it('plays frames at the sequence rate and moves on at the end', () => {
    const player = new ReplayPlayer()
    player.select(5)
    const short = player.sequence
    expect(short.frames.length).toBeLessThan(12)
    const first = player.advance(1000 / 30 + 0.01)
    expect(first.map((f) => f.index)).toEqual([0])
    expect(first[0]?.t).toBe(0)
    expect(player.advance(5)).toEqual([])
    let total = first.length
    while (player.sequenceIndex === 5) total += player.advance(1000 / 30 + 0.01).length
    expect(total).toBe(short.frames.length)
    expect(player.frameIndex).toBe(0)
    expect(player.sequenceIndex).toBe(6)
  })

  it('loops one sequence when not continuous and caps a backlog', () => {
    const player = new ReplayPlayer()
    player.continuous = false
    player.select(14)
    const frames = player.advance(10_000)
    expect(frames.length).toBe(4)
    expect(player.sequenceIndex).toBe(14)
    player.playing = false
    expect(player.advance(1000)).toEqual([])
  })
})

describe('camera source', () => {
  it('pins the WASM runtime to the installed tasks-vision version', () => {
    const pkg = JSON.parse(readFileSync(new URL('../../../package.json', import.meta.url), 'utf8'))
    expect(pkg.dependencies['@mediapipe/tasks-vision']).toBe(TASKS_VISION_VERSION)
  })
})
