import type { Metadata } from "next";
import { DefenseDemo } from "@/components/defense/DefenseDemo";
import "@/components/landing/landing.css";
import "@/components/room/room.css";
import "@/components/defense/defense.css";

export const metadata: Metadata = {
  title: "Project defense demo · Crucible",
  description: "A scripted Crucible project defense: audit topology, live chaos run, grill and merge gate.",
};

// Demo of the Project Defense flow on mock data until the defense backend exists (FE-6).
export default function DefenseDemoPage() {
  return (
    <main id="main" className="lp" tabIndex={-1}>
      <h1 className="sr-only">Project defense demo: bank-transfer</h1>
      <DefenseDemo />
    </main>
  );
}
