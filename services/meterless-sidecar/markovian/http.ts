// Meterless Markovian (the vendored reference implementation) driven step by step over HTTP.
// The engine owns the chain: mode prompts, the marker protocol, the carryover compression cascade, chunk accounting
// and run history. The host (INVERSE, in Python) owns the model calls, so every generation still goes through
// Nightshift. Protocol: POST /markovian/start returns the first prompt; the host answers with POST /markovian/step
// {run_id, text, usage}; each step returns the next prompt or the finished run. Local only; no outbound requests.
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));

type Deferred<T> = { promise: Promise<T>; resolve: (v: T) => void; reject: (e: unknown) => void };
function deferred<T>(): Deferred<T> {
  let resolve!: (v: T) => void, reject!: (e: unknown) => void;
  const promise = new Promise<T>((a, b) => { resolve = a; reject = b; });
  return { promise, resolve, reject };
}

type Pending = { prompt: string; step: number; reply: Deferred<string> };
type RunState = {
  id: string; goal: string; started: number; steps: number; carryover: string;
  waiting?: Pending; next: Deferred<Pending | null>; result?: any; error?: string;
  measured: { prompt_tokens: number; completion_tokens: number; calls: number };
};

export async function makeMarkovian(stateDir: string): Promise<MarkovianHost> {
  const mod = await import(pathToFileURL(path.join(here, "..", "vendor", "markovian", "src", "index.ts")).href);
  return new MarkovianHost(mod, stateDir);
}

export class MarkovianHost {
  readonly runs = new Map<string, RunState>();
  private seq = 0;
  constructor(private readonly mod: any, private readonly stateDir: string) {}

  /** POST /markovian/start {goal, mode?, chunkConfig?, memoryContext?, attachments?} -> first prompt. */
  async start(b: any) {
    const goal = String(b?.goal ?? "").trim();
    if (!goal) throw new Error("goal is required");
    const id = `mk-${Date.now().toString(36)}-${++this.seq}`;
    const engine = new this.mod.Markovian({ chunkConfig: b.chunkConfig ?? {}, historyDir: path.join(this.stateDir, "markovian") });   // may throw: nothing registered yet
    const st: RunState = { id, goal, started: Date.now(), steps: 0, carryover: "", next: deferred(), measured: { prompt_tokens: 0, completion_tokens: 0, calls: 0 } };
    this.runs.set(id, st);
    const generator = async (prompt: string) => {
      const p: Pending = { prompt, step: st.steps + 1, reply: deferred<string>() };
      st.waiting = p;
      st.next.resolve(p);                           // hand the prompt to the request waiting on /start or /step
      const text = await p.reply.promise;           // the host's model output arrives through /step
      st.steps += 1;
      st.waiting = undefined;
      return { text };
    };
    engine
      .run({ goal, mode: b.mode ?? "RESEARCH", memoryContext: b.memoryContext || undefined, attachments: b.attachments ?? [], generator, reflect: false })
      .then((run: any) => { st.result = run; st.next.resolve(null); })
      .catch((e: any) => { st.error = String(e?.message ?? e); st.next.resolve(null); });
    return this.wait(st);
  }

  /** POST /markovian/step {run_id, text, usage?} -> next prompt, or the finished run. */
  async step(b: any) {
    const st = this.runs.get(String(b?.run_id ?? ""));
    if (!st) throw new Error("unknown run");
    if (!st.waiting) throw new Error("run is not waiting for a reply");
    if (b.usage) {
      st.measured.prompt_tokens += Number(b.usage.prompt_tokens ?? 0);
      st.measured.completion_tokens += Number(b.usage.completion_tokens ?? 0);
      st.measured.calls += 1;
    }
    st.next = deferred();                           // the generator's next call resolves this one
    st.waiting.reply.resolve(String(b.text ?? ""));
    return this.wait(st);
  }

  /** POST /markovian/abandon {run_id}: finish a chain the host gave up on, so nothing leaks. */
  abandon(b: any) {
    const st = this.runs.get(String(b?.run_id ?? ""));
    if (!st) return { ok: false };
    st.waiting?.reply.resolve("[TASK_COMPLETE]");
    this.runs.delete(st.id);
    return { ok: true };
  }

  health() {
    return { ok: true, engine: "markovian", source: "vendor/markovian (Meterless reference)", active_runs: this.runs.size };
  }

  private async wait(st: RunState) {
    const p = await st.next.promise;
    if (p) {
      st.carryover = carryoverOf(p.prompt);
      return { run_id: st.id, done: false, step: p.step, prompt: p.prompt, carryover: st.carryover };
    }
    this.runs.delete(st.id);
    const run = st.result;
    if (!run) throw new Error(st.error ?? "run failed");
    return {
      run_id: st.id, done: true, status: run.status, output: run.output,
      chunks: run.chunks.map((c: any) => ({ id: c.id, tokens_estimated: c.tokens, carryover_in: c.carryover, content: c.content })),
      estimated: { tokens_used: run.totalTokensUsed, tokens_saved: run.totalTokensSaved, efficiency_percent: run.efficiencyPercent, label: run.tokenLabel },
      measured: st.measured, chunk_config: run.chunkConfig, duration_ms: Date.now() - st.started, error: run.error,
    };
  }
}

function carryoverOf(prompt: string): string {
  const m = prompt.match(/\[CARRYOVER STATE\]\n([\s\S]*?)(?:\n\n|$)/);
  return m ? m[1].trim() : "";
}

/** Returns [status, json] for /markovian/* routes, or undefined when the path is not ours. */
export async function handleMarkovian(host: MarkovianHost, method: string, pathname: string, body: any): Promise<[number, unknown] | undefined> {
  if (!pathname.startsWith("/markovian/")) return undefined;
  if (method === "GET" && pathname === "/markovian/healthz") return [200, host.health()];
  if (method !== "POST") return [404, { error: "not found" }];
  try {
    if (pathname === "/markovian/start") return [200, await host.start(body)];
    if (pathname === "/markovian/step") return [200, await host.step(body)];
    if (pathname === "/markovian/abandon") return [200, host.abandon(body)];
  } catch (e: any) {
    return [400, { error: String(e?.message ?? e) }];
  }
  return [404, { error: "not found" }];
}
