// The classification pipeline: One Euro filtering, finger rules with
// hysteresis and N-frame confirmation. A port of gesturecontrol/pipeline.py
// and gesturecontrol/stabilizer.py, checked against the same golden vectors.

import rules from "./rules.json";
import { LandmarkFilter } from "./oneEuro.js";
import { FingerClassifier, relayStatesForCount } from "./rules.js";

export const DEFAULT_RULES = rules;

export class CountStabilizer {
  constructor(confirmFrames) {
    if (confirmFrames < 1) throw new Error("confirmFrames must be at least 1");
    this.confirmFrames = confirmFrames;
    this.confirmed = -1;
    this.candidate = -1;
    this.run = 0;
  }

  reset() {
    this.candidate = -1;
    this.run = 0;
  }

  update(rawCount) {
    if (rawCount < 0) {
      this.reset();
      return { confirmed: this.confirmed, changed: false, runLength: 0 };
    }
    if (rawCount === this.candidate) {
      this.run += 1;
    } else {
      this.candidate = rawCount;
      this.run = 1;
    }
    let changed = false;
    if (this.run >= this.confirmFrames && this.candidate !== this.confirmed) {
      this.confirmed = this.candidate;
      changed = true;
    }
    return { confirmed: this.confirmed, changed, runLength: this.run };
  }
}

export class GesturePipeline {
  constructor(width, height, config = DEFAULT_RULES) {
    if (!(width > 0 && height > 0)) throw new Error("frame size must be positive");
    this.width = width;
    this.height = height;
    this.config = config;
    this.filter = new LandmarkFilter(config.filter);
    this.classifier = new FingerClassifier(config);
    this.stabilizer = new CountStabilizer(config.confirm_frames);
  }

  get confirmedCount() {
    return this.stabilizer.confirmed;
  }

  reset() {
    this.filter.reset();
    this.classifier.reset();
    this.stabilizer.reset();
  }

  // landmarks: array of 21 [x, y] in normalised coordinates, or null for no hand.
  // t: timestamp in seconds. Returns the same fields as the Python FrameResult.
  process(landmarks, t) {
    if (landmarks === null || landmarks === undefined) {
      this.reset();
      const c = this.stabilizer.update(-1);
      return {
        handPresent: false,
        rawCount: -1,
        fingerStates: null,
        confirmedCount: c.confirmed,
        changed: false,
        relays: relayStatesForCount(c.confirmed),
        pointsPx: null,
      };
    }
    const filtered = this.filter.filter(landmarks, t);
    const pointsPx = filtered.map(([x, y]) => [x * this.width, y * this.height]);
    const raw = this.classifier.update(pointsPx);
    const c = this.stabilizer.update(raw);
    return {
      handPresent: true,
      rawCount: raw,
      fingerStates: raw >= 0 ? [...this.classifier.states] : null,
      confirmedCount: c.confirmed,
      changed: c.changed,
      relays: relayStatesForCount(c.confirmed),
      pointsPx,
    };
  }
}
