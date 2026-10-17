import type { Metadata } from "next";

import { HistoryPage } from "@/components/workspace/history-page";

export const metadata: Metadata = {
  title: "History & Workspace – Yield Guardian",
  description: "View past fab production runs, compare results, and manage investigations.",
};

export default function HistoryRoute() {
  return <HistoryPage />;
}
