// Canvas drawing for the viewport and the scope. Both are drawn from the frame loop, outside
// React, because they change on every frame.

import { HAND_CONNECTIONS, type FrameResult, type Point } from '../engine.ts'

const AMBER = '#f5a524'
const GREEN = '#8be37d'
const RAW = 'rgba(242, 237, 228, 0.35)'
const FRAME_UP = 'rgba(94, 200, 220, 0.9)'
const FRAME_WIDTH = 'rgba(94, 200, 220, 0.55)'
const MONO = "500 12px 'Space Mono', ui-monospace, monospace"

export interface ViewportFrame {
  width: number
  height: number
  /** The live video when the source is the webcam; null for a replay. */
  video: HTMLVideoElement | null
  landmarks: Point[] | null
  result: FrameResult
  label: string
  detail: string
  mirrored: boolean
}

/** The fingertip landmark of each latch, thumb first. */
const TIPS = [4, 8, 12, 16, 20]

export function drawViewport(canvas: HTMLCanvasElement, frame: ViewportFrame): void {
  const { width, height } = frame
  if (canvas.width !== width || canvas.height !== height) {
    canvas.width = width
    canvas.height = height
  }
  const ctx = canvas.getContext('2d')
  if (ctx === null) return
  const mx = (x: number) => (frame.mirrored ? width - x : x)

  if (frame.video !== null && frame.video.readyState >= 2) {
    ctx.save()
    if (frame.mirrored) {
      ctx.translate(width, 0)
      ctx.scale(-1, 1)
    }
    ctx.drawImage(frame.video, 0, 0, width, height)
    ctx.restore()
    ctx.fillStyle = 'rgba(20, 18, 16, 0.18)'
    ctx.fillRect(0, 0, width, height)
  } else {
    ctx.fillStyle = '#141210'
    ctx.fillRect(0, 0, width, height)
    ctx.strokeStyle = 'rgba(242, 237, 228, 0.05)'
    ctx.lineWidth = 1
    ctx.beginPath()
    for (let x = 40; x < width; x += 40) {
      ctx.moveTo(x + 0.5, 0)
      ctx.lineTo(x + 0.5, height)
    }
    for (let y = 40; y < height; y += 40) {
      ctx.moveTo(0, y + 0.5)
      ctx.lineTo(width, y + 0.5)
    }
    ctx.stroke()
  }

  // Raw landmarks: what the detector saw, before the filter.
  if (frame.landmarks !== null) {
    ctx.fillStyle = RAW
    for (const [nx, ny] of frame.landmarks) {
      ctx.beginPath()
      ctx.arc(mx(nx * width), ny * height, 2.2, 0, Math.PI * 2)
      ctx.fill()
    }
  }

  const points = frame.result.pointsPx
  if (points !== null) {
    // The hand frame the rules measure in: wrist to middle MCP is up, index MCP to pinky MCP is
    // the palm width.
    const wrist = points[0]
    const middle = points[9]
    const index = points[5]
    const pinky = points[17]
    if (wrist && middle && index && pinky) {
      ctx.strokeStyle = FRAME_UP
      ctx.lineWidth = 1.5
      ctx.setLineDash([])
      ctx.beginPath()
      ctx.moveTo(mx(wrist[0]), wrist[1])
      ctx.lineTo(mx(middle[0]), middle[1])
      ctx.stroke()
      ctx.strokeStyle = FRAME_WIDTH
      ctx.setLineDash([3, 3])
      ctx.beginPath()
      ctx.moveTo(mx(index[0]), index[1])
      ctx.lineTo(mx(pinky[0]), pinky[1])
      ctx.stroke()
      ctx.setLineDash([])
    }

    ctx.strokeStyle = AMBER
    ctx.lineWidth = 1.6
    ctx.beginPath()
    for (const [a, b] of HAND_CONNECTIONS) {
      const pa = points[a]
      const pb = points[b]
      if (!pa || !pb) continue
      ctx.moveTo(mx(pa[0]), pa[1])
      ctx.lineTo(mx(pb[0]), pb[1])
    }
    ctx.stroke()

    const states = frame.result.fingerStates
    points.forEach(([x, y], i) => {
      const tip = TIPS.indexOf(i)
      const extended = tip >= 0 && states !== null && states[tip] === true
      ctx.fillStyle = extended ? GREEN : AMBER
      ctx.beginPath()
      ctx.arc(mx(x), y, extended ? 4.5 : 3, 0, Math.PI * 2)
      ctx.fill()
    })
  }

  // The source and the frame counter, as an overlay in the corner.
  ctx.font = MONO
  ctx.textBaseline = 'middle'
  const label = `${frame.label}  ${frame.detail}`
  const w = ctx.measureText(label).width + 16
  ctx.fillStyle = 'rgba(20, 18, 16, 0.75)'
  ctx.fillRect(8, 8, w, 22)
  ctx.fillStyle = '#f2ede4'
  ctx.fillText(label, 16, 19)
  if (!frame.result.handPresent) {
    const text = 'NO HAND'
    const tw = ctx.measureText(text).width + 16
    ctx.fillStyle = 'rgba(20, 18, 16, 0.75)'
    ctx.fillRect(width - tw - 8, 8, tw, 22)
    ctx.fillStyle = 'rgba(242, 237, 228, 0.6)'
    ctx.fillText(text, width - tw, 19)
  }
}

export interface TraceSample {
  t: number
  raw: Point | null
  filtered: Point | null
}

const SCOPE_WINDOW_S = 4

/** The index fingertip's x over the last seconds: the detector's value and the filter's. */
export function drawScope(canvas: HTMLCanvasElement, samples: TraceSample[], tNow: number): void {
  const dpr = window.devicePixelRatio || 1
  const cssWidth = canvas.clientWidth || 300
  const cssHeight = canvas.clientHeight || 120
  const width = Math.round(cssWidth * dpr)
  const height = Math.round(cssHeight * dpr)
  if (canvas.width !== width || canvas.height !== height) {
    canvas.width = width
    canvas.height = height
  }
  const ctx = canvas.getContext('2d')
  if (ctx === null) return
  ctx.save()
  ctx.scale(dpr, dpr)
  ctx.clearRect(0, 0, cssWidth, cssHeight)

  const left = 36
  const top = 8
  const plotW = cssWidth - left - 8
  const plotH = cssHeight - top - 18
  const tStart = tNow - SCOPE_WINDOW_S
  const visible = samples.filter((s) => s.t >= tStart)

  let min = Infinity
  let max = -Infinity
  for (const s of visible) {
    for (const p of [s.raw, s.filtered]) {
      if (p === null) continue
      min = Math.min(min, p[0])
      max = Math.max(max, p[0])
    }
  }
  if (!Number.isFinite(min)) {
    min = 0
    max = 1
  }
  const pad = Math.max(8, (max - min) * 0.15)
  min -= pad
  max += pad

  const x = (t: number) => left + ((t - tStart) / SCOPE_WINDOW_S) * plotW
  const y = (v: number) => top + plotH - ((v - min) / (max - min)) * plotH

  // Grid and axis labels.
  ctx.strokeStyle = 'rgba(242, 237, 228, 0.08)'
  ctx.lineWidth = 1
  ctx.font = "500 10px 'Space Mono', ui-monospace, monospace"
  ctx.fillStyle = 'rgba(242, 237, 228, 0.45)'
  ctx.textBaseline = 'middle'
  for (let i = 0; i <= 4; i++) {
    const v = min + ((max - min) * i) / 4
    const yy = Math.round(y(v)) + 0.5
    ctx.beginPath()
    ctx.moveTo(left, yy)
    ctx.lineTo(left + plotW, yy)
    ctx.stroke()
    ctx.textAlign = 'right'
    ctx.fillText(String(Math.round(v)), left - 4, yy)
  }
  ctx.textAlign = 'center'
  ctx.textBaseline = 'top'
  for (let s = 0; s <= SCOPE_WINDOW_S; s++) {
    const xx = Math.round(x(tStart + s)) + 0.5
    ctx.beginPath()
    ctx.moveTo(xx, top)
    ctx.lineTo(xx, top + plotH)
    ctx.stroke()
    ctx.fillText(`-${SCOPE_WINDOW_S - s}s`, xx, top + plotH + 4)
  }

  const trace = (pick: (s: TraceSample) => Point | null, color: string, dash: number[]) => {
    ctx.strokeStyle = color
    ctx.lineWidth = dash.length ? 1 : 1.8
    ctx.setLineDash(dash)
    ctx.beginPath()
    let pen = false
    for (const s of visible) {
      const p = pick(s)
      if (p === null) {
        pen = false
        continue
      }
      if (pen) ctx.lineTo(x(s.t), y(p[0]))
      else ctx.moveTo(x(s.t), y(p[0]))
      pen = true
    }
    ctx.stroke()
    ctx.setLineDash([])
  }
  trace((s) => s.raw, RAW, [3, 3])
  trace((s) => s.filtered, AMBER, [])
  ctx.restore()
}
