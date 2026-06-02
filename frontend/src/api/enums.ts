// GP-010 (frontend translation): enumerated states — order states, user roles,
// NCR states, etc. — MUST come from the generated OpenAPI client's enum schemas
// or from typed `as const` objects. Bare string literals scattered across the
// codebase are forbidden (a typo compiles fine and breaks silently).
//
// Pattern to follow once the backend exposes real enums:
//
//   import type { components } from "./generated/schema";
//   export type OrderState = components["schemas"]["OrderStateEnum"];
//
// Until those contracts exist (NSG-18, NSG-25), the only enum is the trivial
// health probe status, re-exported here from the generated client so consumers
// import the typed value rather than re-declaring "ok" / "degraded".

import type { components } from "./generated/schema";

export type HealthStatus = components["schemas"]["HealthStatusEnum"];

/**
 * Typed lookup of health-status values. Use `HEALTH_STATUS.ok` instead of the
 * literal "ok" so the set of valid states stays discoverable and refactor-safe.
 */
export const HEALTH_STATUS = {
  ok: "ok",
  degraded: "degraded",
} as const satisfies Record<HealthStatus, HealthStatus>;
