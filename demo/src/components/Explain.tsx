import { RELAY_PINS } from '../bench/board.ts'
import {
  HEARTBEAT_INTERVAL_S,
  HEARTBEAT_TIMEOUT_MS,
  MIN_SWITCH_INTERVAL_S,
} from '../bench/controller.ts'
import { RULES } from '../engine.ts'

const MAPPING = [
  ['0', 'fist', 'all off'],
  ['1', 'index finger', 'relay 1'],
  ['2', 'index and middle', 'relay 2'],
  ['3', 'three fingers', 'relay 3'],
  ['4', 'four fingers, thumb tucked', 'relay 4'],
  ['5', 'open hand', 'all on'],
]

/** What the bench is showing, in four cards. */
export default function Explain() {
  return (
    <section className="explain" aria-label="How it works">
      <div className="panel card">
        <div className="faceplate">
          <h2>The hand frame</h2>
        </div>
        <div className="card-body">
          <p>
            MediaPipe gives 21 landmarks per frame. Every measurement is taken in a frame attached
            to the hand: the up axis runs from the wrist to the middle-finger MCP, the side axis
            points to the thumb, and the palm width (index MCP to pinky MCP) is the unit of length.
            A finger is extended when its tip lies beyond its PIP joint along the up axis by more
            than {RULES.finger.raise_threshold} palm widths, the thumb when its tip lies beyond the
            index MCP along the side axis by more than {RULES.thumb.raise_threshold}. Because the
            frame turns with the hand and the measures are ratios, the count survives distance,
            resolution, mirroring, either hand and rotation in the image plane.
          </p>
        </div>
      </div>
      <div className="panel card">
        <div className="faceplate">
          <h2>Latches and confirmation</h2>
        </div>
        <div className="card-body">
          <p>
            Each finger latches with hysteresis: it releases only below{' '}
            {RULES.finger.lower_threshold} ({RULES.thumb.lower_threshold} for the thumb), so a tip
            hovering at the threshold does not flicker. A count reaches the relays only after{' '}
            {RULES.confirm_frames} consecutive frames with a hand present. Losing the hand resets
            that run but leaves the relays as they are; a fist turns everything off. The constants
            are the engine's rules.json, loaded as is.
          </p>
          <table className="mapping">
            <tbody>
              {MAPPING.map(([count, gesture, relays]) => (
                <tr key={count}>
                  <td className="num">{count}</td>
                  <td>{gesture}</td>
                  <td className="muted">{relays}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <div className="panel card">
        <div className="faceplate">
          <h2>Relay policies</h2>
        </div>
        <div className="card-body">
          <p>
            The host writes pin levels over USB with Firmata. The module is active-low, so a relay
            is on when its pin is LOW; a relay never switches twice within {MIN_SWITCH_INTERVAL_S}{' '}
            s; every serial write is guarded, with one reconnect that restores the relay states; and
            every exit path, Ctrl-C and SIGTERM included, de-energises the relays before the board
            is closed. The host sends a heartbeat every {HEARTBEAT_INTERVAL_S * 1000} ms; the
            watchdog sketch on the board releases every relay when none arrives for{' '}
            {HEARTBEAT_TIMEOUT_MS} ms, and the host restates them once it is back. The bench models
            the board and the sketch; the host side is the engine's controller, ported line by line.
          </p>
        </div>
      </div>
      <div className="panel card">
        <div className="faceplate">
          <h2>Wiring</h2>
        </div>
        <div className="card-body">
          <pre className="wiring mono">{`Arduino UNO            4-channel relay module
pin ${RELAY_PINS[0]}  ----------->  IN1   relay 1
pin ${RELAY_PINS[1]}  ----------->  IN2   relay 2
pin ${RELAY_PINS[2]}  ----------->  IN3   relay 3
pin ${RELAY_PINS[3]}  ----------->  IN4   relay 4
5V     ----------->  VCC
GND    ----------->  GND
USB    <----------   host: Firmata at 57600 baud`}</pre>
          <p className="small muted">
            The relay contacts switch the appliance side; nothing on the bench models mains. See the
            README's safety section for what the watchdog can and cannot cover.
          </p>
        </div>
      </div>
    </section>
  )
}
