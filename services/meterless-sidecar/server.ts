// Node sidecar: exposes the real H-MEM reference over a small local HTTP API.
// Hypothesis ledger = H-MEM records; trust = source + confidence on every write.
import http from "node:http";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const { HMEM } = await import(pathToFileURL(path.join(here, "vendor/hmem/src/index.ts")).href);
const hmem = new HMEM({ persistDir: process.env.SIDECAR_STATE ?? path.join(here, ".state") });
const PORT = Number(process.env.SIDECAR_PORT ?? 8100);

const body = (req: http.IncomingMessage) =>
  new Promise<any>((ok) => {
    let s = "";
    req.on("data", (c) => (s += c));
    req.on("end", () => ok(s ? JSON.parse(s) : {}));
  });
const send = (res: http.ServerResponse, code: number, obj: unknown) => {
  res.writeHead(code, { "content-type": "application/json" });
  res.end(JSON.stringify(obj));
};

http
  .createServer(async (req, res) => {
    const url = new URL(req.url ?? "/", "http://x");
    try {
      if (req.method === "GET" && url.pathname === "/healthz") return send(res, 200, { ok: true, engine: "hmem" });
      if (req.method === "POST" && url.pathname === "/ledger/hypotheses") {
        const b = await body(req);
        const rec = hmem.add({
          content: JSON.stringify(b.hypothesis),
          type: "general",
          tags: ["hypothesis", `equipment:${b.equipment}`, `status:${b.hypothesis.status}`],
          source: b.source,
          confidence: b.confidence,
        });
        return send(res, 200, { id: rec.id, source: rec.source, confidence: rec.confidence });
      }
      if (req.method === "GET" && url.pathname === "/ledger/hypotheses") {
        const eq = url.searchParams.get("equipment");
        const rows = hmem.store
          .all()
          .filter((r: any) => r.tags.includes("hypothesis") && (!eq || r.tags.includes(`equipment:${eq}`)))
          .map((r: any) => ({ id: r.id, source: r.source, confidence: r.confidence, hypothesis: JSON.parse(r.content) }));
        return send(res, 200, { hypotheses: rows });
      }
      if (req.method === "POST" && url.pathname === "/ledger/reset") {
        const b = await body(req);
        let n = 0;
        for (const r of hmem.store.all()) {
          if (r.tags.includes("hypothesis") && r.tags.includes(`equipment:${b.equipment}`)) { hmem.store.delete(r.id, "demo reset"); n++; }
        }
        return send(res, 200, { deleted: n });
      }
      send(res, 404, { error: "not found" });
    } catch (e: any) {
      send(res, 500, { error: String(e?.message ?? e) });
    }
  })
  .listen(PORT, "127.0.0.1", () => console.log(`sidecar on 127.0.0.1:${PORT} (H-MEM reference)`));
