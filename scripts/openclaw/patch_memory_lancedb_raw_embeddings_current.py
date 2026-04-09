#!/usr/bin/env python3
"""Patch current OpenClaw memory-lancedb plugin to use raw HTTP embeddings."""
from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

PLUGIN = Path("/usr/lib/node_modules/openclaw/dist/extensions/memory-lancedb/index.js")

OLD = """var Embeddings = class {
\tconstructor(apiKey, model, baseUrl, dimensions) {
\t\tthis.model = model;
\t\tthis.dimensions = dimensions;
\t\tthis.client = new OpenAI({
\t\t\tapiKey,
\t\t\tbaseURL: baseUrl
\t\t});
\t}
\tasync embed(text) {
\t\tconst params = {
\t\t\tmodel: this.model,
\t\t\tinput: text
\t\t};
\t\tif (this.dimensions) params.dimensions = this.dimensions;
\t\tensureGlobalUndiciEnvProxyDispatcher();
\t\treturn (await this.client.embeddings.create(params)).data[0].embedding;
\t}
};
"""

NEW = """var Embeddings = class {
\tconstructor(apiKey, model, baseUrl, dimensions) {
\t\tthis.model = model;
\t\tthis.dimensions = dimensions;
\t\tthis.apiKey = apiKey;
\t\tthis.baseUrl = baseUrl;
\t\tthis.client = new OpenAI({
\t\t\tapiKey,
\t\t\tbaseURL: baseUrl
\t\t});
\t}
\tasync embed(text) {
\t\tconst baseUrl = typeof this.baseUrl === "string" && this.baseUrl.trim() ? this.baseUrl.replace(/\\/$/, "") : "";
\t\tconst expectedDims = typeof this.dimensions === "number" ? this.dimensions : void 0;
\t\tif (baseUrl) {
\t\t\tensureGlobalUndiciEnvProxyDispatcher();
\t\t\tconst response = await fetch(`${baseUrl}/embeddings`, {
\t\t\t\tmethod: "POST",
\t\t\t\theaders: {
\t\t\t\t\t"Content-Type": "application/json",
\t\t\t\t\tAuthorization: `Bearer ${this.apiKey}`
\t\t\t\t},
\t\t\t\tbody: JSON.stringify({
\t\t\t\t\tmodel: this.model,
\t\t\t\t\tinput: text
\t\t\t\t})
\t\t\t});
\t\t\tif (!response.ok) throw new Error(`Embeddings request failed (${response.status} ${response.statusText})`);
\t\t\tconst payload = await response.json();
\t\t\tconst embedding = payload?.data?.[0]?.embedding;
\t\t\tif (!Array.isArray(embedding) || embedding.length === 0) throw new Error("Embeddings response missing numeric vector");
\t\t\tconst vector = embedding.map((value) => Number(value));
\t\t\tif (vector.some((value) => !Number.isFinite(value))) throw new Error("Embeddings response contains non-numeric values");
\t\t\tif (expectedDims && vector.length !== expectedDims) throw new Error(`Embeddings dimension mismatch: expected ${expectedDims}, got ${vector.length}`);
\t\t\treturn vector;
\t\t}
\t\tconst params = {
\t\t\tmodel: this.model,
\t\t\tinput: text
\t\t};
\t\tif (this.dimensions) params.dimensions = this.dimensions;
\t\tensureGlobalUndiciEnvProxyDispatcher();
\t\tconst embedding = (await this.client.embeddings.create(params)).data[0].embedding;
\t\tif (expectedDims && Array.isArray(embedding) && embedding.length !== expectedDims) throw new Error(`Embeddings dimension mismatch: expected ${expectedDims}, got ${embedding.length}`);
\t\treturn embedding;
\t}
};
"""


def main() -> int:
    if not PLUGIN.is_file():
        raise SystemExit(f"plugin not found: {PLUGIN}")
    text = PLUGIN.read_text(encoding="utf-8")
    if NEW in text:
        print("already patched")
        return 0
    if OLD not in text:
        raise SystemExit("expected Embeddings block not found; plugin layout changed")
    backup = PLUGIN.with_name(f"{PLUGIN.name}.bak-memory-raw-embeddings-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
    shutil.copy2(PLUGIN, backup)
    PLUGIN.write_text(text.replace(OLD, NEW, 1), encoding="utf-8")
    print(str(backup))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
