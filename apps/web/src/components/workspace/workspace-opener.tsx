"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";

import { openWorkspace, setSession } from "@/lib/api/workspace";

/**
 * Opens this device's workspace on every page: on a first visit the API makes a visitor
 * session and its workspace (no sign-up), and every visit renews the cookie. The answer is the
 * session, put in the session query's cache (the page's first read of it is this answer:
 * lib/api/opening.ts). Renders nothing.
 */
export function WorkspaceOpener() {
  const client = useQueryClient();
  useEffect(() => {
    let mounted = true;
    void openWorkspace().then((session) => {
      if (mounted && session) void setSession(client, session);
    });
    return () => {
      mounted = false;
    };
  }, [client]);
  return null;
}
