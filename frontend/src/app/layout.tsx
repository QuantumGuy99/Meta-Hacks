import type { Metadata, Viewport } from "next";
import { Geist_Mono, Hanken_Grotesk } from "next/font/google";
import { ViewTransition } from "react";
import { MotionProvider } from "@/components/motion/MotionProvider";
import { Toaster } from "@/components/ui/sonner";
import "./globals.css";

const hanken = Hanken_Grotesk({
  variable: "--font-sans",
  subsets: ["latin"],
  weight: ["400", "500"],
});

// Code only: the editor fragments and the interview room's Monaco fallback.
const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Crucible: the AI interviewer that watches how you engineer",
  description:
    "Live coding interviews and project defense with an AI interviewer that follows every edit, nudges you when you skip a step and grades your process.",
};

// Matches --bg so browser chrome blends with the dark page.
export const viewport: Viewport = {
  themeColor: "#0c0c0d",
  colorScheme: "dark",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      // The inline script adds the "js" class before hydration.
      suppressHydrationWarning
      className={`${hanken.variable} ${geistMono.variable} dark h-full antialiased`}
    >
      <head>
        {/* Motion hides content only once JS is known to run (taste-skill motion rule). */}
        <script
          dangerouslySetInnerHTML={{
            __html: "document.documentElement.classList.add('js')",
          }}
        />
      </head>
      <body className="min-h-full flex flex-col">
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
