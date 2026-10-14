import { test } from "@playwright/test";

import { expectAccessible, SCHEMES, settle, VIEWPORTS } from "../axe";
import { discover } from "./api";

/** axe on every route of the real stack at 1440 and 375 px, light and dark. */
type Ids = Awaited<ReturnType<typeof discover>>;
const ROUTES: { name: string; path: (ids: Ids) => string | null }[] = [
  { name: "home", path: () => "/" },
  { name: "line", path: () => "/line" },
  { name: "investigations", path: () => "/investigations" },
  { name: "an investigation", path: (ids) => (ids.investigation ? `/investigations/${ids.investigation}` : null) },
  { name: "a unit", path: (ids) => `/units/${ids.unit}` },
  { name: "wafer lab with a wafer", path: (ids) => `/wafers?wafer=${ids.wafer}` },
  { name: "lots", path: () => "/lots" },
  { name: "a lot", path: (ids) => `/lots/${ids.lot}` },
  { name: "sensor health", path: () => "/sensors?sensor=S060" },
  { name: "work orders", path: () => "/work-orders" },
  { name: "a work order", path: (ids) => (ids.workOrder ? `/work-orders/${ids.workOrder}` : null) },
  { name: "models", path: () => "/models" },
  { name: "methods", path: () => "/methods" },
];

for (const viewport of VIEWPORTS) {
  for (const scheme of SCHEMES) {
    test.describe(`${viewport.name} px, ${scheme}`, () => {
      test.use({ viewport: { width: viewport.width, height: viewport.height }, colorScheme: scheme });
      let ids: Ids;
      test.beforeAll(async ({ request }) => {
        ids = await discover(request);
      });
      for (const route of ROUTES) {
        test(`axe ${route.name}`, async ({ page }) => {
          const path = route.path(ids);
          test.skip(path === null, "no such record in this database");
          await settle(page, path!);
          await expectAccessible(page, `${viewport.name} ${scheme} ${path}`);
        });
      }
    });
  }
}
