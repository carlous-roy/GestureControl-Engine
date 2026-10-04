// The recorded and synthetic hands of fixtures/golden_vectors.json, played back at their own frame
// rate. Every sequence carries the outputs the pipeline must produce on each frame, so the deck
// can show the port's parity with the engine while it plays.

import golden from '../../test/golden_vectors.json'
import { Pipeline, type Point, type Rules } from '../engine.ts'

export interface ExpectedFrame {
  hand: boolean
  raw: number
  confirmed: number
  changed: boolean
  /** Relay states as a bit string, relay 1 first. */
  relays: string
  /** Finger latches as a bit string, thumb first, or null without a usable hand. */
  fingers: string | null
  sum_px: number | null
}

export interface Sequence {
  name: string
  description: string
  width: number
  height: number
  fps: number
  frames: Array<Point[] | null>
  expected: ExpectedFrame[]
}

interface GoldenFile {
  version: number
  generated_by: string
  description: string
  rules: Rules
  sequences: Sequence[]
}

const file = golden as unknown as GoldenFile

export const GOLDEN_RULES: Rules = file.rules
export const SEQUENCES: readonly Sequence[] = file.sequences

export interface ParityResult {
  name: string
  frames: number
  mismatches: number
  /** The first frame that differed, or null when every frame matched. */
  firstMismatch: number | null
}

const bits = (flags: readonly boolean[]): string => flags.map((f) => (f ? '1' : '0')).join('')

/** Runs one sequence through a fresh pipeline and compares every frame with the file. */
export function checkParity(sequence: Sequence, rules: Rules = GOLDEN_RULES): ParityResult {
  const pipeline = new Pipeline(sequence.width, sequence.height, rules)
  let mismatches = 0
  let firstMismatch: number | null = null
  sequence.frames.forEach((frame, i) => {
    const want = sequence.expected[i]
    const got = pipeline.process(frame, i / sequence.fps)
    const fingers = got.fingerStates === null ? null : bits(got.fingerStates)
    const sum = got.pointsPx === null ? null : got.pointsPx.reduce((acc, [x, y]) => acc + x + y, 0)
    const ok =
      want !== undefined &&
      got.handPresent === want.hand &&
      got.rawCount === want.raw &&
      got.confirmedCount === want.confirmed &&
      got.changed === want.changed &&
      bits(got.relays) === want.relays &&
      fingers === want.fingers &&
      (sum === null
        ? want.sum_px === null
        : want.sum_px !== null && Math.abs(sum - want.sum_px) < 1e-5)
    if (!ok) {
      mismatches++
      if (firstMismatch === null) firstMismatch = i
    }
  })
  return { name: sequence.name, frames: sequence.frames.length, mismatches, firstMismatch }
}

/** Every sequence's parity, in file order. */
export function checkAllParity(rules: Rules = GOLDEN_RULES): ParityResult[] {
  return SEQUENCES.map((s) => checkParity(s, rules))
}

export interface ReplayFrame {
  sequence: Sequence
  index: number
  landmarks: Point[] | null
  /** The frame's timestamp in the sequence's own clock, seconds. */
  t: number
  expected: ExpectedFrame
}

/**
 * Steps through the sequences at their frame rate. `advance` returns the frames that became due
 * in the elapsed time, at most a few per call, so a hidden tab does not replay a backlog at once.
 */
export class ReplayPlayer {
  sequenceIndex = 0
  frameIndex = 0
  playing = true
  /** Move on to the next sequence when one ends; otherwise loop the same one. */
  continuous = true
  speed = 1
  private carryMs = 0
  private readonly maxFramesPerAdvance = 4

  get sequence(): Sequence {
    return SEQUENCES[this.sequenceIndex] ?? (SEQUENCES[0] as Sequence)
  }

  /** The frame about to be shown. */
  current(): ReplayFrame {
    const sequence = this.sequence
    const index = Math.min(this.frameIndex, sequence.frames.length - 1)
    return {
      sequence,
      index,
      landmarks: sequence.frames[index] ?? null,
      t: index / sequence.fps,
      expected: sequence.expected[index] as ExpectedFrame,
    }
  }

  select(index: number): void {
    this.sequenceIndex = ((index % SEQUENCES.length) + SEQUENCES.length) % SEQUENCES.length
    this.frameIndex = 0
    this.carryMs = 0
  }

  /** The frames due after `elapsedMs` of real time, in order. */
  advance(elapsedMs: number): ReplayFrame[] {
    if (!this.playing) return []
    const sequence = this.sequence
    const frameMs = 1000 / (sequence.fps * this.speed)
    this.carryMs += elapsedMs
    const due: ReplayFrame[] = []
    while (this.carryMs >= frameMs && due.length < this.maxFramesPerAdvance) {
      this.carryMs -= frameMs
      due.push(this.step())
    }
    if (this.carryMs > frameMs * this.maxFramesPerAdvance) this.carryMs = 0
    return due
  }

  /** Emits the current frame and moves to the next one, wrapping or moving on at the end. */
  step(): ReplayFrame {
    const frame = this.current()
    this.frameIndex++
    if (this.frameIndex >= this.sequence.frames.length) {
      if (this.continuous) this.select(this.sequenceIndex + 1)
      else this.frameIndex = 0
    }
    return frame
  }
}
