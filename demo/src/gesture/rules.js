// Finger-state rules on the 21 MediaPipe hand landmarks, a port of
// gesturecontrol/rules.py. See that file for the description of the hand
// frame (up axis wrist -> middle MCP, side axis towards the thumb, palm
// width as the unit of length) and of the hysteresis latches.

export const WRIST = 0;
export const THUMB_TIP = 4;
export const INDEX_MCP = 5;
export const MIDDLE_MCP = 9;
export const PINKY_MCP = 17;
export const FINGER_TIP_PIP = [[8, 6], [12, 10], [16, 14], [20, 18]];
export const NUM_LANDMARKS = 21;
export const FINGER_NAMES = ["thumb", "index", "middle", "ring", "pinky"];

const sub = (a, b) => [a[0] - b[0], a[1] - b[1]];
const dot = (a, b) => a[0] * b[0] + a[1] * b[1];
const length = (a) => Math.sqrt(a[0] * a[0] + a[1] * a[1]);

// Returns {up, side, palmWidth} or null when the geometry is too small to trust.
export function handFrame(points, minPalmWidth) {
  if (points.length !== NUM_LANDMARKS) {
    throw new Error(`expected ${NUM_LANDMARKS} landmarks, got ${points.length}`);
  }
  const upVec = sub(points[MIDDLE_MCP], points[WRIST]);
  const upLen = length(upVec);
  const across = sub(points[INDEX_MCP], points[PINKY_MCP]);
  const palmWidth = length(across);
  if (palmWidth < minPalmWidth || upLen < minPalmWidth) return null;
  const up = [upVec[0] / upLen, upVec[1] / upLen];
  let side = [-up[1], up[0]];
  if (dot(across, side) < 0.0) side = [-side[0], -side[1]];
  return { up, side, palmWidth };
}

// Tip-beyond-PIP distance along the up axis, in palm widths, for index..pinky.
export function fingerExtensions(points, frame) {
  return FINGER_TIP_PIP.map(([tip, pip]) => dot(sub(points[tip], points[pip]), frame.up) / frame.palmWidth);
}

// Thumb tip offset from the index MCP along the side axis, in palm widths.
export function thumbExtension(points, frame) {
  return dot(sub(points[THUMB_TIP], points[INDEX_MCP]), frame.side) / frame.palmWidth;
}

export function latch(wasUp, value, band) {
  if (wasUp) return value > band.lower_threshold;
  return value > band.raise_threshold;
}

export function measure(points, config) {
  const frame = handFrame(points, config.min_palm_width_px);
  if (frame === null) return null;
  return { thumb: thumbExtension(points, frame), fingers: fingerExtensions(points, frame), palmWidth: frame.palmWidth };
}

export class FingerClassifier {
  constructor(config) {
    this.config = config;
    this.states = [false, false, false, false, false];
  }

  reset() {
    this.states = [false, false, false, false, false];
  }

  // Returns the number of extended fingers (0-5) or -1 for unusable landmarks.
  update(points) {
    const m = measure(points, this.config);
    if (m === null) {
      this.reset();
      return -1;
    }
    this.states[0] = latch(this.states[0], m.thumb, this.config.thumb);
    for (let i = 0; i < 4; i++) {
      this.states[i + 1] = latch(this.states[i + 1], m.fingers[i], this.config.finger);
    }
    return this.states.reduce((n, up) => n + (up ? 1 : 0), 0);
  }
}

const RELAY_MAPPING = {
  0: [false, false, false, false],
  1: [true, false, false, false],
  2: [false, true, false, false],
  3: [false, false, true, false],
  4: [false, false, false, true],
  5: [true, true, true, true],
};

export function relayStatesForCount(count) {
  return [...(RELAY_MAPPING[count] ?? [false, false, false, false])];
}
