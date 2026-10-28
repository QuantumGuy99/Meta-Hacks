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

      // A thin cobalt line under the nav tracks how far down the page you are.
      gsap.fromTo(
        ".lp-progress",
        { scaleX: 0 },
        { scaleX: 1, ease: "none", scrollTrigger: { start: 0, end: "max", scrub: 0.3 } },
      );

      // The nav slips away while you read down and comes back the moment you scroll up.
      const nav = document.querySelector<HTMLElement>(".lp-nav");
      if (nav) {
        ScrollTrigger.create({
          start: 0,
          end: "max",
          onUpdate: (self) => nav.toggleAttribute("data-hidden", self.direction === 1 && self.scroll() > 480),
        });
      }

      // Facts, the principles list and the footer columns arrive one after another.
      const stagger = (targets: string, trigger: string, vars: gsap.TweenVars = {}) =>
        gsap.from(targets, {
          autoAlpha: 0,
          y: 14,
          duration: 0.9,
          ease: "power3.out",
          stagger: 0.08,
          ...vars,
          scrollTrigger: { trigger, start: "top 85%", once: true },
        });
      stagger(".fact", ".facts");
      stagger(".facts-models", ".facts", { delay: 0.3 });
      stagger(".cred-rules li", ".cred-term", { y: 0, x: -10, stagger: 0.07, delay: 0.2 });
      stagger(".foot-brand, .foot-links > div", ".site-foot");

      // Portraits settle from a little smaller as their tiles rise in.
      gsap.from(".team-photo", {
        scale: 0.9,
        duration: 1.1,
        ease: "power3.out",
        stagger: 0.08,
        scrollTrigger: { trigger: ".team-grid", start: "top 85%", once: true },
      });

      // The start dialog rises into place as the blue field arrives.
      gsap.fromTo(
        ".cta .dlg",
        { y: 40 },
        { y: 0, ease: "none", scrollTrigger: { trigger: ".cta", start: "top bottom", end: "top 30%", scrub: 0.8 } },
      );
    });

    // The nav gets its hairline and frosted backing once the page has moved (not motion, so always on).
    const nav = document.querySelector<HTMLElement>(".lp-nav");
    const onScroll = () => nav?.toggleAttribute("data-scrolled", window.scrollY > 8);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });

    // Fonts and SplitText change line heights after first paint; re-measure trigger points then.
    const refresh = () => ScrollTrigger.refresh();
    document.fonts?.ready.then(refresh);
    window.addEventListener("load", refresh, { once: true });

    return () => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("load", refresh);
      mm.revert();
    };
  });

  return null;
}
