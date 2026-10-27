// One code palette for Monaco (live editor) and Shiki (static code) so every snippet matches.

export const codePalette = {
  bg: "#121214",
  fg: "#e6e6e3",
  muted: "#7c7c84",
  lineHighlight: "#18181b",
  selection: "#1c80ba40",
  cursor: "#1c80ba",
  keyword: "#6cb6e3",
  string: "#9fd49a",
  number: "#e9b872",
  func: "#f2f2f0",
  type: "#b9a8f0",
  comment: "#6b6b73",
  flagged: "#e5484d",
} as const;

const p = codePalette;

// TextMate theme for Shiki.
export const shikiTheme = {
  name: "crucible",
  type: "dark" as const,
  colors: {
    "editor.background": p.bg,
    "editor.foreground": p.fg,
  },
  tokenColors: [
    { scope: ["comment", "punctuation.definition.comment"], settings: { foreground: p.comment, fontStyle: "italic" } },
    { scope: ["keyword", "storage", "storage.type", "keyword.operator.logical"], settings: { foreground: p.keyword } },
    { scope: ["string", "string.quoted"], settings: { foreground: p.string } },
    { scope: ["constant.numeric", "constant.language"], settings: { foreground: p.number } },
    { scope: ["entity.name.function", "support.function"], settings: { foreground: p.func } },
    { scope: ["support.type", "entity.name.type", "storage.type.annotation"], settings: { foreground: p.type } },
    { scope: ["variable", "variable.parameter"], settings: { foreground: p.fg } },
  ],
};

const hex = (c: string) => c.replace("#", "");

// Monaco theme built from the same palette (passed to monaco.editor.defineTheme).
export const monacoTheme = {
  base: "vs-dark" as const,
  inherit: true,
  rules: [
    { token: "comment", foreground: hex(p.comment), fontStyle: "italic" },
    { token: "keyword", foreground: hex(p.keyword) },
    { token: "string", foreground: hex(p.string) },
    { token: "number", foreground: hex(p.number) },
    { token: "type", foreground: hex(p.type) },
    { token: "identifier", foreground: hex(p.fg) },
  ],
  colors: {
    "editor.background": p.bg,
    "editor.foreground": p.fg,
    "editor.lineHighlightBackground": p.lineHighlight,
    "editor.selectionBackground": p.selection,
    "editorCursor.foreground": p.cursor,
    "editorLineNumber.foreground": "#4a4a50",
    "editorLineNumber.activeForeground": p.muted,
    "editorGutter.background": p.bg,
    "editorIndentGuide.background1": "#1e1e22",
    "scrollbarSlider.background": "#2a2a2f80",
  },
};
