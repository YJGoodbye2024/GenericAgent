from __future__ import annotations


class SceneBroker:
    def __init__(self, state: dict):
        self.state = state

    def observe(self, focus: str | None = None) -> dict:
        raise NotImplementedError

    def act(self, action: str, args: dict | None = None) -> dict:
        raise NotImplementedError

    def log(self, kind: str, payload: dict) -> None:
        self.state.setdefault("log", []).append({"kind": kind, **payload})
