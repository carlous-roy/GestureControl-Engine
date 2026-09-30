# Technical report: gesture-based relay control

System design, implementation, verification and limitations.

---

## 1. Introduction

The system counts the extended fingers of one hand in a webcam picture and
switches four relays accordingly: 0 fingers turns every relay off, 1 to 4
turns on the matching relay, 5 turns all four on. A laptop runs the vision
and classification; an Arduino UNO running Firmata drives the relay module
over USB.

The project started as a final-year B.E. project in 2022. The code in this
repository is a rebuild: a Python package with a command-line interface, a
rule-based classifier in the hand's own frame of reference, a fail-safe
relay controller, a hardware-free simulator, a benchmark tool, tests, CI,
and a browser demo that runs the same classifier.

### 1.1 Scope

Six gestures (0 to 5 extended fingers) from one hand facing the camera. No
sign language, no arbitrary gestures, no user identification. The gesture
vocabulary is small on purpose: the rules are readable and testable, and
every relay change can be traced to a measured quantity.

---

## 2. System overview

```
webcam ──► OpenCV capture ──► MediaPipe Hands ──► One Euro filter ──► finger rules
                                                                          │
   relay module ◄── Arduino (Firmata) ◄── serial ◄── relay controller ◄── 3-frame confirmation
```

Software (host):

- OpenCV for capture, mirroring and the optional window;
- MediaPipe Hands for the 21 landmarks (legacy Solutions API or Tasks API,
  whichever the installed mediapipe provides);
- `gesturecontrol`: filter, rules, confirmation, relay controller, loop,
  simulator, benchmark;
- `pyfirmata2` for the Firmata protocol over serial.

Hardware:

- Arduino UNO with `StandardFirmata` or the `RelayWatchdogFirmata` sketch
  from `firmware/`;
- a 5 V four-channel opto-isolated relay module, active-low by default;
- loads on the normally-open contacts.

---

## 3. Software design

### 3.1 Modules

| Module | Responsibility |
|--------|----------------|
| `detector.py` | MediaPipe Hands on either API; returns normalised landmarks of the first hand |
| `model.py` | pinned, checksummed hand landmarker bundle for the Tasks API, cached per user |
| `filters.py` | One Euro filter per landmark coordinate |
| `rules.py` | hand frame, finger and thumb extension, hysteresis latches, relay mapping |
| `stabilizer.py` | N-frame confirmation with reset on hand loss |
| `pipeline.py` | filter + rules + confirmation; no OpenCV, MediaPipe or hardware dependency |
| `controller.py` | relay controller: polarity, switching interval, guarded writes, reconnect, cleanup, heartbeat |
| `app.py` | the loop, signal handling, exit codes |
| `camera.py` | camera or video-file frame source |
| `scenarios.py` | recorded and synthetic hands, transforms, scripted sequences |
| `simulate.py` | end-to-end replay without hardware |
| `bench.py` | per-stage latency and frame-rate measurement |
| `config.py`, `rules.json` | every constant |

The pipeline is deliberately free of I/O so that it can be driven by
recorded landmarks in tests, by the simulator, and by the JavaScript port
in the browser demo.

### 3.2 Classifier

The classifier is described in full in `ALGORITHM.md`. In short:

1. landmarks are smoothed by a One Euro filter (Casiez, Roussel and Vogel,
   2012) in normalised coordinates;
2. a frame is attached to the hand: up axis from the wrist to the middle
   MCP, side axis towards the thumb, palm width as the unit;
3. a finger is extended when its tip lies beyond its PIP joint along the up
   axis by more than 0.35 palm widths (lowering below 0.25); the thumb is
   extended when its tip lies beyond the index MCP along the side axis by
   more than 0.40 palm widths (lowering below 0.30);
4. a count must hold for three consecutive frames before it is confirmed;
   losing the hand resets the run but keeps the confirmed count.

Because the measures are ratios inside a frame that rotates with the hand,
the count does not depend on camera distance, resolution, mirroring, hand
side or in-plane rotation. That is verified on 198 fixture cases derived
from four recorded hands and six synthetic poses.

### 3.3 Relay controller and safety

The relay side is where a software mistake has a physical consequence, so
the controller is built around a few rules:

- polarity is explicit (active-low by default, `--active-high` otherwise)
  and the watchdog firmware is told the same choice;
- a relay is not switched twice within the minimum switching interval
  (0.5 s); a change requested inside the window is applied when it ends,
  and a change reversed before then is dropped;
- every serial write is guarded; one reconnect is attempted, with the relay
  levels restored, and a second failure stops the program and reports that
  the relay states are unknown;
- cleanup drives every relay to its off level and closes the board on every
  exit path: normal quit, `SIGINT`, `SIGTERM`, `SIGHUP`, camera failure,
  board failure, unhandled errors. It never raises, and a failure to release
  the relays is reported through exit code 3;
- with the watchdog sketch, the host sends a heartbeat every 250 ms and the
  board releases all relays if none arrives for one second. This covers
  the cases software on the host cannot: a crash, `kill -9`, a frozen
  process, a pulled cable.

Residual risk remains and is stated in the README: with `StandardFirmata`
an uncontrolled host death leaves the relays as they were; there is no
read-back of the contacts; a hung Arduino keeps driving its pins; any hand
in view for three frames can switch a load.

### 3.4 Simulation

`gesturecontrol simulate` replays fifteen scripted sequences (recorded
hands, synthetic poses, rotations, approach, jitter, hand loss, flicker,
transitions) through the real pipeline and relay controller on a simulated
clock, prints a per-frame trace, and exits non-zero if any sequence does
not produce its declared confirmations, final count and final relay state.
It needs no camera, display or board, and CI runs it on every push.

---

## 4. Verification

### 4.1 Tests

| Area | What is checked |
|------|-----------------|
| filter | pass-through of the first sample, jitter reduction at rest, bounded lag in fast motion, reset, duplicate timestamps |
| rules | 198 fixture cases (`tests/fixtures/classifier_cases.json`), each from a fresh classifier and from one pre-latched to all-up; a 0.1 palm-width margin from every threshold; rotation and scale invariance of the raw measures; the side axis for both hands; degenerate geometry |
| confirmation | commit on the third frame, reset on loss and on count change, hold on loss |
| pipeline | fifteen scripted sequences with expected confirmations and relay states; `fixtures/golden_vectors.json` replayed frame by frame |
| controller | polarity, switching interval, chatter collapse, connect failure, missing library, reconnect with state restore, reconnect failure, cleanup failure reporting, watchdog configuration and acknowledgement, heartbeat gap handling, heartbeat thread |
| loop | headless run, hold on loss, camera read failure, camera open failure, board connection failure, lost board, quit key, `--no-ui` opening no window, frame budget, `SIGINT`/`SIGTERM`/`SIGHUP` delivered to the process |
| model | size and checksum verification, download to a temporary file, corrupt download, missing model without network |
| detector | real MediaPipe inference on synthetic frames on whichever API is installed, tracking and detect-every-frame modes |
| bench | fake stages on a ticking clock; a generated video file with real inference |
| demo | the JavaScript port replays the same golden vectors (Vitest) |

CI (GitHub Actions) runs ruff, ruff format, mypy in strict mode, the test
suite on Python 3.11 and 3.12 with the legacy MediaPipe API and on the
Tasks API with current mediapipe, the simulator, the Vitest test and the
Vite build of the demo, and an `arduino-cli` compile of the watchdog
sketch for the UNO.

### 4.2 Recorded hands

Four hands were recovered as MediaPipe landmarks from frames in the 2022
project report (two webcam screenshots of an open palm, a photograph of an
open palm seen from behind, a photograph of a fist). Only the coordinates
are in the repository (`gesturecontrol/data/hands.json`). They are the
real-data anchor for the fixture set; every transform in the fixtures is
applied to them as well as to the synthetic poses. Four hands are not a
dataset, and no accuracy figure is claimed from them.

### 4.3 Measurements

Frame rate and per-stage latency are measured with `gesturecontrol bench`,
which reports medians per stage and end-to-end frames per second together
with the machine, camera, resolution and library versions. The README holds
the table; it is filled in only from runs on a named machine with a camera.

One measurement that does not need a camera: the cost of MediaPipe's palm
detector. On a recorded 640x480 frame replayed as a video file in a
2-vCPU cloud container (no camera, so no capture latency), the inference
stage in tracking mode against detect-every-frame mode:

| mediapipe | API | tracking, median ms | every frame, median ms |
|-----------|-----|---------------------|------------------------|
| 0.10.21 | Solutions | 9.2 | 18.9 |
| 1.0.1 | Tasks | 9.8 | 20.9 |

The roughly twofold difference is the palm detector, which in tracking mode
runs only when no hand is being tracked. These are inference-stage timings
from one machine that no user would run this on; they say nothing about
the frame rate of the loop on a laptop with a camera.

---

## 5. Limitations

- Geometry, not learning: the rules assume a hand roughly facing the
  camera. Tilting the hand towards the camera shortens finger extension
  and can drop fingers; half-curled fingers are ambiguous by design.
- MediaPipe's errors pass through. On one recorded frame the Tasks model
  in detect-every-frame mode placed two fingertips wrongly and the count
  read 3 instead of 5; the same frame in tracking mode read 5.
- The thresholds were chosen from four recorded hands and a synthetic
  model; a proper recording set with several people would allow measured
  error rates.
- One hand only, and MediaPipe chooses which. Two people in view are not
  handled.
- No arming gesture: a hand held for three frames switches a load.
- Frame rate and latency are unmeasured until the bench is run on real
  hardware.
- The watchdog firmware compiles and is tested on the host side against a
  fake device; it has not yet been run on a board.

---

## 6. Future work

- Record a landmark dataset from several people and hands, and report
  per-finger error rates and a confusion matrix.
- An arming gesture or a minimum dwell for turning loads on.
- Read-back of relay state (a sense input per channel).
- Pitch tolerance: use the palm length as a second scale reference.
- Multi-hand policy (ignore the second hand, or require both).

---

## References

1. Zhang, F. et al. (2020). MediaPipe Hands: On-device Real-time Hand
   Tracking. arXiv:2006.10214. MediaPipe Hand Landmarker documentation:
   https://ai.google.dev/edge/mediapipe/solutions/vision/hand_landmarker
2. Casiez, G., Roussel, N. and Vogel, D. (2012). 1 Euro Filter: A Simple
   Speed-based Low-pass Filter for Noisy Input in Interactive Systems.
   CHI 2012. https://doi.org/10.1145/2207676.2208639
3. pyFirmata2: https://github.com/berndporr/pyFirmata2
4. Firmata protocol: https://github.com/firmata/protocol
5. OpenCV: https://opencv.org/

---

Project: B.E. Electronics and Communication Engineering, Sathyabama
Institute of Science and Technology, Chennai (2022)

Authors: Roy Carlous Christudass, Vasanth Mathew B

Guide: Dr. T. Ravi, M.E., Ph.D., Head of Department, ECE
