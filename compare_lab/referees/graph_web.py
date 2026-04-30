from __future__ import annotations

from compare_lab.referees.base import SceneBroker


class GraphWebBroker(SceneBroker):
    def _page(self) -> dict:
        return self.state["world"]["pages"][self.state["world"]["current_page"]]

    def observe(self, focus: str | None = None) -> dict:
        page = self._page()
        return {
            "status": "success",
            "kind": "graph_web",
            "page_id": self.state["world"]["current_page"],
            "title": page.get("title", ""),
            "body": page.get("body", ""),
            "links": page.get("links", []),
            "focus": focus,
        }

    def act(self, action: str, args: dict | None = None) -> dict:
        args = args or {}
        parts = action.strip().split()
        verb = parts[0].lower()
        target = args.get("target") or (" ".join(parts[1:]).strip() if len(parts) > 1 else "")
        world = self.state["world"]
        if verb in {"open", "visit"}:
            if target not in world["pages"]:
                return {"status": "error", "msg": f"没有页面 {target}"}
            world.setdefault("history", []).append(world["current_page"])
            world["current_page"] = target
            self.log("open", {"target": target})
            return {"status": "success", "msg": f"已打开 {target}", "title": self._page().get("title", "")}
        if verb == "back":
            history = world.get("history", [])
            if not history:
                return {"status": "error", "msg": "没有上一页。"}
            world["current_page"] = history.pop()
            self.log("back", {"to": world["current_page"]})
            return {"status": "success", "msg": f"已返回 {world['current_page']}"}
        if verb == "search":
            query = target.lower()
            hits = []
            for page_id, page in world["pages"].items():
                blob = " ".join([page_id, page.get("title", ""), page.get("body", ""), " ".join(page.get("tags", []))]).lower()
                score = sum(1 for tok in query.split() if tok and tok in blob)
                if score:
                    hits.append({"page_id": page_id, "title": page.get("title", ""), "score": score})
            hits.sort(key=lambda x: (-x["score"], x["page_id"]))
            self.log("search", {"query": target, "hits": [x["page_id"] for x in hits]})
            return {"status": "success", "results": hits[:8]}
        return {"status": "error", "msg": f"未知动作: {action}"}
