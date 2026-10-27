import type { Metadata, Viewport } from "next";
import { Geist_Mono, Inter, Space_Grotesk } from "next/font/google";
import Script from "next/script";
import { ViewTransition } from "react";
import { MotionProvider } from "@/components/motion/MotionProvider";
import { Toaster } from "@/components/ui/sonner";
import "./globals.css";
import "@/components/theme/liquid-glass.css";
import "@/components/theme/vivid.css";
import "@/components/theme/hacker.css";

// Reading text: body copy, descriptions, chat messages.
const inter = Inter({
  variable: "--font-sans",
  subsets: ["latin"],
});

// Display face: headings, the wordmark, nav, buttons and labels.
const spaceGrotesk = Space_Grotesk({
  variable: "--font-display",
  subsets: ["latin"],
  weight: ["400", "500", "600"],
});

// Code and terminal cues only: editor fragments, file names, timers, the principles panel.
const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Crucible: the AI interviewer that watches how you engineer",
  description:
    "Live coding interviews and project defense with an AI interviewer that follows every edit, nudges you when you skip a step and grades your process.",
};

// Matches --bg so browser chrome blends with the black page.
export const viewport: Viewport = {
  themeColor: "#000000",
  colorScheme: "dark",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      // data-theme keys the liquid-glass tokens; the inline script adds the "js" class before hydration.
      data-theme="dark"
      suppressHydrationWarning
      className={`${inter.variable} ${spaceGrotesk.variable} ${geistMono.variable} dark h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        {/* Motion hides content only once JS is known to run (taste-skill motion rule). */}
        <Script id="js-flag" strategy="beforeInteractive">
          {"document.documentElement.classList.add('js')"}
        </Script>
        <a href="#main" className="skip-link">
          Skip to Content
        </a>
        <MotionProvider>
          {/* Route changes crossfade (React 19.3 view transitions; reduced motion in globals.css). */}
          <ViewTransition>{children}</ViewTransition>
        </MotionProvider>
        {/* Top right, below the bars, so toasts never cover the room's Ask box. */}
        <Toaster position="top-right" offset={64} />
      </body>
    </html>
  );
}
