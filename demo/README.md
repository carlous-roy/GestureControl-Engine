# The bench

The page at https://gesture.roycarlous.com is built from this folder: the
engine's filter, rules and confirmation running in the browser on the golden
sequences or a webcam, with the relay side on the bench next to them.

What is real and what is modelled:

- `src/gesture/` is a line-for-line port of the engine's One Euro filter
  (`gesturecontrol/filters.py`), finger rules (`rules.py`) and confirmation
  (`stabilizer.py`, `pipeline.py`). It reads `src/gesture/rules.json`, a copy
  of `gesturecontrol/rules.json`, and `test/golden.test.js` replays every
  sequence of `test/golden_vectors.json` (a copy of
  `fixtures/golden_vectors.json`) through it, comparing each frame's raw
  count, confirmed count, relay states, finger latches and filtered
  coordinates with the file. The Python suite does the same and fails if
  either copy drifts from its source; after changing the rules or the
  scenarios, run `python scripts/export_golden_vectors.py` and
  `python scripts/sync_demo_fixtures.py` from the repository root. The page
  checks the same parity as it plays and shows it on the deck.
- `src/bench/controller.ts` is a port of `gesturecontrol/controller.py`:
  active-low polarity, the switching interval per relay, guarded writes with
  one reconnect, the heartbeat that restates the relays after a gap, and a
  cleanup that never raises. `src/bench/board.ts` models the Arduino running
  `firmware/RelayWatchdogFirmata.ino`: safe levels at reset, the armed and
  tripped states, writes ignored while tripped. `src/bench/host.ts` is the
  control loop of `app.py` with its heartbeat thread and exit codes, plus the
  faults the page can inject: a stalled host, a pulled cable, a power cut,
  Ctrl-C, a restart.
- With the webcam, MediaPipe's hand landmarker runs in the browser through
  `@mediapipe/tasks-vision`, on the model bundle the engine pins in
  `gesturecontrol/config.py`, fetched from the same URL and checked against
  the same SHA-256 before it is handed to the runtime. The WASM runtime comes
  from jsDelivr at the installed package's version. Frames never leave the
  browser. The replay needs none of this; the MediaPipe code is loaded only
  when the webcam is chosen.

What the page does not have: the camera's exposure and transfer delay, the
serial link's own timing, and the mains side of the relays.

## Layout

```
src/gesture/      the JavaScript port (kept in the Python's layout; not formatted by Prettier)
src/engine.ts     the typed face of the port
src/bench/        board, controller, host, log, timings
src/sources/      the golden replay and the webcam
src/hooks/        useBench, the frame loop
src/lib/draw.ts   the viewport and the scope
src/components/   the panels
test/             the parity test and the golden vectors
```

## Commands

```bash
npm ci
npm test             # parity test, bench models, components
npm run lint && npm run format:check && npm run typecheck
npm run dev          # local development server
npm run build        # production build in dist/
```

The page deploys from this folder with Vite's defaults; `vercel.json`
carries the response headers.
