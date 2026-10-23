"""obs-service: serves deterministic synthetic sensor data as REST JSON for Zetaris."""
import numpy as np
from fastapi import FastAPI

app = FastAPI(title="obs-service")


def _oscillator(c, seed, n=400, dt=0.01, m=1.0, k=100.0, noise=0.01):
    rng = np.random.default_rng(seed)
    x, v = 1.0, 0.0
    rows = []
    for i in range(n):
        rows.append({"t": round(i * dt, 4), "x": float(x + rng.normal(0, noise)), "v": float(v)})
        a = -(c * v + k * x) / m
        v += a * dt
        x += v * dt
    return rows


DATASETS = {
    "p104-baseline": lambda: _oscillator(c=2.0, seed=1),
    "p104-current": lambda: _oscillator(c=2.8, seed=2),
}


@app.get("/datasets/{dataset_id}/samples")
def samples(dataset_id: str):
    return {"dataset_id": dataset_id, "samples": DATASETS[dataset_id]()}


@app.get("/healthz")
def healthz():
    return {"ok": True}
