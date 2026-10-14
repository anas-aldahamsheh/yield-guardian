import type { Metadata, Viewport } from "next";
import { Atkinson_Hyperlegible_Next, Source_Serif_4 } from "next/font/google";
import { headers } from "next/headers";
import type { ReactNode } from "react";

import { Providers } from "@/components/providers";
import { SiteFooter } from "@/components/shell/site-footer";
import { TopBar } from "@/components/shell/top-bar";

import "./globals.css";

/** Readings, data and interface. Glyphs that are easy to confuse (0 O, 1 l I, 5 S) differ. */
const reading = Atkinson_Hyperlegible_Next({
  subsets: ["latin"],
  variable: "--font-reading",
  display: "swap",
});

/** Text a language model wrote. Optical sizes keep it crisp at report sizes. */
const written = Source_Serif_4({
  subsets: ["latin"],
  axes: ["opsz"],
  style: ["normal", "italic"],
  variable: "--font-written",
  display: "swap",
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
  // fetched while building).
  const nonce = (await headers()).get("x-nonce") ?? undefined;

  return (
    <html lang="en" suppressHydrationWarning className={`${reading.variable} ${written.variable}`}>
      <body className="flex min-h-dvh flex-col">
        <Providers nonce={nonce}>
          <a href="#main" className="skip-link">
            Skip to content
          </a>
          <TopBar />
          <main id="main" tabIndex={-1} className="flex-1 outline-none">
            {children}
          </main>
          <SiteFooter />
        </Providers>
      </body>
    </html>
  );
}
