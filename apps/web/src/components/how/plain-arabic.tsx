"use client";

import { useQuery } from "@tanstack/react-query";
import type {
  Estimate,
  MeasuredResults,
  OperatingPoints,
  SecomMetrics,
} from "@yield-guardian/contracts";
import type { ReactNode } from "react";

import { useApi } from "@/lib/api/context";
import { q } from "@/lib/api/queries";
import { formatInt, formatNumber, formatPercent } from "@/lib/format";
import { STATIONS, type StationName } from "@/lib/routes";
import { cn } from "@/lib/utils";

/*
 * The plain-language part of How it works, in Arabic (PLAN_V2 §4.3): what the product does,
 * where the data comes from and what it cannot do (§12). The numbers in the limits are read
 * from the API, which reads the bundles; none is written into this file.
 */

const STATION_TEXT: Record<StationName, { name: string; does: string }> = {
  manufacturing: {
    name: "Manufacturing",
    does: "يقرأ مدخلك ويتحقق منه: العدد، والقراءات المفقودة، والترتيب الزمني.",
  },
  monitoring: {
    name: "Monitoring",
    does: "يراقب حساسات كل وحدة: درجة الخطر، ومخططات التحكم، والانحراف، وصحة الحساسات.",
  },
  wafer_test: {
    name: "Wafer test",
    does: "يصنّف نمط العيب على كل رقاقة، ويجد أشبه الرقاقات الحقيقية بها، ويختبر الدفعة.",
  },
  investigation: {
    name: "Investigation",
    does: "عند إنذار، وإذا طلبت، يجمع المحقق الأدلة ويكتب تقريراً.",
  },
  decision: {
    name: "Decision",
    does: "المهندس يوافق فيُفتح أمر عمل، أو يرفض. لا شيء يحدث دون موافقته.",
  },
};

/** Stations that run only when someone asks: their mark and rule are dashed. */
const ON_DEMAND = new Set<StationName>(["investigation", "decision"]);

const BLOCK_NAME: Record<OperatingPoints["block"], string> = {
  train: "التدريب",
  validation: "التحقق",
  test: "الاختبار",
};

/** An LTR number inside the Arabic text, isolated so its digits, signs and % keep their order. */
function Num({ children }: { children: ReactNode }) {
  return (
    <bdi dir="ltr" className="tnum font-semibold text-ink">
      {children}
    </bdi>
  );
}

/** A value read from the API, with a plain stand-in while it loads or when it is not measured. */
function Value({ loading, value }: { loading: boolean; value: ReactNode | null }) {
  if (value != null) return <>{value}</>;
  if (loading)
    return (
      <span
        className="inline-block h-[1em] w-10 animate-pulse rounded-sm bg-die-2 align-middle"
        aria-label="جارٍ التحميل"
      />
    );
  return <span className="text-ink-3">(لم يُقَس بعد)</span>;
}

/** "0.52 (فترة ثقة 95%: 0.45 إلى 0.60)" */
function EstimateAr({ estimate, digits = 2 }: { estimate: Estimate; digits?: number }) {
  const level = Math.round((estimate.ci_level ?? 0.95) * 100);
  return (
    <>
      <Num>{formatNumber(estimate.value, digits)}</Num>
      {estimate.ci_low != null && estimate.ci_high != null ? (
        <span className="text-ink-2">
          {" "}
          (فترة ثقة <Num>{`${level}%`}</Num>: <Num>{formatNumber(estimate.ci_low, digits)}</Num> إلى{" "}
          <Num>{formatNumber(estimate.ci_high, digits)}</Num>)
        </span>
      ) : null}
    </>
  );
}

const mainRocAuc = (m: SecomMetrics | undefined) =>
  m?.models.find((x) => x.main)?.metrics.find((x) => x.metric === "roc_auc")?.estimate ?? null;
const resultEstimate = (r: MeasuredResults | undefined, id: string) =>
  r?.results.find((x) => x.id === id)?.estimate ?? null;

export function PlainArabic() {
  const api = useApi();
  const metrics = useQuery(q.secomMetrics(api));
  const points = useQuery(q.operatingPoints(api));
  const results = useQuery(q.results(api));

  const roc = mainRocAuc(metrics.data);
  const point = points.data?.points.find((p) => p.id === points.data.default) ?? null;
  const lotF1 = resultEstimate(results.data, "wafer_macro_f1_lot_grouped");
  const officialF1 = resultEstimate(results.data, "wafer_macro_f1_official");

  return (
    <div lang="ar" dir="rtl" className="mx-auto max-w-[920px]">
      <header className="pb-10">
        <h1
          id="how-title"
          className="text-[30px] leading-[44px] font-semibold text-ink sm:text-[38px] sm:leading-[56px]"
        >
          كيف يعمل Yield Guardian
        </h1>
        <p className="mt-3 max-w-[64ch] text-[18px] leading-9 text-ink-2">
          برنامج لمهندسي الجودة والمردود في مصانع رقائق السيليكون: يساعدهم على اكتشاف المشكلة مبكراً
          وتضييق مكان البحث عنها. هذا القسم بكلام بسيط، وتحته قسم للخبراء بالإنجليزية، ثم دليل
          الاستخدام.
        </p>
      </header>

      <section
        id="what"
        aria-labelledby="what-title"
        className="border-t border-hairline-strong pt-8 pb-12"
      >
        <h2 id="what-title" className="text-[24px] leading-10 font-semibold text-ink">
          ماذا يفعل
        </h2>
        <div className="mt-3 grid max-w-[66ch] gap-4 text-[17px] leading-8 text-ink">
          <p>
            تعطيه بيانات: عينة حقيقية، أو حالة تختارها، أو عيباً ترسمه على رقاقة، أو ملفاً من مصنعك.
            فيمررها على خط إنتاج من خمس محطات، ويحسب كل نتيجة لحظة وصولها. لا شيء مسجّل يُعاد
            تشغيله، ولا يتحرك شيء قبل أن تعطيه مدخلاً.
          </p>
          <p>
            عندما يرفع إنذاراً تستطيع أن تطلب تحقيقاً: يجمع المحقق الأدلة بأدوات تحسب كل رقم، ويكتب
            تقريراً يربط كل رقم بدليله، ثم يقرر المهندس. النماذج اللغوية تكتب وتشرح فقط، ولا تُنتج
            أي رقم.
          </p>
        </div>
        {/* The line itself: five stations on one amber rule, in the order a unit or wafer meets them. */}
        <ol
          className="mt-8 grid grid-cols-[minmax(0,1fr)] md:grid-cols-5"
          aria-label="المحطات الخمس بالترتيب"
        >
          {STATIONS.map((s, i) => (
            <li
              key={s}
              className={cn(
                "relative grid content-start gap-1 ps-11 pb-7 last:pb-0 md:ps-0 md:pe-5 md:pt-12 md:pb-0",
                // The rule to the next station: down the start edge on a phone, along the top from md.
                "before:absolute before:start-[13px] before:top-8 before:bottom-0 before:w-px before:bg-safelight last:before:hidden",
                "md:before:start-9 md:before:end-0 md:before:top-[13px] md:before:bottom-auto md:before:h-px md:before:w-auto",
                // The way into an on-demand station is dashed.
                STATIONS[i + 1] &&
                  ON_DEMAND.has(STATIONS[i + 1]!) &&
                  "before:border-s before:border-dashed before:border-safelight before:bg-transparent md:before:border-s-0 md:before:border-t",
              )}
            >
              <span
                aria-hidden="true"
                className={cn(
                  "tnum absolute start-0 top-0.5 grid size-7 place-items-center rounded-full border-2 border-safelight bg-room text-[14px] leading-none font-semibold text-ink md:top-0",
                  ON_DEMAND.has(s) && "border-dashed",
                )}
              >
                {i + 1}
              </span>
              <span
                dir="ltr"
                className="justify-self-start text-[16px] leading-7 font-semibold text-ink"
              >
                {STATION_TEXT[s].name}
              </span>
              <span className="text-[15px] leading-7 text-ink-2">{STATION_TEXT[s].does}</span>
            </li>
          ))}
        </ol>
      </section>

      <section
        id="sources"
        aria-labelledby="sources-title"
        className="border-t border-hairline-strong pt-8 pb-12"
      >
        <h2 id="sources-title" className="text-[24px] leading-10 font-semibold text-ink">
          من أين تأتي البيانات
        </h2>
        <dl className="mt-4 grid max-w-[70ch] gap-5 text-[17px] leading-8">
          <div>
            <dt className="font-semibold text-ink">
              <bdi>SECOM</bdi>: الحساسات
            </dt>
            <dd className="text-ink-2">
              وحدات إنتاج حقيقية من مصنع أشباه موصلات. لكل وحدة قراءات حساسات بلا أسماء، ونتيجة
              الفحص النهائي (نجاح أو فشل)، ووقت إنتاجها.
            </dd>
          </div>
          <div>
            <dt className="font-semibold text-ink">
              <bdi>WM-811K</bdi>: خرائط الرقاقات
            </dt>
            <dd className="text-ink-2">
              خرائط رقاقات حقيقية من مصانع حقيقية: كل شريحة على الرقاقة سليمة أو معطلة، وجزء من
              الخرائط صنّفه مهندسون بنمط عيب، مثل الحلقة على الحافة أو الخدش.
            </dd>
          </div>
          <div>
            <dt className="font-semibold text-ink">بياناتك أنت</dt>
            <dd className="text-ink-2">
              ملف من مصنعك (Excel أو CSV) أو رسمة ترسمها، يعالجها نفس الكود الذي يعالج العينات.
              تُحفظ التشغيلات مؤقتاً ثم تُحذف، إلا ما يعتمد عليه تحقيق.
            </dd>
          </div>
        </dl>
        <p className="mt-6 max-w-[70ch] text-[17px] leading-8 text-ink">
          المصدران منشوران للعموم، ومصدر كل منهما وترخيصه وبصمات ملفاته في قسم الخبراء. لا توجد
          بيانات مصنوعة: كل رقم إما محسوب الآن من مدخلك، أو مقاس على بيانات حقيقية لم يرها الموديل
          أثناء تدريبه.
        </p>
      </section>

      <section
        id="limits"
        aria-labelledby="limits-title"
        className="border-t border-hairline-strong pt-8 pb-12"
      >
        <h2 id="limits-title" className="text-[24px] leading-10 font-semibold text-ink">
          ما الذي لا يستطيعه
        </h2>
        <ul className="mt-4 grid max-w-[70ch] gap-4 text-[17px] leading-8 text-ink" data-limits>
          <li className="limit">
            التنبؤ بفشل الوحدة من الحساسات ضعيف على SECOM: ‏<bdi dir="ltr">ROC-AUC</bdi> على بيانات
            الاختبار{" "}
            <Value loading={metrics.isPending} value={roc ? <EstimateAr estimate={roc} /> : null} />
            {"، "}
            {point ? (
              <>
                وعند نقطة التشغيل التي نسبة إنذاراتها الكاذبة{" "}
                <Num>{formatPercent(point.target_fpr ?? point.fpr.value, 0)}</Num> اكتشف{" "}
                <Num>{formatInt(point.tp)}</Num> من <Num>{formatInt(point.tp + point.fn)}</Num> حالة
                فشل في بيانات {BLOCK_NAME[points.data!.block]}.
              </>
            ) : (
              <>
                وعدد حالات الفشل التي يكتشفها عند نقطة التشغيل الافتراضية{" "}
                <Value loading={points.isPending} value={null} />.
              </>
            )}{" "}
            لذلك يتكلم البرنامج عن إنذار مبكر وتضييق مكان البحث، ومصنف الرقاقات هو الذي يحمل ادعاء
            الدقة: <bdi dir="ltr">macro-F1</bdi>{" "}
            <Value
              loading={results.isPending}
              value={lotF1 ? <EstimateAr estimate={lotF1} /> : null}
            />{" "}
            على تقسيم يفصل الدفعات، وتنخفض إلى حوالي{" "}
            <Value
              loading={results.isPending}
              value={officialF1 ? <Num>{formatNumber(officialF1.value, 2)}</Num> : null}
            />{" "}
            على التقسيم الرسمي لـ <bdi>WM-811K</bdi>.
          </li>
          <li className="limit">حساسات SECOM بلا أسماء، فالنتائج تسمّي مجموعات حساسات، لا آلات.</li>
          <li className="limit">
            مجموعتا البيانات مصدران حقيقيان منفصلان، ولا تُعرضان أبداً كأنهما شريحة واحدة.
          </li>
          <li className="limit">الأسباب فرضيات من الأبحاث حتى يؤكدها مهندس.</li>
          <li className="limit">
            المحقق يعتمد على سرعة خادم AMD، فيعمل عند الطلب فقط ويعرض تقدمه خطوة بخطوة.
          </li>
          <li className="limit">
            ملف الحساسات المرفوع يجب أن يكون بتخطيط SECOM (<Num>590</Num> حساساً). حساسات مصنع آخر
            تحتاج إعادة تدريب الموديلات.
          </li>
        </ul>
      </section>
    </div>
  );
}
