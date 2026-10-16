"use client";

import {
  CircleCheckIcon,
  InfoIcon,
  Loader2Icon,
  OctagonXIcon,
  TriangleAlertIcon,
} from "lucide-react";
import { useTheme } from "next-themes";
import { Toaster as Sonner, type ToasterProps } from "sonner";

/** Toasts float as silicon planes; the icon carries the status colour, the words stay ink. */
const Toaster = ({ ...props }: ToasterProps) => {
  const { theme = "system" } = useTheme();

  return (
    <Sonner
      theme={theme as ToasterProps["theme"]}
      className="toaster group"
      icons={{
        success: <CircleCheckIcon className="size-[18px] text-pass" strokeWidth={1.9} />,
        info: <InfoIcon className="size-[18px] text-signal" strokeWidth={1.9} />,
        warning: <TriangleAlertIcon className="size-[18px] text-concern" strokeWidth={1.9} />,
        error: <OctagonXIcon className="size-[18px] text-fail" strokeWidth={1.9} />,
        loading: <Loader2Icon className="size-[18px] animate-spin text-ink-2" strokeWidth={1.9} />,
      }}
      toastOptions={{
        classNames: {
          toast:
            "gap-3! rounded-[14px]! px-4! py-3.5! font-sans! shadow-overlay! ring-1! ring-hairline!",
          title: "text-[14px]! leading-5! font-[600]! text-ink!",
          description: "text-[13px]! leading-5! text-ink-2!",
          actionButton: "rounded-full! bg-ink! px-3! text-[13px]! font-[560]! text-canvas!",
          cancelButton: "rounded-full! bg-surface-2! px-3! text-[13px]! font-[560]! text-ink!",
        },
      }}
      style={
        {
          "--normal-bg": "var(--surface)",
          "--normal-text": "var(--ink)",
          "--normal-border": "transparent",
          "--border-radius": "14px",
        } as React.CSSProperties
      }
      {...props}
    />
  );
};

export { Toaster };
