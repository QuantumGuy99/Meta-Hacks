import Link from "next/link";
import { Button } from "@/components/ui/button";

// FE-5 placeholder: the setup form (difficulty, topic, feedback, voice, speak replies) lands here.
export default function CodingSetup() {
  return (
    <main className="mx-auto flex min-h-svh w-full max-w-3xl flex-col justify-center gap-6 px-6">
      <h1 className="text-5xl font-medium tracking-tight">Coding Interview Setup</h1>
      <p className="text-lg">
        The setup form is next on the build list (FE-5). It will create a session and open the
        interview room. Until then, try the scripted room.
      </p>
      <div className="flex flex-wrap items-center gap-6">
        <Button render={<Link href="/coding/demo" />} size="lg" nativeButton={false}>
          Open the Demo Room
        </Button>
        <Link href="/" className="underline underline-offset-4">
          Back to the Main Screen
        </Link>
      </div>
    </main>
  );
}
