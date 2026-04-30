from __future__ import annotations

from compare_lab.referees.base import SceneBroker


class WerewolfBroker(SceneBroker):
    def observe(self, focus: str | None = None) -> dict:
        world = self.state["world"]
        return {
            "status": "success",
            "kind": "werewolf",
            "phase": world.get("phase", "day"),
            "self_role": world.get("self_role", "villager"),
            "alive": world.get("alive", []),
            "public_log": world.get("public_log", []),
            "notes": world.get("notes", []),
            "focus": focus,
        }

    def act(self, action: str, args: dict | None = None) -> dict:
        args = args or {}
        world = self.state["world"]
        if action == "speak":
            text = args.get("text", "").strip()
            if not text:
                return {"status": "error", "msg": "speak 需要 text。"}
            world.setdefault("public_log", []).append({"speaker": "self", "text": text})
            self.log("speak", {"text": text})
            return {"status": "success", "msg": "发言已记录。"}
        if action == "vote":
            target = args.get("target")
            if target not in world.get("alive", []):
                return {"status": "error", "msg": f"{target} 不在存活名单中。"}
            world["last_vote"] = target
            self.log("vote", {"target": target})
            return {"status": "success", "msg": f"已记录投票给 {target}。", "alive": world.get("alive", [])}
        return {"status": "error", "msg": f"未知动作: {action}"}
