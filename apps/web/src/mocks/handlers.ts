/**
 * MSW request handlers that answer like the Yield Guardian API, from the contract fixtures.
 * Development and tests only (see fixtures.ts). Records that have no fixture answer 404 with a
 * problem, the way the API does for an unknown ID, so empty and error states stay visible.
 */
import type {
  ChatEvent,
  ChatRequest,
  Hypothesis,
  Investigation,
  InvestigationEvent,
  Problem,
  SessionInfo,
  WorkOrder,
  WorkOrderUpdate,
} from "@yield-guardian/contracts";
import { CSRF_HEADER, PROBLEM_MEDIA_TYPE } from "@yield-guardian/contracts";
import { http, HttpResponse, type HttpHandler } from "msw";

import { fixture } from "./fixtures";
import { TEST_DOUBLE } from "./test-doubles";

const API = "*/api/v1";
const SESSION_COOKIE = "yg_session";

function problem(status: number, code: Problem["code"], title: string, detail?: string) {
  const body: Problem = { type: "about:blank", title, status, detail: detail ?? null, code };
  return HttpResponse.json(body, { status, headers: { "Content-Type": PROBLEM_MEDIA_TYPE } });
}

const notInFixtures = (what: string) =>
  problem(404, "not_found", "Not found", `${what} has no development fixture.`);

function json(name: string) {
  return () => HttpResponse.json(fixture(name) as Record<string, unknown>);
}

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

function eventStream<T>(
  events: T[],
  frame: (event: T) => string,
  delayFor: (event: T, index: number) => number,
): Response {
  const encoder = new TextEncoder();
  const stream = new ReadableStream<Uint8Array>({
    async start(controller) {
      try {
        for (const [index, event] of events.entries()) {
          await sleep(delayFor(event, index));
          controller.enqueue(encoder.encode(frame(event)));
        }
      } finally {
        controller.close();
      }
    },
  });
  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
    },
  });
}

/**
 * Test doubles for the v2 report fields (V5): an investigation whose report carries a
 * hypothesis table, and its work order, closed with a confirmed cause. Built from the fixtures'
 * own evidence IDs, numbers and literature source, and labelled as test doubles; development
 * and tests only, like every handler here.
 */
function hypothesisDouble(base: Investigation): Investigation {
  const source = fixture<{ sources: { source_id: string }[] }>("get_pattern_causes").sources[0]
    ?.source_id;
  const share = base.report?.numbers.find((n) => n.evidence_id === "E2");
  const hypotheses: Hypothesis[] = [
    {
      hypothesis:
        "Test double: the sensor group with the largest T² share is associated with the alarm.",
      source_ids: source ? [source] : [],
      evidence_for: [
        {
          evidence_id: "E2",
          observation: share
            ? `Its share of T² is ${share.as_written}.`
            : "Its share of T² is the largest.",
        },
      ],
      evidence_against: [
        { evidence_id: "E3", observation: "Test double: similar units did not raise the alarm." },
      ],
      assessment: "supported",
    },
    {
      hypothesis: "Test double: a single faulty sensor, not the group.",
      source_ids: [],
      evidence_for: [],
      evidence_against: [
        { evidence_id: "E4", observation: "Test double: more than one sensor of the group moved." },
      ],
      assessment: "not_supported",
    },
  ];
  return {
    ...base,
    investigation_id: TEST_DOUBLE.investigationId,
    title: "Test double: report with a hypothesis table",
    work_order_id: TEST_DOUBLE.workOrderId,
    report: base.report ? { ...base.report, hypotheses } : base.report,
  };
}

function workOrderDouble(): WorkOrder {
  const base = fixture<{ items: WorkOrder[] }>("list_work_orders").items[0]!;
  return {
    ...base,
    work_order_id: TEST_DOUBLE.workOrderId,
    investigation_id: TEST_DOUBLE.investigationId,
    title: "Test double: work order closed with a confirmed cause",
    status: "done",
    confirmed_cause: {
      text: "Test double: the engineer found the cause on the tool.",
      hypothesis_index: 0,
    },
  };
}

/** The chat's offer to investigate the unit on screen (a test double of the model's suggestion). */
function offerDouble(unitId: number): ChatEvent {
  return {
    type: "suggestion",
    action: "start_investigation",
    trigger: { kind: "unit", ref: String(unitId) },
    title: `Unit ${unitId}`,
  };
}

export interface MockOptions {
  /** Milliseconds between streamed events; 0 in tests. */
  streamDelayMs?: number;
}

/** Fresh handler set with its own sessions and decisions. */
export function createHandlers({ streamDelayMs = 420 }: MockOptions = {}): HttpHandler[] {
  const sessions = new Map<string, SessionInfo>();
  const decided = new Set<string>();
  const updatedOrders = new Map<string, WorkOrder>();

  const workOrderFor = (id: string): WorkOrder | null =>
    updatedOrders.get(id) ??
    (id === TEST_DOUBLE.workOrderId
      ? workOrderDouble()
      : (fixture<{ items: WorkOrder[] }>("list_work_orders").items.find(
          (item) => item.work_order_id === id,
        ) ?? null));

  const sessionOf = (request: Request): SessionInfo => {
    const cookie = request.headers.get("cookie") ?? "";
    const id = cookie.match(new RegExp(`${SESSION_COOKIE}=([^;]+)`))?.[1];
    return (id && sessions.get(id)) || fixture<SessionInfo>("get_session");
  };

  const startSession = (session: SessionInfo) => {
    const id = crypto.randomUUID();
    sessions.set(id, session);
    return HttpResponse.json(session, {
      headers: { "Set-Cookie": `${SESSION_COOKIE}=${id}; Path=/; HttpOnly; SameSite=Lax` },
    });
  };

  /** Engineer or admin with a matching CSRF token, as the API requires for every action. */
  const guard = (request: Request, role: "engineer" | "admin" = "engineer") => {
    const session = sessionOf(request);
    if (session.role === "visitor") {
      return problem(
        401,
        "unauthorized",
        "Sign in first",
        "Start a session with “Try as engineer”.",
      );
    }
    if (role === "admin" && session.role !== "admin") {
      return problem(403, "forbidden", "Admins only", "Only an admin can assign models to roles.");
    }
    if (request.headers.get(CSRF_HEADER) !== session.csrf_token) {
      return problem(403, "csrf_failed", "CSRF check failed");
    }
    return null;
  };

  const investigationFor = (id: string): Investigation | null => {
    if (id === TEST_DOUBLE.investigationId)
      return hypothesisDouble(fixture<Investigation>("decide_investigation"));
    const name = decided.has(id) ? "decide_investigation" : "get_investigation";
    const inv = fixture<Investigation>(name);
    if (inv.investigation_id === id) return inv;
    const listed = fixture<{ items: Investigation[] }>("list_investigations").items.find(
      (item) => item.investigation_id === id,
    );
    return listed ? ({ ...inv, ...listed } as Investigation) : null;
  };

  return [
    http.get(`${API}/health`, () => HttpResponse.json({ status: "ok" })),
    http.get(`${API}/meta`, json("get_meta")),
    http.get(`${API}/results`, json("get_measured_results")),

    // Session
    http.get(`${API}/session`, ({ request }) => HttpResponse.json(sessionOf(request))),
    http.post(`${API}/session/guest`, () => startSession(fixture("start_guest_session"))),
    http.post(`${API}/session/login`, async ({ request }) => {
      const body = (await request.json()) as { username?: string; password?: string };
      if (!body.username || !body.password) return problem(401, "unauthorized", "Sign-in failed");
      return startSession(fixture("login"));
    }),
    http.post(`${API}/session/logout`, () => new HttpResponse(null, { status: 204 })),

    // Units and alarms
    http.get(`${API}/alarms`, json("list_alarms")),
    http.get(`${API}/units`, json("list_units")),
    http.get(`${API}/fdc/series`, json("get_fdc_series")),
    http.get(`${API}/units/:unitId`, ({ params }) => {
      const unit = fixture<{ unit_id: number }>("get_unit");
      return Number(params.unitId) === unit.unit_id
        ? HttpResponse.json(unit)
        : notInFixtures(`Unit ${String(params.unitId)}`);
    }),
    http.get(`${API}/units/:unitId/risk`, ({ params }) => {
      const risk = fixture<{ unit_id: number }>("get_unit_risk");
      return Number(params.unitId) === risk.unit_id
        ? HttpResponse.json(risk)
        : notInFixtures(`Unit ${String(params.unitId)}`);
    }),
    http.get(`${API}/units/:unitId/explanation`, ({ params }) => {
      const explanation = fixture<{ unit_id: number }>("get_unit_explanation");
      return Number(params.unitId) === explanation.unit_id
        ? HttpResponse.json(explanation)
        : notInFixtures(`The explanation of unit ${String(params.unitId)}`);
    }),
    http.get(`${API}/units/:unitId/contributions`, ({ params, request }) => {
      const contributions = fixture<{ unit_id: number; statistic: string }>(
        "get_unit_contributions",
      );
      const statistic = new URL(request.url).searchParams.get("statistic") ?? "t2";
      return Number(params.unitId) === contributions.unit_id &&
        statistic === contributions.statistic
        ? HttpResponse.json(contributions)
        : notInFixtures(
            `The ${statistic.toUpperCase()} contributions of unit ${String(params.unitId)}`,
          );
    }),

    // Sensors
    http.get(`${API}/sensors/groups`, json("get_sensor_groups")),
    http.get(`${API}/sensors/health`, json("get_sensor_health")),
    http.get(`${API}/sensors/:sensor/series`, ({ params }) => {
      const series = fixture<{ sensor: string }>("get_sensor_series");
      return params.sensor === series.sensor
        ? HttpResponse.json(series)
        : notInFixtures(`The series of ${String(params.sensor)}`);
    }),
    http.get(`${API}/secom/operating-points`, json("get_operating_points")),

    // Investigations
    http.get(`${API}/investigations`, json("list_investigations")),
    http.post(`${API}/investigations`, ({ request }) => {
      const denied = guard(request);
      if (denied) return denied;
      return HttpResponse.json(fixture("create_investigation"), { status: 202 });
    }),
    http.get(`${API}/investigations/:id`, ({ params }) => {
      const inv = investigationFor(String(params.id));
      return inv ? HttpResponse.json(inv) : notInFixtures(`Investigation ${String(params.id)}`);
    }),
    http.get(`${API}/investigations/:id/events`, ({ params, request }) => {
      const id = String(params.id);
      const inv = investigationFor(id);
      if (!inv) return notInFixtures(`Investigation ${id}`);
      const after = Number(request.headers.get("Last-Event-ID") ?? "0") || 0;
      const events = fixture<InvestigationEvent[]>("stream_investigation_events").filter(
        (event) => event.seq > after,
      );
      return eventStream(
        events,
        (event) => `event: ${event.type}\nid: ${event.seq}\ndata: ${JSON.stringify(event)}\n\n`,
        (event) =>
          streamDelayMs === 0
            ? 0
            : event.type === "report"
              ? streamDelayMs * 4
              : event.type === "verification"
                ? streamDelayMs * 3
                : streamDelayMs,
      );
    }),
    http.post(`${API}/investigations/:id/decision`, ({ params, request }) => {
      const denied = guard(request);
      if (denied) return denied;
      const id = String(params.id);
      const inv = investigationFor(id);
      if (!inv) return notInFixtures(`Investigation ${id}`);
      if (inv.status !== "awaiting_decision") {
        return problem(409, "conflict", "Already decided", "This report already has a decision.");
      }
      decided.add(id);
      return HttpResponse.json(investigationFor(id));
    }),
    http.get(`${API}/investigations/:id/evidence/:evidenceId`, ({ params }) => {
      const inv = investigationFor(String(params.id));
      const evidence = inv?.evidence.find((item) => item.evidence_id === params.evidenceId);
      return evidence
        ? HttpResponse.json(evidence)
        : notInFixtures(`Evidence ${String(params.evidenceId)}`);
    }),

    // Work orders and audit
    http.get(`${API}/work-orders`, json("list_work_orders")),
    http.get(`${API}/work-orders/:id`, ({ params }) => {
      const order = workOrderFor(String(params.id));
      return order ? HttpResponse.json(order) : notInFixtures(`Work order ${String(params.id)}`);
    }),
    http.patch(`${API}/work-orders/:id`, async ({ params, request }) => {
      const denied = guard(request);
      if (denied) return denied;
      const order = workOrderFor(String(params.id));
      if (!order) return notInFixtures(`Work order ${String(params.id)}`);
      const patch = (await request.json()) as WorkOrderUpdate;
      const status = patch.status ?? order.status;
      if (patch.confirmed_cause && status !== "done") {
        return problem(
          400,
          "bad_request",
          "Invalid argument",
          'A confirmed cause is recorded when the work order is closed: send it with status "done".',
        );
      }
      const next: WorkOrder = {
        ...order,
        status,
        note: "note" in patch ? (patch.note ?? null) : order.note,
        outcome: "outcome" in patch ? (patch.outcome ?? null) : order.outcome,
        outcome_confirmed: patch.outcome_confirmed ?? order.outcome_confirmed,
        confirmed_cause:
          status !== "done"
            ? null
            : "confirmed_cause" in patch
              ? (patch.confirmed_cause ?? null)
              : (order.confirmed_cause ?? null),
        updated_at: new Date().toISOString(),
      };
      updatedOrders.set(next.work_order_id, next);
      return HttpResponse.json(next);
    }),
    http.get(`${API}/audit`, json("list_audit_entries")),

    // Wafers and lots
    http.get(`${API}/wafers`, json("list_wafers")),
    http.get(`${API}/wafers/hero`, json("get_hero_wafer")),
    http.get(`${API}/wafers/:waferId`, ({ params }) => {
      const id = String(params.waferId);
      const wafer = fixture<{ wafer: { wafer_id: string } }>("get_wafer");
      if (wafer.wafer.wafer_id === id) return HttpResponse.json(wafer);
      const similar = fixture<{ results: { wafer: { wafer_id: string }; map: unknown }[] }>(
        "get_similar_wafers",
      ).results.find((item) => item.wafer.wafer_id === id);
      if (similar) {
        return HttpResponse.json({
          wafer: similar.wafer,
          map: similar.map,
          prediction: null,
          spatial: null,
          attribution: (wafer as unknown as { attribution: string }).attribution,
        });
      }
      return notInFixtures(`Wafer ${id}`);
    }),
    http.get(`${API}/wafers/:waferId/prediction`, ({ params }) => {
      const prediction = fixture<{ wafer_id: string }>("get_wafer_prediction");
      return params.waferId === prediction.wafer_id
        ? HttpResponse.json(prediction)
        : notInFixtures(`The prediction for wafer ${String(params.waferId)}`);
    }),
    http.get(`${API}/wafers/:waferId/similar`, ({ params }) => {
      const similar = fixture<{ wafer_id: string }>("get_similar_wafers");
      return params.waferId === similar.wafer_id
        ? HttpResponse.json(similar)
        : notInFixtures(`Similar wafers for ${String(params.waferId)}`);
    }),
    http.get(`${API}/lots`, json("list_lots")),
    http.get(`${API}/lots/:lot`, ({ params }) => {
      const lot = fixture<{ lot: string }>("get_lot");
      return params.lot === lot.lot
        ? HttpResponse.json(lot)
        : notInFixtures(`Lot ${String(params.lot)}`);
    }),

    // Knowledge
    http.get(`${API}/knowledge/search`, json("search_knowledge")),
    http.get(`${API}/knowledge/patterns`, json("get_pattern_causes")),

    // Chat (SSE over POST)
    http.post(`${API}/chat`, async ({ request }) => {
      const denied = guard(request);
      if (denied) return denied;
      const body = (await request.json().catch(() => null)) as ChatRequest | null;
      const unitId = body?.context?.unit_id;
      const events = fixture<ChatEvent[]>("chat");
      if (unitId != null) {
        const at = events.findIndex((e) => e.type === "token");
        events.splice(at < 0 ? events.length - 1 : at, 0, offerDouble(unitId));
      }
      return eventStream(
        events,
        (event) => `event: ${event.type}\ndata: ${JSON.stringify(event)}\n\n`,
        (event) => (streamDelayMs === 0 ? 0 : event.type === "token" ? 45 : streamDelayMs),
      );
    }),

    // Models
    http.get(`${API}/llm/catalog`, () =>
      HttpResponse.json(fixture<unknown[]>("get_model_catalog")),
    ),
    http.get(`${API}/llm/roles`, () =>
      HttpResponse.json(fixture<unknown[]>("get_role_assignments")),
    ),
    http.put(`${API}/llm/roles/:role`, async ({ params, request }) => {
      const denied = guard(request, "admin");
      if (denied) return denied;
      const update = (await request.json()) as Record<string, unknown>;
      const current = fixture<{ role: string }[]>("get_role_assignments").find(
        (item) => item.role === params.role,
      );
      return HttpResponse.json({
        ...current,
        ...Object.fromEntries(Object.entries(update).filter(([, v]) => v != null)),
        role: params.role,
        updated_at: new Date().toISOString(),
        updated_by: sessionOf(request).display_name,
      });
    }),
    http.get(`${API}/llm/usage`, json("get_llm_usage")),
    http.get(`${API}/llm/evaluations`, json("get_llm_evaluations")),

    // Methods
    http.get(`${API}/methods`, json("get_methods_overview")),
    http.get(`${API}/methods/secom`, json("get_secom_metrics")),
    http.get(`${API}/methods/wafermap`, json("get_wafer_metrics")),
    http.get(`${API}/methods/model-cards/:name`, ({ params }) => {
      const card = fixture<{ name: string }>("get_model_card");
      return params.name === card.name
        ? HttpResponse.json(card)
        : notInFixtures(`The ${String(params.name)} model card`);
    }),
  ];
}
