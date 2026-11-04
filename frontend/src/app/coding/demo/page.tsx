import type { Metadata } from "next";
import { RoomDemo } from "@/components/room/RoomDemo";
import "@/components/landing/landing.css";
import "@/components/room/room.css";

export const metadata: Metadata = {
  title: "Interview room demo · Ares",
  description: "A scripted Ares coding interview: Monaco editor, live interviewer and test runs.",
};

// Demo of the interview room on mock data until the session WebSocket exists (FE-3/FE-4).
export default function CodingDemoPage() {
  return (
    <main id="main" className="lp" tabIndex={-1}>
      <h1 className="sr-only">Coding interview room demo</h1>
      <RoomDemo />
    </main>
  );
}
