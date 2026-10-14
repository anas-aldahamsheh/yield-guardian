/**
 * Development fixtures from packages/contracts/fixtures (one file per API operation). Only the
 * mock gateway (scripts/gateway.ts), tests and dev-only pages may import this module; ESLint
 * forbids it everywhere else and CI fails if fixture content reaches a production build.
 */
import { readFileSync } from "node:fs";
import path from "node:path";

const FIXTURES = path.join(import.meta.dirname, "../../../../packages/contracts/fixtures");

const cache = new Map<string, unknown>();

export function fixture<T = unknown>(name: string): T {
  if (!cache.has(name)) {
    cache.set(name, JSON.parse(readFileSync(path.join(FIXTURES, `${name}.json`), "utf8")));
  }
  return structuredClone(cache.get(name)) as T;
}
