/**
 * The user guide, the last section of How it works (/how#guide). Interface labels are quoted as
 * they appear on screen.
 *
 * It holds no measured number: those are read from the API in the expert section above it. A
 * `shot` block is a screenshot of the real product under public/guide/, taken from the real API
 * behind the production gateway by e2e/guide-screenshots.shot.ts (never from the development
 * fixtures), at 1440 px in the light theme and cropped to what its entry describes.
 */

export type Block =
  | { type: "p"; text: string }
  | { type: "list"; items: readonly string[] }
  | { type: "steps"; items: readonly string[] }
  | { type: "table"; head: readonly string[]; rows: readonly (readonly string[])[] }
  | { type: "note"; text: string }
  | {
      type: "shot";
      id: string;
      /** Under the picture, for everyone. */
      caption: string;
      /** What the picture shows, for a reader who cannot see it. */
      alt: string;
      src: string;
      /** The file's own size in pixels. */
      width: number;
      height: number;
    };

export interface Category {
  id: string;
  label: string;
  /** One line under the category heading. */
  lede: string;
}

export interface Entry {
  id: string;
  category: string;
  title: string;
  blocks: readonly Block[];
}

export const CATEGORIES: readonly Category[] = [
  { id: "pages", label: "The three pages", lede: "Three pages and a chat button." },
  {
    id: "start",
    label: "Four ways to start",
    lede: "Nothing moves on the line until you give it input.",
  },
  {
    id: "stations",
    label: "The five stations",
    lede: "What each station computes, and what its colours mean.",
  },
  { id: "alarms", label: "Alarms", lede: "When an alarm is raised, and who raises it." },
  {
    id: "investigate",
    label: "Investigation",
    lede: "What happens when you press Investigate, and how to read the report.",
  },
  {
    id: "decide",
    label: "Approval and work orders",
    lede: "The engineer's decision, the work order and the confirmed cause.",
  },
  { id: "chat", label: "Chat", lede: "The Ask button on every page." },
  {
    id: "calculator",
    label: "Savings calculator",
    lede: "Hours and money saved for your fab, from your own numbers.",
  },
  { id: "glossary", label: "Glossary", lede: "The technical words, in plain language." },
];

export const ENTRIES: readonly Entry[] = [
  // ───────────────────────── The three pages ─────────────────────────
  {
    id: "guide-pages",
    category: "pages",
    title: "Line, Investigations and How it works",
    blocks: [
      {
        type: "list",
        items: [
          "«Line»: give the production line an input and watch each station's result as it is computed.",
          "«Investigations»: investigations running, awaiting a decision and decided, plus the «Work orders» tab with the audit log.",
          "«How it works»: this page, with the plain introduction, «For experts» and this guide.",
          "The floating «Ask» button at the bottom of every page opens the chat; the theme menu in the top bar switches light, dark or system.",
          "On a phone the pages sit behind the menu button.",
        ],
      },
      {
        type: "shot",
        id: "guide-nav",
        caption: "The top bar with its three pages, and the Ask button at the bottom",
        alt: "The Line page before any input: the top bar holds the Line, Investigations and How it works links, the theme button and Try as engineer; below are the title and the four input buttons, the idle stations, an empty Alarms column and the floating Ask button.",
        src: "/guide/guide-nav.webp",
        width: 1440,
        height: 900,
      },
    ],
  },
  {
    id: "guide-old-links",
    category: "pages",
    title: "Old addresses",
    blocks: [
      {
        type: "list",
        items: [
          "Every version 1 address still works and redirects to its new place, so saved links keep working.",
          "/wafers, /lots and /sensors open the matching station on «Line»; /units/…, /wafers/… and /lots/… open that item there.",
          "/work-orders opens the «Work orders» tab; /work-orders/… opens the investigation that opened the order.",
          "/models, /methods and /guide open their sections of «How it works».",
          "The language-model role settings live on a hidden admin page: anyone can read it, only the admin changes roles.",
        ],
      },
    ],
  },
  {
    id: "guide-session",
    category: "pages",
    title: "When to sign in",
    blocks: [
      {
        type: "list",
        items: [
          "Running the line needs no sign-in: any visitor can try a sample, draw a defect or upload a file.",
          "Investigating, approving or rejecting, updating a work order and chatting need an engineer session: press «Try as engineer» for an instant guest session.",
          "Changing the model behind a role needs the admin account («Sign in»).",
        ],
      },
    ],
  },

  // ───────────────────────── Four ways to start ─────────────────────────
  {
    id: "guide-ways-in",
    category: "start",
    title: "The four buttons",
    blocks: [
      {
        type: "list",
        items: [
          "«Try a real sample»: one click; the server draws, with a recorded seed, consecutive real SECOM test units the risk model never saw, and every demo wafer of one real WM-811K lot. The rule and seed are shown.",
          "«Pick a case»: choose a real case from the list, or browse the real units, wafers and lots yourself.",
          "«Draw a defect»: draw failed dies on a real WM-811K wafer layout.",
          "«Upload a file»: an Excel (.xlsx) or CSV file from your fab, checked before it runs.",
          "Every input goes through the same code, so a sample is processed exactly like your file.",
        ],
      },
      {
        type: "shot",
        id: "guide-input-bar",
        caption: "The input bar with its four buttons on the idle Line page",
        alt: "The page title Run real fab data down the line, with a sentence saying each station computes its result in front of you; beside it the Try a real sample button and a line saying the sample is drawn at random with its rule and seed shown; below, Pick a case, Draw a defect and Upload a file, each with what it does.",
        src: "/guide/guide-input-bar.webp",
        width: 1408,
        height: 502,
      },
    ],
  },
  {
    id: "guide-cases",
    category: "start",
    title: "Pick a case",
    blocks: [
      {
        type: "list",
        items: [
          "Real situations from the data: a unit that raised an SPE alarm, a slow drift, a scratched wafer, an unknown pattern, a lot with a repeating pattern.",
          "Each case is a real item found by the rule written beside it, not a made-up example.",
        ],
      },
    ],
  },
  {
    id: "guide-draw",
    category: "start",
    title: "Draw a defect",
    blocks: [
      {
        type: "list",
        items: [
          "Pick a wafer layout: each is the die arrangement of a real WM-811K wafer.",
          "All dies start as pass; draw over the ones you want as fail.",
          "Draw two or more wafers to get a lot test, then run: your drawing goes through the same model as real wafers.",
          "A shape unlike the maps the model learned from keeps its nearest pattern, with a prompt to check it by eye.",
        ],
      },
      {
        type: "shot",
        id: "guide-draw",
        caption: "A line of failed dies drawn by hand on a real WM-811K wafer layout",
        alt: "The Draw a defect panel: the six layout size buttons, a wafer layout with a diagonal line of red failed dies, the failed die count and the Run your drawing button, and a note that an unfamiliar shape gets the nearest pattern with a prompt to check it by eye.",
        src: "/guide/guide-draw.webp",
        width: 1376,
        height: 790,
      },
    ],
  },
  {
    id: "guide-upload",
    category: "start",
    title: "Upload a file",
    blocks: [
      {
        type: "list",
        items: [
          "The server checks the file before any run; an error names the column, the row and the problem, and the run waits until you fix it.",
          "Download an empty template (headers only) or an example file with real data in the same format.",
        ],
      },
      {
        type: "table",
        head: ["File", "One row is", "Columns"],
        rows: [
          ["Sensors", "one production unit", "unit_id, timestamp, S001 … S590, result"],
          ["Wafers", "one die", "lot, wafer, x, y, result"],
        ],
      },
      {
        type: "list",
        items: [
          "Sensors: the S columns are the SECOM sensors in order; an empty cell is a missing reading; result is optional (pass or fail).",
          "Timestamps are ISO 8601 without a time zone (YYYY-MM-DDTHH:MM:SS); a space instead of T and Excel date cells also work.",
          "Several units in time order enable drift detection (EWMA and CUSUM) and the sensor health check.",
          "Wafers: x is the column and y the row, counted from 0 at the top left; a position not listed has no die. Several wafers of one lot enable the lot test.",
        ],
      },
      {
        type: "shot",
        id: "guide-upload-check",
        caption:
          "The check on an uploaded wafer file: the real example file from the app, with one cell changed by hand to «faild». The app names the row and the problem, and does not start the run.",
        alt: 'The Upload a file panel after uploading wafers-example.csv: a line saying the file is wafer maps, a red sentence saying it will not run until the error is fixed, and the error: Row 14: the result "faild" is not pass or fail. On the right, the columns of both files and links to the empty templates and real examples.',
        src: "/guide/guide-upload-check.webp",
        width: 1376,
        height: 396,
      },
    ],
  },

  // ───────────────────────── The five stations ─────────────────────────
  {
    id: "guide-stations",
    category: "stations",
    title: "The stations in order",
    blocks: [
      {
        type: "list",
        items: [
          "① «Manufacturing» reads and checks the input: counts, missing readings, unmonitored sensors, time order, and whether the run mixes two sources.",
          "② «Monitoring», for units: failure risk with its measured skill, the most influential sensors (SHAP), T² and SPE control charts with contributing sensors, EWMA and CUSUM drift, and sensor health.",
          "③ «Wafer test», for wafers: defect pattern and confidence, auto-accept or «for review», failure clustering, the most similar real wafers and causes named in the literature; for two or more wafers of a lot, whether a pattern repeats beyond chance, with the stacked map.",
          "«Actual outcome»: the recorded real results (the result column, or wafer results) compared with our predictions, per unit and per wafer.",
          "④ «Investigation» and ⑤ «Decision» start on request from the Alarms column.",
          "Each result appears in its station the moment it is computed.",
          "SECOM sensors and WM-811K wafer maps are separate real sources; when both run together a bar says so.",
        ],
      },
      {
        type: "shot",
        id: "guide-line-run",
        caption:
          "The line running a real sample, with the first alarm in the Alarms column. Taken on a server without live investigations, so a line says so in place of the Investigate button.",
        alt: "The line running a real sample: the sample description (40 SECOM units and 13 WM-811K wafer maps) with the Where this input comes from button, a bar noting the two sources are separate, then the stations: Manufacturing done, Monitoring red with an alarm, Wafer test and Actual outcome computed. The Alarms column shows a T² alarm on a unit with Show unit, and a wafer pattern warning below it.",
        src: "/guide/guide-line-run.webp",
        width: 1392,
        height: 790,
      },
    ],
  },
  {
    id: "guide-station-states",
    category: "stations",
    title: "Station colours",
    blocks: [
      {
        type: "list",
        items: [
          "Grey, «Needs data»: it needs an input you have not given, such as wafers for «Wafer test»; a line says what is missing.",
          "Blue, «Computing»: computing now, with the real elapsed time.",
          "Green, «Done»: finished, no alarm. Red, «Alarm»: an alarm was raised.",
          "Under each station, one sentence and one number sum up its result.",
        ],
      },
    ],
  },
  {
    id: "guide-drawers",
    category: "stations",
    title: "Station details and results",
    blocks: [
      {
        type: "list",
        items: [
          "Click a station tile to open its details in a drawer under the line.",
          "Units: risk with its skill, SHAP bars, sensor groups, T² and SPE with their limits and contributing sensors, EWMA and CUSUM, and the sensor health table.",
          "Wafer: the map, pattern probabilities, the unknown and energy scores, the clustering test, similar wafers, and causes from the literature with their sources.",
          "Lot: the stacked map and the tests.",
          "The result section under the line has three tabs: «Predicted problems», «Failure predictions vs outcome» and «Pattern predictions vs outcome».",
          "Pattern names: WM-811K's «none» is shown as «Light scatter» and «Random» as «Heavy scatter».",
        ],
      },
      {
        type: "shot",
        id: "guide-drawer-wafer",
        caption: "A real wafer's details: the map, the pattern and similar wafers",
        alt: "Details of a real WM-811K wafer: its map with failed dies in red, the predicted pattern Edge-Ring auto-accepted and matching its original label, the pattern probability bars, the unknown score below its threshold and the energy score, the clustering test, and the ten most similar real wafers with each one's recorded or predicted pattern.",
        src: "/guide/guide-drawer-wafer.webp",
        width: 1316,
        height: 863,
      },
    ],
  },

  // ───────────────────────── Alarms ─────────────────────────
  {
    id: "guide-alarms",
    category: "alarms",
    title: "When an alarm is raised",
    blocks: [
      {
        type: "list",
        items: [
          "Alarms appear in a column beside the line, each with a title, a plain meaning, a level (warning or alarm) and an «Investigate» button.",
          "Code raises every alarm with a fixed rule and writes its meaning; AI never raises an alarm.",
        ],
      },
      {
        type: "table",
        head: ["Type", "Raised when"],
        rows: [
          ["risk", "The unit's failure risk reaches the operating threshold."],
          ["t2", "T² is above its limit: the unit is far from normal."],
          ["spe", "SPE is above its limit: the usual relation between sensors broke."],
          ["ewma", "A small, steady drift across consecutive units."],
          ["cusum", "A slow drift building up across consecutive units."],
          ["wafer_pattern", "The model classified the wafer with a defect pattern."],
          ["unknown_pattern", "The wafer is unlike the training maps: check it by eye."],
          ["lot_excursion", "A pattern repeats in the lot more than chance explains."],
        ],
      },
    ],
  },

  // ───────────────────────── Investigation ─────────────────────────
  {
    id: "guide-investigate",
    category: "investigate",
    title: "Press Investigate",
    blocks: [
      {
        type: "list",
        items: [
          "Press «Investigate» on any alarm (needs «Try as engineer»).",
          "The investigator starts at once; each tool it calls and how long it took appear live, on the line and on the investigation page.",
          "The writer model writes the report once, and the investigation moves to «Awaiting decision».",
          "The time shown is the real elapsed time.",
        ],
      },
      {
        type: "shot",
        id: "guide-investigation-live",
        caption:
          "The steps of a real recorded investigation, in order: each tool the investigator called, how long it took and the evidence it produced. The same steps appear one by one during an investigation.",
        alt: "The Run panel of a recorded investigation of a failure risk alarm on unit 1303: the models used and their call counts, then the completed steps in order: reading the unit's record, choosing the next evidence, SHAP, SPE and T² contributions, sensor groups, sensor health and the control chart window. Each step has its duration, each piece of evidence its number from E1 to E7.",
        src: "/guide/guide-investigation-live.webp",
        width: 440,
        height: 1040,
      },
    ],
  },
  {
    id: "guide-report",
    category: "investigate",
    title: "Reading the report",
    blocks: [
      {
        type: "list",
        items: [
          "The summary, findings and proposed actions are written by a language model, so they appear in a serif font; check their evidence links.",
          "Numbers link to their evidence (such as E3): click one to see where it came from.",
          "The wording is «associated with», not «caused by»: the data is historical.",
        ],
      },
    ],
  },
  {
    id: "guide-hypotheses",
    category: "investigate",
    title: "The hypotheses table",
    blocks: [
      {
        type: "table",
        head: ["Column", "Meaning"],
        rows: [
          ["Hypothesis", "A possible cause, often from the causes named in the literature."],
          ["Sources", "The papers that name it."],
          ["Evidence for", "Evidence from the run that supports it."],
          ["Evidence against", "Evidence from the run that goes against it."],
          ["Assessment", "supported, not supported or inconclusive."],
        ],
      },
      {
        type: "list",
        items: [
          "Wafers: evidence comes from pattern confidence, the unknown score, similar wafers and their labels, repetition in the lot, clustering and the stacked map.",
          "Units: which sensor groups drifted, by how much and since when.",
          "«supported» means the run's evidence agrees with it; an engineer confirms the cause.",
        ],
      },
    ],
  },
  {
    id: "guide-investigations-list",
    category: "investigate",
    title: "The investigations list",
    blocks: [
      {
        type: "list",
        items: [
          "«Running»: investigations in progress, with elapsed time.",
          "«Awaiting decision»: a report ready for an engineer.",
          "«Decided»: reports an engineer approved or rejected.",
          "Failed recording attempts are kept behind a button at the bottom of the list.",
        ],
      },
    ],
  },

  // ───────────────────────── Approval and work orders ─────────────────────────
  {
    id: "guide-approve",
    category: "decide",
    title: "Approve or Reject",
    blocks: [
      {
        type: "list",
        items: [
          "Read the report and check its evidence.",
          "Select the actions you agree with and press «Approve»: a work order opens with them.",
          "Or press «Reject report»; the report stays on file, marked rejected.",
          "Nothing happens in the fab without a person's approval.",
        ],
      },
    ],
  },
  {
    id: "guide-work-orders",
    category: "decide",
    title: "Work orders",
    blocks: [
      {
        type: "list",
        items: [
          "A work order appears inside the investigation that opened it, under the report.",
          "Status: open, in progress, done, or cancelled. The engineer updates it with a note and the outcome.",
          "The «Work orders» tab on «Investigations» lists every order with the audit log: who did what, and when.",
        ],
      },
      {
        type: "shot",
        id: "guide-work-orders",
        caption:
          "The Work orders tab and audit log as they were on the server the picture was taken from: no orders yet, since no report had been approved, and two engineer trial sessions in the log.",
        alt: "The Work orders tab on the Investigations page: the Work orders panel says No work orders yet and explains that an order opens when an engineer approves a report's actions; the Audit log panel has an action filter and two entries titled Started an engineer trial, each with its time and session.",
        src: "/guide/guide-work-orders.webp",
        width: 1392,
        height: 443,
      },
    ],
  },
  {
    id: "guide-confirmed-cause",
    category: "decide",
    title: "Confirmed cause",
    blocks: [
      {
        type: "list",
        items: [
          "When closing a work order, the engineer can record the cause actually found and the hypothesis it confirms.",
          "It shows on the work order as the fab's own record, collected for the fab to learn from later.",
        ],
      },
    ],
  },

  // ───────────────────────── Chat ─────────────────────────
  {
    id: "guide-chat",
    category: "chat",
    title: "The Ask button",
    blocks: [
      {
        type: "list",
        items: [
          "«Ask» floats at the bottom of every page and is reachable with Tab.",
          "It can read what is visible on the current page: the run, station and item on «Line», or the open investigation, shown in the «About …» box above the input. Clear it to ask a general question.",
          "Type and press Enter or the arrow button, or pick a suggested question.",
          "It explains results, answers «why», cites causes from the literature, compares with similar wafers, summarises the run and helps with uploads.",
          "It may suggest an investigation; you press the button.",
        ],
      },
    ],
  },

  // ───────────────────────── Savings calculator ─────────────────────────
  {
    id: "guide-calculator",
    category: "calculator",
    title: "Using the calculator",
    blocks: [
      {
        type: "list",
        items: [
          "Open «Savings calculator» under «For experts» and enter your fab's numbers: «Wafers per day», engineer minutes per wafer map, «Engineer hour cost», «Downtime hour cost» and «Wafer cost». All fields start empty.",
          "Each line appears once its inputs are filled: a value, and below it a range from the measured rate's confidence interval.",
          "The two measured rates come from the API: the share of wafer maps auto-classified at a 99% precision target, and the control charts' false alarm rate.",
          "Savings are the engineer hours not spent reviewing auto-classified maps, and their cost; false alarms are counted alongside, priced per downtime hour and per scrapped wafer.",
          "Every assumption is written under the calculator, and each line shows its formula.",
        ],
      },
      {
        type: "shot",
        id: "guide-calculator",
        caption:
          "The calculator with rounded example numbers typed in, as you would type your fab's: 1000 wafers a day, 2 minutes a map, 50 per engineer hour, 1000 per downtime hour and 500 per wafer. These are a reader's example inputs; only the two measured rates come from the API.",
        alt: "The savings calculator: the Your numbers panel with its five fields filled with the example numbers; the Per month panel with auto-classified maps, engineer hours freed and their cost, then false alarms and their downtime and wafer cost, each with a value, a range and a formula; and the Measured rates panel with both rates and their intervals.",
        src: "/guide/guide-calculator.webp",
        width: 1392,
        height: 910,
      },
    ],
  },

  // ───────────────────────── Glossary ─────────────────────────
  {
    id: "guide-glossary",
    category: "glossary",
    title: "Short glossary",
    blocks: [
      {
        type: "table",
        head: ["Term", "Meaning"],
        rows: [
          ["Unit", "One SECOM product, with its sensor readings and final test result."],
          ["Wafer", "The silicon disc the dies are made on."],
          ["Die", "A small square on the wafer; on the map it is pass or fail."],
          ["Lot", "A group of wafers made together."],
          [
            "T²",
            "How far a unit is from normal, along the directions sensors usually move together.",
          ],
          [
            "SPE",
            "How much the usual relation between sensors broke: what the normal model cannot explain.",
          ],
          [
            "EWMA and CUSUM",
            "Drift detectors across consecutive units: small steady drift, and slow cumulative drift.",
          ],
          ["SHAP", "How much each sensor contributed to this unit's risk score."],
          [
            "CI",
            "Confidence interval: the range the true value most likely falls in. Every measured number has one.",
          ],
          ["ROC-AUC and PR-AUC", "How well the model ranks failing units ahead of good ones."],
          [
            "Macro-F1",
            "The average F1 over all patterns, each weighted equally; F1 combines precision and recall.",
          ],
          [
            "Unknown pattern",
            "A map unlike the training maps; the nearest pattern is shown with a prompt to check by eye.",
          ],
          ["Work order", "A fab task opened when an engineer approves a report's actions."],
        ],
      },
    ],
  },
];

/** Every screenshot of the guide, with the entry it belongs to. */
export const SHOT_SLOTS: readonly (Extract<Block, { type: "shot" }> & { entry: string })[] =
  ENTRIES.flatMap((e) =>
    e.blocks.flatMap((b) => (b.type === "shot" ? [{ ...b, entry: e.id }] : [])),
  );
