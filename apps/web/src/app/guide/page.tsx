import type { Metadata } from "next";

import { GuideView } from "@/components/guide/guide-view";

export const metadata: Metadata = {
  title: "دليل الاستخدام",
  description:
    "دليل Yield Guardian الكامل بالعربي: ماذا يفعل، وكيف تستخدمه، والموديلات والبيانات، والمشاكل وحلولها، وكيف تتحقق من النجاح.",
};

export default function GuidePage() {
  return <GuideView />;
}
