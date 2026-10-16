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
 * Both families are bundled from @fontsource-variable and self-hosted by next/font/local, so the
 * build needs no network and the page loads no font from another origin.
 */
/** Readings, data and interface. Glyphs that are easy to confuse (0 O, 1 l I, 5 S) differ. */
const reading = localFont({
  src: "../../node_modules/@fontsource-variable/atkinson-hyperlegible-next/files/atkinson-hyperlegible-next-latin-wght-normal.woff2",
  style: "normal",
  weight: "200 800",
  variable: "--font-reading",
  display: "swap",
  adjustFontFallback: "Arial",
});

/**
 * Its italic, as a family of its own so that only the upright face is preloaded: no screen sets
 * interface text in italic, and emphasis in Markdown (below the fold) fetches it when it appears.
 */
const readingItalic = localFont({
  src: "../../node_modules/@fontsource-variable/atkinson-hyperlegible-next/files/atkinson-hyperlegible-next-latin-wght-italic.woff2",
  style: "italic",
  weight: "200 800",
  variable: "--font-reading-italic",
  display: "swap",
  preload: false,
  adjustFontFallback: "Arial",
});

/** Text a language model wrote. Optical sizes keep it crisp at report sizes. */
const written = localFont({
  src: [
    {
      path: "../../node_modules/@fontsource-variable/source-serif-4/files/source-serif-4-latin-opsz-normal.woff2",
      style: "normal",
    },
    {
      path: "../../node_modules/@fontsource-variable/source-serif-4/files/source-serif-4-latin-opsz-italic.woff2",
      style: "italic",
    },
  ],
  weight: "200 900",
  variable: "--font-written",
  display: "swap",
  // Report text sits below the fold or on later screens: not worth 250 KB of preload.
  preload: false,
  adjustFontFallback: "Times New Roman",
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
    { media: "(prefers-color-scheme: light)", color: "#eef0f2" },
    { media: "(prefers-color-scheme: dark)", color: "#13120c" },
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
      className={`${reading.variable} ${readingItalic.variable} ${written.variable}`}
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
