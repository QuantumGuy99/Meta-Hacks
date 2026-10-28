import type { Metadata } from "next";
import { Suspense } from "react";
import { LiveReport } from "@/components/report/LiveReport";
import "@/components/landing/landing.css";
import "@/components/room/room.css";
import "@/components/defense/defense.css";
import "@/components/report/report.css";
import "@/components/live/live.css";

export const metadata: Metadata = {
  title: "Report · Ares",
  description: "Scores, key moments and a replay of an Ares session.",
};

type Params = PageProps<"/report/[id]">["params"];

// With Cache Components, the route's params are request data: read them inside a Suspense boundary.
export default function ReportPage({ params }: PageProps<"/report/[id]">) {
  return (
    <main id="main" className="lp" tabIndex={-1}>
      <Suspense>
        <SessionReport params={params} />
      </Suspense>
    </main>
  );
}

async function SessionReport({ params }: { params: Params }) {
  const { id } = await params;
  return <LiveReport id={id} />;
}
