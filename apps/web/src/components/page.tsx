import type { ComponentProps, ReactNode } from "react";

import { cn } from "@/lib/utils";

/** Page frame: the console's width and gutters. The page's entrance is app/template.tsx's. */
export function PageFrame({ className, ...props }: ComponentProps<"div">) {
  return (
    <div
      className={cn("mx-auto w-full max-w-[1600px] px-gutter pt-10 pb-24 sm:pt-14", className)}
      {...props}
    />
  );
}

/** Title row of a console page: what this page is for, and its actions. */
export function PageHeader({
  title,
  description,
  actions,
  meta,
  className,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  meta?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "mb-10 flex flex-wrap items-end justify-between gap-x-10 gap-y-5 sm:mb-12",
        className,
      )}
    >
      <div className="max-w-[min(100%,980px)] min-w-0">
        <h1 className="text-page font-[660] text-ink">{title}</h1>
        {description ? (
          <p className="mt-4 max-w-[64ch] text-[17px] leading-7 text-ink-2 sm:text-lede">
            {description}
          </p>
        ) : null}
        {meta ? <div className="mt-4 text-[14px] leading-5 text-ink-2">{meta}</div> : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  );
}

/**
 * A panel: a flat plane of silicon with a hairline edge (a lit top edge in dark). `live` runs the
 * film's light along its top edge: use it only for a panel whose content is updating right now.
 */
export function Panel({
  title,
  description,
  actions,
  children,
  className,
  bodyClassName,
  live = false,
  as: Tag = "section",
  ...props
}: {
  title?: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  children?: ReactNode;
  className?: string;
  bodyClassName?: string;
  live?: boolean;
  as?: "section" | "div" | "article" | "aside";
} & Omit<ComponentProps<"section">, "title" | "ref">) {
  return (
    <Tag className={cn("panel relative min-w-0", className)} {...props}>
      {live ? <span aria-hidden className="live-edge" /> : null}
      {title || actions ? (
        <header className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2 px-5 pt-5 pb-3 sm:px-6">
          <div className="min-w-0">
            {title ? (
              <h2 className="text-[17px] leading-6 font-[630] tracking-[-0.012em] text-ink">
                {title}
              </h2>
            ) : null}
            {description ? (
              <p className="mt-0.5 text-[13.5px] leading-5 text-ink-2">{description}</p>
            ) : null}
          </div>
          {actions ? (
            <div className="flex max-w-full min-w-0 flex-wrap items-center gap-2">{actions}</div>
          ) : null}
        </header>
      ) : null}
      <div
        className={cn("px-5 pb-5 sm:px-6 sm:pb-6", !(title || actions) && "pt-5", bodyClassName)}
      >
        {children}
      </div>
    </Tag>
  );
}

/** A labelled reading: label above, value below in tabular figures. */
export function Reading({
  label,
  value,
  detail,
  className,
}: {
  label: ReactNode;
  value: ReactNode;
  detail?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("min-w-0", className)}>
      <dt className="text-[12.5px] leading-[18px] text-ink-3">{label}</dt>
      <dd className="tnum mt-0.5 text-[15px] leading-6 font-[520] text-ink">
        {value}
        {detail ? <span className="ml-1.5 text-[13px] font-[420] text-ink-3">{detail}</span> : null}
      </dd>
    </div>
  );
}
