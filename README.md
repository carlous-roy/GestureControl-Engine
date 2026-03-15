# GestureControl Engine

**Real-time hand gesture recognition system for home automation**

Uses computer vision to detect hand gestures (0-5 fingers) via webcam and controls home appliances through an Arduino UNO and 4-channel relay module.

[Live Demo](https://gesture.roycarlous.com) | [Portfolio](https://roycarlous.com)

---

## How It Works

A three-stage pipeline processes each video frame at 30 FPS:

```
Webcam (OpenCV)  -->  MediaPipe Hands (21 landmarks)  -->  Finger Counting  -->  PyFirmata  -->  Arduino  -->  Relays
```

1. **OpenCV** captures video frames from the webcam
2. **MediaPipe Hands** detects 21 3D hand landmarks per frame using a pre-trained neural network
3. **Finger counting algorithm** compares fingertip positions against joint positions to determine how many fingers are raised
4. **PyFirmata** sends digital HIGH/LOW signals to the Arduino over serial USB
5. **Arduino UNO** drives the 4-channel relay module to switch appliances on/off

## Gesture Mapping

| Fingers | Gesture | Action |
|---------|---------|--------|
| 0 | Fist | All appliances OFF |
| 1 | Index finger | Appliance 1 ON |
| 2 | Peace sign | Appliance 2 ON |
| 3 | Three fingers | Appliance 3 ON |
| 4 | Four fingers | Appliance 4 ON |
| 5 | Open hand | All appliances ON |

Relays hold their last state when the hand leaves frame. Show a fist to explicitly turn everything OFF.

## Tech Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Runtime | Python 3.8+ | Application runtime |
| Video | OpenCV | Camera capture and frame processing |
| Hand Tracking | MediaPipe Hands | 21-landmark hand detection |
| Arduino Protocol | PyFirmata | Serial communication with Arduino |
| Microcontroller | Arduino UNO (ATmega328P) | Drives relay coils |
| Switching | 4-Channel Relay Module | Controls mains-voltage appliances |

## Project Structure

```
GestureControl-Engine/
    main.py                      Entry point
    requirements.txt             Python dependencies
    src/
        __init__.py
        hand_detector.py         MediaPipe hand tracking + finger counting
        controller.py            Arduino relay control via PyFirmata
        ui_overlay.py            Real-time status overlay on video feed
    docs/
        ALGORITHM.md             Finger counting algorithm details
        HARDWARE.md              Wiring guide and hardware specs
        TECHNICAL_REPORT.md      Corrected project report
        ORIGINAL_REPORT.pdf      Original B.E. submission (2022)
    tests/
        __init__.py
        test_controller.py       Unit tests for relay controller
    simulation/
        demo.py                  Text-based demo (no webcam needed)
```

## Quick Start

### Software Only (Simulation Mode)

No Arduino required. Runs hand detection and displays simulated relay states.

```bash
git clone https://github.com/carlous-roy/GestureControl-Engine.git
cd GestureControl-Engine
pip install -r requirements.txt
python main.py
```

### With Arduino Hardware

1. Upload **StandardFirmata** to your Arduino via Arduino IDE:
   File > Examples > Firmata > StandardFirmata > Upload

2. Wire the relay module:
   ```
   Arduino Pin 7 --> IN1 (Relay 1)
   Arduino Pin 6 --> IN2 (Relay 2)
   Arduino Pin 5 --> IN3 (Relay 3)
   Arduino Pin 4 --> IN4 (Relay 4)
   Arduino 5V    --> VCC
   Arduino GND   --> GND
   ```

3. Run with your serial port:
   ```bash
   python main.py --port COM6              # Windows
   python main.py --port /dev/ttyACM0      # Linux
   python main.py --port /dev/cu.usbmodem* # macOS
   ```

### CLI Options

```bash
python main.py --camera 1                  # Use external webcam
python main.py --width 1280 --height 720   # Higher resolution
python main.py --no-ui                     # Disable overlay
python main.py --detection-confidence 0.8  # Stricter detection
```

### Controls

- **Q / ESC** — Quit (click the video window first)
- **S** — Save screenshot to `screenshots/`

## Finger Counting Algorithm

**Thumb:** Uses a distance-based approach instead of naive x-axis comparison. Measures the distance from thumb tip (landmark 4) to the index finger MCP (landmark 5), compared against the thumb MCP (landmark 2) to the same reference. The thumb is "up" when the tip is 1.2x farther from the palm than the MCP, plus a wrist-distance extension check.

**Other fingers:** Each fingertip's y-coordinate is compared against its PIP (proximal interphalangeal) joint. A finger is "up" when the tip is above the PIP by at least 15 pixels, preventing jitter on borderline poses.

**Stabilization:** A 3-frame stability window requires the same finger count for 3 consecutive frames before triggering a relay change.

See [docs/ALGORITHM.md](docs/ALGORITHM.md) for the complete breakdown.

## Hardware (~$25 total)

| Component | Cost |
|-----------|------|
| Arduino UNO (or clone) | $5-8 |
| 4-Channel Relay Module (optocoupler) | $3-5 |
| Jumper wires | $2-3 |
| Bulbs + sockets (demo) | $5-10 |
| USB-A to USB-B cable | $2-3 |

See [docs/HARDWARE.md](docs/HARDWARE.md) for the complete wiring guide and safety notes.

## Background

This was my Bachelor's degree project at Sathyabama Institute of Science and Technology, Chennai (2022), done as part of the B.E. Electronics and Communication Engineering program. The original code was lost, so I reconstructed the entire codebase from scratch with improvements to the detection algorithm, code architecture, and documentation.

## License

MIT
