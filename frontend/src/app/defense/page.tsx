import Link from "next/link";

// FE-6 placeholder: sample app cards (and zip upload, P1) land here.
export default function DefensePicker() {
  return (
    <main className="mx-auto flex min-h-svh w-full max-w-3xl flex-col justify-center gap-6 px-6">
      <h1 className="text-5xl font-medium tracking-tight">Project Defense</h1>
      <p className="text-lg">
        The sample app picker is on the build list (FE-6). Pick an app, watch it get audited and
        attacked, then defend your fix.
      </p>
      <Link href="/" className="underline underline-offset-4">
        Back to the Main Screen
      </Link>
    </main>
  );
}
