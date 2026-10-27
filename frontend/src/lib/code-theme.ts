// One code palette for Monaco (live editor) and Shiki (static code) so every snippet matches.

export const codePalette = {
  // transparent so editors take the solid panel they sit in
  bg: "#00000000",
  fg: "#ffffff",
  muted: "#8a8a94",
  lineHighlight: "#ffffff0d",
  selection: "#2f6bff66",
  cursor: "#2f6bff",
  keyword: "#8fb3ff",
  string: "#6f9bff",
  number: "#8fb3ff",
  func: "#ffffff",
  type: "#ffffff",
  comment: "#6b6b75",
  flagged: "#ffffff",
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
    "editorLineNumber.foreground": "#4d5566",
    "editorWidget.background": "#0e121bf2",
    "editorHoverWidget.background": "#0e121bf2",
    "editorHoverWidget.border": "#ffffff1a",
    "minimap.background": "#00000000",
    "editorLineNumber.activeForeground": p.muted,
    "editorGutter.background": p.bg,
    "editorIndentGuide.background1": "#ffffff0d",
    "scrollbarSlider.background": "#2a334580",
  },
};
