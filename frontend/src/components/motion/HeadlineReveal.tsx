"use client";

import { useGSAP } from "@gsap/react";
import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { SplitText } from "gsap/SplitText";
import { useRef } from "react";

gsap.registerPlugin(ScrollTrigger, SplitText, useGSAP);

// Masked letter-by-letter rise for headings that mix fonts and colours (React Bits'
// SplitText takes a plain string; this keeps the inline <em>/<span> styling).
// Visible as-is without JS or with reduced motion.
export function HeadlineReveal({
  as: Tag = "h2",
  id,
  className,
  onLoad = false,
  children,
}: {
  as?: "h1" | "h2";
  id?: string;
  className?: string;
  /** play on page load instead of when scrolled into view */
  onLoad?: boolean;
  children: React.ReactNode;
}) {
  const ref = useRef<HTMLHeadingElement>(null);

  useGSAP(
    () => {
      const el = ref.current;
      if (!el) return;
      const mm = gsap.matchMedia();
      mm.add("(prefers-reduced-motion: no-preference)", () => {
        let split: SplitText | null = null;
        let alive = true;
        const run = () => {
          if (!alive) return;
          split = SplitText.create(el, {
            type: "words,chars",
            mask: "chars",
            charsClass: "hl-char",
            wordsClass: "hl-word",
          });
          gsap.set(el, { visibility: "visible" });
          gsap.from(split.chars, {
            yPercent: 118,
            duration: 1.05,
            ease: "expo.out",
            stagger: 0.016,
            scrollTrigger: onLoad ? undefined : { trigger: el, start: "top 88%", once: true },
          });
        };
        // Split after the web fonts settle so line breaks don't shift mid-animation.
        if (document.fonts?.ready) document.fonts.ready.then(run);
        else run();
        return () => {
          alive = false;
          split?.revert();
        };
      });
      return () => mm.revert();
    },
    { scope: ref },
  );

  return (
    <Tag ref={ref} id={id} className={`hl-reveal ${className ?? ""}`}>
      {children}
    </Tag>
  );
}
