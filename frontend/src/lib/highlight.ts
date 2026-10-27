import "server-only";
import { cacheLife } from "next/cache";
import { createHighlighter, type Highlighter } from "shiki";
import { shikiTheme } from "./code-theme";

// Server-side Shiki: static code ships as HTML, no highlighter JS in the browser.
let highlighter: Promise<Highlighter> | null = null;

function getHighlighter() {
  highlighter ??= createHighlighter({ themes: [shikiTheme], langs: ["python"] });
  return highlighter;
}

// Cached so prerendering doesn't trip on Shiki's internal Date.now() (Cache Components).
export async function highlightPython(code: string) {
  "use cache";
  cacheLife("max"); // the snippets are fixed at build time
  const h = await getHighlighter();
  return h.codeToHtml(code, { lang: "python", theme: "crucible" });
}
