# Oxide: design system of the web app

The source of truth for values is `src/app/globals.css` (tokens), `src/lib/optics/oxide.ts`
(the film colours and the signal colour, computed) and `src/components/motion` (springs and the
motion primitives). This page is the plan: the concept, every value and why, the motion system,
the component states, the wireframes of every page, and the review that changed the first draft.

It replaces the Yellow Room. The owner rejected all of it (layout, colour, motion, hover), asked
for the most beautiful interface that can be made and for large, professional motion everywhere,
built with Motion. Nothing of the Yellow Room is kept except what is not a look: the rule that a
model's prose is set in a serif, the rule that the line moves only when a result arrives, and the
computed-not-picked discipline for colour.

## Subject, audience, job

- **Subject:** a wafer under inspection. Polished silicon is a dark blue-grey mirror; a thermal
  oxide on it shows interference colours that cycle as the film thickens. Fabs judge oxide
  thickness by eye from that sequence (the oxide colour chart). Probers step over the dies; a
  test head stamps the result.
- **Audience:** yield, process and quality engineers; scientists who check every number; judges
  who see it once and must understand it in a minute.
- **Job:** run real data down the line, show what each station computed while it computes, and
  let an engineer investigate an alarm and decide.

## Concept: the interface is a wafer under inspection

Three materials, one light.

1. **Silicon** (the surfaces). Dark theme: the polished wafer in a dim cleanroom, a deep blue
   graphite (OKLCH hue 266, the cast of polished silicon). Light theme: the cleanroom under white
   light, cool porcelain whites on the same hue. Panels are flat planes of the same material, one
   step lighter, separated by thin streets.
2. **Instrument screens** (where data lives). The line's stations show their readings on dark
   glass in both themes, like the displays of the tools themselves. Data glows on them.
3. **Ink** (the interface). Text, controls and primary actions are monochrome: white on silicon,
   graphite on white. A primary button is solid ink.
4. **The film** (the one light). The only colour that is not data is the oxide's second-order
   interference sequence, violet to green, 280 to 362 nm. Each stop takes the hue the thin-film
   physics gives at its thickness (`oxide.ts`, Airy summation in `thinfilm.ts`), so the gradient
   is a measured object, not a mood. It appears only as light: on the brand mark, on the line's
   track as data moves down it, as the sheen that crosses a station while it computes, and as the
   indicator of the page you are on. The **signal** colour (focus, selection, live) is the film's
   hue at 310 nm.

What is memorable: the line itself. A machine of four stations on one body, a track of film light
that advances only as far as data has arrived, instrument screens that light up with real
readings (590 sensor lamps, three dials, a wafer probed die by die, a stamp landing), and giant
wide type above it. Everything around it stays quiet, exact and fast.

## Colour

`src/lib/design-tokens.test.ts` reads `globals.css` and fails the build if any pair below drops
under its minimum in either theme, or if pass and fail stop being separable for colour-vision
deficiency. `src/lib/optics/oxide.test.ts` pins the film and signal tokens to the physics.

### Surfaces and ink (neutral hue 266)

| Token             | Role                                               | Dark      | Light     |
| ----------------- | -------------------------------------------------- | --------- | --------- |
| `canvas`          | Page background                                    | `#0c1220` | `#f4f6f8` |
| `surface`         | Panels, the bay, cards                             | `#121928` | `#ffffff` |
| `surface-2`       | Raised: inputs, menus, popovers, rows on hover     | `#1a2131` | `#eff1f5` |
| `surface-3`       | Pressed, selected fill, tracks of controls         | `#242b3c` | `#e5e7ec` |
| `screen`          | Instrument glass (always dark, both themes)        | `#060b18` | `#060b18` |
| `hairline`        | Separators, panel borders (decorative)             | `#282f3e` | `#e0e2e7` |
| `hairline-strong` | Strong separators, quiet control borders           | `#3d4453` | `#cbced4` |
| `edge`            | Borders that identify a control (3:1, WCAG 1.4.11) | `#7a808e` | `#7c8089` |
| `ink`             | Text, primary button fill                          | `#f2f4f9` | `#111620` |
| `ink-2`           | Secondary text                                     | `#bec2cc` | `#444954` |
| `ink-3`           | Muted text, axis labels (still 4.5:1)              | `#9ba0ac` | `#5e636e` |

### Light and data

| Token        | Role                                                                | Dark      | Light     |
| ------------ | ------------------------------------------------------------------- | --------- | --------- |
| `signal`     | Focus ring, selection edge, live dot, links on hover. Never a fill  | `#7cc2fe` | `#0871b3` |
| `pass`       | A die, unit or check that passed                                    | `#31d2be` | `#0b867f` |
| `concern`    | Elevated risk, warnings. Always with a label                        | `#f7bc57` | `#c2790c` |
| `fail`       | A die or unit that failed, alarms, destructive actions              | `#f95e62` | `#d01a34` |
| `mark-muted` | Baselines and context series in charts, direct-labelled             | `#7b808d` | `#7c808a` |
| `film-1..6`  | The oxide film at 280, 296, 310, 324, 340, 362 nm (hues 302 to 154) | computed  | computed  |

The film stops are computed at lightness 0.76 (dark) and 0.56 (light) and 86% of the largest
chroma sRGB holds at their hue, so they are equally light and vivid; only the hue comes from the
physics. In the dark theme they read `#c09df4 #9aadf4 #71b8f4 #43c1eb #44c6ca #44cf80`.

**Contrast (WCAG 2.2, worst of canvas, surface and surface-2, dark / light):** ink 14.8 / 16.0;
ink-2 9.1 / 8.0; ink-3 6.2 / 5.3 (5.5 / 4.9 on surface-3); signal 8.5 / 4.6; pass 8.6 / 4.4;
fail 5.3 / 5.4; concern 9.5 / 3.1; edge and mark-muted 4.1 / 3.5. Every mark and control edge
clears 3:1 and every text token 4.5:1.

**Colour-vision deficiency (Machado 2009, OKLab ΔE×100, dark / light):** pass and fail: normal
32.9 / 30.3, protan 23.5 / 16.4, deutan 12.7 / 11.6, tritan 38.4 / 33.2. Concern and fail:
normal 21.7 / 17.5, deutan 14.9 / 9.1. The dataviz validator's lightness band flags the dark
status colours as lighter than a categorical series would be: they are status marks on dark
glass, not series, and contrast and CVD are the checks that apply.

**Data colour jobs.** Magnitude: one hue (sensor lamps: the film's 324 nm cyan, brightness is
|z|; failure frequency: the fail hue). Polarity (SHAP towards failure or passing): fail and pass
around a neutral grey. Comparison: the main model in ink, baselines in `mark-muted` with direct
labels. Status (pass, concern, fail) always comes with an icon or a word. The film is never used
for data.

## Type

| Face                                                                             | Job                                                  | Why                                                                                                                                                                                                                                       |
| -------------------------------------------------------------------------------- | ---------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **YG Sans**, our cut of Mona Sans (variable, wght 400 to 700, wdth 100 to 112.5) | Everything Latin: display, headings, interface, data | One family with a width axis: expanded and heavy it is the display voice, at normal width a crisp interface face. Its tabular figures carry a slashed zero, which separates 0 and O in IDs like `S060` and `lot47542`; I, l and 1 differ. |
| **Newsreader** (variable, optical sizes)                                         | Text a language model wrote: reports, chat answers   | A contemporary text serif with optical sizes. Serif means "a model wrote this; check its evidence links".                                                                                                                                 |
| **Readex Pro** (variable, wght 160 to 700)                                       | The Arabic sections (How it works, the guide)        | A modern Arabic sans drawn for screens, with a large x-height and open counters that match YG Sans's proportions, so mixed Arabic and Latin lines share one rhythm. 23 KB for the Arabic subset, fetched only when Arabic text is shown.  |

The Latin face is on every first paint, so it is cut to what the app sets
(`scripts/cut-ui-font.py`): widths 100 to 112.5, weights 400 to 700, Basic Latin with the Latin-1
signs, dashes, quotes and arrows, and kerning and the figure sets. 48 KB instead of 98 KB. An
accented letter falls back to the system face. Mona Sans is licensed under the SIL Open Font License
with the reserved name "Mona", so the cut is named YG Sans and its licence sits next to it
(`src/fonts/OFL.txt`).

Scale (px, line height). Display sizes use `clamp()` between phone and desktop.

| Token / class  | Size / leading            | Setting                             | Use                            |
| -------------- | ------------------------- | ----------------------------------- | ------------------------------ |
| `text-hero`    | 40 to 104 / 0.94          | wdth 112, wght 680, −0.035em        | The Line headline only         |
| `text-display` | 40 to 72 / 1.0            | wdth 112, wght 660, −0.035em        | The experts' heading on /how   |
| `text-page`    | 36 to 60 / 1.02           | wdth 112, wght 660, −0.035em        | Page titles (`PageHeader`)     |
| `text-title`   | 30 to 40 / 1.08           | wdth 106, wght 650, −0.02em         | Section titles on /how         |
| `text-h2`      | 24 / 30                   | wdth 106, wght 630, −0.02em         | Section headings               |
| `text-h3`      | 18 / 26                   | wght 620, −0.01em                   | Panel headings                 |
| `text-lede`    | 19 / 30                   | wght 420                            | Introductions                  |
| `text-body`    | 16 / 26                   | wght 420 (400 in dark)              | Body                           |
| `text-ui`      | 14 / 20                   | wght 500                            | Controls, tables               |
| `text-micro`   | 12 / 16                   | wght 520, +0.01em                   | Ticks, footnotes, table heads  |
| `.readout`     | 28 to 48                  | wdth 108, wght 560, −0.03em, lining | Instrument readings and counts |
| `.written`     | 18 / 30 (summary 21 / 33) | Newsreader, wght 420                | Model-written prose            |
| Arabic body    | 17 / 30                   | Readex Pro 400; headings 600 / 1.35 | Arabic sections                |

Sentence case everywhere. No all-caps labels, no tracked-out eyebrows, no monospace data labels.
Big numbers use proportional lining figures; columns use tabular figures (`.tnum`).

## Space, shape, depth

- **Grid.** 4 px base. Page gutter `clamp(16px, 4vw, 40px)`; content up to 1600 px wide; reading
  measure 68 ch. Section rhythm 64 and 96 px; panel padding 20 and 24 px; panels that sit side by
  side are separated by a 16 px street (`--spacing-street`), like dies on a wafer.
- **Radius by hierarchy** (never one radius everywhere): the bay and dialogs 28 px; panels 20 px;
  screens and inner cards 14 px; inputs, menu items and small buttons 10 px; buttons, chips, the
  navigation pill and tabs fully round.
- **Depth.** Panels are flat: a hairline in light, one lightness step in dark plus a 1 px top
  highlight (light catching a polished edge). Shadows only on what floats: the top bar once the
  page scrolls, menus, popovers, toasts, dialogs, sheets. Light: layered, low-opacity, cool-tinted
  shadows (`--shadow-float`, `--shadow-overlay`). Dark: a deep shadow plus the top highlight.
- **Iconography.** lucide at 16, 18 and 20 px, stroke 1.75, always beside a word except icon
  buttons, which have an accessible name and a tooltip.

## Motion

Motion is the second material of this interface: things move because data arrived or because a
person acted, and the movement shows what changed. Every animation is transform, opacity or
filter; nothing animates layout properties.

**Tools.** Motion (`framer-motion`, Motion's React package; `m` components under `LazyMotion`) for
springs, presence, layout and shared-element transitions, gestures and number tickers. Nothing
moves on a page's first paint, so Motion's renderer is in no page's first load: a sliding mark
(`Indicator`: the navigation and tab pills, toggle thumbs, the open way's light) is a plain span
until the reader first points, touches, types or scrolls, when `MotionProvider` fetches Motion and
the mark becomes a shared-layout element; the investigations list fetches Motion's features once
the page has loaded and the browser is idle (`MotionFeatures`). A theme switch repaints every
colour in one frame: no transition runs while it happens (`.theme-switching`). GSAP for the
line's timeline (it is advanced only by arrived results). CSS keyframes for
what must run before hydration (the first paint of a page) and for Radix overlays (spring curves
written with `linear()`). The browser's view transitions (React `<ViewTransition>`,
`src/components/page-transition.tsx`) for what travels between a list and one of its items. No
page loads three.js: the prober's wafer is a flat die map drawn from the result, crisp dies with a
faint sheen (the 3D scenes in `components/wafer` and `components/lot` are no longer mounted).

**Springs** (`src/components/motion/springs.ts`):

| Name     | Spring                              | Use                                                          |
| -------- | ----------------------------------- | ------------------------------------------------------------ |
| `press`  | stiffness 700, damping 40, mass 0.6 | Buttons and rows going down under a press                    |
| `hover`  | stiffness 420, damping 32           | Lifts, the hover pill, the magnetic primary action           |
| `layout` | stiffness 320, damping 36           | Layout changes, shared elements, the navigation indicator    |
| `arrive` | stiffness 190, damping 22           | A result arriving: numbers, chips, alarms (slight overshoot) |
| `stamp`  | stiffness 260, damping 15           | The final-test stamp landing                                 |

**Easing and duration (CSS):** `--ease-out` cubic-bezier(0.22, 1, 0.36, 1); `--ease-in-out`
cubic-bezier(0.65, 0, 0.35, 1); `--ease-spring` a `linear()` spring with 6% overshoot.
`--dur-1` 120 ms (colour), `--dur-2` 200 ms (press, small state), `--dur-3` 320 ms (component
enter and exit), `--dur-4` 520 ms (panel, page), `--dur-5` 900 ms (the hero's lines). Overlays
finish in under 400 ms, a page's entrance in under 700 ms.

**Choreography.**

1. _First paint of the Line page_ (CSS, before hydration, about 1 s), only when it opens with no
   run: the headline's lines rise out of their masks 80 ms apart; the lede and the four ways
   settle in. A page opened, reloaded or linked to with a run arrives at rest: nothing on the line
   (instruments, counts, dials, rail) moves until a result arrives or the reader acts, and an
   entrance plays only for what appears while the reader is on the page (`useEntrance`).
2. _A run arrives_ (driven by results only): the track's film lights up stretch by stretch, up to
   each station when that station's first result is shown; its node lights; its screen gets one
   sweep of light; its chip springs to the new state; its count ticks from zero to the value.
   Lamps power up row by row; needles sweep to each unit; dies are probed in order; wafers slide
   into the carrier; the stamp drops with a spring. Alarms slide into the rail with a spring, and
   a red ring pulses once on the station that turned red.
3. _Navigation:_ the page settles in (opacity and a 14 px rise, 520 ms); the navigation indicator
   slides to the new item (shared layout); the mobile menu's links stagger in. Between the
   investigations list and an investigation, the title and the status chip travel from the row to
   the heading and back (520 ms, softened by a 2 px blur mid-flight) while the page slides 56 px the
   way the reader moves: forward, the list leaves to the left; back, to the right. Only those links
   carry a direction; every other navigation keeps the page's own entrance.
4. _Answers to actions:_ opening a station's details grows the drawer into place (layout); tabs
   slide their indicator; toggles and segmented controls slide their thumb; rows and menu items get
   a hover pill that follows the pointer; buttons lift on hover and press down with a spring;
   dialogs and sheets spring in while the backdrop fades and blurs. Choosing a way in (pick, draw,
   upload) grows its panel under the hero and scrolls it into view, clear of the bar and the Ask
   button, since at 1440 × 900 it opens below the fold.
5. _How it works:_ scroll-linked: the five-station diagram draws as it is read; the experts'
   section index follows the scroll with its indicator.
6. _Charts:_ a series draws in (path length) and bars grow from the baseline when their data
   arrives or first scrolls into view: real values only, once.

**Motion and the compositor.** While a transform runs, Chrome cannot tell where its element ends
up, so everything drawn after it that might overlap it is lifted onto layers of its own until it
settles; on the line that is every station below or beside it, rastered again on every frame. So
the line moves only where nothing can overlap: swapped content (an evidence record, a tab, a
station's sentence) crossfades without moving; the primary action, the show-all buttons and a
station's chip move inside a clip of their own, with room for a shadow, a focus ring or a spring's
overshoot; the track's film lights up by opacity and stops short of the next station; one-shot
lights (a screen's sweep, the red ring) leave the page once played; a screen's glow on hover shows
at once; the prober's light is drawn into its canvas, which is drawn on the CPU, instead of laid
over it. A result arriving then rasters again what it changed, not the stations around it.

**Reduced motion.** `MotionConfig reducedMotion="user"` turns Motion's transforms and layout
animation off; the CSS rule cuts every animation and transition to nothing, view transitions
included (pages swap at once); the line's timeline rests the scene at once (every arrived result
shown, no replay); tickers jump to the value; sheens, rings and scroll-linked drawing are hidden
or static; the live rail and live edge show their light still, full length.

## Component states

| Component               | Rest                                                 | Hover                          | Press      | Focus                         | Selected / on                                                                                                           | Disabled |
| ----------------------- | ---------------------------------------------------- | ------------------------------ | ---------- | ----------------------------- | ----------------------------------------------------------------------------------------------------------------------- | -------- |
| Primary button (ink)    | ink fill, canvas text, pill                          | lifts 1 px, film sheen crosses | scale 0.97 | 2 px signal ring, offset 3 px | n/a                                                                                                                     | 45%      |
| Secondary button        | surface-2, hairline-strong edge                      | surface-3, lifts 1 px          | scale 0.97 | signal ring                   | n/a                                                                                                                     | 45%      |
| Ghost button, menu item | transparent                                          | hover pill (surface-2)         | surface-3  | signal ring or inset          | `lit`: signal wash and inset edge                                                                                       | 45%      |
| Input, select           | surface, edge, radius 10, 16 px text on phones       | edge darkens                   | n/a        | signal ring                   | n/a                                                                                                                     | 45%      |
| Tab, segmented control  | ink-2 text                                           | ink text                       | n/a        | signal ring                   | ink text on a sliding pill (layout)                                                                                     | 45%      |
| Table row, list row     | transparent                                          | surface-2                      | n/a        | signal ring on the row's link | `aria-current`: signal edge at the start                                                                                |          |
| Station                 | ghost instruments, grey node                         | screen shows its glow and edge | n/a        | on its open button            | open: signal edge; working: signal node, one sheen, clock; done: calm; alarm: fail tint and one ring; failed: fail text |          |
| Status chip             | idle hidden; needs grey                              |                                |            |                               | working: signal dot pulsing; done: pass dot; alarm and failed: fail dot                                                 |          |
| New row, new alarm      | lit once in signal (new) or fail (alarm), then fades |                                |            |                               |                                                                                                                         |          |
| Not measured yet        | unexposed die field, plain words, "Check again"      |                                |            |                               |                                                                                                                         |          |
| Loading                 | a surface-2 plane with a slow sheen crossing it      |                                |            |                               |                                                                                                                         |          |
| Lifecycle stage         | grey ring on the rail; empty stage says so           |                                |            |                               | holds items: ink node; running: live dot and the film's light running down the rail                                     |          |

## Pages

Text is left aligned (right aligned in Arabic); numbers in tables right aligned on tabular figures.

### Line (`/`), 1440

```
+----------------------------------------------------------------------------------------+
| (o) Yield Guardian   (Line) Investigations  How it works            [~]  Try as engineer |
+----------------------------------------------------------------------------------------+
|                                                                                        |
|  Run real fab data                        +-----------+ +---------+ +--------+ +------+ |
|  down the line                            | (o) Try a | | Pick a  | | Draw a | |Upload| |
|  (hero type, wide, 104 px)                | real      | | case    | | defect | |a file| |
|                                           | sample    | |         | |        | |      | |
|  Choose an input. Each station computes   +-----------+ +---------+ +--------+ +------+ |
|  its result from it while you watch ...   A real sample is ... seed ...                |
|                                                                                        |
|  [way panel: case picker, draw tool or upload, full width, grows open]                 |
|                                                                                        |
|  A random real sample                                     [Show every result now]      |
|  rule and seed ...  kept until ...                                                     |
|                                                                                        |
| +-- the bay: one body, four stations ----------------------------------+ +- Alarms ---+ |
| | o====================o=====================o==================o      | | 5 alarms,  | |
| | +screen-------+  | +screen------------+  | +screen-----------+ | +sc-+ | | 17 warnings| |
| | | 590 lamps   |  | | T2   SPE   Risk  |  | | wafer   carrier | | |seal| | | +--------+ | |
| | |             |  | | units / EWMA     |  | |                 | | |    | | | | alarm  | | |
| | +-------------+  | +------------------+  | +-----------------+ | +----+ | | +--------+ | |
| | 1 Manufacturing  | 2 Monitoring (Alarm)  | 3 Wafer test (Alarm)| Final  | | | alarm  | | |
| | sentence         | sentence              | sentence            | test   | | +--------+ | |
| | 40 units read    | 2 units out of control| 1 lot flagged       |        | |            | |
| | [Open details]   | [Open details]        | [Open details]      |        | |            | |
| +----------------------------------------------------------------------+ +------------+ |
|  (o) The run is finished: every station has its result ...                             |
|  +- 2 Monitoring in detail -------------------------------------------------- Close -+  |
|  | risk chart, control charts, drift, health, units ...                             |  |
|  +-----------------------------------------------------------------------------------+  |
|  +- 4 Investigation ---------------------+ +- 5 Decision --------------------------+    |
+----------------------------------------------------------------------------------------+
| footer: data sources, versions, checksums                                     (Ask)    |
```

### Line, 375

```
+-----------------------------+
| (o) Yield Guardian   [~] [=]|
+-----------------------------+
| Run real fab                |
| data down the               |
| line                        |
| Choose an input ...         |
| +-------------------------+ |
| | (o) Try a real sample   | |
| +-------------------------+ |
| +-----------+ +-----------+ |
| | Pick case | | Draw      | |
| +-----------+ +-----------+ |
| +-------------------------+ |
| | Upload a file           | |
| +-------------------------+ |
| o | 1 Manufacturing  Done   |  the track runs down the left
| | | [screen]                |
| o | 2 Monitoring  Alarm     |
| | | [screen]                |
| o | 3 Wafer test            |
| o | Final test              |
| Alarms                      |
|                       (Ask) |
+-----------------------------+
```

### How it works (`/how`)

```
1440                                                  375
+-----------------------------------------------+     +-----------------------+
|                    كيف يعمل Yield Guardian     |     |  كيف يعمل Yield       |
|        (display Arabic, right aligned)         |     |  Guardian             |
|        lede in Arabic                          |     |  lede                 |
|  o----o----o----o----o   (draws on scroll,     |     |  o  1 Manufacturing   |
|  the five stations, right to left)             |     |  |  ...               |
|  [the data: SECOM]   [the data: WM-811K]       |     |  o  2 Monitoring      |
|  [your own data]                               |     |  ...                  |
|  what it cannot do: numbers from the API       |     |  sources, limits      |
+-----------------------------------------------+     +-----------------------+
| For experts (English, left to right)          |     | For experts           |
| +index (sticky)--+ +-------------------------+ |     | [index as a row of    |
| | Results       | | Measured results table  | |     |  pills, scrolls]      |
| | Models        | | Models: cards, tables   | |     | sections stacked      |
| | Methods       | | Methods: charts         | |     |                       |
| | Data          | | Data and provenance     | |     |                       |
| | Calculator    | | Savings calculator      | |     |                       |
| +---------------+ +-------------------------+ |     |                       |
+-----------------------------------------------+     +-----------------------+
| The guide (Arabic, right to left): search,    |     | guide                 |
| filter chips, entries with screenshots        |     |                       |
+-----------------------------------------------+     +-----------------------+
```

### Investigations (`/investigations`), list and work orders

```
+----------------------------------------------------------------------------+
| Investigations                                       (display type)        |
| What each alarm investigation found and what was decided.                  |
| ( Investigations | Work orders )   <- segmented tabs, sliding pill          |
|                                                                            |
| o  Running 1          the lifecycle rail: one node per stage, lit when it  |
| :  +- table: title, status, from, elapsed, points, work order ---------+   |
| :  +-------------------------------------------------------------------+   |
| o  Awaiting decision 1                                                     |
| |  +- table ----------------------------------------------------------+    |
| o  Decided 0      "No report has been decided yet."                        |
| o  Failed 0                                                                |
+----------------------------------------------------------------------------+
Rows move between stages with a spring (shared layout) when their status changes; while one
runs, the film's light runs down the rail from its stage.
Work orders tab: one table (order, title, status track, investigation, opened);
?order= opens the order's section below the table, with its history.
375: groups stack; tables scroll inside their panel.
```

### Investigation (`/investigations/[id]`)

```
+----------------------------------------------------------------------------+
| <- Investigations                                                          |
| Title of the alarm (title type)                    status   elapsed         |
| +- Run (live) --------+ +- Report (serif) -------------+ +- Evidence ------+ |
| | steps with marks    | | summary (21/33)               | | tabs: E1 E2 ... | |
| | triage, plan, tools | | sections; numbers link to [E] | | record, JSON    | |
| | write, verify       | | hypotheses table              | | highlighted     | |
| +---------------------+ +-------------------------------+ +-----------------+ |
| +- Decision ------------------------------------------------------------+   |
| | actions with checkboxes   [Approve]  [Reject]                          |   |
| +------------------------------------------------------------------------+  |
| +- Work order (when approved) -------------------------------------------+  |
+----------------------------------------------------------------------------+
375: one column in reading order: report, decision, run, evidence.
```

### Model roles (`/admin`), chat, navigation

```
/admin                                         chat (sheet from the right)
+------------------------------------------+   +-----------------------------+
| Model roles (title)                      |   | mark, title             [x] |
| roles table: role, model, evaluation,    |   | suggestions: rows, arrow    |
| usage today; [Change] opens a dialog     |   | you: question               |
| evaluations; catalog                     |   | answer with [E1] chips      |
+------------------------------------------+   | evidence cards              |
                                               | [ask field             (^)] |
mobile navigation (sheet, full height)         +-----------------------------+
+-----------------------------+
| Line                        |  links in display type, staggered in;
| Investigations              |  the current page marked by the film bar
| How it works                |
| theme, session              |
+-----------------------------+
```

In the chat, an answer a model wrote is set in Newsreader, like every other model prose; one the
rules wrote stays in YG Sans. A citation chip keeps the word before it and the punctuation after
it on its line. The question and its round Ask button share one field, which takes the focus
ring. Toasts drop in under the top bar, centred: clear of the Ask button and of the sheet's field,
and on a wide screen clear of the open sheet.

## Principles

1. **One light.** Colour that is not data is the oxide film, and it marks only what is live,
   arriving or chosen.
2. **Motion has a cause.** A result arrived, a person acted, or the page arrived. Nothing loops
   except a state that is really ongoing (computing, live).
3. **Measured or written.** Readings in YG Sans; model prose in Newsreader with evidence links.
4. **Instruments, not illustrations.** The line's screens draw computed values with their scales,
   not pictures of machines.
5. **No estimate without its interval;** not ready is a state, not an error.
6. **Light on a phone.** A page's first load carries no Motion renderer and no dialog or drawer it
   does not show; the interface's typeface is cut to the characters it writes. First and last
   come from the index, not from `group-first`, `group-last`, `space-*` or `divide-*`: their
   `:first-child` and `:last-child` selectors make every node the parser adds restyle the subtree
   around it.

## Review against the brief and the design skill: what changed

The first draft was checked against the owner's words and against the defaults a similar brief
produces. Changes:

1. **Violet accent on near-black.** The first draft used a saturated violet for buttons and links,
   which is the commonest look of generated interfaces. Changed: the interface is monochrome ink;
   the only chromatic signature is the computed oxide film, and the signal colour is the film's
   own 310 nm blue, used for focus, selection and live state only.
2. **Gradient as decoration.** An aurora gradient behind the hero was considered and dropped. The
   film appears only as light on thin things (the track, the mark, a sweep, the nav indicator),
   and its stops are physics pinned by a test.
3. **The SaaS card kit.** Four identical rounded station cards with the same soft shadow was the
   first layout. Changed: the stations are segments of one machine body with one track running
   through them; radius follows hierarchy; shadows only on floating layers.
4. **A serif display headline.** Changed to an expanded grotesk; the serif keeps its meaning (a
   model wrote this).
5. **Fade-up on every section.** Rejected. The first paint has one choreography; after that,
   movement comes from data and actions. The owner's "huge animation" is spent where it carries
   meaning: the line running, transitions between states and pages, and the hover and press
   feel of every control.
6. **Equipment drawings.** The Yellow Room drew chambers, consoles and probers as line art. The
   owner found it unprofessional. Changed: the stations are instrument screens that draw only
   computed values (lamps, dials, the wafer map, the carrier, the seal).
7. **Big-number tiles.** Counts stay attached to their sentence and unit; they tick only when a
   result arrives.
8. **Labels.** No all-caps eyebrows, no middle-dot meta strings, no monospace labels, no arrows
   appended to links. Numbering appears only where the content is a sequence (the five stations,
   the investigation's steps).
