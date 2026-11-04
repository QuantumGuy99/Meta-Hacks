// Project Defense uploads (PLAN §11.1): the server takes one zip, but people usually have a folder. This turns
// the files they pick (a folder, or a few files) into a zip in the browser, with no dependency: entries are
// stored, not compressed, and the 6,000-line limit keeps a project far under the 2 MB cap anyway.
// The filters match the server's (defense/projects.py), so caches and venvs never count against the limits.

/** Folders the server skips (SKIP_DIRS); hidden folders and files are skipped too. */
const SKIP_DIRS = new Set([".git", "venv", ".venv", "node_modules", "__pycache__", "fixed"]);
/** The only file types the server reads (TEXT_SUFFIXES). */
const TEXT_SUFFIXES = [".py", ".txt", ".toml", ".cfg", ".ini", ".json", ".sql", ".html", ".md", ".yaml", ".yml"];

export type PickedFile = { path: string; file: Blob };

/** Whether the server would read this path: a text file outside caches, venvs and hidden folders. */
export function keepPath(path: string): boolean {
  const parts = path.replace(/\\/g, "/").split("/").filter(Boolean);
  if (!parts.length || parts.some((p) => SKIP_DIRS.has(p) || p.startsWith("."))) return false;
  const name = parts[parts.length - 1].toLowerCase();
  return TEXT_SUFFIXES.some((s) => name.endsWith(s));
}

const CRC_TABLE = (() => {
  const table = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    table[n] = c >>> 0;
  }
  return table;
})();

export function crc32(data: Uint8Array): number {
  let c = 0xffffffff;
  for (let i = 0; i < data.length; i++) c = CRC_TABLE[(c ^ data[i]) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

const DOS_DATE = (0 << 9) | (1 << 5) | 1; // 1980-01-01, the earliest date a zip can hold
const UTF8_NAMES = 1 << 11;

/** A zip (stored entries, UTF-8 names) of the given files, in the order given. */
export async function zipFiles(files: PickedFile[]): Promise<Blob> {
  const encoder = new TextEncoder();
  const chunks: Uint8Array[] = [];
  const central: Uint8Array[] = [];
  let offset = 0;
  for (const { path, file } of files) {
    const name = encoder.encode(path.replace(/\\/g, "/"));
    const data = new Uint8Array(await file.arrayBuffer());
    const crc = crc32(data);

    const local = new DataView(new ArrayBuffer(30));
    local.setUint32(0, 0x04034b50, true);
    local.setUint16(4, 20, true); // version needed: 2.0
    local.setUint16(6, UTF8_NAMES, true);
    local.setUint16(8, 0, true); // stored
    local.setUint16(10, 0, true);
    local.setUint16(12, DOS_DATE, true);
    local.setUint32(14, crc, true);
    local.setUint32(18, data.length, true);
    local.setUint32(22, data.length, true);
    local.setUint16(26, name.length, true);
    local.setUint16(28, 0, true);
    chunks.push(new Uint8Array(local.buffer), name, data);

    const entry = new DataView(new ArrayBuffer(46));
    entry.setUint32(0, 0x02014b50, true);
    entry.setUint16(4, 20, true); // made by
    entry.setUint16(6, 20, true); // needed
    entry.setUint16(8, UTF8_NAMES, true);
    entry.setUint16(10, 0, true);
    entry.setUint16(12, 0, true);
    entry.setUint16(14, DOS_DATE, true);
    entry.setUint32(16, crc, true);
    entry.setUint32(20, data.length, true);
    entry.setUint32(24, data.length, true);
    entry.setUint16(28, name.length, true);
    entry.setUint32(42, offset, true); // the rest (extra, comment, disk, attributes) stays 0
    central.push(new Uint8Array(entry.buffer), name);

    offset += 30 + name.length + data.length;
  }
  const centralSize = central.reduce((n, c) => n + c.length, 0);
  const end = new DataView(new ArrayBuffer(22));
  end.setUint32(0, 0x06054b50, true);
  end.setUint16(8, files.length, true);
  end.setUint16(10, files.length, true);
  end.setUint32(12, centralSize, true);
  end.setUint32(16, offset, true);
  return new Blob([...chunks, ...central, new Uint8Array(end.buffer)] as BlobPart[], { type: "application/zip" });
}
