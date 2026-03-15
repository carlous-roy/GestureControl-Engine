# Technical Report: AI Gesture-Based Home Automation

**Corrected and accurate version of the original B.E. project report**

---

## 1. Introduction

This project implements a real-time hand gesture recognition system for controlling home appliances. A webcam captures the user's hand gestures, computer vision software detects and counts the number of raised fingers (0-5), and the count is mapped to relay states that switch appliances on and off through an Arduino UNO microcontroller.

The system targets accessibility use cases: elderly individuals, people with mobility impairments, and situations where touchless interaction is preferred.

### 1.1 Objective

- Detect hand gestures in real-time using a standard webcam
- Count raised fingers (0-5) using landmark-based geometric analysis
- Control 4 home appliances via an Arduino UNO and relay module
- Achieve low-latency response (under 50ms per frame)

### 1.2 Scope

The system recognizes six discrete gestures (0-5 fingers) and maps each to a fixed appliance state. It does not perform sign language recognition, arbitrary gesture classification, or multi-hand tracking. The gesture vocabulary is intentionally limited to ensure high reliability.

---

## 2. System Architecture

### 2.1 Overview

The system consists of two subsystems:

**Software subsystem** (runs on a laptop/PC):
- OpenCV for webcam capture and video display
- Google MediaPipe Hands for hand landmark detection
- Custom finger counting algorithm based on landmark geometry
- PyFirmata protocol for serial communication with Arduino

**Hardware subsystem:**
- Arduino UNO (ATmega328P) microcontroller
- 4-channel relay module with optocoupler isolation
- Household appliances (bulbs for demonstration)
- 5V regulated power supply

### 2.2 Processing Pipeline

```
Frame Capture (OpenCV, 30 FPS)
        |
        v
Hand Detection (MediaPipe Hands)
  - Palm detection model locates hand region
  - Hand landmark model extracts 21 3D keypoints
        |
        v
Finger Counting (Custom Algorithm)
  - Thumb: distance-based comparison (tip vs MCP relative to index base)
  - Fingers: vertical y-axis comparison (tip above PIP joint)
  - 3-frame stabilization before relay change
        |
        v
Relay Command (PyFirmata over USB Serial)
  - Digital HIGH/LOW to Arduino pins 4-7
        |
        v
Appliance Switching (Relay Module)
  - Optocoupler-isolated relay coils
  - Normally-Open contacts switch mains voltage
```

### 2.3 Latency Breakdown

| Stage | Latency |
|-------|---------|
| Frame capture | ~3ms |
| MediaPipe hand detection | 15-30ms |
| Finger counting | <1ms |
| Serial communication | ~2ms |
| Relay switching | ~10ms |
| **Total per frame** | **~30-45ms** |

---

## 3. Software Implementation

### 3.1 Hand Detection: MediaPipe Hands

Google's MediaPipe Hands provides real-time hand tracking that extracts 21 three-dimensional landmarks per detected hand. The model uses a two-stage pipeline:

1. **Palm detection model** — A lightweight single-shot detector that locates the hand's bounding box in the full frame. This runs once and then only re-runs when tracking is lost.

2. **Hand landmark model** — Operates on the cropped hand region and predicts 21 keypoint positions in 3D (x, y, z). The model was trained on approximately 30,000 real-world images plus synthetic hand renderings.

The 21 landmarks correspond to:
- Wrist (1 point)
- Each finger: MCP, PIP, DIP, and TIP joints (4 points x 5 fingers = 20 points)

MediaPipe runs entirely on CPU and achieves 30 FPS on modern laptop hardware.

**Note on "Deep Forest Algorithm":** The original project report (2022) referenced a "Deep Forest Algorithm" in section 4.4.3. This was inaccurate — the described content was about the DeepForest Python package for detecting tree crowns in aerial forestry imagery, which is unrelated to hand gesture recognition. The actual hand detection in this project uses exclusively MediaPipe Hands. No custom deep learning model was trained.

### 3.2 Finger Counting Algorithm

#### Thumb Detection (Improved)

The original implementation used a simple x-axis comparison (thumb tip x > thumb IP x). This approach fails when the hand is rotated, tilted, or when using the left hand.

The improved approach uses distance-based comparison:

```
thumb_tip = landmark[4]     // THUMB_TIP
thumb_mcp = landmark[2]     // THUMB_MCP
index_mcp = landmark[5]     // INDEX_MCP
wrist     = landmark[0]     // WRIST

dist_tip_to_index = euclidean(thumb_tip, index_mcp)
dist_mcp_to_index = euclidean(thumb_mcp, index_mcp)

thumb_up = (dist_tip_to_index > dist_mcp_to_index * 1.2) 
           AND (distance(thumb_tip, wrist) > distance(thumb_ip, wrist))
```

The thumb is considered "up" when:
1. The thumb tip is at least 1.2x farther from the index finger base than the thumb MCP is (thumb is extended outward)
2. The thumb tip is farther from the wrist than the thumb IP joint (thumb is not folded inward)

#### Other Fingers Detection

For index, middle, ring, and pinky fingers, a vertical comparison is used:

```
For each finger i in [index, middle, ring, pinky]:
    tip_y = landmark[TIP_ID[i]].y       // Fingertip y-coordinate
    pip_y = landmark[TIP_ID[i] - 2].y   // PIP joint y-coordinate
    
    finger_up = (pip_y - tip_y) > 15 pixels
```

A finger is "up" when its tip is above its PIP joint by at least 15 pixels. This minimum gap threshold prevents borderline poses from causing jitter.

#### Stabilization

To prevent rapid relay switching from momentary detection noise, a 3-frame stabilization requirement is enforced:

```
if current_count == stable_count:
    stable_frames += 1
else:
    stable_count = current_count
    stable_frames = 1

if stable_frames >= 3 AND stable_count != confirmed_count:
    confirmed_count = stable_count
    update_relays(confirmed_count)
```

Additionally, when the hand leaves the camera frame, relays hold their last confirmed state rather than defaulting to OFF. The user must show a fist (0 fingers) to explicitly turn everything off.

### 3.3 Relay Control: PyFirmata

PyFirmata is a Python library that implements the Firmata protocol for communicating with Arduino boards over serial USB. The Arduino runs the StandardFirmata sketch, which turns it into a general-purpose I/O device controllable from the host computer.

Pin assignments:
- Digital Pin 7 → Relay 1 (Appliance 1)
- Digital Pin 6 → Relay 2 (Appliance 2)
- Digital Pin 5 → Relay 3 (Appliance 3)
- Digital Pin 4 → Relay 4 (Appliance 4)

Relay mapping:
- 0 fingers → all pins LOW (all off)
- N fingers (1-4) → pin N HIGH, others LOW
- 5 fingers → all pins HIGH (all on)

### 3.4 Simulation Mode

The system includes a simulation mode that runs without Arduino hardware. When no serial port is specified, relay commands are printed to the console instead of being sent to hardware. This allows development, testing, and demonstration without physical components.

---

## 4. Hardware Implementation

### 4.1 Arduino UNO

The Arduino UNO is based on the ATmega328P microcontroller. Key specifications:
- Operating voltage: 5V
- Digital I/O pins: 14 (of which 4 are used for relay control)
- Clock speed: 16 MHz
- Flash memory: 32 KB
- USB interface for serial communication with host computer

The Arduino runs the StandardFirmata sketch, which allows the host computer to read/write digital pins over serial USB without custom Arduino code.

### 4.2 4-Channel Relay Module

The relay module includes:
- 4 independent SPDT (Single Pole Double Throw) relays
- Optocoupler isolation between control logic and relay coils
- LED indicators for each relay state
- Rated for 10A at 250VAC or 30VDC per channel

The optocoupler isolation protects the Arduino from voltage spikes when relay coils switch. Input pins are active-LOW on most modules (though logic is handled in software).

### 4.3 Wiring

```
Arduino UNO          4-Channel Relay Module
─────────────        ─────────────────────
Pin 7  ──────────>   IN1  (Relay 1)
Pin 6  ──────────>   IN2  (Relay 2)
Pin 5  ──────────>   IN3  (Relay 3)
Pin 4  ──────────>   IN4  (Relay 4)
5V     ──────────>   VCC
GND    ──────────>   GND
```

Each relay's COM (Common) terminal connects to mains live, and the NO (Normally Open) terminal connects to the appliance, which returns to mains neutral.

**Safety warning:** The relay module switches mains voltage (120V/240V AC). For safe demonstration, use low-voltage LEDs (5V) connected directly to the relay outputs.

---

## 5. Results

- Hand detection works reliably under standard indoor lighting
- Finger counting achieves consistent accuracy for deliberate gestures
- System operates at 25-30 FPS on a modern laptop
- Relay response is perceived as instantaneous by the user
- Simulation mode allows demonstration without hardware
- Thumb detection accuracy significantly improved with distance-based approach over the naive x-axis method

---

## 6. Conclusion

The system successfully demonstrates gesture-based home automation using commodity hardware (webcam + Arduino) and open-source software (OpenCV, MediaPipe, PyFirmata). The total hardware cost is under $30, and the software runs on any Python-capable computer with a webcam.

Key improvements in the reconstructed codebase over the original implementation include modular code architecture, distance-based thumb detection, 3-frame gesture stabilization, state-holding behavior when the hand leaves frame, simulation mode for hardware-free operation, and comprehensive documentation.

### Future Work

- Expand gesture vocabulary beyond finger counting (e.g., swipe gestures for dimming)
- Replace Arduino with Raspberry Pi for standalone operation (camera + controller in one device)
- Add voice feedback for accessibility
- Implement multi-hand support for different user gestures
- Integrate with smart home protocols (MQTT, Zigbee)

---

## References

1. MediaPipe Hands — Google AI Edge. https://ai.google.dev/edge/mediapipe/solutions/vision/hand_landmarker
2. PyFirmata — Python interface for Firmata protocol. https://github.com/tino/pyFirmata
3. OpenCV — Open Source Computer Vision Library. https://opencv.org/
4. Arduino StandardFirmata. https://docs.arduino.cc/libraries/firmata/

---

**Project:** B.E. Electronics and Communication Engineering, Sathyabama Institute of Science and Technology, Chennai (2022)

**Authors:** Roy Carlous C, Vasanth Mathew B

**Guide:** Dr. T. Ravi, M.E., Ph.D., Head of Department, ECE
