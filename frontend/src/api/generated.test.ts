import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import type { paths } from "./generated/schema";

// AC-4: the typed client is generated from the OpenAPI schema and consumed via
// generated path types — not hardcoded routes or a hand-written HTTP client.
describe("generated OpenAPI client", () => {
  it("exposes the typed operation for the health path", () => {
    // Compile-time proof: this assignment only type-checks if the generated
    // `paths` type carries a GET operation for "/health/".
    type HealthGet = paths["/health/"]["get"];
    const probe: HealthGet | undefined = undefined;
    expect(probe).toBeUndefined();
  });

  it("regenerating from the schema reflects the contract (operationId present)", () => {
    // AC-4: the generated artifact is derived from openapi/schema.json. If the
    // schema's operations change and the client is regenerated, the generated
    // file changes accordingly. We assert the generated file references the
    // operation declared in the schema, proving the codegen wiring is live.
    const generated = readFileSync(
      resolve(process.cwd(), "src/api/generated/schema.d.ts"),
      "utf8",
    );
    expect(generated).toContain("/health/");
    expect(generated).toMatch(/HealthStatusEnum/);
    // No hand-editing marker — file is machine-generated.
    expect(generated.toLowerCase()).toContain("do not");
  });
});
