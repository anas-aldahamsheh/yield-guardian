import type { Metadata } from "next";

import { WorkOrdersView } from "@/components/work-orders/work-orders-view";

export const metadata: Metadata = {
  title: "Work orders",
  description: "Approved actions from investigation reports, their outcomes, and the audit log.",
};

export default function WorkOrdersPage() {
  return <WorkOrdersView />;
}
