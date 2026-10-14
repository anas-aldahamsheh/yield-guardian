# Yellow Room: design system of the web app

Work item U2. The source of truth for values is `src/app/globals.css` (tokens) and
`src/lib/optics/` (the physics the wafer colour and the safelight colour come from).
This page records the plan, the review against the brief, and what the review changed.

## Subject, audience, job

- **Subject:** a lithography bay. Photoresist reacts to blue and UV light, so the bay is
  lit by tri-phosphor tubes behind yellow filters. In that room the only colourful
  objects are the wafers, whose oxide films interfere with light.
- **Audience:** yield, process and quality engineers; scientists who will check every
  number; hackathon judges who see it once.
- **Job:** show which units and wafers are associated with failure, show the evidence,
  and let an engineer decide.

## Colour: six named roles

| Token | Role | Yellow room (dark) | Inspection (light) |
|---|---|---|---|
| `room` | The bay in shadow: page background and the streets between panels | `#13120c` | `#eef0f2` |
| `die` | Panels (a panel is a die; the gap between panels is a street) | `#1b1913` | `#fcfdfe` |
| `ink` | Readings and text | `#eceade` | `#1a1e24` |
| `safelight` | Light: focus, selection, the active step, the exposure field. Never an error, never a button fill | `#f5d326` | `#a27900` (strokes), wash from the dark value |
| `pass` | A die or unit that passed | `#3fa0c9` | `#0f76a2` |
| `fail` | A die or unit that failed | `#eb556e` | `#c62b44` |

- The safelight hue is computed, not picked: CIE illuminant FL11 (tri-phosphor
  fluorescent) behind an ideal 500 nm long-pass filter has chromaticity
  x 0.480, y 0.512 (OKLCH hue 97). It lies outside sRGB, so it is mapped into gamut by
  lowering chroma at constant hue. Neutrals in the dark theme carry the same hue at
  chroma 0.010 to 0.016, because grey surfaces under that lamp reflect its colour.
  `src/lib/optics/safelight.ts` computes it; a unit test pins the token to it.
- The light theme is the same bay under white inspection light: neutrals turn cool
  (hue 240 to 255), which makes the safelight read even more clearly as light.
- **Pass and fail** keep the wafer-map convention (cool means good, red means bad) but
  move to a pair that survives colour-vision deficiency. Validated with the dataviz
  validator (Machado 2009, severity 1): worst CVD ΔE 14.9 dark, 15.8 light (target 8);
  normal-vision ΔE 28.0 and 28.4; both at least 3:1 against the panel.
- **Contrast (WCAG 2.2):** ink 14.6:1 and 16.4:1; secondary ink 9.1:1 and 7.6:1; muted
  ink 5.8:1 and 5.2:1 on panels. Safelight 11.9:1 on dark panels; the light theme's
  safelight stroke is 3.9:1, used for focus outlines and marks, never for body text.
  A yellow dark enough for 3:1 on a light panel reads as olive, so the light-theme
  stroke turns 12° towards orange (OKLCH 0.60 0.123 85). Control edges (`edge`),
  baseline marks and the elevated-risk step (`concern`) reach 3:1 on every surface.
  `src/lib/design-tokens.test.ts` reads `globals.css` and fails the build if any of
  these pairs drops below its minimum, in either theme, or if pass and fail stop
  being separable under protan, deutan or tritan simulation.
- **Data colour jobs:** magnitude uses one-hue ramps (fail hue for failure frequency,
  pass hue for counts such as the confusion matrix); polarity (SHAP towards failure or
  towards passing) uses fail and pass around a neutral grey; comparisons use emphasis
  (the main model in ink, baselines in muted ink with direct labels). No categorical
  rainbow anywhere, and no yellow or orange series, because yellow is light.

## Type: two faces, two jobs

| Face | Job | Why this face |
|---|---|---|
| Atkinson Hyperlegible Next (variable 200 to 800) | Readings, data, interface | Drawn by the Braille Institute so that confusable glyphs differ: slashed zero, distinct I, l and 1, distinct 5 and S. That matters in IDs such as `S060`, `lot47542`, `AL-1187-t2`. Has `tnum` for columns. |
| Source Serif 4 (variable, optical sizes) | Text a language model wrote: the investigator's report, model answers in the chat | A transitional serif of scientific publishing; optical sizes keep it crisp at 17 to 18 px. |

**Rule:** serif means "a model wrote this; check its evidence links". Text answered
straight from data by deterministic rules stays in the reading face. Nothing a model
wrote appears in the reading face, and every number in serif text links to the
evidence it came from.

Scale (Bringhurst's classic sizes, px / line height): 12/16 ticks and footnotes,
14/20 interface and tables (tabular figures), 16/24 body, 18/29 serif report text,
21/28, 24/30, 36/40, and 52/54 and 72/72 for the home page only. Weights 400, 500
and 650; tracking −0.02 em from 36 px up.

## Layout

The console is a die map: panels sit on the room colour, separated by 8 px streets,
square-cornered like dies (2 px radius to soften rendering; controls 4 px). No shadows;
overlays use a raised panel, a hairline and a dimmed room behind.

```
Home, 1440 (the hero is always the dark bay, in both themes)
+--------------------------------------------------------------------------------+
| (o) Yield Guardian  Line  Investigations  Wafer lab  Lots  Sensor health        |
|                     Work orders  Models  Methods          unit 812/1,567  Try  |
+--------------------------------------------------------------------------------+
|                                                                                |
|  Find the wafers that will fail      .------------------.                      |
|  final test while there is still    /   3D wafer, dies  \   <- safelight      |
|  time to act.                       |   from WM-811K     |      field steps   |
|                                     \   lot / wafer      /      field by field |
|  [Open the live line] [Try as        '------------------'                      |
|   engineer]                          lot, wafer, dies, failed, label, source   |
+--------------------------------------------------------------------------------+
|  Measured on data the models never saw (ledger: claim, value, CI bar, n, data) |
|  How an investigation runs: 1 alarm 2 evidence 3 report 4 checks 5 decision    |
|  Where the data and the models come from                                       |
+--------------------------------------------------------------------------------+

Line, 1440 (charts share one x axis; one y axis per chart)
+----------------------------------------------+-------------------------------+
| Failure risk per unit, threshold line        | Open alarms, newest first     |
+----------------------------------------------+  unit, kind, value vs limit,  |
| Hotelling T2 with 99% and 99.9% limits       |  Investigate                  |
+----------------------------------------------+                               |
| SPE (Q) with 99% and 99.9% limits            |                               |
+----------------------------------------------+-------------------------------+
| Recent units: unit, time, risk, band, T2, SPE, alarms, final test            |
+------------------------------------------------------------------------------+

Investigation, 1440
+-------------------+----------------------------------+-----------------------+
| Steps (live)      | Report (serif); claims link to   | Evidence panels       |
| triage, plan,     | evidence [E3]; numbers checked   | open where a claim    |
| tools, write,     | against tool output              | points; charts are 2D |
| verify            | Approve / Reject (needs session) |                       |
+-------------------+----------------------------------+-----------------------+

390 px: one column; navigation in a sheet; charts keep one axis and grow taller.
```

Text is left aligned everywhere; numbers in tables are right aligned on tabular figures.

## Motion

- **One orchestrated sequence:** on the home page the safelight field steps across the
  real wafer like a stepper (stage move, exposure flash, results revealed under the
  field), about 4.5 s, once, with a replay control. Lenis smooth scroll on the home
  page only.
- **Everywhere else motion answers an action:** an evidence panel opening, a result
  arriving, a stream step starting (its marker is lit by the safelight).
- Easing: `--ease-arrive` cubic-bezier(0.16, 1, 0.3, 1) for things arriving;
  `--ease-stage` cubic-bezier(0.65, 0, 0.35, 1) for the stepper stage. Durations 120,
  220 and 420 ms.
- `prefers-reduced-motion`: the wafer renders fully revealed and still; no scan, no
  smooth scroll, no transitions beyond opacity.

## Principles

1. Light marks attention. The safelight appears only where someone is looking or
   something is running.
2. Measured or written. Readings in the reading face; model prose in serif, with links.
3. Objects in 3D, numbers in 2D. Only the wafer and the carrier are 3D.
4. No estimate without its interval. Every metric shows its 95% CI and its n.
5. Quiet by default: no gradients as decoration, no shadows, no motion without a cause.

## Review against the brief: what changed

The first plan was checked against the generic defaults a similar brief tends to
produce. Changes:

1. **Near-black with one bright accent.** The first plan used a neutral near-black with
   an amber accent on buttons. Changed: the neutrals now take the computed safelight hue
   (they are surfaces in that room), and the safelight never fills a button or a brand
   mark. Primary actions are ink on room; the safelight only marks light.
2. **Amber picked by eye.** The first value was a hand-picked amber. Changed: the hue is
   computed from a lamp and filter model with the same spectral code as the wafer, which
   gives a golden yellow (hue 97) instead of orange. It reads as the room's light rather
   than as a brand colour.
3. **Monospace for data labels.** The first plan used a monospace face for readings.
   Changed to Atkinson Hyperlegible Next with tabular figures: it keeps columns aligned
   without the terminal look, and its glyph shapes solve a real problem (sensor and lot
   IDs mixing 0/O, 1/l/I, 5/S).
4. **Serif headings.** A serif display face for headings is the most common pairing.
   Changed: headings use the reading face; the serif is reserved for model-written text
   so that it carries meaning.
5. **Big-number KPI tiles.** The first home page had large result tiles. Changed to a
   results ledger: each claim with its value, a CI bar on a shared axis, n and the data
   block, because a judge or scientist must see uncertainty first.
6. **Rounded cards with soft shadows.** Changed to flat panels separated by streets (the
   wafer's own grid), with radius by hierarchy rather than one radius everywhere.
7. **Light theme as cream paper.** The obvious light theme was warm off-white. Changed
   to the bay under white inspection light: cool neutrals that let the safelight read
   as light.
8. **Section labels.** No all-caps eyebrows or numbered markers, except for the
   investigation flow, which really is a sequence.
