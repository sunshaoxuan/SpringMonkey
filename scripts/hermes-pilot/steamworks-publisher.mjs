import { createServer } from "node:http";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";
import { z } from "zod";
import { register as registerBuilds } from "./dist/tools/getAppBuilds.js";
import { register as registerBetas } from "./dist/tools/getAppBetas.js";

const APP_ID = 4417110;
const HOST = "hermes-steamworks-mcp";
const BIND = "172.18.254.14";

let credential = "";
for await (const chunk of process.stdin) {
  credential += chunk.toString("ascii");
  if (credential.length >= 32) break;
}
if (!/^[A-Fa-f0-9]{32}$/.test(credential)) throw Error("Publisher credential unavailable");
process.env.STEAM_API_KEY = credential;
credential = "";

function scopedServer() {
  const server = new McpServer({ name: "springmonkey-steamworks", version: "1.0.0" });
  const allowlist = new Set(["steam_getAppBuilds", "steam_getAppBetas"]);
  const scoped = {
    registerTool(name, definition, handler) {
      if (!allowlist.delete(name)) throw Error("Unexpected publisher method");
      server.registerTool(name, {
        ...definition,
        inputSchema: { ...definition.inputSchema, appid: z.literal(APP_ID) },
      }, async (args, extra) => {
        const result = await handler(args, extra);
        if (!result.isError) return result;
        return { isError: true, content: [{ type: "text", text: "Valve publisher query failed" }] };
      });
    },
  };
  registerBuilds(scoped);
  registerBetas(scoped);
  return server;
}

const http = createServer(async (req, res) => {
  if (req.headers.host?.split(":")[0] !== HOST) {
    res.writeHead(403).end();
    return;
  }
  if (req.url === "/healthz" && req.method === "GET") {
    res.writeHead(200, { "Content-Type": "application/json" }).end('{"ok":true}');
    return;
  }
  if (req.url !== "/mcp" || req.method !== "POST") {
    res.writeHead(req.url === "/mcp" ? 405 : 404).end();
    return;
  }
  const chunks = [];
  let size = 0;
  try {
    for await (const chunk of req) {
      size += chunk.length;
      if (size > 8192) {
        res.writeHead(413).end();
        return;
      }
      chunks.push(chunk);
    }
    const body = JSON.parse(Buffer.concat(chunks).toString("utf8"));
    const server = scopedServer();
    const transport = new StreamableHTTPServerTransport({ sessionIdGenerator: undefined });
    res.once("close", () => { void server.close(); });
    await server.connect(transport);
    await transport.handleRequest(req, res, body);
  } catch {
    if (!res.headersSent) res.writeHead(400).end();
  }
});
http.listen(3000, BIND, () => console.error("Steamworks read-only publisher service ready"));
