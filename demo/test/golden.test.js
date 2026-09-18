// The JavaScript port must reproduce fixtures/golden_vectors.json frame by
// frame, exactly as the Python pipeline does (tests/test_golden_vectors.py).
import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { GesturePipeline, DEFAULT_RULES } from "../src/gesture/pipeline.js";
import { measure, relayStatesForCount } from "../src/gesture/rules.js";

const here = dirname(fileURLToPath(import.meta.url));
const golden = JSON.parse(readFileSync(join(here, "golden_vectors.json"), "utf8"));

const bits = (flags) => flags.map((f) => (f ? "1" : "0")).join("");

describe("golden vectors", () => {
  it("carry the same rules the demo loads", () => {
    expect(golden.rules).toEqual(DEFAULT_RULES);
  });

  for (const seq of golden.sequences) {
    it(`${seq.name}: ${seq.description}`, () => {
      const pipeline = new GesturePipeline(seq.width, seq.height, golden.rules);
      seq.frames.forEach((frame, i) => {
        const want = seq.expected[i];
        const r = pipeline.process(frame, i / seq.fps);
        expect(
          { hand: r.handPresent, raw: r.rawCount, confirmed: r.confirmedCount, changed: r.changed, relays: bits(r.relays), fingers: r.fingerStates === null ? null : bits(r.fingerStates) },
          `${seq.name} frame ${i}`,
        ).toEqual({ hand: want.hand, raw: want.raw, confirmed: want.confirmed, changed: want.changed, relays: want.relays, fingers: want.fingers });
        if (r.pointsPx === null) {
          expect(want.sum_px).toBeNull();
        } else {
          const sum = r.pointsPx.reduce((acc, [x, y]) => acc + x + y, 0);
          expect(Math.abs(sum - want.sum_px)).toBeLessThan(1e-5);
        }
      });
    });
  }
});

describe("rules", () => {
  it("map counts to relays like the engine", () => {
    expect(relayStatesForCount(0)).toEqual([false, false, false, false]);
    expect(relayStatesForCount(3)).toEqual([false, false, true, false]);
    expect(relayStatesForCount(5)).toEqual([true, true, true, true]);
    expect(relayStatesForCount(-1)).toEqual([false, false, false, false]);
  });

  it("report unusable geometry as null", () => {
    const tiny = Array.from({ length: 21 }, () => [320, 240]);
    expect(measure(tiny, DEFAULT_RULES)).toBeNull();
  });
});
