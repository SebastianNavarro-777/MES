import js from "@eslint/js";
import globals from "globals";
import tseslint from "typescript-eslint";

// AC-7: TypeScript lint that the verification pipeline runs. The
// no-explicit-any rule complements `tsc --strict` to keep implicit/explicit
// `any` out of the codebase.
export default tseslint.config(
  {
    ignores: [
      "dist",
      "src/api/generated/**",
      "playwright-report",
      "test-results",
      "eslint.config.js",
    ],
  },
  js.configs.recommended,
  ...tseslint.configs.recommendedTypeChecked,
  {
    languageOptions: {
      ecmaVersion: 2022,
      globals: { ...globals.browser, ...globals.node },
      parserOptions: {
        projectService: true,
        tsconfigRootDir: import.meta.dirname,
      },
    },
    rules: {
      "@typescript-eslint/no-explicit-any": "error",
      "@typescript-eslint/no-unused-vars": ["error", { argsIgnorePattern: "^_" }],
    },
  },
  {
    // Test and config files run in Node and may use dev-only globals.
    files: ["**/*.test.{ts,tsx}", "*.config.{ts,js}", "e2e/**"],
    languageOptions: { globals: { ...globals.node } },
  },
);
