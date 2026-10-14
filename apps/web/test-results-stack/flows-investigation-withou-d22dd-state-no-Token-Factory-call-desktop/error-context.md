# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: flows.spec.ts >> investigation without a key: not-configured state, no Token Factory call
- Location: e2e/stack/flows.spec.ts:134:1

# Error details

```
Error: expect(received).toBe(expected) // Object.is equality

Expected: 503
Received: 202
```

# Page snapshot

```yaml
- generic [active] [ref=f1e1]:
  - link "Skip to content" [ref=f1e2] [cursor=pointer]:
    - /url: "#main"
  - banner [ref=f1e3]:
    - generic [ref=f1e4]:
      - link "Yield Guardian" [ref=f1e5] [cursor=pointer]:
        - /url: /
      - navigation "Main" [ref=f1e19]:
        - list [ref=f1e20]:
          - listitem [ref=f1e21]:
            - link "Line" [ref=f1e22] [cursor=pointer]:
              - /url: /line
          - listitem [ref=f1e23]:
            - link "Investigations" [ref=f1e24] [cursor=pointer]:
              - /url: /investigations
          - listitem [ref=f1e25]:
            - link "Wafer lab" [ref=f1e26] [cursor=pointer]:
              - /url: /wafers
          - listitem [ref=f1e27]:
            - link "Lots" [ref=f1e28] [cursor=pointer]:
              - /url: /lots
          - listitem [ref=f1e29]:
            - link "Sensor health" [ref=f1e30] [cursor=pointer]:
              - /url: /sensors
          - listitem [ref=f1e31]:
            - link "Work orders" [ref=f1e32] [cursor=pointer]:
              - /url: /work-orders
          - listitem [ref=f1e33]:
            - link "Models" [ref=f1e34] [cursor=pointer]:
              - /url: /models
          - listitem [ref=f1e35]:
            - link "Methods" [ref=f1e36] [cursor=pointer]:
              - /url: /methods
          - listitem [aria-hidden]
      - generic [ref=f1e37]:
        - link "Line replay at unit 624 of 1567. Open the line." [ref=f1e38] [cursor=pointer]:
          - /url: /line
          - generic [ref=f1e40]:
            - text: Unit 624
            - generic [ref=f1e41]: of 1,567
        - button "Ask" [ref=f1e43]
        - button "Choose the colour theme" [ref=f1e44]
        - button "Engineer" [ref=f1e45]
  - main [ref=f1e48]:
    - generic [ref=f1e49]:
      - link "All investigations" [ref=f1e50] [cursor=pointer]:
        - /url: /investigations
      - generic [ref=f1e51]:
        - generic [ref=f1e52]:
          - heading "Unit 618" [level=1] [ref=f1e53]
          - generic [ref=f1e55]:
            - generic [ref=f1e56]: Failed
            - generic [ref=f1e58]:
              - text: From unit
              - link "618" [ref=f1e59] [cursor=pointer]:
                - /url: /units/618
            - generic [ref=f1e60]: Started 2026-10-14 13:06
        - button "Replay the run" [ref=f1e62]
      - status [ref=f1e63]:
        - generic [ref=f1e69]:
          - paragraph [ref=f1e70]: Not ready yet
          - generic [ref=f1e71]: No investigator is configured on this server, so the investigation could not run.
      - generic [ref=f1e72]:
        - generic [ref=f1e73]:
          - generic [ref=f1e75]:
            - heading "Report" [level=2] [ref=f1e76]
            - paragraph [ref=f1e77]: Written by a language model from the evidence only. Numbers link to the value they came from.
          - paragraph [ref=f1e79]: This run ended without a report.
        - generic [ref=f1e80]:
          - generic [ref=f1e81]:
            - generic [ref=f1e83]:
              - heading "Run" [level=2] [ref=f1e84]
              - paragraph [ref=f1e85]: .
            - paragraph [ref=f1e87]: No steps were recorded.
          - generic [ref=f1e89]:
            - generic [ref=f1e91]:
              - heading "Evidence" [level=2] [ref=f1e92]
              - paragraph [ref=f1e93]: Tool results exactly as stored. The report may cite only these.
            - paragraph [ref=f1e95]: No evidence yet. Each tool result is stored here as it arrives.
  - contentinfo [ref=f1e96]:
    - generic [ref=f1e97]:
      - paragraph [ref=f1e98]:
        - text: "Plant data: SECOM (UCI Machine Learning Repository). Wafer maps: WM-811K (MIR Lab, National Tsing Hua University). Findings are associations in historical data, not causes."
        - link "Methods and limitations" [ref=f1e99] [cursor=pointer]:
          - /url: /methods
      - generic [ref=f1e100]:
        - generic [ref=f1e101]:
          - term [ref=f1e102]: Version
          - definition [ref=f1e103]: 0.1.0 (2cea140)
        - generic [ref=f1e104]:
          - term [ref=f1e105]: SECOM models
          - definition [ref=f1e106]: v1, checksums verified
        - generic [ref=f1e107]:
          - term [ref=f1e108]: Wafer models
          - definition [ref=f1e109]: v1, checksums verified
  - region "Notifications alt+T":
    - list:
      - listitem [ref=f1e110]:
        - generic [ref=f1e115]:
          - generic [ref=f1e116]: Signed in as engineer
          - generic [ref=f1e117]: You can now start investigations, approve or reject reports and ask questions.
  - alert [ref=f1e118]: Unit 618
```

# Test source

```ts
  45  |   const table = page.getByRole("table", { name: "Measured results with confidence intervals" });
  46  |   await expect(table.locator("tbody tr")).toHaveCount(results.length);
  47  |   for (const r of measured) {
  48  |     const row = table.getByRole("row").filter({ has: page.getByRole("rowheader", { name: r.label }) });
  49  |     await expect(row).toHaveCount(1);
  50  |     await expect(row).not.toContainText("Not measured yet");
  51  |   }
  52  |   expect(problems).toEqual([]);
  53  | });
  54  | 
  55  | test("line: goes live over the WebSocket and units arrive", async ({ page }) => {
  56  |   const problems = watch(page);
  57  |   const frames: string[] = [];
  58  |   page.on("websocket", (ws) => ws.on("framereceived", (f) => typeof f.payload === "string" && frames.push(f.payload)));
  59  | 
  60  |   await page.goto("/line");
  61  |   await expect(page.getByRole("status").filter({ hasText: "Live" })).toBeVisible({ timeout: 45_000 });
  62  |   await expect(page.getByRole("heading", { name: "Control charts (FDC)" })).toBeVisible();
  63  |   const units = page.getByRole("table", { name: /Recent units/ }).locator("tbody tr");
  64  |   await expect(units.first()).toBeVisible();
  65  |   // A unit event arrives over the socket after the snapshot.
  66  |   await expect.poll(() => frames.filter((f) => f.includes('"unit"')).length, { timeout: 60_000 }).toBeGreaterThan(1);
  67  |   expect(problems).toEqual([]);
  68  | });
  69  | 
  70  | test("unit: page with its control-chart contributions", async ({ page }) => {
  71  |   const problems = watch(page);
  72  |   await page.goto(`/units/${ids.unit}`);
  73  |   await expect(page.locator("h1")).toHaveText(`Unit ${ids.unit.toLocaleString("en-US")}`);
  74  |   await expect(page.getByRole("heading", { name: "Sensors behind the control-chart statistic" })).toBeVisible();
  75  |   await expect(page.getByRole("heading", { name: "Alarms and investigations" })).toBeVisible();
  76  |   await expect(page.getByText("The API did not answer")).toHaveCount(0);
  77  |   expect(problems).toEqual([]);
  78  | });
  79  | 
  80  | test("wafer lab: list and a selected wafer", async ({ page }) => {
  81  |   const problems = watch(page);
  82  |   await page.goto(`/wafers?wafer=${ids.wafer}`);
  83  |   await expect(page.locator("h1")).toHaveText("Wafer lab");
  84  |   await expect(page.getByRole("heading", { name: `Wafer ${ids.wafer}` })).toBeVisible();
  85  |   await expect(page.getByRole("heading", { name: "Most similar wafers" })).toBeVisible();
  86  |   expect(problems).toEqual([]);
  87  | });
  88  | 
  89  | test("lot: the stack and the pattern test", async ({ page }) => {
  90  |   const problems = watch(page);
  91  |   await page.goto(`/lots/${ids.lot}`);
  92  |   await expect(page.locator("h1")).toHaveText(`Lot ${ids.lot}`);
  93  |   await expect(page.getByRole("heading", { name: "The lot as a stack" })).toBeVisible();
  94  |   await expect(page.getByRole("heading", { name: "Patterns against the expected rate" })).toBeVisible();
  95  |   expect(problems).toEqual([]);
  96  | });
  97  | 
  98  | test("sensor health: field, a sensor and the groups", async ({ page }) => {
  99  |   const problems = watch(page);
  100 |   await page.goto("/sensors?sensor=S060");
  101 |   await expect(page.locator("h1")).toHaveText("Sensor health");
  102 |   const field = page.getByRole("img", { name: /Health of \d+ sensors/ });
  103 |   await expect(field).toBeVisible();
  104 |   await field.focus();
  105 |   await page.keyboard.press("ArrowRight");
  106 |   await expect(page).toHaveURL(/sensor=S061/);
  107 |   await expect(page.getByRole("heading", { name: "Sensor groups associated with failure" })).toBeVisible();
  108 |   expect(problems).toEqual([]);
  109 | });
  110 | 
  111 | test("methods: every model card renders", async ({ page, request }) => {
  112 |   const problems = watch(page);
  113 |   const methods = await getJson<{ model_cards: { name: string; title: string }[] }>(request, "/methods");
  114 |   expect(methods.model_cards.length).toBeGreaterThan(0);
  115 |   await page.goto("/methods");
  116 |   await expect(page.locator("h1")).toHaveText("Methods");
  117 |   const panel = page.locator("section, div").filter({ has: page.getByRole("heading", { name: "Model cards", exact: true }) }).last();
  118 |   for (const card of methods.model_cards) {
  119 |     if (methods.model_cards.length > 1) await page.getByRole("radio", { name: card.title }).click();
  120 |     // The card's markdown has its own headings once it loads.
  121 |     await expect(panel.getByRole("heading").nth(1)).toBeVisible();
  122 |     await expect(panel.getByText("Loading the model card")).toHaveCount(0);
  123 |   }
  124 |   expect(problems).toEqual([]);
  125 | });
  126 | 
  127 | test("guest session: Try as engineer signs in", async ({ page }) => {
  128 |   await page.goto(`/units/${ids.unit}`);
  129 |   await page.getByRole("button", { name: "Try as engineer", exact: true }).first().click();
  130 |   await expect(page.getByText("Engineer", { exact: true }).first()).toBeVisible();
  131 |   await expect(page.getByRole("button", { name: "Investigate this unit" })).toBeVisible();
  132 | });
  133 | 
  134 | test("investigation without a key: not-configured state, no Token Factory call", async ({ page }) => {
  135 |   const outbound: string[] = [];
  136 |   page.on("request", (r) => /tokenfactory|token-factory|amd\.com/i.test(r.url()) && outbound.push(r.url()));
  137 | 
  138 |   await page.goto("/investigations");
  139 |   await expect(page.getByRole("note")).toContainText("Live investigations are not configured on this server");
  140 | 
  141 |   await page.goto(`/units/${ids.unit}`);
  142 |   await page.getByRole("button", { name: "Try as engineer", exact: true }).first().click();
  143 |   const start = page.waitForResponse((r) => r.url().endsWith("/api/v1/investigations") && r.request().method() === "POST");
  144 |   await page.getByRole("button", { name: "Investigate this unit" }).click();
> 145 |   expect((await start).status()).toBe(503);
      |                                  ^ Error: expect(received).toBe(expected) // Object.is equality
  146 |   await expect(page.locator("[data-sonner-toast]").filter({ hasText: "not configured" })).toContainText(
  147 |     "Live investigations are not configured on this server",
  148 |   );
  149 |   await expect(page).toHaveURL(new RegExp(`/units/${ids.unit}$`));
  150 |   expect(outbound).toEqual([]);
  151 | });
  152 | 
  153 | test("chat without a key: not-configured state, nothing sent", async ({ page }) => {
  154 |   const chats: string[] = [];
  155 |   page.on("request", (r) => r.url().includes("/api/v1/chat") && chats.push(r.url()));
  156 | 
  157 |   await page.goto(`/units/${ids.unit}`);
  158 |   await page.getByRole("button", { name: "Ask", exact: true }).click();
  159 |   const sheet = page.getByRole("dialog");
  160 |   await expect(sheet.getByRole("note")).toContainText("Chat is not configured on this server");
  161 |   await expect(sheet.getByRole("textbox", { name: "Question" })).toHaveCount(0);
  162 |   expect(chats).toEqual([]);
  163 | });
  164 | 
  165 | test("work orders: the list and the audit log match the API", async ({ page, request }) => {
  166 |   const problems = watch(page);
  167 |   const list = await getJson<{ total: number }>(request, "/work-orders");
  168 |   await page.goto("/work-orders");
  169 |   await expect(page.locator("h1")).toHaveText("Work orders");
  170 |   if (list.total === 0) {
  171 |     await expect(page.getByText("No work orders yet")).toBeVisible();
  172 |   } else {
  173 |     await expect(page.getByRole("link", { name: ids.workOrder! }).first()).toBeVisible();
  174 |     await page.goto(`/work-orders/${ids.workOrder}`);
  175 |     await expect(page.getByRole("heading", { name: "History" })).toBeVisible();
  176 |   }
  177 |   await expect(page.getByRole("heading", { name: /Audit log/ })).toBeVisible();
  178 |   expect(problems).toEqual([]);
  179 | });
  180 | 
```