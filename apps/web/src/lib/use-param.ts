"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";

/** One search parameter as state: reading it follows the URL, setting it replaces the URL without scrolling. */
export function useParam(name: string) {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const value = params.get(name);
  const set = (next: string | null) => {
    const p = new URLSearchParams(params.toString());
    if (next == null || next === "") p.delete(name);
    else p.set(name, next);
    router.replace(`${pathname}${p.size ? `?${p}` : ""}`, { scroll: false });
  };
  return [value, set] as const;
}
