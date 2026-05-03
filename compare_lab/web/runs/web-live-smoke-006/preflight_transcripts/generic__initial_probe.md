# GenericAgent / initial_probe

## Prompt

请立刻使用浏览器工具确认当前是否有可用网页标签。若能看到页面，请只用一两句话告诉我当前页标题和 URL；若失败，也如实说出错误。

## Response

LLM Running (Turn 1) ...

🛠️ web_scan({"tabs_only": true})


LLM Running (Turn 2) ...

<summary>浏览器无标签页，需排查原因</summary>



当前**没有可用的浏览器标签页**——调用 web_scan 返回错误 "没有可用的浏览器标签页"。

这可能是因为浏览器实例尚未启动或已关闭。请确认您是否需要我先打开一个浏览器标签页？如果需要，请告诉我目标 URL 或搜索关键词，我会立即启动浏览器并导航。

