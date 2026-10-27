"use client";

import { LazyMotion, MotionConfig, domAnimation } from "motion/react";

// Small Motion core (`m` components) with the basic feature pack; reducedMotion="user"
// keeps fades but drops movement for people who ask for less motion.
export function MotionProvider({ children }: { children: React.ReactNode }) {
  return (
    <LazyMotion features={domAnimation}>
      <MotionConfig reducedMotion="user">{children}</MotionConfig>
    </LazyMotion>
  );
}
