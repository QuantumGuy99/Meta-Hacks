import type { Metadata } from "next";
import { Suspense } from "react";
import { LiveRoom } from "@/components/room/LiveRoom";
import "@/components/landing/landing.css";
import "@/components/room/room.css";
import "@/components/live/live.css";

export const metadata: Metadata = {
  title: "Interview room · Ares",
  description: "A live Ares coding interview.",
};

type Params = PageProps<"/coding/[id]">["params"];

// With Cache Components, the route's params are request data: read them inside a Suspense boundary.
export default function CodingRoomPage({ params }: PageProps<"/coding/[id]">) {
  return (
    <main id="main" className="lp" tabIndex={-1}>
      <h1 className="sr-only">Coding interview room</h1>
      <Suspense>
        <Room params={params} />
      </Suspense>
    </main>
  );
}

async function Room({ params }: { params: Params }) {
  const { id } = await params;
  return <LiveRoom id={id} />;
}
