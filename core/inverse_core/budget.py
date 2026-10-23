"""Caps rounds, LLM calls and wall-clock per task."""
import time


class BudgetExceeded(RuntimeError):
    pass


class Budget:
    def __init__(self, max_rounds=3, max_llm_calls=10, max_seconds=420):
        self.max_rounds, self.max_llm_calls, self.max_seconds = max_rounds, max_llm_calls, max_seconds
        self.rounds = self.llm_calls = 0
        self.t0 = time.time()

    def charge_llm(self):
        self.llm_calls += 1
        self.check()

    def check(self):
        if self.llm_calls > self.max_llm_calls:
            raise BudgetExceeded(f"LLM call budget {self.max_llm_calls} exceeded")
        if time.time() - self.t0 > self.max_seconds:
            raise BudgetExceeded(f"wall-clock budget {self.max_seconds}s exceeded")
