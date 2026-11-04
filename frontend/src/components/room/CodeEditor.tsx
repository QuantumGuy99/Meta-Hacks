"use client";

import Editor, { type BeforeMount, loader, type OnMount } from "@monaco-editor/react";
import { useEffect, useRef, useState } from "react";
import { monacoTheme } from "@/lib/code-theme";

// Monaco from this app (public/monaco, copied by scripts/copy-monaco.mjs), never the loader's default CDN:
// a network that blocked cdn.jsdelivr.net left every room without an editor.
loader.config({ paths: { vs: "/monaco/vs" } });
const LOAD_WARNING_MS = 15_000;

type Monaco = Parameters<BeforeMount>[0];
type StandaloneEditor = Parameters<OnMount>[0];

export type FlaggedLine = { line: number; note: string };

// Monaco in the Ares theme, set up like an interview (no autocomplete, no minimap).
// Flagged lines get a red gutter marker and a hover note, never a fix.
export function CodeEditor({
  value,
  onChange,
  flagged = [],
  readOnly = false,
  onRun,
  onEditor,
  path,
  language = "python",
  height = "100%",
}: {
  value: string;
  onChange?: (code: string) => void;
  flagged?: FlaggedLine[];
  readOnly?: boolean;
  onRun?: () => void;
  /** The mounted Monaco editor, e.g. for `attachEditorCapture` (lib/capture/editor.ts). */
  onEditor?: (editor: StandaloneEditor) => void;
  /** One model per path (defense file tabs): switching keeps each file's edits and isn't an edit itself. */
  path?: string;
  /** Monaco's language id; the contract's `Language` values ("python", "java", "cpp", "c") are all ids. */
  language?: string;
  height?: string | number;
}) {
  const editorRef = useRef<StandaloneEditor | null>(null);
  const monacoRef = useRef<Monaco | null>(null);
  const decorations = useRef<ReturnType<StandaloneEditor["createDecorationsCollection"]> | null>(null);
  const runRef = useRef(onRun);
  useEffect(() => {
    runRef.current = onRun;
  });

  const beforeMount: BeforeMount = (monaco) => {
    monaco.editor.defineTheme("ares", monacoTheme);
  };

  const onMount: OnMount = (editor, monaco) => {
    editorRef.current = editor;
    monacoRef.current = monaco;
    decorations.current = editor.createDecorationsCollection();
    // Monaco measures glyphs on a canvas, so it needs the real next/font family name, not the CSS variable.
    const mono = getComputedStyle(document.documentElement).getPropertyValue("--font-geist-mono").trim();
    if (mono) editor.updateOptions({ fontFamily: mono });
    // Ctrl/Cmd+Enter runs the visible tests, same as the Run button.
    editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.Enter, () => runRef.current?.());
    applyFlags();
    onEditor?.(editor);
  };

  function applyFlags() {
    const monaco = monacoRef.current;
    if (!monaco || !decorations.current) return;
    decorations.current.set(
      flagged.map((f) => ({
        range: new monaco.Range(f.line, 1, f.line, 1),
        options: {
          isWholeLine: true,
          className: "cm-flagged-line",
          glyphMarginClassName: "cm-flagged-glyph",
          glyphMarginHoverMessage: { value: f.note },
          hoverMessage: { value: `**Interviewer:** ${f.note}` },
        },
      })),
    );
  }

  // Re-apply markers whenever the flagged set changes.
  useEffect(applyFlags, [flagged]);

  return (
    <Editor
      height={height}
      path={path}
      language={language}
      value={value}
      theme="ares"
      beforeMount={beforeMount}
      onMount={onMount}
      onChange={(v) => onChange?.(v ?? "")}
      loading={<EditorLoading />}
      options={{
        readOnly,
        fontFamily: "monospace",
        fontSize: 13,
        lineHeight: 20,
        minimap: { enabled: false },
        quickSuggestions: false,
        suggestOnTriggerCharacters: false,
        wordBasedSuggestions: "off",
        parameterHints: { enabled: false },
        glyphMargin: true,
        scrollBeyondLastLine: false,
        renderLineHighlight: "line",
        padding: { top: 12, bottom: 12 },
        automaticLayout: true,
        tabSize: 4,
      }}
    />
  );
}

// The loading state says so when Monaco takes too long, instead of spinning forever.
function EditorLoading() {
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    const id = setTimeout(() => setSlow(true), LOAD_WARNING_MS);
    return () => clearTimeout(id);
  }, []);
  return (
    <div className="cm-loading" role="status">
      {slow ? "The editor is taking a while to load. Check your connection, then reload the page." : "Loading editor…"}
    </div>
  );
}
