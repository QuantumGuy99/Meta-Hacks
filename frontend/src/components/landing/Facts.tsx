"use client";

import NumberFlow from "@number-flow/react";
import { useEffect, useRef, useState } from "react";

// Verifiable facts only (README and PLAN.md), no invented user counts or ratings.
const FACTS = [
  { value: 2, label: "interview modes, one live interviewer" },
  { value: 7, label: "Meta models in the loop" },
  { value: 200, label: "concurrent requests in a chaos attack, at most" },
  { value: 0, label: "problems copied from LeetCode" },
];

// README "Meta models we use" (SAM 3.1 joined for the defense grill's "circle the flaw").
const MODELS = ["Muse Spark 1.3", "Muse Wonder 1.0", "Muse Voice Transcribe", "Muse Glimmer", "Muse Spark Open", "Muse Image", "SAM 3.1"];

// Numbers roll up once when the strip scrolls into view.
export function Facts() {
  const root = useRef<HTMLElement>(null);
  const [seen, setSeen] = useState(false);

  useEffect(() => {
    const el = root.current;
    if (!el) return;
    const io = new IntersectionObserver(
      ([e]) => {
        if (e.isIntersecting) {
          setSeen(true);
          io.disconnect();
        }
      },
      { threshold: 0.4 },
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);

  return (
    <section ref={root} className="facts" aria-label="Ares in numbers">
      <dl className="facts-grid">
        {FACTS.map((f) => (
          <div key={f.label} className="fact">
            <dt className="fact-label">{f.label}</dt>
            <dd className="fact-num">
              <NumberFlow value={seen ? f.value : 0} />
            </dd>
          </div>
        ))}
      </dl>
      <p className="facts-models">
        <span className="facts-models-label">Built on</span>
        {MODELS.map((m) => (
          <span key={m} className="facts-model" translate="no">
            {m}
          </span>
        ))}
      </p>
    </section>
  );
}
