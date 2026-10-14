import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

/**
 * Production code must never see development data. Mock handlers, development fixtures and
 * MSW itself live under src/mocks and may be imported only by tests, the mock API server and
 * dev-only pages (`*.dev.tsx`).
 */
const mockImportBan = {
  patterns: [
    {
      group: ["@/mocks", "@/mocks/*", "**/mocks", "**/mocks/*", "msw", "msw/*"],
      message:
        "Development data and MSW stay out of production code. Import them only from tests, src/mocks or *.dev.tsx pages.",
    },
    {
      group: ["@yield-guardian/contracts/fixtures/*"],
      message: "Contract fixtures are synthetic. Import them only from tests or src/mocks.",
    },
  ],
};

const config = [
  ...nextVitals,
  ...nextTs,
  {
    ignores: [
      ".next/**",
      "node_modules/**",
      "playwright-report/**",
      "test-results/**",
      "public/mockServiceWorker.js",
      "next-env.d.ts",
    ],
  },
  {
    files: ["**/*.{ts,tsx,mts,mjs}"],
    rules: {
      "no-restricted-imports": ["error", mockImportBan],
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
    },
  },
];

export default config;
