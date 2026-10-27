"use client";

import Editor, { type BeforeMount, type OnMount } from "@monaco-editor/react";
import { useEffect, useRef } from "react";
import { monacoTheme } from "@/lib/code-theme";

type Monaco = Parameters<BeforeMount>[0];
type StandaloneEditor = Parameters<OnMount>[0];

export type FlaggedLine = { line: number; note: string };

// Monaco in the Crucible theme, set up like an interview (no autocomplete, no minimap).
// Flagged lines get a red gutter marker and a hover note, never a fix.
export function CodeEditor({
  value,
  onChange,
  flagged = [],
  readOnly = false,
  onRun,
  height = "100%",
}: {
  value: string;
  onChange?: (code: string) => void;
  flagged?: FlaggedLine[];
  readOnly?: boolean;
  onRun?: () => void;
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
    monaco.editor.defineTheme("crucible", monacoTheme);
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
      defaultLanguage="python"
      value={value}
      theme="crucible"
      beforeMount={beforeMount}
      onMount={onMount}
      onChange={(v) => onChange?.(v ?? "")}
      loading={<div className="cm-loading">Loading editor…</div>}
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
