import Link from "next/link";

import { PageFrame, PageHeader } from "@/components/page";
import { WorkOrdersTab } from "@/components/work-orders/work-orders-view";
import { cn } from "@/lib/utils";

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
      />
      <nav aria-label="Investigations views" className="mb-6 border-b border-hairline">
        <ul className="-mb-px flex gap-1">
          {TABS.map((t) => {
            const active = t.id === tab;
            return (
              <li key={t.id}>
                <Link
                  href={t.href}
                  scroll={false}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "inline-flex min-h-10 items-center border-b-2 px-3 text-[14px] no-underline transition-colors duration-[var(--dur-micro)]",
                    active
                      ? "border-safelight font-medium text-ink"
                      : "border-transparent text-ink-2 hover:text-ink",
                  )}
                >
                  {t.label}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
      {tab === "work-orders" ? <WorkOrdersTab order={order} /> : <InvestigationsIndex />}
    </PageFrame>
  );
}
