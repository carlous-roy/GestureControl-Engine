import { memo } from 'react'
import type { BenchView, SourceMode, StageView } from '../hooks/useBench.ts'

interface Props {
  mode: SourceMode
  timings: BenchView['timings']
}

function ms(value: number | null, digits = 2): string {
  return value === null ? '' : value.toFixed(digits)
}

function Row({ name, stage, note }: { name: string; stage: StageView; note: string }) {
  return (
    <tr>
      <td>
        {name}
        <span className="small muted note">{note}</span>
      </td>
      <td className="num">{ms(stage.median)}</td>
      <td className="num">{ms(stage.p95)}</td>
      <td className="num">{ms(stage.last)}</td>
    </tr>
  )
}

/** Per-stage latencies over the last 120 frames, the way the engine's bench command reports them. */
const Timings = memo(function Timings({ mode, timings }: Props) {
  return (
    <section className="panel timings" aria-label="Timings">
      <div className="faceplate">
        <h2>Timings</h2>
        <span className="spacer" />
        <span className="small muted">
          {timings.fps === null ? 'frames' : `${timings.fps.toFixed(1)} fps`}
        </span>
      </div>
      <table>
        <thead>
          <tr>
            <th>stage</th>
            <th className="num">median ms</th>
            <th className="num">p95 ms</th>
            <th className="num">last ms</th>
          </tr>
        </thead>
        <tbody>
          {mode === 'camera' && (
            <Row name="landmarker" stage={timings.inference} note="MediaPipe, 21 points, GPU" />
          )}
          <Row
            name="filter, rules, confirm"
            stage={timings.pipeline}
            note="the engine's pipeline"
          />
          <Row name="draw" stage={timings.draw} note="viewport and scope" />
        </tbody>
      </table>
      <p className="panel-note">
        {mode === 'camera'
          ? 'Medians over the last 120 frames. The engine measures the same stages with gesturecontrol bench, plus camera capture and the serial write.'
          : 'The replay feeds landmarks straight from the file, so there is no detector stage here; switch to the webcam to time the landmarker.'}
      </p>
    </section>
  )
})

export default Timings
