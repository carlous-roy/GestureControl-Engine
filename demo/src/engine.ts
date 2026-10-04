// The typed face of src/gesture, the JavaScript port of the engine's filter, rules and
// confirmation. The port itself stays plain JavaScript, laid out line for line like the Python it
// mirrors and checked against the same golden vectors; this module gives the bench the shapes it
// renders without touching that code.

import { DEFAULT_RULES, GesturePipeline } from './gesture/pipeline.js'
import { FINGER_NAMES, measure, relayStatesForCount } from './gesture/rules.js'

export type Point = [number, number]

export interface Band {
  raise_threshold: number
  lower_threshold: number
}

/** gesturecontrol/rules.json, the constants both implementations read. */
export interface Rules {
  version: number
  filter: { min_cutoff_hz: number; beta: number; derivative_cutoff_hz: number }
  finger: Band
  thumb: Band
  min_palm_width_px: number
  confirm_frames: number
}

/** One frame's outcome, the same fields as the Python FrameResult. */
export interface FrameResult {
  handPresent: boolean
  /** Extended fingers this frame, or -1 without a usable hand. */
  rawCount: number
  /** The five latches (thumb first), or null without a usable hand. */
  fingerStates: boolean[] | null
  /** The count that drives the relays; -1 until the first confirmation. */
  confirmedCount: number
  changed: boolean
  relays: boolean[]
  /** Filtered landmarks in pixels, or null without a hand. */
  pointsPx: Point[] | null
}

/** What the rules measure before the latches: in palm widths, thumb first. */
export interface Measurement {
  thumb: number
  fingers: number[]
  palmWidth: number
}

export const RULES: Rules = DEFAULT_RULES as Rules
export const FINGERS: readonly string[] = FINGER_NAMES as string[]

/** The 21 landmark indices joined by the skeleton, as detector.py draws them. */
export const HAND_CONNECTIONS: ReadonlyArray<readonly [number, number]> = [
  [0, 1], [1, 2], [2, 3], [3, 4],
  [0, 5], [5, 6], [6, 7], [7, 8],
  [0, 9], [9, 10], [10, 11], [11, 12],
  [0, 13], [13, 14], [14, 15], [15, 16],
  [0, 17], [17, 18], [18, 19], [19, 20],
  [5, 9], [9, 13], [13, 17],
] // prettier-ignore

interface Stabilizer {
  confirmed: number
  candidate: number
  run: number
}

interface RawPipeline {
  width: number
  height: number
  stabilizer: Stabilizer
  reset(): void
  process(landmarks: Point[] | null, t: number): FrameResult
}

/** The engine's pipeline for one frame size: One Euro filter, hand-frame rules, confirmation. */
export class Pipeline {
  private readonly inner: RawPipeline

  constructor(width: number, height: number, rules: Rules = RULES) {
    this.inner = new GesturePipeline(width, height, rules) as unknown as RawPipeline
  }

  get width(): number {
    return this.inner.width
  }

  get height(): number {
    return this.inner.height
  }

  /** How many consecutive frames the current candidate count has held. */
  get runLength(): number {
    return this.inner.stabilizer.run
  }

  /** The count waiting to be confirmed, or -1. */
  get candidate(): number {
    return this.inner.stabilizer.candidate
  }

  reset(): void {
    this.inner.reset()
  }

  /** `landmarks` are normalised (0 to 1) or null for no hand; `t` is in seconds. */
  process(landmarks: Point[] | null, t: number): FrameResult {
    return this.inner.process(landmarks, t)
  }
}

/** The rules' measurements for landmarks in pixels, or null when the hand is too small to trust. */
export function measureHand(pointsPx: Point[], rules: Rules = RULES): Measurement | null {
  return measure(pointsPx, rules) as Measurement | null
}

/** The relay pattern a confirmed count selects: relays 1 to 4 for counts 1 to 4, all for 5. */
export function relaysForCount(count: number): boolean[] {
  return relayStatesForCount(count) as boolean[]
}
