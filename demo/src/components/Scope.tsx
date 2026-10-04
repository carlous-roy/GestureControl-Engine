import { useEffect, useRef } from 'react'
import { RULES } from '../engine.ts'

interface Props {
  onBind: (canvas: HTMLCanvasElement | null) => void
}

/** The One Euro filter at work: the index fingertip's x before and after it, over the last seconds. */
export default function Scope({ onBind }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  useEffect(() => {
    onBind(canvasRef.current)
    return () => onBind(null)
  }, [onBind])
  const f = RULES.filter
  return (
    <section className="panel scope" aria-label="Filter trace">
      <div className="faceplate">
        <h2>One Euro filter</h2>
        <span className="small muted">index fingertip, x in px</span>
        <span className="spacer" />
        <span className="small legend">
          <i className="trace-raw" /> detector <i className="trace-filtered" /> filtered
        </span>
      </div>
      <div className="scope-screen">
        <canvas ref={canvasRef} aria-label="Raw and filtered coordinate over time" />
      </div>
      <p className="panel-note">
        Cutoff {f.min_cutoff_hz} Hz at rest, rising with speed (beta {f.beta}, derivative cutoff{' '}
        {f.derivative_cutoff_hz} Hz): jitter is smoothed while the hand is still and a fast move is
        followed with little lag. Casiez, Roussel and Vogel, CHI 2012.
      </p>
    </section>
  )
}
