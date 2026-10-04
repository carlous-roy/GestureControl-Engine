import { memo, useEffect, useRef, useState } from 'react'
import type { LogLine } from '../bench/log.ts'

interface Props {
  lines: LogLine[]
  onClear: () => void
}

function clock(ms: number): string {
  const s = Math.floor(ms / 1000)
  const mm = String(Math.floor(s / 60) % 60).padStart(2, '0')
  const ss = String(s % 60).padStart(2, '0')
  const frac = String(Math.floor(ms % 1000)).padStart(3, '0')
  return `${mm}:${ss}.${frac}`
}

/** The host's log lines and the board's serial strings, followed as they arrive. */
export default function LogPane({ lines, onClear }: Props) {
  const [follow, setFollow] = useState(true)
  const bodyRef = useRef<HTMLDivElement>(null)
  const lastSeq = lines[lines.length - 1]?.seq

  useEffect(() => {
    const el = bodyRef.current
    if (follow && el) el.scrollTop = el.scrollHeight
  }, [lastSeq, follow])

  return (
    <section className="panel log" aria-label="Log">
      <div className="faceplate">
        <h2>Log</h2>
        <span className="small muted num">{lines.length}</span>
        <span className="spacer" />
        <span className="small muted legend">
          <i className="src-host" /> host <i className="src-board" /> board{' '}
          <i className="src-bench" /> bench
        </span>
        <button
          type="button"
          className={`btn btn-sm ${follow ? 'selected' : ''}`}
          aria-pressed={follow}
          onClick={() => setFollow(!follow)}
        >
          Follow
        </button>
        <button type="button" className="btn btn-sm btn-ghost" onClick={onClear}>
          Clear
        </button>
      </div>
      <div
        className="log-body mono"
        ref={bodyRef}
        onScroll={(e) => {
          const el = e.currentTarget
          const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 8
          if (!atBottom && follow) setFollow(false)
        }}
      >
        {lines.map((line) => (
          <Line key={line.seq} line={line} />
        ))}
        {lines.length === 0 && <p className="small muted">Nothing logged yet.</p>}
      </div>
    </section>
  )
}

const Line = memo(function Line({ line }: { line: LogLine }) {
  return (
    <div className={`line level-${line.level} src-${line.source}`}>
      <span className="t">{clock(line.t)}</span>
      <span className="lvl">{line.level.padEnd(5)}</span>
      <span className="src">{line.source}</span>
      <span className="msg">{line.message}</span>
    </div>
  )
})
