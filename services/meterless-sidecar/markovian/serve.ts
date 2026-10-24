// Stand-alone Markovian service: the vendored Meterless reference engine behind /markovian/* on its own port, so it can
// run next to the H-MEM/World Model sidecar without touching it. Local only. Start: npx tsx markovian/serve.ts
import http from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { makeMarkovian, handleMarkovian } from "./http.ts";

const here = path.dirname(fileURLToPath(import.meta.url));
const STATE = process.env.SIDECAR_STATE ?? path.join(here, "..", ".state");
const PORT = Number(process.env.MARKOVIAN_PORT ?? 8101);
const host = await makeMarkovian(STATE);

const body = (req: http.IncomingMessage) =>
  new Promise<any>((ok) => {
    let s = "";
    req.on("data", (c) => (s += c));
    req.on("end", () => ok(s ? JSON.parse(s) : {}));
  });

http
  .createServer(async (req, res) => {
    const url = new URL(req.url ?? "/", "http://x");
    let r: [number, unknown] | undefined;
    try {
      if (req.method === "GET" && url.pathname === "/healthz") r = [200, host.health()];
      else r = await handleMarkovian(host, req.method ?? "GET", url.pathname, req.method === "POST" ? await body(req) : {});
    } catch (e: any) {
      r = [500, { error: String(e?.message ?? e) }];
    }
    res.writeHead(r ? r[0] : 404, { "content-type": "application/json" });
    res.end(JSON.stringify(r ? r[1] : { error: "not found" }));
  })
  .listen(PORT, "127.0.0.1", () => console.log(`markovian on 127.0.0.1:${PORT} (Meterless reference, vendored)`));
