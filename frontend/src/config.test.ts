import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

// AC-2: TypeScript runs in strict mode with no implicit `any`. The production
// `build` script (`tsc --noEmit && vite build`) fails on any type error; this
// test guards the configuration that makes that gate meaningful.
//
// tsconfig.json is JSONC (it carries comments), so we assert on the raw text
// rather than JSON.parse.
describe("tsconfig strictness", () => {
  const tsconfig = readFileSync(resolve(process.cwd(), "tsconfig.json"), "utf8");

  it("enables strict mode", () => {
    expect(tsconfig).toMatch(/"strict":\s*true/);
  });

  it("forbids implicit any", () => {
    expect(tsconfig).toMatch(/"noImplicitAny":\s*true/);
  });
});
