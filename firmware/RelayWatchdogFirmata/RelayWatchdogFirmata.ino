/*
  RelayWatchdogFirmata

  A small Firmata sketch for the GestureControl relay board with one addition
  over StandardFirmata: a host-loss watchdog. The host sends a heartbeat
  SysEx message (command 0x01) every 250 ms. If no heartbeat arrives for
  the configured timeout (1000 ms unless the host says otherwise), every
  relay pin is driven to its de-energised level and further writes to the
  relay pins are ignored until a heartbeat arrives again. A host that
  crashes, is killed, or loses its USB link therefore cannot leave a load
  switched on for longer than the timeout.

  Messages understood:
    SET_PIN_MODE, DIGITAL_MESSAGE      as in StandardFirmata (digital only)
    SysEx 0x01 (heartbeat)             no payload
    SysEx 0x02 (watchdog config)       [active_low, timeout_lo7, timeout_hi7]
                                       answered with SysEx 0x02 [1]
    SysEx 0x79 (report firmware)       handled by the Firmata library
    SYSTEM_RESET                       releases all relays

  Relay pins (Arduino pin -> module input): 7 -> IN1, 6 -> IN2, 5 -> IN3,
  4 -> IN4. The default polarity is active-low (relay on when the pin is
  LOW), matching the host default; the host sends its own setting in the
  config message so the two sides always agree on which level is safe.

  Requires the Firmata library that ships with the Arduino IDE (2.5 or
  later). Upload it like any sketch; the host program then uses it exactly
  as it would use StandardFirmata.
*/

#include <Firmata.h>

static const byte RELAY_PINS[4] = {7, 6, 5, 4};
static const byte SYSEX_HEARTBEAT = 0x01;
static const byte SYSEX_WATCHDOG_CONFIG = 0x02;
static const unsigned long DEFAULT_TIMEOUT_MS = 1000;

static bool activeLow = true;
static unsigned long timeoutMs = DEFAULT_TIMEOUT_MS;
static unsigned long lastHeartbeat = 0;
static bool armed = false;    // a heartbeat has been seen since reset
static bool tripped = false;  // the watchdog has released the relays

static int safeLevel() {
  return activeLow ? HIGH : LOW;
}

static bool isRelayPin(byte pin) {
  for (byte i = 0; i < 4; i++) {
    if (RELAY_PINS[i] == pin) return true;
  }
  return false;
}

static void releaseAllRelays() {
  for (byte i = 0; i < 4; i++) {
    digitalWrite(RELAY_PINS[i], safeLevel());
    Firmata.setPinState(RELAY_PINS[i], safeLevel());
  }
}

static void initRelayPin(byte pin) {
  // Set the level before switching the pin to output so it never passes
  // through the energised level (on AVR this enables the pull-up first).
  pinMode(pin, INPUT);
  digitalWrite(pin, safeLevel());
  pinMode(pin, OUTPUT);
  Firmata.setPinMode(pin, OUTPUT);
  Firmata.setPinState(pin, safeLevel());
}

static void setPinModeCallback(byte pin, int mode) {
  if (isRelayPin(pin)) {
    // Relay pins are always outputs and keep their current level.
    return;
  }
  if (!IS_PIN_DIGITAL(pin)) return;
  switch (mode) {
    case INPUT:
      pinMode(PIN_TO_DIGITAL(pin), INPUT);
      Firmata.setPinMode(pin, INPUT);
      break;
    case PIN_MODE_PULLUP:
      pinMode(PIN_TO_DIGITAL(pin), INPUT_PULLUP);
      Firmata.setPinMode(pin, PIN_MODE_PULLUP);
      break;
    case OUTPUT:
      pinMode(PIN_TO_DIGITAL(pin), OUTPUT);
      Firmata.setPinMode(pin, OUTPUT);
      break;
    default:
      Firmata.sendString("RelayWatchdogFirmata: unsupported pin mode");
      break;
  }
}

static void digitalWriteCallback(byte port, int value) {
  for (byte bit = 0; bit < 8; bit++) {
    byte pin = port * 8 + bit;
    if (!IS_PIN_DIGITAL(pin)) continue;
    if (Firmata.getPinMode(pin) != OUTPUT) continue;
    if (isRelayPin(pin) && tripped) continue;  // ignored until the host is back
    int level = (value >> bit) & 0x01;
    digitalWrite(PIN_TO_DIGITAL(pin), level);
    Firmata.setPinState(pin, level);
  }
}

static void sendWatchdogAck() {
  Firmata.write(START_SYSEX);
  Firmata.write(SYSEX_WATCHDOG_CONFIG);
  Firmata.write(1);
  Firmata.write(END_SYSEX);
}

static void sysexCallback(byte command, byte argc, byte *argv) {
  switch (command) {
    case SYSEX_HEARTBEAT:
      lastHeartbeat = millis();
      armed = true;
      if (tripped) {
        tripped = false;
        Firmata.sendString("watchdog: heartbeat resumed");
      }
      break;
    case SYSEX_WATCHDOG_CONFIG:
      if (argc >= 3) {
        activeLow = argv[0] != 0;
        timeoutMs = (unsigned long)argv[1] | ((unsigned long)argv[2] << 7);
        if (timeoutMs == 0) timeoutMs = DEFAULT_TIMEOUT_MS;
      }
      lastHeartbeat = millis();
      armed = true;
      tripped = false;
      sendWatchdogAck();
      break;
    default:
      break;
  }
}

static void systemResetCallback() {
  releaseAllRelays();
  armed = false;
  tripped = false;
}

void setup() {
  for (byte i = 0; i < 4; i++) {
    initRelayPin(RELAY_PINS[i]);
  }
  Firmata.setFirmwareNameAndVersion("RelayWatchdogFirmata.ino", 1, 0);
  Firmata.attach(SET_PIN_MODE, setPinModeCallback);
  Firmata.attach(DIGITAL_MESSAGE, digitalWriteCallback);
  Firmata.attach(START_SYSEX, sysexCallback);
  Firmata.attach(SYSTEM_RESET, systemResetCallback);
  Firmata.begin(57600);
}

void loop() {
  while (Firmata.available()) {
    Firmata.processInput();
  }
  if (armed && !tripped && (millis() - lastHeartbeat) > timeoutMs) {
    tripped = true;
    releaseAllRelays();
    Firmata.sendString("watchdog: no heartbeat, relays released");
  }
}
