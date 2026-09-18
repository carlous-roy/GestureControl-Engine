# Browser demo

The page at https://gesture.roycarlous.com is built from this folder. It
runs MediaPipe Hands in the browser and shows a simulated relay panel.

The classifier is not a reimplementation: `src/gesture/` is a line-for-line
port of the engine's filter (`gesturecontrol/filters.py`), rules
(`gesturecontrol/rules.py`) and confirmation (`gesturecontrol/stabilizer.py`,
`gesturecontrol/pipeline.py`). Both read the same constants:

- `src/gesture/rules.json` is a copy of `gesturecontrol/rules.json`;
- `test/golden_vectors.json` is a copy of `fixtures/golden_vectors.json`,
  the landmark sequences with the outputs the pipeline must produce.

`npm test` (Vitest) replays every golden sequence through the JavaScript
pipeline and compares each frame's raw count, confirmed count, relay states,
finger latches and filtered coordinates with the file. The Python suite does
the same in `tests/test_golden_vectors.py`, and it also fails if either copy
in this folder drifts from its source. After changing the rules or the
scenarios in the engine, run from the repository root:

```bash
python scripts/export_golden_vectors.py
python scripts/sync_demo_fixtures.py
```

What the page does not have: the relay switching interval, the heartbeat
and the watchdog are hardware policies in the engine's controller and are
not simulated here.

## Commands

```bash
npm ci
npm test        # golden-vector parity test
npm run dev     # local development server
npm run build   # production build in dist/
```

The MediaPipe loader, WASM and model are fetched from jsDelivr at run time
(see `loadMediaPipe` in `src/App.jsx`); camera frames never leave the
browser.
