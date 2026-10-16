import type { RunEvent } from "@yield-guardian/contracts";

import {
  SENSORS_ONLY_ID,
  sampleEvents,
  sensorsOnlyEvents,
  snapshotOf,
} from "../../../e2e/story/fixture";

import { glanceOf } from "./glance";
import { pack, unpack, type Packed } from "./packed";

/** As JSON carries it: what the page receives, and what it must unpack to. */
const viaJson = <T>(value: T): T => JSON.parse(JSON.stringify(value)) as T;

describe("the packed form of a stored run", () => {
  const runs = [
    snapshotOf(sampleEvents as RunEvent[]),
    snapshotOf(sensorsOnlyEvents(), SENSORS_ONLY_ID),
  ];

  it("unpacks to the run, field for field", () => {
    for (const run of runs) {
      for (const value of [
        run,
        glanceOf(run, { station: null, focus: null }).run,
        glanceOf(run, { station: 2, focus: { kind: "unit", index: 3 } }).run,
        glanceOf(run, { station: 3, focus: null }).run,
      ]) {
        expect(unpack(viaJson(pack(value)))).toEqual(viaJson(value));
      }
    }
  });

  it("takes less room than the run as plain JSON", () => {
    const glance = glanceOf(runs[0]!, { station: null, focus: null }).run;
    const plain = JSON.stringify(glance).length;
    expect(JSON.stringify(pack(glance)).length).toBeLessThan(plain * 0.8);
  });

  it("writes a list of like objects as columns, and a column of one value once", () => {
    const rows = Array.from({ length: 6 }, (_, i) => ({ index: i, level: "none", top: null }));
    const packed = viaJson(pack({ units: rows })) as unknown as {
      units: { "~rows": string[]; n: number; cols: unknown[] };
    };
    expect(packed.units["~rows"]).toEqual(["index", "level", "top"]);
    expect(packed.units.n).toBe(6);
    expect(packed.units.cols).toEqual([
      [0, 1, 2, 3, 4, 5],
      { "~same": "none", n: 6 },
      { "~same": null, n: 6 },
    ]);
    expect(unpack(packed as unknown as Packed<{ units: typeof rows }>)).toEqual({ units: rows });
  });

  it("keeps lists it cannot pack as they are", () => {
    const value = {
      empty: [],
      short: [{ a: 1 }, { a: 2 }],
      mixed: [{ a: 1 }, { a: 2 }, { b: 3 }, { a: 4 }],
      partly: [{ a: 1 }, { a: 2 }, { a: 3 }, null],
      lists: [[1, 2], [3], [], [4, 4, 4, 4]],
      values: [0, "0", false, null, 1.5],
      nested: [
        { id: "x", tests: [{ q: 0.1 }, { q: 0.2 }, { q: 0.3 }, { q: 0.4 }] },
        { id: "y", tests: [] },
        { id: "z", tests: [{ q: 1 }] },
        { id: "w", tests: [{ q: 0.5 }, { q: 0.5 }, { q: 0.5 }, { q: 0.5 }] },
      ],
      text: "~rows",
    };
    expect(unpack(viaJson(pack(value)))).toEqual(value);
  });
});
