export interface NavItem {
  href: string;
  label: string;
  /** What the page is for, shown in the mobile menu. */
  hint: string;
}

export const NAV_ITEMS: readonly NavItem[] = [
  { href: "/line", label: "Line", hint: "Live replay, risk and control charts" },
  {
    href: "/investigations",
    label: "Investigations",
    hint: "Reports with evidence, awaiting decisions",
  },
  { href: "/wafers", label: "Wafer lab", hint: "Die maps, patterns and similar wafers" },
  { href: "/lots", label: "Lots", hint: "Pattern excursions per lot" },
  { href: "/sensors", label: "Sensor health", hint: "Missing, stuck and drifting sensors" },
  { href: "/work-orders", label: "Work orders", hint: "Approved actions and the audit log" },
  { href: "/models", label: "Models", hint: "Model roles, evaluations and usage" },
  { href: "/methods", label: "Methods", hint: "Data, metrics with intervals, limitations" },
  { href: "/guide", label: "الدليل", hint: "دليل الاستخدام الكامل بالعربي" },
];

export function isActive(pathname: string, href: string): boolean {
  return pathname === href || pathname.startsWith(`${href}/`);
}
