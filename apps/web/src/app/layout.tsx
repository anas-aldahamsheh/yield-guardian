import type { Metadata, Viewport } from "next";
import localFont from "next/font/local";
import { headers } from "next/headers";
import type { ReactNode } from "react";

import { ChatLauncher } from "@/components/chat/chat-launcher";
import { Providers } from "@/components/providers";
import { SiteFooter } from "@/components/shell/site-footer";
import { TopBar } from "@/components/shell/top-bar";
import { metaState } from "@/lib/api/server";

import "./globals.css";

/*
 * Every face is bundled from @fontsource-variable and self-hosted by next/font/local, so the build
 * needs no network and the page loads no font from another origin (docs/DESIGN.md, "Type").
 */
/**
 * YG Sans, our cut of Mona Sans: display, headings, interface and data, with the width axis for
 * the display voice. It is on every first paint, so it holds only the widths, weights and
 * characters the app sets (scripts/cut-ui-font.py).
 */
const ygSans = localFont({
  src: "../fonts/yg-sans-latin.woff2",
  style: "normal",
  weight: "400 700",
  variable: "--font-yg-sans",
  display: "swap",
  adjustFontFallback: "Arial",
  declarations: [{ prop: "font-stretch", value: "100% 112.5%" }],
});

/** Newsreader: text a language model wrote. Reports and answers sit below the fold or later. */
const newsreader = localFont({
  src: [
    {
      path: "../../node_modules/@fontsource-variable/newsreader/files/newsreader-latin-wght-normal.woff2",
      style: "normal",
    },
    {
      path: "../../node_modules/@fontsource-variable/newsreader/files/newsreader-latin-wght-italic.woff2",
      style: "italic",
    },
  ],
  weight: "200 800",
  variable: "--font-newsreader",
  display: "swap",
  preload: false,
  adjustFontFallback: "Times New Roman",
});

/**
 * Readex Pro: the Arabic sections. Its unicode range is the Arabic block, so a page without
 * Arabic text never fetches it.
 */
const readex = localFont({
  src: "../../node_modules/@fontsource-variable/readex-pro/files/readex-pro-arabic-wght-normal.woff2",
  style: "normal",
  weight: "160 700",
  variable: "--font-readex",
  display: "swap",
  preload: false,
  adjustFontFallback: false,
  declarations: [
    {
      prop: "unicode-range",
      value:
        "U+0600-06FF, U+0750-077F, U+0870-088E, U+0890-0891, U+0897-08E1, U+08E3-08FF, U+200C-200E, U+2010-2011, U+204F, U+2E41, U+FB50-FDFF, U+FE70-FE74, U+FE76-FEFC",
    },
  ],
});

export const metadata: Metadata = {
  title: {
    default: "Yield Guardian",
    template: "%s – Yield Guardian",
  },
  description:
    "Failure risk, control charts and wafer-map patterns for a semiconductor line, with an investigator that cites its evidence.",
  applicationName: "Yield Guardian",
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f4f6f8" },
    { media: "(prefers-color-scheme: dark)", color: "#0c1220" },
  ],
  colorScheme: "light dark",
};

export default async function RootLayout({ children }: { children: ReactNode }) {
  // Every page renders per request (the CSP nonce is per request, and no API data is ever
  // fetched while building). What the API serves comes with the page: nothing waits for it.
  const [nonce, meta] = await Promise.all([
    headers().then((h) => h.get("x-nonce") ?? undefined),
    metaState(),
  ]);

  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`${ygSans.variable} ${newsreader.variable} ${readex.variable}`}
    >
      <body className="flex min-h-dvh flex-col">
        <Providers nonce={nonce} state={meta}>
          <a href="#main" className="skip-link">
            Skip to content
          </a>
          <TopBar />
          <main id="main" tabIndex={-1} className="flex-1 outline-none">
            {children}
          </main>
          <SiteFooter />
          <ChatLauncher />
        </Providers>
      </body>
    </html>
  );
}
