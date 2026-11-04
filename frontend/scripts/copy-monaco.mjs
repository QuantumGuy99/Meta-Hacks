// Copies the installed Monaco build into public/monaco/vs so the editor is served by this app, not a CDN.
// @monaco-editor/react fetches Monaco from cdn.jsdelivr.net by default: on a network that blocks or slows it,
// every room sat on "Loading editor…" forever, and the CDN copy (0.55) wasn't the version installed here.
// Runs before `dev` and `build`; skips the copy when the version already there matches.
import { cpSync, existsSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const pkg = join(root, "node_modules", "monaco-editor");
const source = join(pkg, "min", "vs");
const target = join(root, "public", "monaco", "vs");
const stamp = join(root, "public", "monaco", "VERSION");
const version = JSON.parse(readFileSync(join(pkg, "package.json"), "utf8")).version;

if (existsSync(stamp) && readFileSync(stamp, "utf8").trim() === version && existsSync(join(target, "loader.js"))) {
  process.exit(0);
}
rmSync(join(root, "public", "monaco"), { recursive: true, force: true });
cpSync(source, target, { recursive: true });
writeFileSync(stamp, `${version}\n`, "utf8");
console.log(`copied monaco-editor ${version} to public/monaco/vs`);
