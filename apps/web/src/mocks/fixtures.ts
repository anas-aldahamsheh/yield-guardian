/**
 * Development fixtures from packages/contracts/fixtures (one file per API operation). Only the
 * mock gateway (scripts/gateway.ts), tests and dev-only pages may import this module; ESLint
 * forbids it everywhere else and CI fails if fixture content reaches a production build.
 */
import { readFileSync } from "node:fs";

const FIXTURES = new URL("../../../../packages/contracts/fixtures/", import.meta.url);

const cache = new Map<string, unknown>();

export function fixture<T = unknown>(name: string): T {
  if (!cache.has(name)) {
    cache.set(name, JSON.parse(readFileSync(new URL(`${name}.json`, FIXTURES), "utf8")));
  }
  return structuredClone(cache.get(name)) as T;
}
