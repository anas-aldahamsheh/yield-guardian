import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

/**
 * Production code must never see development data. Mock handlers, the contract fixtures and MSW
 * itself may be imported only by tests, the mock API server (scripts/) and dev-only pages
 * (`*.dev.tsx`, which `next build` does not compile, see next.config.ts). CI also scans the build
 * output for fixture content.
 */
const DEV_DATA_MESSAGE =
  "Development data stays out of production code. Import mocks, MSW and contract fixtures only from tests, src/mocks, scripts/ or *.dev.tsx pages.";

const devDataImportBan = {
  patterns: [
    {
      group: ["@/mocks", "@/mocks/*", "**/mocks", "**/mocks/*", "msw", "msw/*"],
      message: DEV_DATA_MESSAGE,
    },
    {
      group: [
        "@yield-guardian/contracts/fixtures",
        "@yield-guardian/contracts/fixtures/*",
        "**/contracts/fixtures",
        "**/contracts/fixtures/*",
        "**/fixtures/*.json",
      ],
      message: DEV_DATA_MESSAGE,
    },
  ],
};

/** The same ban for `import()` and `require()`, which no-restricted-imports does not see. */
const DEV_DATA_SOURCE = "/(^|\\/)(mocks|fixtures)(\\/|$)|^msw(\\/|$)/";
const devDataDynamicImportBan = [
  {
    selector: `ImportExpression[source.value=${DEV_DATA_SOURCE}]`,
    message: DEV_DATA_MESSAGE,
  },
  {
    selector: "ImportExpression[source.type!='Literal']",
    message: "Use a string literal in import() so the development-data rule can check it.",
  },
  {
    selector: `CallExpression[callee.name='require'][arguments.0.value=${DEV_DATA_SOURCE}]`,
    message: DEV_DATA_MESSAGE,
  },
];

const config = [
  ...nextVitals,
  ...nextTs,
  {
    ignores: [
      ".next/**",
      "node_modules/**",
      "playwright-report/**",
      "test-results/**",
      "docs/**",
      "next-env.d.ts",
    ],
  },
  {
    files: ["**/*.{ts,tsx,mts,mjs}"],
    rules: {
      "no-restricted-imports": ["error", devDataImportBan],
      "no-restricted-syntax": ["error", ...devDataDynamicImportBan],
      "@typescript-eslint/no-unused-vars": [
        "error",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_", caughtErrorsIgnorePattern: "^_" },
      ],
      "@typescript-eslint/consistent-type-imports": ["error", { fixStyle: "inline-type-imports" }],
      "react/jsx-no-target-blank": "error",
      eqeqeq: ["error", "smart"],
    },
  },
  {
    files: [
      "src/mocks/**",
      "**/*.dev.tsx",
      "**/*.test.{ts,tsx}",
      "e2e/**",
      "vitest.setup.ts",
      "scripts/**",
    ],
    rules: {
      "no-restricted-imports": "off",
      "no-restricted-syntax": "off",
    },
  },
];

export default config;
