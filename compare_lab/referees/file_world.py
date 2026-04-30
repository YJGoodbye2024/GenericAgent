from __future__ import annotations

from compare_lab.referees.base import SceneBroker


class FileWorldBroker(SceneBroker):
    def _room(self) -> dict:
        room_id = self.state["world"]["current_room"]
        return self.state["world"]["rooms"][room_id]

    def observe(self, focus: str | None = None) -> dict:
        room = self._room()
        payload = {
            "status": "success",
            "kind": "file_world",
            "room": self.state["world"]["current_room"],
            "description": room.get("description", ""),
            "items": room.get("items", []),
            "exits": room.get("exits", {}),
            "inventory": self.state["world"].get("inventory", []),
            "objective": self.state["world"].get("objective", ""),
        }
        if focus and focus in room.get("details", {}):
            payload["focus"] = {focus: room["details"][focus]}
        return payload

    def act(self, action: str, args: dict | None = None) -> dict:
        args = args or {}
        world = self.state["world"]
        room = self._room()
        parts = action.strip().split()
        verb = parts[0].lower()
        target = args.get("target") or (" ".join(parts[1:]).strip() if len(parts) > 1 else "")
        if verb in {"move", "go"}:
            dest = room.get("exits", {}).get(target)
            if not dest:
                return {"status": "error", "msg": f"没有通向 {target} 的路。"}
            world["current_room"] = dest
            self.log("move", {"to": dest})
            return {"status": "success", "msg": f"已移动到 {dest}。", "current_room": dest}
        if verb in {"inspect", "look"}:
            details = room.get("details", {})
            if target in details:
                self.log("inspect", {"target": target})
                return {"status": "success", "detail": details[target]}
            return {"status": "error", "msg": f"这里看不出 {target}。"}
        if verb in {"take", "pick"}:
            if target not in room.get("items", []):
                return {"status": "error", "msg": f"{target} 不在这里。"}
            room["items"].remove(target)
            world.setdefault("inventory", []).append(target)
            self.log("take", {"item": target})
            return {"status": "success", "msg": f"你拿起了 {target}。", "inventory": world["inventory"]}
        if verb in {"read", "open", "use"}:
            details = room.get("details", {})
            if target in details:
                self.log("use", {"target": target})
                return {"status": "success", "detail": details[target]}
            if target in world.get("inventory", []):
                inv_details = world.get("inventory_details", {})
                return {"status": "success", "detail": inv_details.get(target, f"你试了试 {target}。")}
            return {"status": "error", "msg": f"{target} 没有可用反馈。"}
        return {"status": "error", "msg": f"未知动作: {action}"}
