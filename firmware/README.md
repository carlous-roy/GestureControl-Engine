# Firmware

`RelayWatchdogFirmata/RelayWatchdogFirmata.ino` is a Firmata sketch with a
host-loss watchdog. It is optional: the host program also works with the
StandardFirmata sketch from the Arduino IDE examples, but then nothing on
the board notices when the host dies, and a relay that was on stays on
until the Arduino loses power.

## What the watchdog does

- The host sends a heartbeat (Firmata SysEx command `0x01`) every 250 ms.
- If no heartbeat arrives for the timeout (1000 ms by default), the sketch
  drives all four relay pins to their de-energised level and ignores writes
  to those pins until the heartbeat resumes. The host re-sends its relay
  states after any gap, so a stalled-but-alive host recovers by itself.
- At connect the host sends a configuration message (SysEx `0x02`) with its
  polarity and timeout, and the sketch acknowledges it. The host logs whether
  the acknowledgement arrived, so you can see in the log which firmware is
  on the board.
- On reset the relay pins are driven to the de-energised level before they
  are switched to outputs, so nothing clicks at power-up or when the serial
  port opens. With StandardFirmata the pins start as inputs and pass through
  LOW when the host sets them to output, which briefly energises an
  active-low module.

## Install

1. Arduino IDE: File > Open > `RelayWatchdogFirmata.ino`. The Firmata
   library is bundled with the IDE (2.5 or later is needed for
   `setPinMode`/`setPinState`).
2. Select Arduino UNO and the port, then Upload.
3. Run the host as usual: `gesturecontrol --port /dev/ttyACM0`. The log
   should show `Firmware: RelayWatchdogFirmata.ino (1, 0)` and
   `Watchdog firmware acknowledged`.

The pin assignment (7, 6, 5, 4 to IN1..IN4) and the default polarity
(active-low) match `gesturecontrol/config.py`. If you change one, change the
other.

## What it does not cover

The watchdog runs on the Arduino, so it cannot help if the Arduino itself
hangs or loses power while a relay is closed: a mechanical relay keeps its
state only while the coil is driven, so loss of board power releases it,
but a hung microcontroller with power does not. There is no read-back of
the relay contacts either. See the safety section of the main README.

The sketch compiles for `arduino:avr:uno` with Firmata 2.5.9 (CI does this
with arduino-cli on every push). It has not yet been run on a board; the
first hardware run should watch the log lines above and the relay LEDs at
connect, at Ctrl-C, and after pulling the USB cable with a relay on.
