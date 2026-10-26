/**
 * Stubs `global.fetch` by URL pathname for component tests (spec §5 F1, day 0).
 *
 *   const api = mockApi({ "/api/story": story, "POST /api/overrides": (req) => reply(201, {...}) });
 *   ...
 *   expect(api.count("/api/story")).toBe(1);
 *
 * - A key is either "/path" (any method) or "METHOD /path" (takes precedence).
 * - A value is the JSON body (status 200), a `reply(status, body)`, or a function of the request
 *   returning either of those (sync or async).
 * - An unmocked path rejects the fetch AND fails the running test (checked when it finishes).
 * - fetch is restored automatically when the test finishes; `api.restore()` restores it earlier.
 *
 * Rendering the whole App (shell included) also needs the shell's own requests:
 *
 *   mockApi({ ...shellRoutes(journeyFixture("pronto")), "/api/story": story });
 */
import { onTestFinished, vi } from "vitest";

import type { JourneyStatus } from "../types/journey";
import journeyFixtures from "./fixtures/journey.json";

export type JourneyFixture = Exclude<keyof typeof journeyFixtures, "_comment">;

/**
 * A fresh copy of a `GET /api/journey` fixture (`test/fixtures/journey.json`): "pronto", "rerunning",
 * "running", "queued" (done/total null), "failed", "none", "dados" or "derived" (plan_derived).
 */
export function journeyFixture(state: JourneyFixture = "pronto"): JourneyStatus {
  return structuredClone(journeyFixtures[state]) as JourneyStatus;
}

/**
 * Requests made by the app shell (`AppLayout`: sidebar journey + alerts badge, topbar run status and
 * alerts bell). Spread them into `mockApi` when rendering through `App`.
 */
export function shellRoutes(
  journey: JourneyStatus = journeyFixture("pronto"),
  urgentAlerts: { critical?: number; high?: number } = {},
): Record<string, MockHandler> {
  return {
    "/api/journey": journey,
    "/api/alerts": {
      summary: {
        total: (urgentAlerts.critical ?? 0) + (urgentAlerts.high ?? 0),
        by_severity: {
          critical: urgentAlerts.critical ?? 0,
          high: urgentAlerts.high ?? 0,
          medium: 0,
          low: 0,
        },
        by_type: {},
      },
      alerts: [],
    },
    "/api/forecast/job": null,
  };
}

export interface MockRequest {
  method: string;
  path: string;
  url: URL;
  /** Query params, decoded. */
  params: URLSearchParams;
  /** Parsed JSON body (FormData / raw string passed through), undefined for GET. */
  body: unknown;
}

export interface MockReply {
  __mockReply: true;
  status: number;
  body: unknown;
}

type Resolved = unknown | MockReply;
export type MockHandler = Resolved | ((req: MockRequest) => Resolved | Promise<Resolved>);

/** A response with an explicit HTTP status: `reply(400, { detail: "Período inválido…" })`. */
export function reply(status: number, body: unknown = null): MockReply {
  return { __mockReply: true, status, body };
}

const isReply = (v: unknown): v is MockReply =>
  !!v && typeof v === "object" && (v as MockReply).__mockReply === true;

function fakeResponse(status: number, body: unknown): Response {
  const text = body === undefined ? "" : JSON.stringify(body);
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: status >= 200 && status < 300 ? "OK" : "Erro",
    headers: new Headers({ "Content-Type": "application/json" }),
    json: async () => (text ? JSON.parse(text) : null),
    text: async () => text,
  } as Response;
}

function parseBody(body: BodyInit | null | undefined): unknown {
  if (body == null) return undefined;
  if (typeof body === "string") {
    try {
      return JSON.parse(body);
    } catch {
      return body;
    }
  }
  return body;
}

export function mockApi(routes: Record<string, MockHandler>) {
  const original = globalThis.fetch;
  const calls: MockRequest[] = [];
  const unmocked: string[] = [];

  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const href = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    const url = new URL(href, "http://localhost");
    const method = (init?.method ?? "GET").toUpperCase();
    const req: MockRequest = {
      method,
      path: url.pathname,
      url,
      params: url.searchParams,
      body: parseBody(init?.body),
    };
    calls.push(req);
    const key = `${method} ${url.pathname}` in routes ? `${method} ${url.pathname}` : url.pathname;
    if (!(key in routes)) {
      const msg = `mockApi: rota não mockada ${method} ${url.pathname}${url.search}`;
      unmocked.push(msg);
      throw new TypeError(msg);
    }
    const handler = routes[key];
    const out =
      typeof handler === "function" ? await (handler as (r: MockRequest) => Resolved)(req) : handler;
    return isReply(out) ? fakeResponse(out.status, out.body) : fakeResponse(200, out);
  });

  globalThis.fetch = fetchMock as unknown as typeof fetch;
  const restore = () => {
    globalThis.fetch = original;
  };
  try {
    onTestFinished(() => {
      restore();
      if (unmocked.length) throw new Error(unmocked.join("\n"));
    });
  } catch {
    /* called outside a running test (e.g. at module level): the caller restores fetch */
  }

  return {
    fetch: fetchMock,
    calls,
    unmocked,
    restore,
    /** Number of requests to a pathname (optionally a "METHOD /path"). */
    count: (key: string) => {
      const [m, p] = key.includes(" ") ? key.split(" ", 2) : [undefined, key];
      return calls.filter((c) => c.path === p && (!m || c.method === m.toUpperCase())).length;
    },
    /** Requests to a pathname, in order. */
    requests: (path: string) => calls.filter((c) => c.path === path),
  };
}
