# Algorithm

This document describes what the code in `gesturecontrol/` does, stage by
stage, and where each number comes from. Module names are given so the
description can be checked against the source.

## 1. Landmark detection (`detector.py`)

MediaPipe Hands provides the 21 landmarks. It is a two-stage pipeline
(Zhang et al., 2020): a palm detector proposes the hand region, and a
landmark model regresses 21 points inside a crop of that region. Figures
about the models (training data, accuracy) are MediaPipe's own and are not
measured by this project; see the reference at the end.

Two APIs are supported and chosen at start-up:

| API | mediapipe | Tracking mode | Detect-every-frame mode |
|-----|-----------|---------------|-------------------------|
| Solutions (`mediapipe.solutions.hands.Hands`) | 0.10.14 to 0.10.21 | `static_image_mode=False` | `static_image_mode=True` |
| Tasks (`HandLandmarker`) | 0.10.14 and later | `RunningMode.VIDEO` with increasing timestamps | `RunningMode.IMAGE` |

In tracking mode the palm detector runs when there is no hand being
tracked from the previous frame; otherwise only the landmark model runs, on
a crop derived from the previous landmarks. The palm detector runs again
when tracking is lost. `--detect-every-frame` forces the detector on every
frame; it exists so the two costs can be measured with `gesturecontrol bench`.

The detector returns the normalised `(x, y)` of the first hand, in the range
0 to 1 relative to the frame width and height, or nothing. The `z`
coordinate is not used. Only one hand is tracked (`max_hands=1`); MediaPipe
picks which one.

Confidence thresholds: palm detection 0.7, tracking 0.6 (the Tasks API
uses the second value for both hand presence and tracking).

## 2. One Euro filter (`filters.py`)

The landmarks are smoothed with a One Euro filter (Casiez, Roussel and
Vogel, 2012), one filter per coordinate of each landmark, in normalised
units. The filter is an exponential low-pass whose cutoff frequency rises
with the speed of the signal:

```
alpha(fc, dt)  = 1 / (1 + 1 / (2 pi fc dt))
dx_hat         = alpha(fd, dt) * (x - x_hat_prev) / dt + (1 - alpha(fd, dt)) * dx_hat_prev
fc             = fc_min + beta * |dx_hat|
x_hat          = alpha(fc, dt) * x + (1 - alpha(fc, dt)) * x_hat_prev
```

Constants (`rules.json`): `fc_min = 1.0 Hz`, `beta = 5.0` per normalised
unit per second, `fd = 10 Hz`. Because the filter runs in normalised
coordinates, `beta` does not depend on the camera resolution.

The values were chosen on the scripted sequences in `scenarios.py`: at
rest, 3 px of deterministic jitter on a 640 px frame is reduced to about a
quarter of its standard deviation; a pose change between two consecutive
frames is followed within the same frame, so filtering adds no frame of
latency on the `count_up` sequence. `tests/test_filters.py` pins both
properties. Duplicate or out-of-order timestamps return the previous
estimate. Losing the hand resets every filter, so the first frame of a
returning hand is passed through unfiltered.

## 3. Hand frame and finger rules (`rules.py`)

All geometry is computed on pixel coordinates (`x * width`, `y * height`)
so that x and y share one unit.

Landmark indices (MediaPipe): 0 wrist; 1-4 thumb CMC, MCP, IP, tip; 5-8
index MCP, PIP, DIP, tip; 9-12 middle; 13-16 ring; 17-20 pinky.

The hand frame:

- `up` is the unit vector from the wrist (0) to the middle-finger MCP (9);
- `side` is perpendicular to `up`, oriented so that the index MCP (5) lies
  on its positive side relative to the pinky MCP (17). This is what makes
  the rules hold for either hand and for mirrored video: the side axis
  always points towards the thumb;
- `palm_width` is the distance between landmarks 5 and 17 and is the unit
  of length.

If the palm width or the wrist-to-MCP distance is below
`min_palm_width_px` (8 px), the frame is unusable and the count is -1.

Measurements, in palm widths:

```
finger_extension[i] = dot(tip_i - pip_i, up) / palm_width     for index, middle, ring, pinky
thumb_extension     = dot(thumb_tip - index_mcp, side) / palm_width
```

A finger's extension is how far its tip lies beyond its PIP joint along
the hand's up axis. An extended finger gives a positive value close to the
length of its two distal phalanges divided by the palm width; a curled
finger gives a negative value because the tip folds back towards the palm.
The thumb's extension is the offset of its tip from the index knuckle
towards the outside of the hand: positive when the thumb is abducted, near
zero when it rests against the index finger, negative when it is folded
across the palm or wrapped over a fist.

Measured values on the recorded hands in `gesturecontrol/data/hands.json`
(MediaPipe landmarks from frames of the 2022 report) and on the synthetic
hand model in `scenarios.py`:

| Case | thumb | index | middle | ring | pinky |
|------|-------|-------|--------|------|-------|
| recorded open palm A (webcam) | 0.91 | 0.77 | 0.91 | 0.87 | 0.67 |
| recorded open palm B (webcam, tilted 25 degrees) | 0.99 | 0.67 | 0.77 | 0.68 | 0.51 |
| recorded open palm (photo, from behind) | 1.08 | 0.74 | 0.88 | 0.83 | 0.61 |
| recorded fist (photo) | -0.47 | -0.34 | -0.35 | -0.33 | -0.29 |
| synthetic open palm | 0.67 | 0.74 | 0.83 | 0.78 | 0.60 |
| synthetic fist | -0.29 | -0.51 | -0.57 | -0.54 | -0.43 |
| synthetic four fingers, thumb against index | -0.06 | 0.74 | 0.83 | 0.78 | 0.60 |
| synthetic four fingers, thumb across palm | -0.67 | 0.74 | 0.83 | 0.78 | 0.60 |

Thresholds (`rules.json`), with hysteresis so a value hovering near the
line does not flip the state every frame:

| Finger | raises above | lowers below |
|--------|--------------|--------------|
| index, middle, ring, pinky | 0.35 | 0.25 |
| thumb | 0.40 | 0.30 |

Every case in the table sits at least 0.1 palm widths away from the
thresholds; `tests/test_rules.py` checks that margin for all 198 fixture
cases. The values were chosen by hand from that table, not fitted; a larger
recording set would allow better ones.

What the frame gives:

- scale: both measures are ratios, so distance to the camera and the
  frame resolution do not matter (down to the 8 px palm minimum);
- rotation in the image plane: the axes rotate with the hand, so an open
  palm pointing sideways or down still reads 5 and an inverted fist still
  reads 0;
- mirroring and handedness: the side axis is derived from the landmarks;
- out-of-plane rotation about the vertical axis (yaw): palm width and the
  thumb offset are both lateral distances and foreshorten together, so
  the thumb ratio is stable; finger extensions grow relative to palm width
  and stay above threshold.

What it does not give:

- tilting the hand towards the camera (pitch) foreshortens finger
  extension but not palm width, so extended fingers read shorter; at
  large pitch angles an open hand loses fingers;
- fingers curled to about ninety degrees at the PIP joint read near zero
  and count as down; a half-curled finger is ambiguous by design;
- MediaPipe's own errors pass straight through: if the landmark model
  places a fingertip in the wrong place, the rule counts what it is given.

## 4. Confirmation (`stabilizer.py`)

The per-frame count goes through a run-length check: it must be the same
on `confirm_frames = 3` consecutive frames with a hand present before it
becomes the confirmed count. A frame with no hand, or with unusable
geometry, resets the run; the confirmed count is kept. This is what makes
the relays hold when the hand leaves the frame, and it stops one frame of a
count seen before the hand left from being credited to its return.

Time to commit: three frame intervals from the first frame of a new pose
(100 ms at 30 frames per second, 200 ms at 15). Single-frame excursions to
another count never reach the relays; a two-frame excursion does not
either. A pose held for three frames does, including intermediate poses
while the hand opens from one finger to five; the relay controller's
switching interval (section 6) limits how often each relay can switch as a
result.

## 5. Relay mapping (`rules.py`)

```
count  relays [R1, R2, R3, R4]
0      off off off off
1      on  off off off
2      off on  off off
3      off off on  off
4      off off off on
5      on  on  on  on
other  off off off off
```

## 6. Relay controller (`controller.py`)

- Polarity: the pin level for "on" is LOW by default (active-low module)
  and HIGH with `--active-high`.
- Minimum switching interval (0.5 s by default, `--min-switch-interval`):
  a relay that changed less than this long ago keeps its state; the
  requested state is stored and applied on the next loop iteration once
  the interval has passed. A request that is reversed before the interval
  ends is cancelled, which collapses chatter.
- Serial writes: on an `OSError` the controller closes the board, opens it
  again, restores the relay levels and retries once; a second failure
  raises and the loop shuts down.
- Cleanup: every relay is driven to its off level regardless of the
  interval, then the board is closed; failures are logged and reported by
  the exit code, never raised.
- Heartbeat: a SysEx message every 250 ms for the watchdog sketch in
  `firmware/`; after a gap longer than the watchdog timeout the controller
  re-sends the relay levels, because the sketch will have released them.

## 7. The loop (`app.py`)

```
read frame -> mirror -> detector.process -> pipeline.process(landmarks, t)
   -> if the confirmed count changed: controller.set_from_finger_count
   -> else: controller.apply (deferred switches)
   -> overlay and window unless --no-ui
```

Timestamps come from a monotonic clock. `SIGINT`, `SIGTERM` and `SIGHUP`
set a stop flag that the loop checks every frame; the `finally` block
stops the heartbeat, closes the detector, releases the camera, closes the
window and runs the relay cleanup on every exit path.

## 8. Tests and fixtures

- `tests/fixtures/classifier_cases.json`: 198 single-frame cases built by
  `scripts/build_fixtures.py` from four recorded hands and six synthetic
  poses under rotation (30 to 180 degrees), scale (12 to 120 px palms),
  mirroring, resolution changes (320x240 to 1920x1080), translation, thumb
  placements and yaw. Each case is checked from a fresh classifier and
  from a classifier pre-latched to all fingers up, so both hysteresis
  bands are exercised.
- `fixtures/golden_vectors.json`: fifteen scripted sequences with the
  pipeline's per-frame outputs, checked by the Python suite and by the
  JavaScript port in `demo/`.
- `gesturecontrol simulate`: the same sequences through the pipeline and
  the relay controller with a simulated clock.

## References

- Zhang, F., Bazarevsky, V., Vakunov, A., Tkachenka, A., Sung, G., Chang,
  C.-L. and Grundmann, M. (2020). MediaPipe Hands: On-device Real-time
  Hand Tracking. arXiv:2006.10214. The palm detector and landmark model,
  their training data and reported accuracy are described there and in the
  MediaPipe documentation
  (https://ai.google.dev/edge/mediapipe/solutions/vision/hand_landmarker).
- Casiez, G., Roussel, N. and Vogel, D. (2012). 1 Euro Filter: A Simple
  Speed-based Low-pass Filter for Noisy Input in Interactive Systems.
  Proceedings of CHI 2012, pages 2527-2530.
  https://doi.org/10.1145/2207676.2208639
