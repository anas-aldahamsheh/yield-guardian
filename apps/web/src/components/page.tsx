import type { ComponentProps, ReactNode } from "react";

import { cn } from "@/lib/utils";

/** Page frame: the console's width and gutters. */
export function PageFrame({ className, ...props }: ComponentProps<"div">) {
  return <div className={cn("mx-auto w-full max-w-[1600px] px-gutter pt-6 pb-16", className)} {...props} />;
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
    <div className={cn("mb-6 flex flex-wrap items-end justify-between gap-x-8 gap-y-4", className)}>
      <div className="max-w-[72ch] min-w-0">
        <h1 className="text-h2 font-semibold tracking-[-0.01em] text-ink">{title}</h1>
        {description ? <p className="mt-1.5 text-[15px] leading-6 text-ink-2">{description}</p> : null}
        {meta ? <div className="mt-2 text-sm text-ink-3">{meta}</div> : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  );
}

/** A panel is a die: flat, square-cornered, on the room colour. */
export function Panel({
  title,
  description,
  actions,
  children,
  className,
  bodyClassName,
  as: Tag = "section",
  ...props
}: {
  title?: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  children?: ReactNode;
  className?: string;
  bodyClassName?: string;
  as?: "section" | "div" | "article" | "aside";
} & Omit<ComponentProps<"section">, "title" | "ref">) {
  return (
    <Tag className={cn("panel min-w-0", className)} {...props}>
      {title || actions ? (
        <header className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2 px-4 pt-3.5 pb-2 sm:px-5">
          <div className="min-w-0">
            {title ? <h2 className="text-[15px] leading-6 font-semibold text-ink">{title}</h2> : null}
            {description ? <p className="text-[13px] leading-5 text-ink-3">{description}</p> : null}
          </div>
          {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
        </header>
      ) : null}
      <div className={cn("px-4 pb-4 sm:px-5", !(title || actions) && "pt-4", bodyClassName)}>{children}</div>
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
      <dt className="text-[13px] leading-5 text-ink-3">{label}</dt>
      <dd className="tnum text-[15px] leading-6 text-ink">
        {value}
        {detail ? <span className="ml-1.5 text-[13px] text-ink-3">{detail}</span> : null}
      </dd>
    </div>
  );
}
