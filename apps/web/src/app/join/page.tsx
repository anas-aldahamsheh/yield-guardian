import type { Metadata } from "next";

import { JoinWorkspace } from "@/components/workspace/join-workspace";

/**
 * Continue on this device with a handoff code. The join link carries the code after `#`, which
 * browsers never send, so it reaches neither this server nor any access log.
 */
export const metadata: Metadata = {
  title: "Continue on this device",
  description: "Attach this device to your workspace with the code your other device shows.",
  robots: { index: false, follow: false },
  referrer: "no-referrer",
};

export default function JoinPage() {
  return <JoinWorkspace />;
}
