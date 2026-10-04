// The live source: MediaPipe's hand landmarker on the Tasks API, the same model bundle the engine
// pins (gesturecontrol/config.py), fetched once, checked against the same SHA-256 and handed to
// the runtime as bytes. Frames never leave the browser; the WASM runtime comes from a CDN at the
// package's own version and the model from Google's model store, as the engine downloads it.

import type { HandLandmarker } from '@mediapipe/tasks-vision'
import type { Point } from '../engine.ts'

/** Must match the installed @mediapipe/tasks-vision; a test checks package.json. */
export const TASKS_VISION_VERSION = '1.0.1'
export const WASM_URL = `https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@${TASKS_VISION_VERSION}/wasm`
export const MODEL_URL =
  'https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task'
export const MODEL_SHA256 = 'fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1'

/** The detector settings of config.py. */
export const DETECTION_CONFIDENCE = 0.7
export const TRACKING_CONFIDENCE = 0.6
export const FRAME_WIDTH = 640
export const FRAME_HEIGHT = 480

export class ModelError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'ModelError'
  }
}

export class CameraError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'CameraError'
  }
}

function hex(buffer: ArrayBuffer): string {
  return [...new Uint8Array(buffer)].map((b) => b.toString(16).padStart(2, '0')).join('')
}

/** Fetches the model bundle and verifies its digest; `onProgress` gets 0 to 1 as bytes arrive. */
export async function loadModel(
  onProgress?: (fraction: number) => void,
  url = MODEL_URL,
  expectedSha256 = MODEL_SHA256
): Promise<Uint8Array> {
  let response: Response
  try {
    response = await fetch(url)
  } catch (e) {
    throw new ModelError(`could not download the hand landmarker model: ${messageOf(e)}`)
  }
  if (!response.ok || response.body === null) {
    throw new ModelError(`could not download the hand landmarker model: HTTP ${response.status}`)
  }
  const total = Number(response.headers.get('content-length') ?? 0)
  const reader = response.body.getReader()
  const chunks: Uint8Array[] = []
  let received = 0
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    chunks.push(value)
    received += value.length
    if (onProgress && total > 0) onProgress(Math.min(1, received / total))
  }
  const bytes = new Uint8Array(received)
  let offset = 0
  for (const chunk of chunks) {
    bytes.set(chunk, offset)
    offset += chunk.length
  }
  const digest = hex(await crypto.subtle.digest('SHA-256', bytes))
  if (digest !== expectedSha256) {
    throw new ModelError(
      `the downloaded model does not match the pinned checksum (got ${digest.slice(0, 12)}, expected ${expectedSha256.slice(0, 12)})`
    )
  }
  onProgress?.(1)
  return bytes
}

/**
 * The landmarker in tracking mode with the engine's thresholds. The MediaPipe package is loaded
 * here, on demand, so the replay-only visit never downloads it.
 */
export async function createLandmarker(model: Uint8Array): Promise<HandLandmarker> {
  const { FilesetResolver, HandLandmarker } = await import('@mediapipe/tasks-vision')
  const vision = await FilesetResolver.forVisionTasks(WASM_URL)
  return HandLandmarker.createFromOptions(vision, {
    baseOptions: { modelAssetBuffer: model, delegate: 'GPU' },
    runningMode: 'VIDEO',
    numHands: 1,
    minHandDetectionConfidence: DETECTION_CONFIDENCE,
    minHandPresenceConfidence: TRACKING_CONFIDENCE,
    minTrackingConfidence: TRACKING_CONFIDENCE,
  })
}

const CAMERA_MESSAGES: Record<string, string> = {
  NotAllowedError:
    'Camera access was denied. Allow the camera for this site; on macOS also check System Settings, Privacy and Security, Camera, for your browser.',
  NotFoundError: 'No camera was found on this device.',
  NotReadableError:
    'The camera is in use by another app. Quit the video call or the camera app and try again.',
  OverconstrainedError: 'This camera cannot provide the 640x480 feed the bench asks for.',
  SecurityError: 'The browser blocked camera access on this page.',
  AbortError: 'Camera startup was interrupted. Try again.',
}

/** Opens the webcam on a video element at the engine's frame size. */
export async function openCamera(video: HTMLVideoElement): Promise<MediaStream> {
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new CameraError('This browser offers no camera access.')
  }
  let stream: MediaStream
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      video: { width: { ideal: FRAME_WIDTH }, height: { ideal: FRAME_HEIGHT }, facingMode: 'user' },
      audio: false,
    })
  } catch (e) {
    const name = e instanceof Error ? e.name : 'Error'
    throw new CameraError(`${CAMERA_MESSAGES[name] ?? 'Could not start the camera.'} [${name}]`)
  }
  video.srcObject = stream
  await video.play()
  return stream
}

export function closeCamera(video: HTMLVideoElement): void {
  const stream = video.srcObject
  if (typeof MediaStream !== 'undefined' && stream instanceof MediaStream) {
    for (const track of stream.getTracks()) track.stop()
  }
  video.srcObject = null
}

export interface Detection {
  landmarks: Point[] | null
  /** Wall-clock milliseconds the landmarker took. */
  inferenceMs: number
}

/** One frame through the landmarker: the first hand's 21 normalised points, or null. */
export function detect(
  landmarker: HandLandmarker,
  video: HTMLVideoElement,
  timestampMs: number
): Detection {
  const started = performance.now()
  const result = landmarker.detectForVideo(video, timestampMs)
  const inferenceMs = performance.now() - started
  const hand = result.landmarks[0]
  if (hand === undefined || hand.length !== 21) return { landmarks: null, inferenceMs }
  return { landmarks: hand.map((p): Point => [p.x, p.y]), inferenceMs }
}

function messageOf(e: unknown): string {
  return e instanceof Error ? e.message : String(e)
}
