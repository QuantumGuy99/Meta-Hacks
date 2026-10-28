import type { Metadata } from "next";
import { Suspense } from "react";
import { SamplePicker } from "@/components/defense/SamplePicker";
import "@/components/landing/landing.css";
import "@/components/live/live.css";

export const metadata: Metadata = {
  title: "New project defense · Ares",
  description: "Pick a sample app: Ares audits it, attacks it, grills you on what broke, then verifies your fix.",
};

export default function DefenseSetupPage() {
  return (
    <main id="main" className="lp setup-page" tabIndex={-1}>
      <Suspense>
        <SamplePicker />
      </Suspense>
    </main>
  );
}
