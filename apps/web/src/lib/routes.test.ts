import { describe, expect, it } from "vitest";

import {
  legacyRedirect,
  lineHref,
  lotHref,
  parsePick,
  sensorHref,
  triggerHref,
  unitHref,
  waferHref,
  workOrderHref,
} from "./routes";

const go = (path: string) => {
  const url = new URL(path, "https://yield-guardian.example");
  return legacyRedirect(url.pathname, url.searchParams);
};

describe("legacyRedirect", () => {
  it("sends every v1 page to its v2 place", () => {
    expect(go("/line")).toBe("/");
    expect(go("/wafers")).toBe("/?station=3");
    expect(go("/wafers/lot47542-1")).toBe("/?pick=wafer:lot47542-1");
    expect(go("/lots")).toBe("/?station=3");
    expect(go("/lots/lot47542")).toBe("/?pick=lot:lot47542");
    expect(go("/units/1062")).toBe("/?pick=unit:1062");
    expect(go("/sensors")).toBe("/?station=2");
    expect(go("/work-orders")).toBe("/investigations?tab=work-orders");
    expect(go("/work-orders/WO-000012")).toBe("/investigations?tab=work-orders&order=WO-000012");
    expect(go("/models")).toBe("/how#models");
    expect(go("/methods")).toBe("/how#methods");
    expect(go("/guide")).toBe("/how#guide");
  });

  it("keeps query strings", () => {
    expect(go("/sensors?sensor=S060")).toBe("/?station=2&sensor=S060");
    expect(go("/lots?flagged=1")).toBe("/?station=3&flagged=1");
    expect(go("/units/1062?tab=shap")).toBe("/?pick=unit:1062&tab=shap");
    expect(go("/work-orders?cursor=50")).toBe("/investigations?tab=work-orders&cursor=50");
    expect(go("/methods?x=1")).toBe("/how?x=1#methods");
  });

  it("turns the wafer lab's selected wafer into a pick", () => {
    expect(go("/wafers?wafer=lot47542-1&label=Scratch")).toBe(
      "/?pick=wafer:lot47542-1&label=Scratch",
    );
    // A value that is not a wafer ID stays a plain parameter.
    expect(go("/wafers?wafer=oops")).toBe("/?station=3&wafer=oops");
  });

  it("does not let a v1 parameter override the target's own", () => {
    expect(go("/sensors?station=5")).toBe("/?station=2");
    expect(go("/work-orders?tab=other")).toBe("/investigations?tab=work-orders");
  });

  it("drops Next.js's _rsc cache key and accepts a trailing slash", () => {
    expect(go("/line?_rsc=abc")).toBe("/");
    expect(go("/models/")).toBe("/how#models");
  });

  it("leaves v2 pages and unknown paths alone", () => {
    for (const path of [
      "/",
      "/investigations",
      "/investigations/inv_01jae5x9k3m2q7r8s0t1v2w3x4",
      "/how",
      "/admin",
      "/healthz",
      "/linear",
      "/units",
      "/units/1/2",
    ]) {
      expect(go(path), path).toBeNull();
    }
  });
});

describe("links", () => {
  it("build the v2 addresses the redirects point to", () => {
    expect(lineHref()).toBe("/");
    expect(lineHref({ station: 3 })).toBe("/?station=3");
    expect(unitHref(1062)).toBe(go("/units/1062"));
    expect(waferHref("lot47542-1")).toBe(go("/wafers/lot47542-1"));
    expect(lotHref("lot47542")).toBe(go("/lots/lot47542"));
    expect(sensorHref("S060")).toBe(go("/sensors?sensor=S060"));
    expect(workOrderHref("WO-000012")).toBe(go("/work-orders/WO-000012"));
    expect(workOrderHref("WO-000012", "inv_01jae5x9k3m2q7r8s0t1v2w3x4")).toBe(
      "/investigations/inv_01jae5x9k3m2q7r8s0t1v2w3x4#work-order",
    );
  });

  it("send an investigation's trigger to the Line", () => {
    expect(triggerHref({ kind: "run_alarm", ref: "run_01jae5x9k3m2:AL-3" })).toBe(
      "/?run=run_01jae5x9k3m2",
    );
    expect(triggerHref({ kind: "run_alarm", ref: "nonsense" })).toBeNull();
    expect(triggerHref({ kind: "alarm", ref: "AL-1062-t2" })).toBe("/?pick=unit:1062");
    expect(triggerHref({ kind: "unit", ref: "1062" })).toBe("/?pick=unit:1062");
    expect(triggerHref({ kind: "wafer", ref: "lot47542-1" })).toBe("/?pick=wafer:lot47542-1");
    expect(triggerHref({ kind: "lot", ref: "lot47542" })).toBe("/?pick=lot:lot47542");
    expect(triggerHref({ kind: "alarm", ref: "something-else" })).toBeNull();
  });

  it("parse a pick back", () => {
    expect(parsePick("unit:1062")).toEqual({ kind: "unit", id: 1062 });
    expect(parsePick("wafer:lot47542-1")).toEqual({ kind: "wafer", id: "lot47542-1" });
    expect(parsePick("lot:lot47542")).toEqual({ kind: "lot", id: "lot47542" });
    expect(parsePick("unit:abc")).toBeNull();
    expect(parsePick("wafer:lot47542")).toBeNull();
    expect(parsePick("sensor:S060")).toBeNull();
    expect(parsePick(null)).toBeNull();
  });
});
