"use client";

import { useState, type DragEvent } from "react";
import { api, errorText } from "@/lib/api";
import { keepPath, zipFiles, type PickedFile } from "@/lib/zip";
import type { Project } from "@/types/contracts";

// /defense: your own project for the defense. Pick or drop a folder, a .zip, or loose files; anything that isn't
// already a zip is zipped here (lib/zip.ts), since the server takes one zip (PLAN §11.1). The notes .txt is kept
// until Start, which sends it with the project.

/** Every file under a dropped folder, with paths from the folder down (skipping what the server skips). */
async function entryFiles(entry: FileSystemEntry, dir = ""): Promise<PickedFile[]> {
  const path = dir + entry.name;
  if (entry.isFile) {
    if (!keepPath(path)) return [];
    const file = await new Promise<File>((ok, fail) => (entry as FileSystemFileEntry).file(ok, fail));
    return [{ path, file }];
  }
  if (!entry.isDirectory || !keepPath(`${path}/x.py`)) return []; // a skipped folder (venv, .git, …)
  const reader = (entry as FileSystemDirectoryEntry).createReader();
  const children: FileSystemEntry[] = [];
  for (;;) {
    const batch = await new Promise<FileSystemEntry[]>((ok, fail) => reader.readEntries(ok, fail));
    if (!batch.length) break;
    children.push(...batch);
  }
  return (await Promise.all(children.map((c) => entryFiles(c, `${path}/`)))).flat();
}

const isZip = (name: string) => name.toLowerCase().endsWith(".zip");

export function ProjectUpload({
  uploaded,
  onUploaded,
  onBusy,
  notes,
  onNotes,
}: {
  uploaded: Project | null;
  onUploaded: (project: Project) => void;
  onBusy: (busy: boolean) => void;
  notes: File | null;
  onNotes: (file: File | null) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [over, setOver] = useState(false);

  const send = async (body: Blob, name: string) => {
    setBusy(true);
    onBusy(true);
    setError(null);
    try {
      onUploaded(await api.uploadProject(body, name));
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
      onBusy(false);
    }
  };

  /** A single .zip goes up as it is; a folder or loose files are zipped first. */
  const take = async (picked: PickedFile[], folder: string | null) => {
    if (picked.length === 1 && isZip(picked[0].path)) return send(picked[0].file, picked[0].path);
    const kept = picked.filter((f) => keepPath(f.path));
    if (!kept.length) {
      setError("Nothing to upload there: pick the folder with your FastAPI app (its .py files and requirements.txt), or a .zip of it.");
      return;
    }
    await send(await zipFiles(kept), `${folder ?? "my-project"}.zip`);
  };

  const fromInput = (list: FileList | null) => {
    const files = [...(list ?? [])];
    if (!files.length) return;
    const folder = files[0].webkitRelativePath ? files[0].webkitRelativePath.split("/")[0] : null;
    void take(files.map((f) => ({ path: f.webkitRelativePath || f.name, file: f })), folder);
  };

  const onDrop = async (e: DragEvent) => {
    e.preventDefault();
    setOver(false);
    if (busy) return;
    const entries = [...e.dataTransfer.items].map((i) => i.webkitGetAsEntry()).filter((x): x is FileSystemEntry => !!x);
    const folder = entries.length === 1 && entries[0].isDirectory ? entries[0].name : null;
    if (entries.length === 1 && entries[0].isFile && isZip(entries[0].name)) {
      const file = e.dataTransfer.files[0];
      return send(file, file.name);
    }
    try {
      await take((await Promise.all(entries.map((x) => entryFiles(x)))).flat(), folder);
    } catch (err) {
      setError(errorText(err));
    }
  };

  return (
    <fieldset className="setup-upload">
      <legend>Your own project</legend>
      <p>
        A Python FastAPI app with its <code>requirements.txt</code> (up to 60 files, 6,000 lines). It runs in a sandbox
        and stays private to you.
      </p>
      <div
        className="up-drop"
        data-over={over || undefined}
        onDragOver={(e) => {
          e.preventDefault();
          setOver(true);
        }}
        onDragLeave={(e) => {
          if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setOver(false);
        }}
        onDrop={(e) => void onDrop(e)}
      >
        <strong>{busy ? "Uploading…" : "Drop your project folder or .zip here, or choose it"}</strong>
        <span className="up-actions">
          <label className="ui-btn ui-btn-primary up-pick" aria-disabled={busy || undefined}>
            <input
              type="file"
              disabled={busy}
              {...{ webkitdirectory: "" }}
              onChange={(e) => {
                fromInput(e.target.files);
                e.target.value = ""; // picking the same folder again still uploads
              }}
            />
            Choose Folder
          </label>
          <label className="ui-btn up-pick" aria-disabled={busy || undefined}>
            <input
              type="file"
              multiple
              disabled={busy}
              accept=".zip,application/zip,application/x-zip-compressed,.py,.txt,.toml,.cfg,.ini,.json,.sql,.html,.md,.yaml,.yml"
              onChange={(e) => {
                fromInput(e.target.files);
                e.target.value = "";
              }}
            />
            Choose .zip or Files
          </label>
        </span>
        {error ? (
          <p className="up-status is-error" role="alert">
            {error}
          </p>
        ) : uploaded && !busy ? (
          <p className="up-status is-ok" role="status">
            Uploaded <strong translate="no">{uploaded.name}</strong>: {uploaded.loc} lines, {uploaded.files.length} files.
            It&rsquo;s selected under Project.
          </p>
        ) : null}
      </div>
      <div className="up-notes">
        <label className="ui-btn up-pick">
          <input
            type="file"
            accept=".txt,text/plain"
            onChange={(e) => {
              onNotes(e.target.files?.[0] ?? null);
              e.target.value = "";
            }}
          />
          {notes ? "Change Notes" : "Add Notes (.txt)"}
        </label>
        <span>{notes ? <strong translate="no">{notes.name}</strong> : "Optional: what the app does and what matters in it, for the audit"}</span>
        {notes && (
          <button type="button" className="ui-btn" onClick={() => onNotes(null)}>
            Remove
          </button>
        )}
      </div>
    </fieldset>
  );
}
