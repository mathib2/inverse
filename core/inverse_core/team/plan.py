"""Plan: inspectable data on disk (plan.json), editable before it runs. Tasks form a DAG; delegation is by dependency."""
from __future__ import annotations

import json
import os
from dataclasses import asdict

from .expert import Task


class PlanError(ValueError):
    pass


class Plan:
    def __init__(self, goal, tasks):
        self.goal, self.tasks = goal, tasks

    @classmethod
    def from_dict(cls, d):
        keep = ("id", "goal", "expert", "depends_on")
        return cls(d["goal"], [Task(**{k: t[k] for k in keep if k in t}) for t in d["tasks"]])

    def to_dict(self):
        return {"goal": self.goal, "tasks": [asdict(t) for t in self.tasks]}

    def validate(self, expert_names):
        ids = [t.id for t in self.tasks]
        if not self.tasks:
            raise PlanError("plan has no tasks")
        if len(set(ids)) != len(ids):
            raise PlanError("duplicate task ids")
        for t in self.tasks:
            if t.expert not in expert_names:
                raise PlanError(f"task {t.id} assigned to unknown or disabled expert {t.expert!r} (known: {', '.join(sorted(expert_names))})")
            missing = [d for d in t.depends_on if d not in ids]
            if missing:
                raise PlanError(f"task {t.id} depends on unknown task(s) {missing}")
        self.order()
        return self

    def order(self):
        """Dependency order; a cycle is a PlanError."""
        done, out, left = set(), [], list(self.tasks)
        while left:
            ready = [t for t in left if all(d in done for d in t.depends_on)]
            if not ready:
                raise PlanError("dependency cycle among tasks " + ", ".join(t.id for t in left))
            for t in ready:
                out.append(t)
                done.add(t.id)
                left.remove(t)
        return out

    def save(self, directory):
        os.makedirs(directory, exist_ok=True)
        path = os.path.join(directory, "plan.json")
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=1, default=str)
        return path

    @classmethod
    def load(cls, path):
        with open(path) as f:
            return cls.from_dict(json.load(f))
