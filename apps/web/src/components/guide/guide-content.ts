/**
 * The user guide, the last section of How it works (/how#guide). Interface labels are quoted as
 * they appear on screen.
 *
 * It holds no measured number: those are read from the API in the expert section above it. A
 * `shot` block is a screenshot of the real product under public/guide/, at 1440 px in the light
 * theme and cropped to what its entry describes. A screen that shows data is taken from the real
 * API, never from the development fixtures; the idle Line page (guide-nav, guide-input-bar) shows
 * none, so it may be taken behind the development gateway. A screen that cannot be taken from
 * real data has no picture rather than an out-of-date one.
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
  { id: "pages", label: "The pages", lede: "Five pages in the top bar, and a chat button." },
  {
    id: "start",
    label: "Four ways to start",
    lede: "Nothing moves on the line until you give it input.",
  },
  {
    id: "stations",
    label: "The five stations",
    lede: "What each station computes, and what its states mean.",
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
  // ───────────────────────── The pages ─────────────────────────
  {
    id: "guide-pages",
    category: "pages",
    title: "Line, Investigations, Work orders, Workspace and How it works",
    blocks: [
      {
        type: "list",
        items: [
          "«Line»: give the production line an input and watch each station's result as it is computed.",
          "«Investigations»: investigations running, awaiting a decision and decided.",
          "«Work orders»: every work order opened by an approved report, with the audit log.",
          "«Workspace»: the runs kept on this device, to reopen, rename, compare, run again, download, archive or delete.",
          "«How it works»: this page, with the plain introduction, «For experts» and this guide.",
          "«History» in the top bar opens the same runs in a side panel; the theme button switches light and dark.",
          "The floating «Ask» button at the bottom of every page opens the chat.",
          "On a phone the pages sit behind the menu button.",
        ],
      },
      {
        type: "shot",
        id: "guide-nav",
        caption: "The top bar with its five pages, and the Ask button at the bottom",
        alt: "The Line page before any input: the top bar holds the Line, Investigations, Work orders, Workspace and How it works links, the History button and the theme button; below are the title Live Semiconductor Production Line, the Run Random Real Sample button and the three other ways in, a link to the workspace, the idle stations and the floating Ask button.",
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
          "/work-orders/… opens that work order under the report of the investigation that opened it, or on «Work orders» when the investigation cannot be looked up.",
          "/models, /methods and /guide open their sections of «How it works».",
          "The language-model role settings live on a hidden admin page: anyone can read it, only the admin changes roles.",
        ],
      },
    ],
  },
  {
    id: "guide-workspace",
    category: "pages",
    title: "Workspace",
    blocks: [
      {
        type: "list",
        items: [
          "Every run you start is kept in this device's workspace with its live status.",
          "Each run's menu opens it on the line, investigates its alarms, renames it, runs the same input again, compares it with another run, downloads its results or report, archives it or deletes it.",
          "Deleting the run that is open on the line, or starting a fresh workspace, clears the line at once.",
          "«Continue on another device» gives a code; «Join another workspace with a code» uses one.",
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
          "No sign-in is needed: the first visit opens a session and a workspace for this device.",
          "«Investigate» and «Ask» start an engineer guest session on their own when there is none, so you can investigate, approve or reject, update a work order and chat.",
          "Changing the model behind a role needs the admin account.",
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
          "«Run Random Real Sample»: one click; the server draws, with a recorded seed, real SECOM test units the risk model never saw and real WM-811K wafer maps. The rule and seed are shown with the run.",
          "«Pick a case»: choose a real case from the list, or browse the real units and wafers yourself.",
          "«Draw a defect»: paint failing dies on a real WM-811K wafer layout.",
          "«Upload fab data»: a CSV or Excel (.xlsx) file from your fab, checked before it runs.",
          "Every input goes through the same code, so a sample is processed exactly like your file.",
        ],
      },
      {
        type: "shot",
        id: "guide-input-bar",
        caption: "The input bar with its four buttons on the idle Line page",
        alt: "The page title Live Semiconductor Production Line with a sentence on what the line does; beside it the Run Random Real Sample button with an information button and the note SECOM (590 sensors) and WM-811K (wafer maps); below, Pick a case, Draw a defect and Upload fab data, each with what it does.",
        src: "/guide/guide-input-bar.webp",
        width: 1408,
        height: 498,
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
          "Pick a die layout: each is the die arrangement of a real WM-811K wafer.",
          "All dies start as pass; paint the ones you want as failing.",
          "Add more wafers to get a lot test, then run: your drawing goes through the same model as real wafers.",
          "A shape unlike the maps the model learned from keeps its nearest pattern, with a prompt to check it by eye.",
        ],
      },
    ],
  },
  {
    id: "guide-upload",
    category: "start",
    title: "Upload fab data",
    blocks: [
      {
        type: "list",
        items: [
          "Upload a sensor file, a wafer file, or one of each to run both streams together.",
          "The server checks the file before any run; an error names the row and the problem, and the run waits until you fix it.",
          "Download an empty template (headers only) or a real example file in the same format, as CSV or Excel.",
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
          "③ «Wafer test», for wafers: defect pattern and confidence, classified automatically or «for review», failure clustering, the most similar real wafers and causes named in the literature; for two or more wafers of a lot, whether a pattern repeats beyond chance, with the stacked map.",
          "«Actual outcome»: the recorded real results (the result column, or wafer labels) compared with our predictions, per unit and per wafer.",
          "④ «Investigation» and ⑤ «Decision» start on request, from an alarm.",
          "Each result appears in its station the moment it is computed.",
          "SECOM sensors and WM-811K wafer maps are separate real sources; when both run together a bar says so.",
        ],
      },
    ],
  },
  {
    id: "guide-station-states",
    category: "stations",
    title: "Station states",
    blocks: [
      {
        type: "list",
        items: [
          "«Bypassed»: the station needs an input you have not given, such as wafers for «Wafer test»; a line says what is missing.",
          "«Computing»: computing now, with the real elapsed time.",
          "«Done»: finished, no alarm. «Alarm»: an alarm was raised. «Stopped»: the station could not finish.",
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
          "Click a station tile to inspect it: the station stays on the left with its diagnostics and its details open beside it. Tabs switch station, and «Back to full pipeline» returns to the whole line.",
          "Units: risk with its skill, SHAP bars, sensor groups, T² and SPE with their limits and contributing sensors, EWMA and CUSUM, and the sensor health table.",
          "Wafer: the map, pattern probabilities, the unknown and energy scores, the clustering test, similar wafers, and causes from the literature with their sources.",
          "Lot: the stacked map and the tests.",
          "The result section under the line has the tabs «Predicted problems», «In-Line Alarms», «Failure predictions vs outcome» and «Pattern predictions vs outcome».",
          "Pattern names: WM-811K's «none» is shown as «Light scatter» and «Random» as «Heavy scatter».",
        ],
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
          "Alarms are listed in the «In-Line Alarms» tab of the result section, each with a title, a plain meaning, a level (warning or alarm) and an «Investigate» button.",
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
          "Press «Investigate» on any alarm; it starts an engineer guest session first if you have none.",
          "The investigator starts at once; the alarm then shows its status and «Open investigation».",
          "The investigation page opens on the «Agent Run» tab of the right panel (tabs «Evidence», «Agent Run» and «Trace»): each tool the investigator called and how long it took, as it happens.",
          "While it runs, the left side shows the current step and the time so far in place of the report.",
          "The writer model writes the report once, in a single pass, and the investigation moves to «Awaiting decision».",
          "By default every language-model role but document reading runs on Claude Haiku (Anthropic), named with its version under «For experts». The time shown is the real elapsed time.",
        ],
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
          "The summary, findings and proposed actions are written by a language model, so they appear in a serif font.",
          "The report is not checked by a second model or by code: check its evidence links yourself before you approve.",
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
          "Select the actions you agree with and press «Approve»: a work order opens with them, and a card says «Approved · Work order WO-… opened» with «Open work order».",
          "Or press «Reject report»: the report stays on file, marked rejected, and the card says «Rejected · no work order» with «Back to the line».",
          "The recorded example investigation every visitor sees cannot be decided.",
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
          "«Work orders» in the top bar lists every order, newest first, with the audit log beside it: who did what, and when.",
          "Change an order's status straight from the list with its status menu, or delete it with its «×» (its investigation and report stay). The example order can be neither changed nor deleted.",
          "Each order is also shown under the report of the investigation that opened it.",
          "Its «Update» form sets the status (Open, In progress, Done or Cancelled), a note and the outcome, with «I confirm this outcome»; every change goes to the audit log with your name.",
        ],
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
          "When setting a work order to Done, the engineer can record the cause actually found and the hypothesis it confirms.",
          "It shows on the work order as the fab's own record, collected for the fab to learn from later. Reopening the order withdraws it.",
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
          "It always reads what is visible on the page: the run, station and item on «Line», or the open investigation.",
          "Type and press Enter or the arrow button, or pick a suggested question. Write in English or Arabic: each message takes its direction from its own text.",
          "Attach a Markdown (.md) or text file to ask about it, and export the conversation as Markdown.",
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
          ["Unit", "One SECOM product, with its sensor readings and its recorded test result."],
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
