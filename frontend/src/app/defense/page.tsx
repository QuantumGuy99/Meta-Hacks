import Link from "next/link";
import { Button } from "@/components/ui/button";

// FE-6 placeholder: sample app cards (and zip upload, P1) land here.
export default function DefensePicker() {
  return (
    <main className="mx-auto flex min-h-svh w-full max-w-3xl flex-col justify-center gap-6 px-6">
      <h1 className="text-5xl font-medium tracking-tight">Project Defense</h1>
      <p className="text-lg">
        The sample app picker is on the build list (FE-6). Pick an app, watch it get audited and
        attacked, then defend your fix. Until then, try the scripted bank-transfer defense.
      </p>
      <div className="flex flex-wrap items-center gap-6">
        <Button render={<Link href="/defense/demo" />} size="lg" nativeButton={false}>
          Open the Defense Demo
        </Button>
        <Link href="/" className="underline underline-offset-4">
          Back to the Main Screen
        </Link>
      </div>
    </main>
  );
}
