# Algorithm & Technical Details

## Overview

The system uses a two-stage machine learning pipeline (via Google's MediaPipe) for hand detection and landmark estimation, followed by a rule-based finger counting algorithm that maps gestures to relay control signals.

## Stage 1: Palm Detection

MediaPipe employs a single-shot detector (SSD) optimized for mobile real-time use to locate palms in the input frame.

**Why palms instead of hands?**
- Palms are rigid objects — easier to estimate bounding boxes for than articulated hands.
- Palms are smaller, so non-maximum suppression works better for self-occlusion (e.g., handshakes).
- Square bounding boxes (anchors) suffice, reducing anchor count by 3–5×.

The model uses an encoder-decoder feature extractor for scene context awareness and minimizes focal loss to handle the large scale variance of hands in a frame.

**Reported accuracy:** 95.7% average precision for palm detection.

## Stage 2: Hand Landmark Model

Once the palm bounding box is established, a second model predicts **21 3D keypoints** within the cropped hand region via direct coordinate regression.

```
         12
        /
  8    11   16
  |   / |   / \
  7  10  15  20
  | / | / | /
  6  9  14  19
  |  |  |   |
  5  |  13  18
   \ | /   /
    \|/   17
  4  |  /
  |  | /
  3  |
  |  |
  2  |
  |  |
  1  |
   \ |
    \|
     0 (WRIST)
```

| ID | Landmark | ID | Landmark |
|----|----------|----|----------|
| 0 | WRIST | 11 | MIDDLE_FINGER_DIP |
| 1 | THUMB_CMC | 12 | MIDDLE_FINGER_TIP |
| 2 | THUMB_MCP | 13 | RING_FINGER_MCP |
| 3 | THUMB_IP | 14 | RING_FINGER_PIP |
| 4 | THUMB_TIP | 15 | RING_FINGER_DIP |
| 5 | INDEX_FINGER_MCP | 16 | RING_FINGER_TIP |
| 6 | INDEX_FINGER_PIP | 17 | PINKY_MCP |
| 7 | INDEX_FINGER_DIP | 18 | PINKY_PIP |
| 8 | INDEX_FINGER_TIP | 19 | PINKY_DIP |
| 9 | MIDDLE_FINGER_MCP | 20 | PINKY_TIP |
| 10 | MIDDLE_FINGER_PIP | | |

The model was trained on ~30,000 manually annotated real-world images plus synthetic hand renders for pose coverage.

## Stage 3: Finger Counting (Rule-Based)

The finger counting algorithm compares fingertip positions against reference joint positions:

### For Index, Middle, Ring, Pinky (Vertical Check)

```python
finger_is_up = (PIP.y - TIP.y) > 15   # pixels
```

In image coordinates, y=0 is at the top, so a raised finger has its tip *above* (lower y) its PIP
joint. A bare `TIP.y < PIP.y` test flickers on half-curled poses where the two joints sit within a
pixel or two of each other, so the classifier requires a minimum gap of 15 pixels. This is a static
geometric margin, not a motion filter — it is evaluated independently on every frame.

### For Thumb (Palm-Width Ratio)

```python
palm_width     = distance(INDEX_MCP, PINKY_MCP)   # landmarks 5 and 17
thumb_to_index = distance(THUMB_TIP, INDEX_MCP)   # landmarks 4 and 5

thumb_is_up = thumb_to_index > palm_width * 0.6
```

The thumb folds laterally rather than vertically, so the tip-above-PIP test reports it raised no
matter what it is doing. A plain `TIP.x > IP.x` comparison is no better: it inverts for the left hand
and breaks as soon as the hand rotates.

Measuring the thumb tip's distance from the index finger base and dividing through by palm width
gives a scale-invariant ratio instead. Tucked across the palm it sits around 0.3-0.4; extended
outward it sits around 0.6-0.8, so the 0.6 threshold separates the two cases with margin either side.
Distances are Euclidean over pixel-space (x, y) coordinates; a palm width under 1 pixel is treated as
unusable geometry and the thumb is reported down.

### Mapping to Relay States

```
Fingers  →  Relay States [R1, R2, R3, R4]
──────────────────────────────────────────
0        →  [OFF, OFF, OFF, OFF]
1        →  [ON,  OFF, OFF, OFF]
2        →  [OFF, ON,  OFF, OFF]
3        →  [OFF, OFF, ON,  OFF]
4        →  [OFF, OFF, OFF, ON ]
5        →  [ON,  ON,  ON,  ON ]
```

## Image Processing Pipeline

```
Webcam Frame (BGR)
       │
       ▼
cv2.cvtColor(BGR → RGB)    # MediaPipe expects RGB
       │
       ▼
MediaPipe Hands.process()   # Palm detection + landmark estimation
       │
       ▼
Extract pixel coordinates   # Convert normalized [0,1] → pixel [0,W/H]
       │
       ▼
Finger counting logic       # Compare TIP vs PIP/IP positions
       │
       ▼
Controller.set_from_count() # Map count to relay configuration
       │
       ▼
cv2.cvtColor(RGB → BGR)    # Convert back for OpenCV display
       │
       ▼
Draw landmarks + overlay    # Render hand landmarks and status UI
       │
       ▼
cv2.imshow()                # Display annotated frame
```

## Performance Characteristics

| Metric | Value |
|--------|-------|
| Frame Rate | 25–30 FPS (CPU-only, modern laptop) |
| Detection Latency | ~30ms per frame |
| End-to-End Latency | <50ms (gesture → relay activation) |
| Detection Confidence Threshold | 0.7 (configurable) |
| Tracking Confidence Threshold | 0.6 (configurable) |
| Supported Hands | 1 (`HandDetector(max_hands=...)` constructor parameter; no CLI flag) |

## Limitations & Known Issues

1. **Geometric, not learned.** The classifier assumes a roughly upright hand facing the camera. The palm-width ratio used for the thumb is handedness-agnostic, but the tip-above-PIP test for the other four fingers degrades as the hand rotates, because the vertical axis stops meaning what the rule assumes.
2. **Lighting sensitivity:** Performance degrades in very low light or strong backlighting.
3. **Occlusion:** Partially visible hands may produce incorrect counts.
4. **Single-hand only:** `max_hands` defaults to 1, so MediaPipe is configured to return at most one hand per frame.
