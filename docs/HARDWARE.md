# Hardware Guide

## Components

### Arduino UNO (ATmega328P)

| Specification | Value |
|--------------|-------|
| Microcontroller | ATmega328P (8-bit AVR) |
| Operating Voltage | 5V |
| Input Voltage | 7–12V (recommended) |
| Digital I/O Pins | 14 (6 PWM capable) |
| Analog Input Pins | 6 |
| Flash Memory | 32 KB (0.5 KB bootloader) |
| Clock Speed | 16 MHz |
| USB | Type-B connector |

The Arduino runs **StandardFirmata**, a firmware that exposes all GPIO pins to the host computer via the Firmata serial protocol. No custom Arduino code is needed — all logic runs in Python on the host.

### 4-Channel Relay Module (with Optocoupler)

| Specification | Value |
|--------------|-------|
| Channels | 4 (independent) |
| Trigger | Active LOW (5V logic) |
| Max Load | 10A @ 250VAC / 10A @ 30VDC |
| Isolation | Optocoupler (no direct electrical connection to controller) |
| Input Pins | IN1, IN2, IN3, IN4, VCC, GND |

Each relay provides **COM** (Common), **NO** (Normally Open), and **NC** (Normally Closed) terminals. The optocoupler ensures the Arduino is electrically isolated from the mains-voltage relay coil circuit.

### Relay Driver: ULN2003

The ULN2003 is a 16-pin Darlington transistor array IC that provides the current amplification needed to drive relay coils from low-current microcontroller GPIO pins. Each of its 7 channels can sink up to 500mA.

## Circuit Diagram

```
                                    ┌───────────────────┐
                                    │  4-Channel Relay   │
┌──────────────┐                    │     Module         │
│              │  Pin 7 ──────────▶ │ IN1 ──▶ Relay 1 ──▶ Load 1
│              │  Pin 6 ──────────▶ │ IN2 ──▶ Relay 2 ──▶ Load 2
│  Arduino UNO │  Pin 5 ──────────▶ │ IN3 ──▶ Relay 3 ──▶ Load 3
│  (ATmega328P)│  Pin 4 ──────────▶ │ IN4 ──▶ Relay 4 ──▶ Load 4
│              │                    │                    │
│              │  5V   ──────────▶ │ VCC                │
│              │  GND  ──────────▶ │ GND                │
└──────┬───────┘                    └───────────────────┘
       │ USB
       │
┌──────▼───────┐
│   PC/Laptop  │
│   (Python +  │
│    Webcam)   │
└──────────────┘
```

## Communication: Firmata Protocol

Firmata is a serial communication protocol based on the MIDI message format (8-bit commands, 7-bit data). It allows the host computer to directly read/write Arduino pins without uploading custom sketches.

**Setup:** Upload `StandardFirmata` via Arduino IDE → File → Examples → Firmata → StandardFirmata.

**Python side:** The `pyfirmata` library handles serial framing and pin abstraction:

```python
import pyfirmata
board = pyfirmata.Arduino('/dev/ttyACM0')
relay = board.get_pin('d:7:o')  # Digital pin 7, Output mode
relay.write(1)  # HIGH → Relay ON
relay.write(0)  # LOW  → Relay OFF
```

## Power Supply

- Arduino is powered via USB from the host computer (5V, 500mA).
- Relay module VCC is powered from Arduino's 5V pin.
- For loads exceeding the USB power budget, use an external 5V supply for the relay module (connect to JD-VCC with jumper removed).
