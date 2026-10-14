"use client";

import { useQuery } from "@tanstack/react-query";

import { useApi } from "./context";
import { q } from "./queries";

/** Copy for a server that runs without a language model key: the data screens work, the language model features do not. */
export const NOT_CONFIGURED = {
  chat: {
    title: "Chat is not configured on this server",
    detail: "It needs a language model key on the API (TOKEN_FACTORY_API_KEY). The data screens work without it.",
  },
  investigations: {
    title: "Live investigations are not configured on this server",
    detail:
      "Starting one needs a language model key on the API (TOKEN_FACTORY_API_KEY). Recorded investigations still open, and the data screens work without it.",
  },
} as const;

/**
 * Which language model features the API serves, from /meta. `undefined` while it loads or
 * when /meta fails, so nothing is hidden on a guess.
 */
export function useFeatures(): { chat: boolean | undefined; liveInvestigations: boolean | undefined } {
  const api = useApi();
  const meta = useQuery(q.meta(api));
  return { chat: meta.data?.features.chat, liveInvestigations: meta.data?.features.live_investigations };
}
