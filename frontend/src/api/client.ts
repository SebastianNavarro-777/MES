// Minimal fetch wrapper. A generated client (drf-spectacular) will replace this
// once the orders backend (Epic NSG-14) publishes its OpenAPI schema; until
// then the frontend talks to MSW-mocked endpoints with the same contract.

/** RFC 7807 problem+json document returned by the API on errors. */
export interface ProblemDocument {
  readonly type: string;
  readonly title: string;
  readonly status: number;
  readonly detail?: string;
  readonly instance?: string;
}

/** Error carrying the HTTP status and (when present) the problem+json body. */
export class ApiError extends Error {
  readonly status: number;
  readonly problem: ProblemDocument | null;

  constructor(status: number, problem: ProblemDocument | null, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.problem = problem;
  }

  get isNotFound(): boolean {
    return this.status === 404;
  }
}

export const API_BASE = "/api/v1";

async function parseProblem(response: Response): Promise<ProblemDocument | null> {
  try {
    const body: unknown = await response.json();
    if (body !== null && typeof body === "object" && "status" in body) {
      return body as ProblemDocument;
    }
  } catch {
    // Body was not JSON; fall through to a null problem document.
  }
  return null;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { Accept: "application/json", ...(init?.headers ?? {}) },
    ...init,
  });

  if (!response.ok) {
    const problem = await parseProblem(response);
    throw new ApiError(
      response.status,
      problem,
      problem?.detail ?? problem?.title ?? response.statusText,
    );
  }

  return (await response.json()) as T;
}

export function getJson<T>(path: string): Promise<T> {
  return request<T>(path);
}

export function postJson<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}
