import { memo } from 'react'
import { RULES } from '../engine.ts'
import Led from './Led.tsx'

interface Props {
  handPresent: boolean
  rawCount: number
  confirmedCount: number
  candidate: number
  runLength: number
}

const MAPPING = ['all off', 'relay 1', 'relay 2', 'relay 3', 'relay 4', 'all on']

/** The count that drives the relays, with the confirmation run under it. */
const Readout = memo(function Readout({
  handPresent,
  rawCount,
  confirmedCount,
  candidate,
  runLength,
}: Props) {
  const confirming = handPresent && rawCount >= 0 && candidate !== confirmedCount
  const run = Math.min(runLength, RULES.confirm_frames)
  return (
    <section className="panel readout" aria-label="Count">
      <div className="faceplate">
        <h2>Count</h2>
        <span className="spacer" />
        <Led on={handPresent} tone="green" label="Hand" />
        <span className="small muted">{handPresent ? 'hand' : 'no hand'}</span>
      </div>
      <div className="digits">
        <div className="digit num" aria-label="Confirmed count">
          {confirmedCount >= 0 ? confirmedCount : '-'}
        </div>
        <div className="digit-side">
          <span className="small muted">confirmed</span>
          <span className="mapping">
            {confirmedCount >= 0 ? MAPPING[confirmedCount] : 'nothing yet'}
          </span>
          <span className="small muted">raw this frame</span>
          <span className="num raw">{rawCount >= 0 ? rawCount : '-'}</span>
        </div>
      </div>
      <div className="confirm">
        <span className="small muted">
          {confirming
            ? `seeing ${candidate}: frame ${run} of ${RULES.confirm_frames}`
            : handPresent
              ? `holding ${confirmedCount >= 0 ? confirmedCount : 'nothing'}`
              : confirmedCount >= 0
                ? 'no hand: the relays hold'
                : 'show a hand'}
        </span>
        <div className="pips" aria-hidden="true">
          {Array.from({ length: RULES.confirm_frames }, (_, i) => (
            <span key={i} className={`pip ${confirming && i < run ? 'on' : ''}`} />
          ))}
        </div>
      </div>
    </section>
  )
})

export default Readout
