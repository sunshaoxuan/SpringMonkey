#!/usr/bin/env python3
"""Patch current OpenClaw memory-lancedb plugin to fall back to text search."""
from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path


PLUGIN_CANDIDATES = (
    Path("/root/.openclaw/npm/node_modules/@openclaw/memory-lancedb/dist/index.js"),
    Path("/var/lib/openclaw/.openclaw/npm/node_modules/@openclaw/memory-lancedb/dist/index.js"),
    Path("/usr/lib/node_modules/openclaw/dist/extensions/memory-lancedb/index.js"),
)


def plugin_path() -> Path:
    for candidate in PLUGIN_CANDIDATES:
        if candidate.is_file():
            return candidate
    return PLUGIN_CANDIDATES[0]


OLD_METHOD = """\tasync list(limit, options = {}) {
\t\tawait this.ensureInitialized();
\t\tlet query = this.table.query().select([
\t\t\t"id",
\t\t\t"text",
\t\t\t"importance",
\t\t\t"category",
\t\t\t"createdAt"
\t\t]);
\t\tif (!options.orderByCreatedAt && limit !== void 0) query = query.limit(limit);
\t\tconst entries = (await query.toArray()).map((row) => ({
\t\t\tid: row.id,
\t\t\ttext: row.text,
\t\t\timportance: row.importance,
\t\t\tcategory: row.category,
\t\t\tcreatedAt: row.createdAt
\t\t}));
\t\tif (options.orderByCreatedAt) entries.sort((a, b) => b.createdAt - a.createdAt);
\t\treturn limit === void 0 ? entries : entries.slice(0, limit);
\t}
"""

NEW_METHOD = """\tasync list(limit, options = {}) {
\t\tawait this.ensureInitialized();
\t\tlet query = this.table.query().select([
\t\t\t"id",
\t\t\t"text",
\t\t\t"importance",
\t\t\t"category",
\t\t\t"createdAt"
\t\t]);
\t\tif (!options.orderByCreatedAt && limit !== void 0) query = query.limit(limit);
\t\tconst entries = (await query.toArray()).map((row) => ({
\t\t\tid: row.id,
\t\t\ttext: row.text,
\t\t\timportance: row.importance,
\t\t\tcategory: row.category,
\t\t\tcreatedAt: row.createdAt
\t\t}));
\t\tif (options.orderByCreatedAt) entries.sort((a, b) => b.createdAt - a.createdAt);
\t\treturn limit === void 0 ? entries : entries.slice(0, limit);
\t}
\tasync textSearch(queryText, limit = 5) {
\t\tconst normalizedQuery = String(queryText || "").toLowerCase().replace(/\\s+/g, " ").trim();
\t\tconst terms = Array.from(new Set(normalizedQuery.split(/[\\s,，。;；:：/\\\\|()[\\]{}<>]+/u).filter((term) => term.length >= 2)));
\t\tconst cjkTerms = Array.from(new Set((normalizedQuery.match(/[\\p{Script=Han}\\p{Script=Katakana}\\p{Script=Hiragana}A-Za-z0-9][\\p{Script=Han}\\p{Script=Katakana}\\p{Script=Hiragana}A-Za-z0-9_-]{1,}/gu) || []).map((term) => term.toLowerCase())));
\t\tconst needles = Array.from(new Set([...terms, ...cjkTerms])).slice(0, 20);
\t\tconst entries = await this.list(void 0, { orderByCreatedAt: true });
\t\tconst scored = entries.map((entry) => {
\t\t\tconst text = String(entry.text || "").toLowerCase();
\t\t\tlet score = normalizedQuery && text.includes(normalizedQuery) ? 1 : 0;
\t\t\tfor (const term of needles) if (text.includes(term)) score += .2;
\t\t\tif (/小红书|小紅書|xhs|costco|frutteto|投稿/i.test(entry.text || "") && /小红书|小紅書|xhs|costco|frutteto|投稿/i.test(queryText || "")) score += .4;
\t\t\treturn { entry, score: Math.min(1, score) };
\t\t}).filter((item) => item.score > 0);
\t\tscored.sort((a, b) => b.score - a.score || (b.entry.createdAt || 0) - (a.entry.createdAt || 0));
\t\treturn scored.slice(0, limit).map((item) => ({
\t\t\tentry: {
\t\t\t\tid: item.entry.id,
\t\t\t\ttext: item.entry.text,
\t\t\t\tvector: item.entry.vector,
\t\t\t\timportance: item.entry.importance,
\t\t\t\tcategory: item.entry.category,
\t\t\t\tcreatedAt: item.entry.createdAt
\t\t\t},
\t\t\tscore: item.score
\t\t}));
\t}
"""

OLD_CLI_SEARCH = """\t\t\tmemory.command("search").description("Search memories").argument("<query>", "Search query").option("--limit <n>", "Max results", "5").action(async (query, opts) => {
\t\t\t\tconst vector = await embeddings.embed(normalizeRecallQuery(query, cfg.recallMaxChars));
\t\t\t\tconst output = (await db.search(vector, Number.parseInt(opts.limit, 10), .3)).map((r) => ({
\t\t\t\t\tid: r.entry.id,
\t\t\t\t\ttext: r.entry.text,
\t\t\t\t\tcategory: r.entry.category,
\t\t\t\t\timportance: r.entry.importance,
\t\t\t\t\tscore: r.score
\t\t\t\t}));
\t\t\t\tconsole.log(JSON.stringify(output, null, 2));
\t\t\t});
"""

NEW_CLI_SEARCH = """\t\t\tmemory.command("search").description("Search memories").argument("<query>", "Search query").option("--limit <n>", "Max results", "5").action(async (query, opts) => {
\t\t\t\tconst limit = Number.parseInt(opts.limit, 10);
\t\t\t\tlet results;
\t\t\t\ttry {
\t\t\t\t\tconst vector = await embeddings.embed(normalizeRecallQuery(query, cfg.recallMaxChars));
\t\t\t\t\tresults = await db.search(vector, limit, .3);
\t\t\t\t} catch (err) {
\t\t\t\t\tconsole.error(`memory-lancedb: vector search failed, using text fallback: ${String(err)}`);
\t\t\t\t\tresults = await db.textSearch(query, limit);
\t\t\t\t}
\t\t\t\tconst output = results.map((r) => ({
\t\t\t\t\tid: r.entry.id,
\t\t\t\t\ttext: r.entry.text,
\t\t\t\t\tcategory: r.entry.category,
\t\t\t\t\timportance: r.entry.importance,
\t\t\t\t\tscore: r.score
\t\t\t\t}));
\t\t\t\tconsole.log(JSON.stringify(output, null, 2));
\t\t\t});
"""

OLD_RECALL_FRAGMENT = """\t\t\t\tconst recall = await runWithTimeout({
\t\t\t\t\ttimeoutMs: DEFAULT_AUTO_RECALL_TIMEOUT_MS,
\t\t\t\t\ttask: async () => {
\t\t\t\t\t\tconst vector = await embeddings.embed(recallQuery, { timeoutMs: DEFAULT_AUTO_RECALL_TIMEOUT_MS });
\t\t\t\t\t\treturn await db.search(vector, 3, .3);
\t\t\t\t\t}
\t\t\t\t});
"""

NEW_RECALL_FRAGMENT = """\t\t\t\tconst recall = await runWithTimeout({
\t\t\t\t\ttimeoutMs: DEFAULT_AUTO_RECALL_TIMEOUT_MS,
\t\t\t\t\ttask: async () => {
\t\t\t\t\t\ttry {
\t\t\t\t\t\t\tconst vector = await embeddings.embed(recallQuery, { timeoutMs: DEFAULT_AUTO_RECALL_TIMEOUT_MS });
\t\t\t\t\t\t\treturn await db.search(vector, 3, .3);
\t\t\t\t\t\t} catch (err) {
\t\t\t\t\t\t\tapi.logger.warn?.(`memory-lancedb: vector recall failed, using text fallback: ${String(err)}`);
\t\t\t\t\t\t\treturn await db.textSearch(recallQuery, 3);
\t\t\t\t\t\t}
\t\t\t\t\t}
\t\t\t\t});
"""


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    if old not in text:
        raise SystemExit(f"expected block not found for {label}; plugin layout changed")
    return text.replace(old, new, 1)


def main() -> int:
    plugin = plugin_path()
    if not plugin.is_file():
        raise SystemExit(f"plugin not found: {plugin}")
    text = plugin.read_text(encoding="utf-8")
    original = text
    text = replace_once(text, OLD_METHOD, NEW_METHOD, "textSearch method")
    text = replace_once(text, OLD_CLI_SEARCH, NEW_CLI_SEARCH, "cli search fallback")
    text = replace_once(text, OLD_RECALL_FRAGMENT, NEW_RECALL_FRAGMENT, "auto recall fallback")
    if text == original:
        print("already patched")
        return 0
    backup = plugin.with_name(f"{plugin.name}.bak-memory-text-fallback-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
    shutil.copy2(plugin, backup)
    plugin.write_text(text, encoding="utf-8")
    print(str(backup))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
