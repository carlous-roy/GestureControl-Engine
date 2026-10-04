// The bench's driver: one pipeline, one host, one source (the golden replay or the webcam), run
// on animation frames. Each frame goes through the port of the engine, then to the host as the
// control loop would hand it over; the viewport and the scope are drawn straight onto their
// canvases from here, and a snapshot of everything else is published for the panels.

import { useCallback, useEffect, useRef, useState } from 'react'
import type { HandLandmarker } from '@mediapipe/tasks-vision'
import {
  Pipeline,
  RULES,
  measureHand,
  type FrameResult,
  type Measurement,
  type Point,
} from '../engine.ts'
import { Host, type HostState } from '../bench/host.ts'
import { BenchLog, type LogLine } from '../bench/log.ts'
import { FrameRate, RollingStats } from '../bench/timings.ts'
import {
  ReplayPlayer,
  SEQUENCES,
  checkAllParity,
  type ExpectedFrame,
  type ParityResult,
} from '../sources/replay.ts'
import {
  closeCamera,
  createLandmarker,
  detect,
  loadModel,
  openCamera,
  FRAME_HEIGHT,
  FRAME_WIDTH,
} from '../sources/camera.ts'
import { drawScope, drawViewport, type TraceSample } from '../lib/draw.ts'

export type SourceMode = 'replay' | 'camera'

export interface ModelStatus {
  phase: 'idle' | 'downloading' | 'starting' | 'ready' | 'error'
  progress: number
  message: string | null
}

export interface FrameView {
  seq: number
  width: number
  height: number
  landmarks: Point[] | null
  result: FrameResult
  measurement: Measurement | null
  runLength: number
  candidate: number
  /** Replay only: where in which sequence, and whether this frame matched the file. */
  replay: {
    name: string
    index: number
    frames: number
    expected: ExpectedFrame
    ok: boolean
  } | null
}

export interface StageView {
  median: number | null
  p95: number | null
  last: number | null
}

export interface BenchView {
  /** Bench clock in milliseconds, for countdowns. */
  now: number
  mode: SourceMode
  model: ModelStatus
  cameraError: string | null
  frame: FrameView | null
  host: {
    state: HostState
    exitCode: number | null
    linkUp: boolean
    powered: boolean
    relays: boolean[]
    desired: boolean[]
    /** Seconds each relay still has to wait before it may switch. */
    holds: number[]
    levels: number[]
    activeLow: boolean
    tripped: boolean
    armed: boolean
    sinceHeartbeatMs: number
    timeoutMs: number
    stallRemainingS: number
    lost: boolean
  }
  log: LogLine[]
  timings: { inference: StageView; pipeline: StageView; draw: StageView; fps: number | null }
  replay: {
    sequenceIndex: number
    frameIndex: number
    playing: boolean
    continuous: boolean
    speed: number
    parity: ParityResult[]
  }
}

const TRACE_SAMPLES = 240
const MAX_FRAME_MS = 100

interface Session {
  nowS: number
  log: BenchLog
  host: Host
  pipeline: Pipeline
  pipelineSequence: string | null
  player: ReplayPlayer
  parity: ParityResult[]
  mode: SourceMode
  frame: FrameView | null
  frameSeq: number
  traces: TraceSample[]
  inference: RollingStats
  pipelineMs: RollingStats
  draw: RollingStats
  frameRate: FrameRate
  landmarker: HandLandmarker | null
  model: ModelStatus
  cameraError: string | null
  video: HTMLVideoElement | null
  viewport: HTMLCanvasElement | null
  scope: HTMLCanvasElement | null
  lastVideoTime: number
  lastTickMs: number | null
}

function createSession(): Session {
  const session: Partial<Session> = { nowS: performance.now() / 1000 }
  const log = new BenchLog(() => (session.nowS ?? 0) * 1000)
  const host = new Host(() => session.nowS ?? 0, log)
  const first = SEQUENCES[0]
  Object.assign(session, {
    log,
    host,
    pipeline: new Pipeline(first?.width ?? FRAME_WIDTH, first?.height ?? FRAME_HEIGHT),
    pipelineSequence: first?.name ?? null,
    player: new ReplayPlayer(),
    parity: checkAllParity(),
    mode: 'replay',
    frame: null,
    frameSeq: 0,
    traces: [],
    inference: new RollingStats(),
    pipelineMs: new RollingStats(),
    draw: new RollingStats(),
    frameRate: new FrameRate(),
    landmarker: null,
    model: { phase: 'idle', progress: 0, message: null },
    cameraError: null,
    video: null,
    viewport: null,
    scope: null,
    lastVideoTime: -1,
    lastTickMs: null,
  })
  host.start()
  return session as Session
}

function stage(stats: RollingStats): StageView {
  return { median: stats.median, p95: stats.p95, last: stats.last }
}

function view(session: Session): BenchView {
  const { host } = session
  const nowMs = session.nowS * 1000
  const controller = host.controller
  return {
    now: nowMs,
    mode: session.mode,
    model: session.model,
    cameraError: session.cameraError,
    frame: session.frame,
    host: {
      state: host.state,
      exitCode: host.exitCode,
      linkUp: host.link.up,
      powered: host.board.powered,
      relays: controller.states,
      desired: controller.desired,
      holds: [0, 1, 2, 3].map((i) => controller.holdRemaining(i)),
      levels: [...host.board.levels],
      activeLow: host.board.activeLow,
      tripped: host.board.tripped,
      armed: host.board.armed,
      sinceHeartbeatMs: host.board.sinceHeartbeat(nowMs),
      timeoutMs: host.board.timeoutMs,
      stallRemainingS: host.state === 'stalled' ? Math.max(0, host.stalledUntil - session.nowS) : 0,
      lost: controller.lost,
    },
    log: session.log.snapshot(),
    timings: {
      inference: stage(session.inference),
      pipeline: stage(session.pipelineMs),
      draw: stage(session.draw),
      fps: session.frameRate.fps,
    },
    replay: {
      sequenceIndex: session.player.sequenceIndex,
      frameIndex: session.player.frameIndex,
      playing: session.player.playing,
      continuous: session.player.continuous,
      speed: session.player.speed,
      parity: session.parity,
    },
  }
}

const bits = (flags: readonly boolean[]): string => flags.map((f) => (f ? '1' : '0')).join('')

function frameMatches(result: FrameResult, want: ExpectedFrame): boolean {
  const fingers = result.fingerStates === null ? null : bits(result.fingerStates)
  return (
    result.handPresent === want.hand &&
    result.rawCount === want.raw &&
    result.confirmedCount === want.confirmed &&
    result.changed === want.changed &&
    bits(result.relays) === want.relays &&
    fingers === want.fingers
  )
}

/** One frame through the pipeline, the host, the traces and the viewport. */
function processFrame(
  session: Session,
  landmarks: Point[] | null,
  t: number,
  replay: { name: string; index: number; frames: number; expected: ExpectedFrame } | null,
  nowMs: number
): void {
  const started = performance.now()
  const result = session.pipeline.process(landmarks, t)
  session.pipelineMs.push(performance.now() - started)
  const measurement = result.pointsPx === null ? null : measureHand(result.pointsPx)
  session.host.onFrame(result)

  // The scope runs on the bench clock, so the trace carries on across sequences and pauses.
  const { width, height } = session.pipeline
  const raw = landmarks?.[8]
  const filtered = result.pointsPx?.[8]
  session.traces.push({
    t: nowMs / 1000,
    raw: raw === undefined ? null : [raw[0] * width, raw[1] * height],
    filtered: filtered === undefined ? null : filtered,
  })
  if (session.traces.length > TRACE_SAMPLES) session.traces.shift()

  session.frame = {
    seq: ++session.frameSeq,
    width,
    height,
    landmarks,
    result,
    measurement,
    runLength: session.pipeline.runLength,
    candidate: session.pipeline.candidate,
    replay: replay === null ? null : { ...replay, ok: frameMatches(result, replay.expected) },
  }
  session.frameRate.mark(nowMs)

  const drawStarted = performance.now()
  if (session.viewport !== null) {
    drawViewport(session.viewport, {
      width,
      height,
      video: session.mode === 'camera' ? session.video : null,
      landmarks,
      result,
      label: replay === null ? 'WEBCAM' : `REPLAY ${replay.name}`,
      detail: replay === null ? `${width}x${height}` : `frame ${replay.index + 1}/${replay.frames}`,
      mirrored: session.mode === 'camera',
    })
  }
  if (session.scope !== null) drawScope(session.scope, session.traces, nowMs / 1000)
  session.draw.push(performance.now() - drawStarted)
}

export interface Bench {
  view: BenchView
  setMode: (mode: SourceMode) => void
  /** Elements the loop draws on and reads from. */
  bind: (refs: {
    viewport: HTMLCanvasElement | null
    scope: HTMLCanvasElement | null
    video: HTMLVideoElement | null
  }) => void
  replay: {
    select: (index: number) => void
    play: (on: boolean) => void
    step: () => void
    setContinuous: (on: boolean) => void
    setSpeed: (speed: number) => void
  }
  faults: {
    stall: (seconds: number) => void
    pullCable: () => void
    plugCable: () => void
    cutPower: () => void
    restorePower: () => void
    interrupt: () => void
    restart: () => void
  }
  clearLog: () => void
}

export function useBench(): Bench {
  const [session] = useState(createSession)
  const [current, setCurrent] = useState<BenchView>(() => view(session))
  const modeRef = useRef<SourceMode>('replay')

  const publish = useCallback(() => setCurrent(view(session)), [session])

  // The animation loop: the host's clock, the board's loop, and the frames the source has ready.
  useEffect(() => {
    let frame = requestAnimationFrame(function tick(nowMs: number) {
      const elapsed =
        session.lastTickMs === null ? 0 : Math.min(MAX_FRAME_MS, nowMs - session.lastTickMs)
      session.lastTickMs = nowMs
      session.nowS = nowMs / 1000
      session.host.tick()
      const frozen = session.host.state === 'stalled'

      if (session.mode === 'replay') {
        for (const due of session.player.advance(elapsed)) {
          if (frozen) continue
          if (session.pipelineSequence !== due.sequence.name) {
            session.pipeline = new Pipeline(due.sequence.width, due.sequence.height)
            session.pipelineSequence = due.sequence.name
            session.traces.push({ t: nowMs / 1000, raw: null, filtered: null })
          }
          processFrame(
            session,
            due.landmarks,
            due.t,
            {
              name: due.sequence.name,
              index: due.index,
              frames: due.sequence.frames.length,
              expected: due.expected,
            },
            nowMs
          )
        }
      } else if (
        session.landmarker !== null &&
        session.video !== null &&
        session.video.readyState >= 2 &&
        session.video.currentTime !== session.lastVideoTime
      ) {
        session.lastVideoTime = session.video.currentTime
        if (!frozen) {
          const width = session.video.videoWidth || FRAME_WIDTH
          const height = session.video.videoHeight || FRAME_HEIGHT
          if (session.pipeline.width !== width || session.pipeline.height !== height) {
            session.pipeline = new Pipeline(width, height)
            session.pipelineSequence = null
            session.traces = []
          }
          const detection = detect(session.landmarker, session.video, nowMs)
          session.inference.push(detection.inferenceMs)
          processFrame(session, detection.landmarks, nowMs / 1000, null, nowMs)
        }
      }
      publish()
      frame = requestAnimationFrame(tick)
    })
    return () => cancelAnimationFrame(frame)
  }, [session, publish])

  const stopCamera = useCallback(() => {
    if (session.video !== null) closeCamera(session.video)
    session.lastVideoTime = -1
  }, [session])

  const startCamera = useCallback(async () => {
    session.cameraError = null
    try {
      // The camera first, so a visitor without one is told at once rather than after a download.
      if (session.video === null) return
      await openCamera(session.video)
      if (modeRef.current !== 'camera') {
        closeCamera(session.video)
        return
      }
      if (session.landmarker === null) {
        session.model = { phase: 'downloading', progress: 0, message: null }
        publish()
        const bytes = await loadModel((fraction) => {
          session.model = { phase: 'downloading', progress: fraction, message: null }
        })
        if (modeRef.current !== 'camera') return
        session.model = { phase: 'starting', progress: 1, message: null }
        publish()
        session.landmarker = await createLandmarker(bytes)
        session.model = { phase: 'ready', progress: 1, message: null }
        session.log.info('bench', 'Hand landmarker ready: model checksum verified, GPU delegate')
      }
      if (modeRef.current !== 'camera') return
      session.pipeline = new Pipeline(FRAME_WIDTH, FRAME_HEIGHT)
      session.pipelineSequence = null
      session.traces = []
      session.inference.clear()
      session.frameRate.clear()
      session.log.info('bench', 'Webcam open; frames stay in this browser')
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e)
      if (e instanceof Error && e.name === 'ModelError') {
        session.model = { phase: 'error', progress: 0, message }
      } else {
        session.cameraError = message
      }
      session.log.error('bench', message)
    }
    publish()
  }, [session, publish])

  const setMode = useCallback(
    (mode: SourceMode) => {
      if (modeRef.current === mode) return
      modeRef.current = mode
      session.mode = mode
      session.frame = null
      session.traces = []
      session.frameRate.clear()
      if (mode === 'camera') {
        session.player.playing = false
        void startCamera()
      } else {
        stopCamera()
        const sequence = session.player.sequence
        session.pipeline = new Pipeline(sequence.width, sequence.height)
        session.pipelineSequence = sequence.name
        session.player.playing = true
      }
      publish()
    },
    [session, publish, startCamera, stopCamera]
  )

  useEffect(() => () => stopCamera(), [stopCamera])

  const bind = useCallback<Bench['bind']>(
    ({ viewport, scope, video }) => {
      session.viewport = viewport
      session.scope = scope
      session.video = video
    },
    [session]
  )

  return {
    view: current,
    setMode,
    bind,
    replay: {
      select: (index) => {
        session.player.select(index)
        session.pipeline = new Pipeline(
          session.player.sequence.width,
          session.player.sequence.height
        )
        session.pipelineSequence = session.player.sequence.name
        session.traces = []
        publish()
      },
      play: (on) => {
        session.player.playing = on
        publish()
      },
      step: () => {
        if (session.mode !== 'replay' || session.host.state === 'stalled') return
        const due = session.player.step()
        if (session.pipelineSequence !== due.sequence.name) {
          session.pipeline = new Pipeline(due.sequence.width, due.sequence.height)
          session.pipelineSequence = due.sequence.name
          session.traces.push({ t: performance.now() / 1000, raw: null, filtered: null })
        }
        processFrame(
          session,
          due.landmarks,
          due.t,
          {
            name: due.sequence.name,
            index: due.index,
            frames: due.sequence.frames.length,
            expected: due.expected,
          },
          performance.now()
        )
        publish()
      },
      setContinuous: (on) => {
        session.player.continuous = on
        publish()
      },
      setSpeed: (speed) => {
        session.player.speed = speed
        publish()
      },
    },
    faults: {
      stall: (seconds) => {
        session.host.stall(seconds)
        publish()
      },
      pullCable: () => {
        session.host.pullCable()
        publish()
      },
      plugCable: () => {
        session.host.plugCable()
        publish()
      },
      cutPower: () => {
        session.host.cutPower()
        publish()
      },
      restorePower: () => {
        session.host.restorePower()
        publish()
      },
      interrupt: () => {
        session.host.interrupt()
        publish()
      },
      restart: () => {
        session.host.restart()
        publish()
      },
    },
    clearLog: () => {
      session.log.clear()
      publish()
    },
  }
}

export { RULES }
