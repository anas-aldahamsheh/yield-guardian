import { PageFrame, PageHeader } from "@/components/page";
import { ViewTabs } from "@/components/view-tabs";
import { WorkOrdersTab } from "@/components/work-orders/work-orders-view";

import { InvestigationsIndex } from "./investigations-list";

export type InvestigationsTab = "investigations" | "work-orders";

const TABS: { id: InvestigationsTab; label: string; href: string }[] = [
  { id: "investigations", label: "Investigations", href: "/investigations" },
  { id: "work-orders", label: "Work orders", href: "/investigations?tab=work-orders" },
];

/**
 * Investigations, with its two views as address-backed tabs: the investigations grouped by
 * where they stand, and every work order with the audit log (`?tab=work-orders`).
 */
export function InvestigationsPage({
  tab,
  order,
}: {
  tab: InvestigationsTab;
  order: string | null;
}) {
  return (
    <PageFrame>
      <PageHeader
        title="Investigations"
        description="Each one gathers evidence with data tools, writes a report whose numbers are checked, and waits for an engineer's decision. Approving opens a work order."
        className="mb-8 sm:mb-10"
      />
      <ViewTabs
        label="Investigations views"
        items={TABS}
        current={tab}
        className="mb-10 sm:mb-12"
      />
      {tab === "work-orders" ? <WorkOrdersTab order={order} /> : <InvestigationsIndex />}
    </PageFrame>
  );
}
