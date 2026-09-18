# Hardware

## Parts

- Arduino UNO (ATmega328P, 5 V logic, 14 digital pins, USB-B), or a clone.
- A 5 V four-channel relay module with optocoupler inputs. Each channel has
  COM, NO (normally open) and NC (normally closed) contacts; the relays on
  these boards are typically rated 10 A at 250 V AC. Check the rating
  printed on the relays you have.
- Jumper wires, a USB-A to USB-B cable, and loads for the demonstration.

## Wiring

```
Arduino UNO                 4-channel relay module
  pin 7  ─────────────────►  IN1   (relay 1)
  pin 6  ─────────────────►  IN2   (relay 2)
  pin 5  ─────────────────►  IN3   (relay 3)
  pin 4  ─────────────────►  IN4   (relay 4)
  5V     ─────────────────►  VCC
  GND    ─────────────────►  GND
     │ USB
  computer with the webcam
```

The pin numbers are `RELAY_PINS` in `gesturecontrol/config.py` and
`RELAY_PINS` in `firmware/RelayWatchdogFirmata/RelayWatchdogFirmata.ino`;
change both if you rewire.

Loads: COM to the supply, NO to the load, so that a released relay means
"off". Never use NC for a load in this project: every safety measure in the
software assumes that a de-energised relay is an open circuit.

## Trigger level: check it before connecting a load

The software writes a pin level for "on" and the opposite level for "off",
so it has to know which level your module expects. The common 5 V
opto-isolated modules are low-level trigger: each IN pin sits at VCC
through the optocoupler's LED, and pulling IN to GND lights the LED and
energises the relay. Some boards switch on HIGH instead, and some have a
jumper to choose. The default here is active-low; `--active-high` selects
the other kind, and the watchdog firmware is told the same choice at
connect so that both sides agree on the safe level.

To check a module with nothing but the Arduino's 5 V and GND connected to
VCC and GND (no loads):

1. Leave IN1 unconnected. The relay 1 LED should be off and the relay
   released.
2. Connect IN1 to GND with a jumper. If the LED lights and the relay
   clicks, the module is active-low (the default). If nothing happens,
   connect IN1 to 5 V instead; if it clicks now, the module is active-high
   and you need `--active-high`.

Then run without loads and watch the LEDs: at connect all four should be
off, a fist should keep them off, one finger should light relay 1 only,
and `Ctrl-C` should switch everything off. Only then wire the loads.

The original 2022 build drove the module through a ULN2003 driver, which
inverts the signal; the 2026 code drives the module inputs directly. If
you keep a driver stage, its inversion changes the effective polarity.

## Firmata

The Arduino runs a Firmata sketch and the host does all the logic. Two
sketches work:

- `StandardFirmata` from the Arduino IDE (File > Examples > Firmata >
  StandardFirmata). The host controls the pins; nothing on the board
  reacts if the host dies.
- `firmware/RelayWatchdogFirmata`, a digital-only Firmata sketch with a
  host-loss watchdog: the host sends a heartbeat every 250 ms, and the
  board releases every relay pin if no heartbeat arrives for one second.
  See `firmware/README.md`.

On the host, `pyfirmata2` (the maintained fork; the original `pyfirmata`
does not import on Python 3.11 and later) opens the port:

```python
import pyfirmata2

board = pyfirmata2.Arduino("/dev/ttyACM0")
relay1 = board.get_pin("d:7:o")   # digital pin 7, output
relay1.write(0)                    # active-low module: LOW energises the relay
relay1.write(1)                    # HIGH releases it
board.exit()
```

`gesturecontrol/controller.py` wraps this with polarity, the switching
interval, reconnect, cleanup and the heartbeat.

Things to expect at connect:

- Opening the serial port resets the UNO. `pyfirmata2` waits five seconds
  for the board to come back before it returns, so `--port` runs take about
  five seconds to start.
- With `StandardFirmata`, the pins start as inputs after the reset. When
  the host sets them to outputs they pass through LOW before the host's
  first "off" write arrives, which energises an active-low relay for a few
  milliseconds; you may hear one click. The watchdog sketch avoids this by
  driving the safe level before making the pins outputs.
- The host asks the board for its firmware name and logs it, and logs
  whether the watchdog acknowledged its configuration. If neither message
  arrives, the log says so; check that a Firmata sketch is on the board.

## Power

- The Arduino is powered from the USB port (5 V, up to 500 mA).
- The relay module's VCC comes from the Arduino's 5 V pin. Four energised
  relay coils draw roughly 70 to 90 mA each on the common modules, so
  switching all four on from USB power is at the limit of what a laptop
  port provides comfortably. Modules with a `JD-VCC` jumper let you feed
  the coils from a separate 5 V supply: remove the jumper, connect the
  supply to `JD-VCC` and GND, and keep VCC on the Arduino's 5 V for the
  optocoupler side.

## Safety

The relay contacts switch whatever they are wired to. For mains loads:
enclosure, no exposed terminals, correct conductor sizes, and a fuse or
breaker on the switched circuit. Use low-voltage loads (5 V or 12 V lamps)
while developing.

What the software guarantees and what it cannot is set out in the README's
"Safety and residual risk" section. The short version: relays are released
on every controlled exit; only the watchdog sketch covers an uncontrolled
host death; nothing reads the contacts back.
