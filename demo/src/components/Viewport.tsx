import { useEffect, useRef } from 'react'
import type { FrameView, ModelStatus, SourceMode } from '../hooks/useBench.ts'

interface Props {
  mode: SourceMode
  frame: FrameView | null
  model: ModelStatus
  cameraError: string | null
  stalled: boolean
  onBind: (canvas: HTMLCanvasElement | null, video: HTMLVideoElement | null) => void
  onRetryCamera: () => void
}

/** The camera or replay picture with the skeleton drawn over it, and the states of the source. */
export default function Viewport({
  mode,
  frame,
  model,
  cameraError,
  stalled,
  onBind,
  onRetryCamera,
}: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const videoRef = useRef<HTMLVideoElement>(null)

  useEffect(() => {
    onBind(canvasRef.current, videoRef.current)
    return () => onBind(null, null)
  }, [onBind])

  const width = frame?.width ?? 640
  const height = frame?.height ?? 480
  const waiting = mode === 'camera' && (model.phase !== 'ready' || cameraError !== null)

  return (
    <section className="panel viewport" aria-label="Viewport">
      <div className="faceplate">
        <h2>Viewport</h2>
        <span className="small muted num">
          {width}x{height}
        </span>
        <span className="spacer" />
        <span className="small muted">
          {mode === 'camera'
            ? 'frames never leave this browser'
            : 'landmarks from the fixture file'}
        </span>
      </div>
      <div className="screen" style={{ aspectRatio: `${width} / ${height}` }}>
        <canvas ref={canvasRef} width={width} height={height} aria-label="Hand tracking picture" />
        <video ref={videoRef} playsInline muted className="hidden-video" />
        {waiting && (
          <div className="screen-note" role="status">
            {cameraError !== null ? (
              <>
                <p className="error">{cameraError}</p>
                <button type="button" className="btn" onClick={onRetryCamera}>
                  Try again
                </button>
              </>
            ) : model.phase === 'error' ? (
              <p className="error">{model.message}</p>
            ) : (
              <>
                <div className="meter">
                  <div
                    className="meter-fill"
                    style={{ width: `${Math.round(model.progress * 100)}%` }}
                  />
                </div>
                <p>
                  {model.phase === 'downloading'
                    ? `Fetching the hand landmarker model, ${Math.round(model.progress * 100)}%: the same 7.5 MB bundle the engine pins, checked against its SHA-256`
                    : model.phase === 'starting'
                      ? 'Starting the landmarker on the GPU'
                      : 'Waiting for the camera'}
                </p>
              </>
            )}
          </div>
        )}
        {stalled && (
          <div className="screen-note stalled" role="status">
            <p>Host stalled: no frames are being processed</p>
          </div>
        )}
      </div>
    </section>
  )
}
