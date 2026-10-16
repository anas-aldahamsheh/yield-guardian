import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";
import { Slot } from "radix-ui";

/**
 * Buttons are pills. The primary one is solid ink with a sweep of the film's light on hover; all
 * of them lift a pixel on hover and go down with a firm spring under a press (`.press`, `.lift`).
 */
const buttonVariants = cva(
  "press lift inline-flex shrink-0 items-center justify-center gap-2 rounded-full text-[14px] leading-5 font-[560] whitespace-nowrap select-none disabled:pointer-events-none disabled:opacity-45 aria-invalid:shadow-[inset_0_0_0_1px_var(--fail)] [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  {
    variants: {
      variant: {
        default:
          "sheen-hover bg-ink text-canvas shadow-[0_1px_2px_rgb(0_0_0/0.12),inset_0_1px_0_rgb(255_255_255/0.12)] hover:bg-ink/92",
        destructive:
          "bg-fail text-canvas shadow-[0_1px_2px_rgb(0_0_0/0.12)] hover:bg-fail/90 focus-visible:outline-fail",
        outline:
          "bg-transparent text-ink shadow-[inset_0_0_0_1px_var(--hairline-strong)] hover:bg-surface-2 hover:shadow-[inset_0_0_0_1px_var(--edge)]",
        secondary: "bg-surface-2 text-ink hover:bg-surface-3",
        ghost: "text-ink-2 hover:bg-surface-2 hover:text-ink",
        link: "rounded-sm px-0 text-ink underline decoration-hairline-strong underline-offset-4 hover:decoration-signal [&.lift]:hover:translate-y-0",
      },
      size: {
        default: "h-10 px-5 has-[>svg]:px-4",
        xs: "h-6 gap-1 px-2.5 text-[12px] has-[>svg]:px-2 [&_svg:not([class*='size-'])]:size-3",
        sm: "h-8 gap-1.5 px-3.5 text-[13px] has-[>svg]:px-3",
        lg: "h-12 px-6 text-[15px] has-[>svg]:px-5",
        icon: "size-10",
        "icon-xs": "size-6 [&_svg:not([class*='size-'])]:size-3",
        "icon-sm": "size-8",
        "icon-lg": "size-12",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  },
);

function Button({
  className,
  variant = "default",
  size = "default",
  asChild = false,
  ...props
}: React.ComponentProps<"button"> &
  VariantProps<typeof buttonVariants> & {
    asChild?: boolean;
  }) {
  const Comp = asChild ? Slot.Root : "button";

  return (
    <Comp
      data-slot="button"
      data-variant={variant}
      data-size={size}
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  );
}

export { Button, buttonVariants };
