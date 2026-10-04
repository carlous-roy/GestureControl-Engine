import { describe, expect, it } from 'vitest'
import { FrameRate, RollingStats } from '../timings.ts'

describe('RollingStats', () => {
  it('reports median, p95 and mean over its window', () => {
    const stats = new RollingStats(5)
    for (const v of [5, 1, 4, 2, 3, 100]) stats.push(v)
    expect(stats.count).toBe(5)
    expect(stats.median).toBe(3)
    expect(stats.p95).toBe(100)
    expect(stats.mean).toBe(22)
    expect(stats.last).toBe(100)
    expect(new RollingStats().median).toBeNull()
  })
})

describe('FrameRate', () => {
  it('derives frames per second from the median interval', () => {
    const rate = new FrameRate()
    expect(rate.fps).toBeNull()
    for (let i = 0; i < 10; i++) rate.mark(i * 33.3)
    expect(rate.fps).toBeCloseTo(30, 0)
  })
})
