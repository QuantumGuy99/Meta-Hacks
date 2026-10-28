import type { Metadata } from "next";
import { Suspense } from "react";
import { LiveDefense } from "@/components/defense/LiveDefense";
import "@/components/landing/landing.css";
import "@/components/room/room.css";
import "@/components/defense/defense.css";
import "@/components/live/live.css";

export const metadata: Metadata = {
  title: "Project defense · Ares",
  description: "A live Ares project defense: audit, attack, grill, fix, verify.",
};

type Params = PageProps<"/defense/[id]">["params"];

// With Cache Components, the route's params are request data: read them inside a Suspense boundary.
export default function DefenseSessionPage({ params }: PageProps<"/defense/[id]">) {
  return (
    <main id="main" className="lp" tabIndex={-1}>
      <h1 className="sr-only">Project defense</h1>
      <Suspense>
        <Defense params={params} />
      </Suspense>
    </main>
  );
}

async function Defense({ params }: { params: Params }) {
  const { id } = await params;
  return <LiveDefense id={id} />;
}
