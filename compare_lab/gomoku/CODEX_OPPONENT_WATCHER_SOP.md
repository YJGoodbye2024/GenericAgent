# Codex Gomoku Opponent Watcher SOP

本 SOP 供 Codex 启动的对手 subagent 使用。目标是让 subagent 持续轮询指定 side 的 gomoku mailbox，并在出现新请求时自动写回下一手棋。

## 目标

- 你只服务一个固定 side：`generic` 或 `lin_daiyu`
- 你不是裁判，不维护棋盘真相；你只读取 request，基于其中的 `prompt` 下子
- 你要持续运行，直到主 agent 明确发出停止指令

## 必须遵守的规则

1. 只处理你被分配的 side 目录
2. 永远优先处理最早的 pending request
3. 如果同名 reply 已存在，则跳过该 request
4. 回复必须只写一个 JSON 文件到 `replies/<request_id>.json`
5. JSON 结构固定：

```json
{"coord":"H8","summary":"一句短理由"}
```

6. 不要写 markdown，不要写代码块，不要写解释性前后文
7. 不要自己发明 `row/col`，统一只回复人类坐标 `coord`
8. 如果你拿不准，也必须给出一个合法且努力求胜的坐标；不要挂机等待

## 每次处理一个 request 的流程

1. 列出 `requests/*.json`
2. 去掉那些已经在 `replies/` 中存在同名 reply 的 request
3. 选字典序最小的那个 request
4. 读出其中：
   - `request_id`
   - `prompt`
   - `reply_path`
   - `watcher_contract`
5. 根据 `prompt` 下子
6. 只生成：

```json
{"coord":"H8","summary":"一句短理由"}
```

7. 先写到临时文件，再原子重命名为正式 reply 文件
8. 继续轮询下一条 request

## 轮询节奏

- 正常情况下每 1 秒轮询一次
- 若连续 30 秒没有新 request，也不要退出；继续等待
- 只有在主 agent 明确说“停止 watcher”时才结束

## 合法性与职责边界

- 你不需要自己判断最终是否合法落子；主 bridge 会二次校验
- 但你应该尽量避免明显非法的点，例如已经被棋盘占据的位置
- 如果主 agent发来 repair 请求，优先处理 repair，并只回复一个新的 `coord + summary`

## 建议的启动指令

主 agent 给 watcher subagent 的启动消息应该类似：

```text
你现在是 gomoku opponent watcher，只服务 side=generic。
请严格按 compare_lab/gomoku/CODEX_OPPONENT_WATCHER_SOP.md 持续轮询：
compare_lab/runs/<run_id>/opponent_mailbox/generic/requests
并把 reply 写到：
compare_lab/runs/<run_id>/opponent_mailbox/generic/replies
除非我明确叫停，否则不要结束。
```
