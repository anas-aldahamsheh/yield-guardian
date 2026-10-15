import { describe, expect, it } from "vitest";

import { lineQuery, parseLineUrl, parsePick } from "./url-state";

const RUN = "run_01m4zc9a4mk6a13y2rvambdcfg";

describe("the Line page's URL", () => {
  it("reads the run, the station, the item and the chosen alarm", () => {
    const state = parseLineUrl(new URLSearchParams(`run=${RUN}&station=2&unit=12&alarm=RA-4`));
    expect(state).toEqual({
      runId: RUN,
      station: 2,
      focus: { kind: "unit", index: 12 },
      alarm: "RA-4",
    });
    expect(lineQuery(state)).toBe(`run=${RUN}&station=2&unit=12&alarm=RA-4`);
  });

  it("keeps a station asked for before there is a run, and nothing else", () => {
    const state = parseLineUrl(new URLSearchParams("station=3&unit=2&alarm=RA-1"));
    expect(state).toEqual({ runId: null, station: 3, focus: null, alarm: null });
    expect(lineQuery(state)).toBe("station=3");
  });

  it("drops values that are not well formed", () => {
    const state = parseLineUrl(new URLSearchParams(`run=${RUN}&station=9&wafer=x&alarm=AL-1`));
    expect(state).toEqual({ runId: RUN, station: null, focus: null, alarm: null });
    expect(parseLineUrl(new URLSearchParams("run=nope")).runId).toBeNull();
  });

  it("turns an old unit, wafer or lot link into the run it asks for", () => {
    expect(parsePick(new URLSearchParams("pick=unit:1062"))).toEqual({
      source: "pick",
      unit_ids: [1062],
      wafer_ids: [],
      lot: null,
    });
    expect(parsePick(new URLSearchParams("pick=wafer:lot47542-1"))).toEqual({
      source: "pick",
      unit_ids: [],
      wafer_ids: ["lot47542-1"],
      lot: null,
    });
    expect(parsePick(new URLSearchParams("pick=lot:lot47542"))).toEqual({
      source: "pick",
      unit_ids: [],
      wafer_ids: [],
      lot: "lot47542",
    });
    expect(parsePick(new URLSearchParams("pick=sensor:S001"))).toBeNull();
  });
});
