import { RELAY_PINS } from '../bench/board.ts'
import {
  HEARTBEAT_INTERVAL_S,
  HEARTBEAT_TIMEOUT_MS,
  MIN_SWITCH_INTERVAL_S,
} from '../bench/controller.ts'
import { REPO_URL } from '../edition.ts'
import { RULES } from '../engine.ts'

export default function Footer() {
  const f = RULES.filter
  return (
    <footer className="foot">
      <p>
        Nothing on this page talks to a server. The filter, the rules and the confirmation are the
        engine's own code path, ported to JavaScript and checked against the same golden vectors;
        the relay controller is ported from the Python; the Arduino and the watchdog sketch are
        modelled. With the webcam, MediaPipe's hand landmarker runs in your browser on the model
        bundle the engine pins, and no frame leaves it.
      </p>
      <p className="constants mono small">
        one euro {f.min_cutoff_hz} Hz, beta {f.beta}, d {f.derivative_cutoff_hz} Hz · fingers{' '}
        {RULES.finger.raise_threshold}/{RULES.finger.lower_threshold} · thumb{' '}
        {RULES.thumb.raise_threshold}/{RULES.thumb.lower_threshold} · confirm {RULES.confirm_frames}{' '}
        frames · switch {MIN_SWITCH_INTERVAL_S} s · heartbeat {HEARTBEAT_INTERVAL_S * 1000} ms ·
        watchdog {HEARTBEAT_TIMEOUT_MS} ms · pins {RELAY_PINS.join(', ')} active-low ·{' '}
        <a href={REPO_URL} target="_blank" rel="noopener noreferrer">
          carlous-roy/GestureControl-Engine
        </a>
      </p>
    </footer>
  )
}
