// One Euro filter, a port of gesturecontrol/filters.py.
//
// Casiez, G., Roussel, N. and Vogel, D. (2012). "1 Euro Filter: A Simple
// Speed-based Low-pass Filter for Noisy Input in Interactive Systems."
// CHI 2012. https://doi.org/10.1145/2207676.2208639
//
// The operations are written in the same order as the Python version so
// that both produce the same doubles for the same input.

export function smoothingFactor(cutoffHz, dt) {
  const tau = 1.0 / (2.0 * Math.PI * cutoffHz);
  return 1.0 / (1.0 + tau / dt);
}

export class OneEuroFilter {
  constructor(config) {
    this.minCutoffHz = config.min_cutoff_hz;
    this.beta = config.beta;
    this.derivativeCutoffHz = config.derivative_cutoff_hz;
    this.reset();
  }

  reset() {
    this.tPrev = null;
    this.xPrev = 0.0;
    this.dxPrev = 0.0;
  }

  filter(x, t) {
    if (this.tPrev === null) {
      this.tPrev = t;
      this.xPrev = x;
      this.dxPrev = 0.0;
      return x;
    }
    const dt = t - this.tPrev;
    if (dt <= 0.0) {
      // Duplicate or out-of-order timestamp: hold the last estimate.
      return this.xPrev;
    }
    const dx = (x - this.xPrev) / dt;
    const aD = smoothingFactor(this.derivativeCutoffHz, dt);
    const dxHat = aD * dx + (1.0 - aD) * this.dxPrev;

    const cutoff = this.minCutoffHz + this.beta * Math.abs(dxHat);
    const a = smoothingFactor(cutoff, dt);
    const xHat = a * x + (1.0 - a) * this.xPrev;

    this.tPrev = t;
    this.xPrev = xHat;
    this.dxPrev = dxHat;
    return xHat;
  }
}

export class LandmarkFilter {
  constructor(config, numPoints = 21) {
    this.filters = [];
    for (let i = 0; i < numPoints; i++) {
      this.filters.push([new OneEuroFilter(config), new OneEuroFilter(config)]);
    }
  }

  reset() {
    for (const [fx, fy] of this.filters) {
      fx.reset();
      fy.reset();
    }
  }

  // points: array of [x, y]; returns a new array of [x, y].
  filter(points, t) {
    if (points.length !== this.filters.length) {
      throw new Error(`expected ${this.filters.length} points, got ${points.length}`);
    }
    return points.map(([x, y], i) => [this.filters[i][0].filter(x, t), this.filters[i][1].filter(y, t)]);
  }
}
