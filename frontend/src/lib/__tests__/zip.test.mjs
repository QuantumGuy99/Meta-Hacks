// Tests for lib/zip.ts: the zip the /defense page builds from a picked folder, read back by hand.
// Run: node --experimental-strip-types --test "frontend/src/lib/**/*.test.mjs"
import assert from "node:assert/strict";
import { test } from "node:test";

import { crc32, keepPath, zipFiles } from "../zip.ts";

/** {path: text} from a stored-only zip, walking the central directory like any unzip tool. */
function readZip(bytes) {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const end = bytes.length - 22;
  assert.equal(view.getUint32(end, true), 0x06054b50);
  const count = view.getUint16(end + 10, true);
  let at = view.getUint32(end + 16, true);
  const out = {};
  for (let i = 0; i < count; i++) {
    assert.equal(view.getUint32(at, true), 0x02014b50);
    const size = view.getUint32(at + 20, true);
    const nameLen = view.getUint16(at + 28, true);
    const local = view.getUint32(at + 42, true);
    const name = new TextDecoder().decode(bytes.subarray(at + 46, at + 46 + nameLen));
    const localName = view.getUint16(local + 26, true);
    const start = local + 30 + localName;
    const data = bytes.subarray(start, start + size);
    assert.equal(view.getUint32(at + 16, true), crc32(data), `crc of ${name}`);
    out[name] = new TextDecoder().decode(data);
    at += 46 + nameLen;
  }
  return out;
}

test("crc32 matches the standard check value", () => {
  assert.equal(crc32(new TextEncoder().encode("123456789")), 0xcbf43926);
});

test("zipFiles stores each file under its path", async () => {
  const zip = await zipFiles([
    { path: "shop/app/main.py", file: new Blob(["from fastapi import FastAPI\napp = FastAPI()\n"]) },
    { path: "shop/requirements.txt", file: new Blob(["fastapi\n"]) },
    { path: "shop\\notes/é.md", file: new Blob(["ok"]) },
  ]);
  const files = readZip(new Uint8Array(await zip.arrayBuffer()));
  assert.deepEqual(files, {
    "shop/app/main.py": "from fastapi import FastAPI\napp = FastAPI()\n",
    "shop/requirements.txt": "fastapi\n",
    "shop/notes/é.md": "ok",
  });
});

test("an empty selection is still a valid zip", async () => {
  assert.deepEqual(readZip(new Uint8Array(await (await zipFiles([])).arrayBuffer())), {});
});

test("keepPath skips what the server skips", () => {
  assert.equal(keepPath("shop/app/main.py"), true);
  assert.equal(keepPath("requirements.txt"), true);
  assert.equal(keepPath("shop/.venv/lib/x.py"), false);
  assert.equal(keepPath("shop/node_modules/a.json"), false);
  assert.equal(keepPath("shop/app/__pycache__/main.cpython-312.pyc"), false);
  assert.equal(keepPath("shop/.env"), false);
  assert.equal(keepPath("shop/logo.png"), false);
});
