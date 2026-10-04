// Per-stage timings as the engine's bench command reports them: medians and a high percentile
// over a window of recent frames, so one slow frame does not define the figure.

export class RollingStats {
  private values: number[] = []
  private readonly window: number

  constructor(window = 120) {
    this.window = window
  }

  push(value: number): void {
    this.values.push(value)
    if (this.values.length > this.window) this.values.shift()
  }

  get count(): number {
    return this.values.length
  }

  get last(): number | null {
    return this.values.length === 0 ? null : (this.values[this.values.length - 1] ?? null)
  }

  private sorted(): number[] {
    return [...this.values].sort((a, b) => a - b)
  }

  /** The value at `fraction` of the sorted window (0.5 is the median), or null when empty. */
  percentile(fraction: number): number | null {
    if (this.values.length === 0) return null
    const sorted = this.sorted()
    const index = Math.min(sorted.length - 1, Math.max(0, Math.ceil(fraction * sorted.length) - 1))
    return sorted[index] ?? null
  }

  get median(): number | null {
    return this.percentile(0.5)
  }

  get p95(): number | null {
    return this.percentile(0.95)
  }

  get mean(): number | null {
    if (this.values.length === 0) return null
    return this.values.reduce((a, b) => a + b, 0) / this.values.length
  }

  clear(): void {
    this.values = []
  }
}

/** Frames per second from the intervals between recent frames. */
export class FrameRate {
  private readonly intervals = new RollingStats(60)
  private last: number | null = null

  /** Records a frame at `nowMs`. */
  mark(nowMs: number): void {
    if (this.last !== null) this.intervals.push(nowMs - this.last)
    this.last = nowMs
  }

  get fps(): number | null {
    const median = this.intervals.median
    return median === null || median <= 0 ? null : 1000 / median
  }

  clear(): void {
    this.intervals.clear()
    this.last = null
  }
}
