"""Interface stub for a future `software` adapter (black-box I/O traces of a program we own; never binaries)."""


class SoftwareAdapter:
    def forward_model(self, *a, **k):
        raise NotImplementedError("stretch goal: not implemented")
