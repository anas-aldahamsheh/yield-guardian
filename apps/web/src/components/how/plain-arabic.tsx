"use client";

import { useQuery } from "@tanstack/react-query";
import type {
  Estimate,
  MeasuredResults,
  OperatingPoints,
  SecomMetrics,
} from "@yield-guardian/contracts";
import type { CSSProperties, ReactNode } from "react";

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
    <bdi dir="ltr" className="tnum font-[620] text-ink">
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
        className="inline-block h-[1em] w-10 animate-pulse rounded-[6px] bg-surface-2 align-middle"
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
    <div lang="ar" dir="rtl" className="mx-auto max-w-[1040px]">
      <header className="pb-14 sm:pb-20">
        <h1
          id="how-title"
          className="hero-line text-[40px] leading-[1.3] font-[640] text-ink sm:text-[60px] sm:leading-[1.25]"
        >
          <span>كيف يعمل Yield Guardian</span>
        </h1>
        <p
          className="rise-in mt-6 max-w-[58ch] text-[18px] leading-9 text-ink-2 sm:text-[20px] sm:leading-10"
          style={{ "--d": "200ms" } as CSSProperties}
        >
          برنامج لمهندسي الجودة والمردود في مصانع رقائق السيليكون: يساعدهم على اكتشاف المشكلة مبكراً
          وتضييق مكان البحث عنها. هذا القسم بكلام بسيط، وتحته قسم للخبراء بالإنجليزية، ثم دليل
          الاستخدام.
        </p>
      </header>

      <section
        id="what"
        aria-labelledby="what-title"
        className="border-t border-hairline pt-12 pb-16 sm:pt-16 sm:pb-20"
      >
        <h2
          id="what-title"
          className="text-[28px] leading-[1.45] font-[640] text-ink sm:text-[34px]"
        >
          ماذا يفعل
        </h2>
        <div className="mt-5 grid max-w-[64ch] gap-5 text-[17px] leading-[2] text-ink">
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
        {/* The line itself: five stations on one track, in the order a unit or wafer meets them.
            The film's light runs along the track as the reader scrolls past it (globals.css,
            .how-line); the way into an on-demand station stays dashed and unlit. */}
        <ol
          className="how-line mt-12 grid grid-cols-[minmax(0,1fr)] rounded-[28px] bg-surface p-6 shadow-[inset_0_0_0_1px_var(--hairline),var(--highlight)] sm:p-8 md:grid-cols-5"
          aria-label="المحطات الخمس بالترتيب"
        >
          {STATIONS.map((s, i) => {
            const next = STATIONS[i + 1];
            const dashed = next != null && ON_DEMAND.has(next);
            const lit = !ON_DEMAND.has(s);
            const style = {
              "--i": i,
              "--seg-a": `var(--film-${i + 1})`,
              "--seg-b": `var(--film-${i + 2})`,
            } as CSSProperties;
            return (
              <li
                key={s}
                style={style}
                className="relative grid content-start gap-1.5 ps-12 pb-9 last:pb-0 md:ps-0 md:pe-6 md:pt-14 md:pb-0"
              >
                {next ? (
                  <>
                    {/* The track to the next station: down the start edge on a phone, along the top from md. */}
                    <span
                      aria-hidden="true"
                      className={cn(
                        "absolute start-[15px] top-10 bottom-1 w-0 border-s-2 border-hairline-strong md:hidden",
                        dashed && "border-dashed",
                      )}
                    />
                    <span
                      aria-hidden="true"
                      className={cn(
                        "absolute start-11 end-1 top-[15px] hidden h-0 border-t-2 border-hairline-strong md:block",
                        dashed && "border-dashed",
                      )}
                    />
                    {!dashed ? (
                      <>
                        <span
                          aria-hidden="true"
                          className="how-fill-y absolute start-[15px] top-10 bottom-1 w-[2px] rounded-full bg-[linear-gradient(180deg,var(--seg-a),var(--seg-b))] md:hidden"
                        />
                        <span
                          aria-hidden="true"
                          className="how-fill-x absolute start-11 end-1 top-[15px] hidden h-[2px] rounded-full bg-[linear-gradient(270deg,var(--seg-a),var(--seg-b))] md:block"
                        />
                      </>
                    ) : null}
                  </>
                ) : null}
                <span
                  aria-hidden="true"
                  className={cn(
                    "tnum absolute start-0 top-0 grid size-8 place-items-center rounded-full bg-surface text-[14px] leading-none font-[620] text-ink shadow-[inset_0_0_0_2px_var(--hairline-strong)]",
                    !lit && "border-2 border-dashed border-hairline-strong shadow-none",
                  )}
                >
                  {lit ? (
                    <span className="how-node absolute inset-0 rounded-full shadow-[inset_0_0_0_2px_var(--seg-a),0_0_0_4px_color-mix(in_oklab,var(--seg-a)_20%,transparent)]" />
                  ) : null}
                  <span className="relative">{i + 1}</span>
                </span>
                <span
                  dir="ltr"
                  className="justify-self-start text-[17px] leading-7 font-[630] text-ink"
                >
                  {STATION_TEXT[s].name}
                </span>
                <span className="text-[15px] leading-7 text-ink-2">{STATION_TEXT[s].does}</span>
              </li>
            );
          })}
        </ol>
      </section>

      <section
        id="sources"
        aria-labelledby="sources-title"
        className="border-t border-hairline pt-12 pb-16 sm:pt-16 sm:pb-20"
      >
        <h2
          id="sources-title"
          className="text-[28px] leading-[1.45] font-[640] text-ink sm:text-[34px]"
        >
          من أين تأتي البيانات
        </h2>
        <dl className="mt-8 grid grid-cols-[minmax(0,1fr)] gap-3 text-[16px] leading-8 md:grid-cols-3">
          <div className="glow panel p-6">
            <SourceGlyph kind="sensors" />
            <dt className="mt-5 text-[18px] leading-8 font-[620] text-ink">
              <bdi>SECOM</bdi>: الحساسات
            </dt>
            <dd className="mt-1 text-ink-2">
              وحدات إنتاج حقيقية من مصنع أشباه موصلات. لكل وحدة قراءات حساسات بلا أسماء، ونتيجة
              الفحص النهائي (نجاح أو فشل)، ووقت إنتاجها.
            </dd>
          </div>
          <div className="glow panel p-6">
            <SourceGlyph kind="wafers" />
            <dt className="mt-5 text-[18px] leading-8 font-[620] text-ink">
              <bdi>WM-811K</bdi>: خرائط الرقاقات
            </dt>
            <dd className="mt-1 text-ink-2">
              خرائط رقاقات حقيقية من مصانع حقيقية: كل شريحة على الرقاقة سليمة أو معطلة، وجزء من
              الخرائط صنّفه مهندسون بنمط عيب، مثل الحلقة على الحافة أو الخدش.
            </dd>
          </div>
          <div className="glow panel p-6">
            <SourceGlyph kind="file" />
            <dt className="mt-5 text-[18px] leading-8 font-[620] text-ink">بياناتك أنت</dt>
            <dd className="mt-1 text-ink-2">
              ملف من مصنعك (Excel أو CSV) أو رسمة ترسمها، يعالجها نفس الكود الذي يعالج العينات.
              تُحفظ التشغيلات مؤقتاً ثم تُحذف، إلا ما يعتمد عليه تحقيق.
            </dd>
          </div>
        </dl>
        <p className="mt-8 max-w-[66ch] text-[17px] leading-[2] text-ink">
          المصدران منشوران للعموم، ومصدر كل منهما وترخيصه وبصمات ملفاته في قسم الخبراء. لا توجد
          بيانات مصنوعة: كل رقم إما محسوب الآن من مدخلك، أو مقاس على بيانات حقيقية لم يرها الموديل
          أثناء تدريبه.
        </p>
      </section>

      <section
        id="limits"
        aria-labelledby="limits-title"
        className="border-t border-hairline pt-12 pb-4 sm:pt-16"
      >
        <h2
          id="limits-title"
          className="text-[28px] leading-[1.45] font-[640] text-ink sm:text-[34px]"
        >
          ما الذي لا يستطيعه
        </h2>
        <ul className="mt-8 grid max-w-[72ch] gap-4 text-[17px] leading-[2] text-ink" data-limits>
          <li className="relative rounded-[20px] bg-surface px-6 py-5 shadow-[inset_0_0_0_1px_var(--hairline),var(--highlight)]">
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
          <Limit>حساسات SECOM بلا أسماء، فالنتائج تسمّي مجموعات حساسات، لا آلات.</Limit>
          <Limit>
            مجموعتا البيانات مصدران حقيقيان منفصلان، ولا تُعرضان أبداً كأنهما شريحة واحدة.
          </Limit>
          <Limit>الأسباب فرضيات من الأبحاث حتى يؤكدها مهندس.</Limit>
          <Limit>المحقق يعتمد على سرعة خادم AMD، فيعمل عند الطلب فقط ويعرض تقدمه خطوة بخطوة.</Limit>
          <Limit>
            ملف الحساسات المرفوع يجب أن يكون بتخطيط SECOM (<Num>590</Num> حساساً). حساسات مصنع آخر
            تحتاج إعادة تدريب الموديلات.
          </Limit>
        </ul>
      </section>
    </div>
  );
}

/** One of the product's limits: a line with a quiet mark at its start. */
function Limit({ children }: { children: ReactNode }) {
  return (
    <li className="relative ps-7">
      <span
        aria-hidden="true"
        className="absolute start-1 top-[15px] size-2 rounded-full shadow-[inset_0_0_0_1.5px_var(--ink-3)]"
      />
      {children}
    </li>
  );
}

/** A small drawing of each source: a bank of sensor lamps, a wafer of dies, a file. */
function SourceGlyph({ kind }: { kind: "sensors" | "wafers" | "file" }) {
  return (
    <svg
      viewBox="0 0 48 48"
      aria-hidden="true"
      className="size-12 rounded-[14px] bg-screen p-2 text-film-4 shadow-[inset_0_0_0_1px_rgb(255_255_255/0.06)]"
    >
      {kind === "sensors"
        ? Array.from({ length: 25 }, (_, k) => (
            <circle
              key={k}
              cx={8 + (k % 5) * 8}
              cy={8 + Math.floor(k / 5) * 8}
              r={1.9}
              fill="currentColor"
              opacity={0.7}
            />
          ))
        : null}
      {kind === "wafers" ? (
        <g>
          <circle cx={24} cy={24} r={19} fill="none" stroke="currentColor" strokeOpacity={0.6} />
          {Array.from({ length: 49 }, (_, k) => {
            const x = 9 + (k % 7) * 5;
            const y = 9 + Math.floor(k / 7) * 5;
            if ((x + 2 - 24) ** 2 + (y + 2 - 24) ** 2 > 15.5 ** 2) return null;
            return (
              <rect
                key={k}
                x={x}
                y={y}
                width={4}
                height={4}
                rx={0.8}
                fill="currentColor"
                opacity={0.55}
              />
            );
          })}
        </g>
      ) : null}
      {kind === "file" ? (
        <g fill="none" stroke="currentColor" strokeWidth={1.6} strokeLinejoin="round">
          <path d="M14 6h14l8 8v28H14z" strokeOpacity={0.8} />
          <path d="M28 6v8h8" strokeOpacity={0.8} />
          <path d="M19 24h12M19 30h12M19 36h8" strokeOpacity={0.5} />
        </g>
      ) : null}
    </svg>
  );
}
