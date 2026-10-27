"use client";

import { useGSAP } from "@gsap/react";
import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

gsap.registerPlugin(ScrollTrigger, useGSAP);

// Landing choreography on GSAP ScrollTrigger. Kept subtle on purpose: short travel, no tilt,
// long soft ease-outs. Everything is transform/opacity, and the whole block is skipped for
// reduced motion (content is then simply visible).
export function LandingMotion() {
  useGSAP(() => {
    const mm = gsap.matchMedia();
    mm.add("(prefers-reduced-motion: no-preference)", () => {
      // Section parts rise in, staggered, the first time they scroll into view.
      ScrollTrigger.batch("[data-reveal]", {
        start: "top 90%",
        once: true,
        onEnter: (els) =>
          gsap.fromTo(
            els,
            { autoAlpha: 0, y: 20 },
            { autoAlpha: 1, y: 0, duration: 1.1, ease: "power3.out", stagger: 0.07, overwrite: true },
          ),
      });

      // The hero room settles from a hair smaller as it scrolls in.
      gsap.fromTo(
        ".hero-stage .room",
        { scale: 0.975, transformOrigin: "50% 0%" },
        {
          scale: 1,
          ease: "none",
          scrollTrigger: { trigger: ".hero-stage", start: "top 92%", end: "top 40%", scrub: 0.8 },
        },
      );

      // The tour's stage drifts a touch slower than the page.
      gsap.fromTo(
        ".hiw-stage",
        { y: 24 },
        { y: -12, ease: "none", scrollTrigger: { trigger: ".hiw", start: "top bottom", end: "bottom top", scrub: true } },
      );

      // The start dialog rises into place as the blue field arrives.
      gsap.fromTo(
        ".cta .dlg",
        { y: 40 },
        { y: 0, ease: "none", scrollTrigger: { trigger: ".cta", start: "top bottom", end: "top 30%", scrub: 0.8 } },
      );
    });

    // Fonts and SplitText change line heights after first paint; re-measure trigger points then.
    const refresh = () => ScrollTrigger.refresh();
    document.fonts?.ready.then(refresh);
    window.addEventListener("load", refresh, { once: true });

    return () => {
      window.removeEventListener("load", refresh);
      mm.revert();
    };
  });

  return null;
}
