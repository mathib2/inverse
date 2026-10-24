// Node sidecar: exposes the real H-MEM reference over a small local HTTP API.
// Hypothesis ledger = H-MEM records; trust = source + confidence on every write.
import http from "node:http";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const { HMEM } = await import(pathToFileURL(path.join(here, "vendor/hmem/src/index.ts")).href);
const { WorldModel } = await import(pathToFileURL(path.join(here, "vendor/world-model/src/index.ts")).href);
const STATE = process.env.SIDECAR_STATE ?? path.join(here, ".state");
const world = new WorldModel({ namespace: "inverse", storage: "file", directory: path.join(STATE, "world") });
const hmem = new HMEM({ persistDir: STATE });
const PORT = Number(process.env.SIDECAR_PORT ?? 8100);

const body = (req: http.IncomingMessage) =>
  new Promise<any>((ok, fail) => {
    let s = "";
    req.on("data", (c) => (s += c));
    req.on("error", fail);
    req.on("end", () => {
      try { ok(s ? JSON.parse(s) : {}); }
      catch (e: any) { fail(Object.assign(new Error(`bad JSON body: ${e?.message ?? e}`), { status: 400 })); }   // a bad body is a 400 for that request, not a crash
    });
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
      // ---- World Model: shared entities (equipment, dataset, hypothesis, validator_result) with stable IDs
      if (req.method === "POST" && url.pathname === "/world/record") {
        const b = await body(req);
        const src = { kind: "validator", at: b.at, by: "inverse", runId: b.run_id };
        const ext = (type: string, id: string) => ({ system: "inverse", id });
        const eq = await world.upsertEntity({ type: "equipment", externalKey: ext("equipment", b.equipment), name: b.equipment, attrs: {}, source: src });
        const ds = await world.upsertEntity({ type: "dataset", externalKey: ext("dataset", b.dataset), name: b.dataset, attrs: {}, source: src });
        const hkey = `${b.equipment}|${b.hypothesis.form}`;
        const h = await world.upsertEntity({ type: "hypothesis", externalKey: ext("hypothesis", hkey), name: b.hypothesis.form, attrs: { equipment: b.equipment, status: b.hypothesis.status, source: b.source }, source: src });
        await world.relate({ from: h.id, to: eq.id, type: "describes", source: src });
        await world.relate({ from: h.id, to: ds.id, type: "tested_on", source: src });
        for (const v of b.validator_results ?? []) {
          const r = await world.upsertEntity({ type: "validator_result", externalKey: ext("validator_result", `${hkey}|${v.validator}`), name: `${v.validator}`, attrs: { validator: v.validator, passed: v.passed, evidence: v.evidence, hypothesis: h.id }, source: src });
          await world.relate({ from: h.id, to: r.id, type: `result_${v.validator}`, source: src });
        }
        return send(res, 200, { hypothesis_id: h.id, entities: world.view("graph").query({}).length });
      }
      if (req.method === "GET" && url.pathname === "/world/summary") {
        const eq = url.searchParams.get("equipment");
        const g = world.view("graph");
        const hyps = g.query({ type: "hypothesis" }).filter((e: any) => !eq || e.attrs.equipment === eq);
        const out = hyps.map((h: any) => ({
          id: h.id, form: h.name, status: h.attrs.status, source: h.attrs.source,
          results: g.neighborsOf(h.id).filter((r: any) => r.type === "validator_result").map((r: any) => ({ validator: r.attrs.validator, passed: r.attrs.passed, evidence: r.attrs.evidence })),
        }));
        return send(res, 200, { hypotheses: out, entities: g.query({}).length, events: world.events().length });
      }
      send(res, 404, { error: "not found" });
    } catch (e: any) {
      send(res, e?.status ?? 500, { error: String(e?.message ?? e) });                     // a bad request is 400; an engine error is 500; the process lives on
    }
  })
  .listen(PORT, "127.0.0.1", () => console.log(`sidecar on 127.0.0.1:${PORT} (H-MEM reference)`));
