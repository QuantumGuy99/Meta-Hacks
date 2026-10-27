import type { Metadata } from "next";
import { ReportDemo } from "@/components/report/ReportDemo";
import "@/components/landing/landing.css";
import "@/components/room/room.css";
import "@/components/defense/defense.css";
import "@/components/report/report.css";

export const metadata: Metadata = {
  title: "Session report demo · Ares",
  description: "A Ares session report: scores, metrics, and a replay of the code with the transcript.",
};

// Demo of the report + replay page on mock timeline data (FE-7).
export default function ReportDemoPage() {
  return (
    <main id="main" className="lp" tabIndex={-1}>
      <ReportDemo />
    </main>
  );
}
