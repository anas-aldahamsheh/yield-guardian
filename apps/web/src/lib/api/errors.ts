import type { Problem } from "@yield-guardian/contracts";

/** An API call that did not succeed: an RFC 9457 problem from the API, or no answer at all. */
export class ApiError extends Error {
  override readonly name = "ApiError";

  constructor(
    readonly status: number,
    readonly problem: Problem | null,
    message?: string,
    /** How long the API asked to wait before asking again (its Retry-After), in ms. */
    readonly retryAfterMs: number | null = null,
  ) {
    super(message ?? problem?.detail ?? problem?.title ?? `The API answered ${status}`);
  }

  get code(): Problem["code"] | "network" {
    return this.problem?.code ?? (this.status === 0 ? "network" : "internal_error");
  }
}

export function isProblem(value: unknown): value is Problem {
  return (
    typeof value === "object" &&
    value !== null &&
    "title" in value &&
    "status" in value &&
    "code" in value
  );
}

export interface ErrorCopy {
  title: string;
  detail: string;
}

/**
 * What to tell a person when a request fails: what happened and what to do next. Uses the API's
 * own problem detail when it has one.
 */
export function describeError(error: unknown): ErrorCopy {
  if (error instanceof ApiError) {
    const detail = error.problem?.detail;
    // A 503 with no problem of the API's own is the proxy in front of it while it wakes up.
    if (error.status === 503 && !error.problem) {
      return {
        title: "The service is starting",
        detail: "It sleeps when nobody uses it and takes up to a minute to wake. Try again then.",
      };
    }
    switch (error.code) {
      case "network":
        return {
          title: "The API did not answer",
          detail: "Check that the Yield Guardian API is running and reachable, then try again.",
        };
      case "not_found":
        return {
          title: "Not found",
          detail: detail ?? "This record does not exist, or has not come off the line yet.",
        };
      case "not_ready":
        return {
          title: "The API is still starting",
          detail: detail ?? "Its models and data are loading. Try again in a moment.",
        };
      case "unauthorized":
        return {
          title: "Your session expired",
          detail: "Reload the page, then try again.",
        };
      case "forbidden":
        return {
          title: "Not allowed for this session",
          detail: detail ?? "This action needs a different role. Sign in as an admin to change it.",
        };
      case "csrf_failed":
        return {
          title: "The session check failed",
          detail: "Reload the page to refresh the session, then try again.",
        };
      case "conflict":
        return {
          title: "Already changed",
          detail: detail ?? "Someone changed this first. Reload to see the current state.",
        };
      case "upstream_error":
        return {
          title: "A model service did not answer",
          detail: detail ?? "AMD Token Factory returned an error. Try again in a moment.",
        };
      case "validation_error":
      case "bad_request":
        return {
          title: "The request was not accepted",
          detail: detail ?? "Check the values and try again.",
        };
      default:
        return {
          title: "The API returned an error",
          detail:
            detail ?? `Status ${error.status}. Try again; if it persists, check the API logs.`,
        };
    }
  }
  return {
    title: "Something went wrong",
    detail: error instanceof Error ? error.message : "Try again.",
  };
}
