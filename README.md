# GestureControl

<p>
  <a href="https://gesture.roycarlous.com"><img src="https://img.shields.io/badge/Browser_demo-gesture.roycarlous.com-22C55E?style=flat-square" alt="Browser demo" /></a>
  <img src="https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3.10+" />
  <img src="https://img.shields.io/badge/OpenCV-5C3EE8?style=flat-square&logo=opencv&logoColor=white" alt="OpenCV" />
  <img src="https://img.shields.io/badge/MediaPipe-0097A7?style=flat-square&logo=google&logoColor=white" alt="MediaPipe" />
  <img src="https://img.shields.io/badge/Arduino-00979D?style=flat-square&logo=arduino&logoColor=white" alt="Arduino" />
</p>

A control loop from a webcam to a 4-channel relay module. MediaPipe Hands
finds 21 hand landmarks in each frame, a rule-based classifier counts the
extended fingers, and the count switches relays on an Arduino UNO over
Firmata.

```
Webcam --> MediaPipe Hands --> One Euro filter --> finger rules --> 3-frame confirmation --> relays
```

MediaPipe Hands is a two-stage pipeline: a palm detector finds the hand
region and a landmark model regresses 21 points inside it. In tracking mode
the palm detector runs only when no hand is being tracked; the landmark
model runs on every frame.

Landmark coordinates pass through a One Euro filter (Casiez, Roussel and
Vogel, CHI 2012), which smooths jitter at rest and follows fast motion with
little lag.

Every measurement is taken in the hand's own frame: the up axis runs from
the wrist to the middle-finger MCP, the side axis points to the thumb, and
palm width is the unit of length. A finger is extended when its tip lies
beyond its PIP joint along the up axis by more than 0.35 palm widths; the
thumb is extended when its tip lies beyond the index MCP along the side
axis by more than 0.40 palm widths. Each finger latches with hysteresis (it
lowers below 0.25 and 0.30 respectively). Because the frame rotates with
the hand and the measures are ratios, the count does not change with camera
distance, resolution, mirroring, left or right hand, or rotation in the
image plane.

A count reaches the relays only after three consecutive frames with a hand
present. Losing the hand resets that run; the relays keep their state until
a new count is confirmed. A fist turns everything off.

The relay side is active-low by default, with a minimum switching interval
per relay, guarded serial writes with one reconnect, every relay
de-energised on every exit path, and an optional Arduino watchdog that
releases the relays if the host stops sending heartbeats.

The constants live in `gesturecontrol/rules.json`. The browser demo loads
the same file and runs a JavaScript port of the same filter and rules;
both implementations are checked against `fixtures/golden_vectors.json`.

## Gesture mapping

| Fingers | Gesture | Relays |
|---------|---------|--------|
| 0 | Fist | all off |
| 1 | Index finger | relay 1 on |
| 2 | Index and middle | relay 2 on |
| 3 | Three fingers | relay 3 on |
| 4 | Four fingers, thumb tucked | relay 4 on |
| 5 | Open hand | all on |

The mapping is exclusive: a new count replaces the previous one. When the
hand leaves the frame the relays hold; show a fist to turn everything off.

## Install

```bash
git clone https://github.com/carlous-roy/GestureControl-Engine.git
cd GestureControl-Engine
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[hardware]"      # add ",dev" for the test tools
```

The only runtime dependency is `mediapipe`, which brings OpenCV with it.
Two MediaPipe lines are supported:

| mediapipe | API | Python | Model |
|-----------|-----|--------|-------|
| 0.10.14 to 0.10.21 | legacy Solutions (`mediapipe.solutions.hands`) | 3.10 to 3.12 | inside the wheel |
| 0.10.30 and later, including 1.0.x | Tasks (`HandLandmarker`) | 3.10 and later | downloaded once, see below |

A fresh `pip install` today takes the Tasks line. On macOS it stops at
1.0.0: the 1.0.1 wheel aborts the whole process while it builds the hand
landmarker graph ([mediapipe#6356](https://github.com/google-ai-edge/mediapipe/issues/6356)),
and the constraint in `pyproject.toml` lifts once a fixed release is out.
On Linux the 1.x wheels link against EGL and OpenGL ES as well as the
libraries OpenCV needs, so a minimal machine wants
`apt-get install libgl1 libglib2.0-0 libegl1 libgles2` (Debian and Ubuntu
package names) before the first import; CI installs the same four.
The first run downloads
the hand landmarker bundle (about 7.8 MB, pinned to a fixed release and
verified by SHA-256) into the per-user cache directory (`~/.cache/gesturecontrol`
on Linux, `~/Library/Caches/gesturecontrol` on macOS,
`%LOCALAPPDATA%\gesturecontrol\Cache` on Windows). Without network access,
download it yourself and point `--model` or `GESTURECONTROL_MODEL` at it;
the URL and checksum are printed in the error and listed in
`gesturecontrol/config.py`.

## Run

```bash
gesturecontrol                          # webcam, relays simulated, window with overlay
gesturecontrol --port /dev/ttyACM0      # Linux with an Arduino running Firmata
gesturecontrol --port COM6              # Windows
gesturecontrol --port /dev/cu.usbmodem* # macOS
gesturecontrol --no-ui --max-frames 600 # headless, no window at all
gesturecontrol --camera clip.avi        # a video file instead of a camera
gesturecontrol run --help               # every option
```

Press `Q` or `Esc` in the window to quit, `S` for a screenshot.
`Ctrl-C`, `SIGTERM` and `SIGHUP` shut the program down the same way as `Q`:
the relays are de-energised and the board is closed before the process
ends.

Options worth knowing:

| Option | Meaning |
|--------|---------|
| `--active-high` | relay module switches on HIGH (default: active-low, on when LOW) |
| `--min-switch-interval 0.5` | a relay is not switched twice within this many seconds |
| `--detect-every-frame` | run MediaPipe's palm detector on every frame (benchmarking) |
| `--backend solutions\|tasks` | force one MediaPipe API |
| `--width`, `--height` | requested camera resolution (640x480 by default) |
| `--detection-confidence`, `--tracking-confidence` | MediaPipe thresholds (0.7 and 0.6) |

Exit codes: 0 normal, 1 failure while running (the camera stopped
delivering frames, the board was lost), 2 failure at start-up (port, camera
or model), 3 the relays could not be released on the way out.

### Without a camera

```bash
gesturecontrol simulate            # replay scripted landmark sequences, exit 1 on any mismatch
gesturecontrol simulate --list     # the scenarios
python simulation/demo.py          # same thing
```

The simulator feeds recorded and synthetic landmark sequences through the
real filter, rules, confirmation and relay controller, prints a per-frame
trace, and checks each scenario's expected outcome. CI runs it as the
end-to-end smoke test.

## Measuring the frame rate

There is no frame-rate figure in this README until it has been measured
with the bench command on a named machine. To measure:

```bash
gesturecontrol bench --frames 300 --width 640 --height 480 --csv bench/results.csv \
    --label "machine, camera model"
```

The command times every stage on every frame, writes the per-frame numbers
to the CSV (and a JSON summary next to it), and prints a table row for this
section. Add `--detect-every-frame` to measure the cost of running the palm
detector on every frame, and `--camera file.avi` to measure on a recording.

| Machine | Source | Resolution | MediaPipe (API, mode) | Frames | Capture ms | Inference ms | Classify ms | Actuate ms | Total ms | End-to-end FPS |
|---|---|---|---|---|---|---|---|---|---|---|
| | | | | | | | | | | |

Latencies are medians over the measured frames. End-to-end latency from a
pose change to a relay change is at least three frame intervals (the
confirmation) plus one loop iteration; the bench does not measure the
camera's own exposure and transfer delay.

## Hardware

- Arduino UNO running `StandardFirmata` (Arduino IDE: File > Examples >
  Firmata > StandardFirmata) or the watchdog sketch in `firmware/`.
- A 5 V four-channel opto-isolated relay module.
- Wiring: pin 7 to IN1, pin 6 to IN2, pin 5 to IN3, pin 4 to IN4, 5V to
  VCC, GND to GND.

The common modules are low-level trigger (relay on when IN is LOW); that is
the default. Boards that switch on HIGH need `--active-high`.
`docs/HARDWARE.md` explains how to check which kind you have before
connecting a load.

### Safety and residual risk

This program switches whatever the relays are wired to. What it does:

- every relay is driven to its de-energised level when the board is opened,
  on normal exit, on `Ctrl-C`, `SIGTERM` and `SIGHUP`, on camera failure
  and on unhandled errors;
- a serial write that fails triggers one reconnect; if that fails too, the
  program stops and reports that the relay states are unknown (exit code 3);
- with the `firmware/RelayWatchdogFirmata` sketch on the Arduino, the board
  itself releases all relays when the host's heartbeat stops for one second,
  which covers a host crash, `kill -9`, a frozen process and an unplugged
  USB cable.

What it cannot do:

- with plain `StandardFirmata`, a host that dies without running its
  shutdown code leaves the relays as they were until the Arduino loses
  power;
- nothing reads the relay contacts back, so a stuck relay or a wiring fault
  is invisible to the software;
- a hung Arduino with power keeps driving its pins;
- any hand in view for three frames can switch a load; there is no arming
  gesture and no user identification.

Treat the relay outputs as unattended switches: use them for loads that
are safe to switch at any moment, and keep the mains side enclosed.

## Development

```bash
pip install -e ".[dev]"
ruff check . && ruff format --check . && mypy
pytest                                   # unit tests and fixture cases
gesturecontrol simulate                  # end-to-end smoke test
python scripts/build_fixtures.py         # regenerate tests/fixtures/classifier_cases.json
python scripts/export_golden_vectors.py  # regenerate fixtures/golden_vectors.json
python scripts/sync_demo_fixtures.py     # copy shared files into demo/
cd demo && npm ci && npm test            # JavaScript parity test
```

The detector and bench tests run real MediaPipe inference on synthetic frames.
Before the first of them, `tests/native.py` builds a detector in a child
process: MediaPipe's graph builder aborts the interpreter rather than raising
on some platform and version combinations, and the child turns that into a
failure that names the backend and shows MediaPipe's own message instead of
ending the run with nothing but "Abort trap".

Layout:

```
gesturecontrol/       the package (console script: gesturecontrol)
  app.py              control loop, signal handling, exit codes
  bench.py            per-stage latency and FPS measurement
  camera.py           camera or video file source
  cli.py              run, simulate and bench commands
  config.py           every constant; loads rules.json
  controller.py       relay controller: polarity, switching interval, reconnect, heartbeat
  detector.py         MediaPipe Hands on the Solutions or Tasks API
  filters.py          One Euro filter
  model.py            pinned, checksummed model bundle for the Tasks API
  overlay.py          on-screen status
  pipeline.py         filter + rules + confirmation, no OpenCV or hardware
  rules.py            hand frame, finger and thumb rules, relay mapping
  scenarios.py        recorded and synthetic hands, transforms, scripted sequences
  simulate.py         the simulate command
  stabilizer.py       N-frame confirmation
  rules.json          the shared constants
  data/hands.json     recorded landmarks (coordinates only)
firmware/             RelayWatchdogFirmata sketch
demo/                 browser demo with the JavaScript port and its Vitest test
fixtures/             golden_vectors.json shared by both test suites
tests/                pytest suite; tests/fixtures/classifier_cases.json
docs/                 ALGORITHM.md, HARDWARE.md, TECHNICAL_REPORT.md
```

The recorded landmarks in `gesturecontrol/data/hands.json` were extracted
with MediaPipe from frames in the 2022 project report; the images
themselves are not in the repository.

## Background

This started as my final-year project in 2022 at Sathyabama Institute of
Science and Technology, Chennai (B.E. Electronics and Communication
Engineering). The code in this repository is a rebuild: the package, the
classifier, the relay controller, the tests, the simulator and the
documentation were written afresh.

## License

MIT
