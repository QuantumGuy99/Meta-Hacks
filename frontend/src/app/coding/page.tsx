import type { Metadata } from "next";
import { Suspense } from "react";
import { SetupForm } from "@/components/coding/SetupForm";
import "@/components/landing/landing.css";
import "@/components/live/live.css";

export const metadata: Metadata = {
  title: "New coding interview · Ares",
  description: "Pick a problem, feedback style and voice, then start a live Ares coding interview.",
};

export default function CodingSetupPage() {
  return (
    <main id="main" className="lp setup-page" tabIndex={-1}>
      {/* useSearchParams (the landing dialog's ?topic=&feedback=) needs a Suspense boundary */}
      <Suspense>
        <SetupForm />
      </Suspense>
    </main>
  );
}
