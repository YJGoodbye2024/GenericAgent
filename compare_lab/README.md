# Compare Lab

`compare_lab/` 是 `GenericAgent/` 与 `GenericAgent_LDY/` 的对比实验框架。

## 设计原则

- 两个 agent 都按各自原生目录运行。
- 每次实验会复制出两个 agent 副本，并在副本内累积 memory。
- 世界探索与五子棋由外部 referee 维护状态。
- 工具探针与狼人杀用原生 prompt probe。
- 报告是质性分析，不做总分。
- 五子棋默认配置是：agent 走 `MiniMax-M2.7`，对手走 `watcher_api`，即 **本地自动 watcher + API 模型对手**。
- 五子棋的 preflight、debug、smoke 和正式赛都必须在**沙盒外**运行；当前沙盒内无法可靠访问本地代理与外网，容易把模型通信问题误判成棋局逻辑问题。

## 目录

- `runner.py`：复制 agent、副本内运行、场景驱动
- `referees/`：世界与狼人杀裁判
- `gomoku/`：五子棋专项代码，含 live runner、对手 client、裁判
- `web/`：真网自由浏览专项代码，含 live runner 与 dashboard
- `scenarios/`：默认场景
- `report.py`：把 run 结果整理成并排报告
- `runs/`：实验输出

## 使用

运行默认套件：

```bash
python -m compare_lab run --run-id smoke --llm-no 0
```

只跑部分场景：

```bash
python -m compare_lab run --run-id smoke-mini --llm-no 0 --only repo_memory_probe,file_world_intro
```

运行工具使用过程 smoke：

```bash
python -m compare_lab run --run-id tool-smoke --llm-no 0 --suite compare_lab/scenarios/suite_tool_use_smoke.json
```

重生成报告：

```bash
python -m compare_lab report --run-id smoke
```

运行五子棋 live 对比（默认：agent=`MiniMax-M2.7`，opponent=`watcher_api` = 本地自动 watcher + API 模型对手）：

```bash
python -m compare_lab gomoku-live --run-id gomoku-001 --port 8765
```

当前五子棋协议里，agent 只需要输出人类坐标（如 `H8`）和一句短理由；裁判层会统一把该坐标转换成内部 `row/col`。

`watcher_api` 对手也吃同一份棋局 prompt；本地 watcher 会把 API 模型返回的坐标与短理由写入 mailbox reply JSON。reply JSON 可以直接给 `row/col`，也可以给 `coord`。

若要显式写出同样的默认行为：

```bash
python -m compare_lab gomoku-live --run-id gomoku-localwatch --agent-llm-no 1 --port 8765 --opponent-backend watcher_api
```

此时对手请求会写到：

```text
compare_lab/runs/<run_id>/opponent_mailbox/<side_id>/requests/
compare_lab/runs/<run_id>/opponent_mailbox/<side_id>/replies/
```

本地 watcher 会为每个请求写一个 JSON 回复：

```json
{"row":7,"col":7,"summary":"take central influence first"}
```

也接受这种形式：

```json
{"coord":"H8","summary":"take center"}
```

比赛进行时打开：

```text
http://127.0.0.1:8765/
```

比赛结束后，静态回放页保存在：

```text
compare_lab/runs/<run_id>/web/index.html
```

`watcher_api` 表示 **本地自动 watcher + API 模型对手**。如果你想由 Codex 亲自桥接两个对手邮箱，则改用 `--opponent-backend external`。

## 真网自由浏览 live 对比

这条实验用于比较 `GenericAgent` 与 `GenericAgent_LDY` 在真实互联网中的自然行为差异。它会：

- 复制两份 agent 副本
- 为两边各起一套**独立**的浏览器 bridge 与新浏览器 profile
- 给两边同一条极轻起始提示
- 连续运行固定时长，并实时记录浏览行为、事件流与 memory 写入
- 导出一个可离线打开的静态回放页

必须在**沙盒外**运行，并且需要显式指定浏览器路径，或设置环境变量：

- `COMPARE_LAB_BROWSER_BIN`
- `BROWSER_BIN`
- `CHROME_BIN`

运行示例：

```bash
python -m compare_lab web-live \
  --run-id web-live-001 \
  --llm-no 1 \
  --duration-minutes 120 \
  --port 8766 \
  --browser-bin /path/to/chrome
```

默认起始页是：

```text
https://example.com/
```

比赛进行时打开：

```text
http://127.0.0.1:8766/
```

预检现在分两层：

- **硬错误直接失败**：浏览器二进制、扩展目录、bridge 基础配置不对时，实验不会启动
- **软错误给自修窗口**：如果只是网页链路未 ready，Agent 会先获得约 10 分钟自修时间，用自己的 `code_run`、网页 SOP 和安装能力排查并修复，再重新探测

自修阶段的 transcript、记忆快照和 diff 会单独记录到 run 目录中，便于比较哪个 Agent 更会把网页能力修起来并沉淀经验。

实验结束后，静态回放页保存在：

```text
compare_lab/web/runs/<run_id>/web/index.html
```

当前实现依赖两条事实：

- `ga.py` 会从各自副本里的 `assets/tmwd_cdp_bridge/config.js` 读取 `TMWD_HOST/TMWD_PORT`
- 浏览器扩展 `background.js` 也会读取同一份配置，因此两边可以真正隔离，不共享默认 `18765` 会话池

## Codex 对手 watcher

如果希望两个 Codex 对手 subagent 持续轮询新的棋局消息并自动回子，不要只给它一句“盯住 mailbox”。应当明确按以下 SOP 启动：

- [compare_lab/gomoku/CODEX_OPPONENT_WATCHER_SOP.md](/fudan_university_cfs/yj/GenericAgent_dev/compare_lab/gomoku/CODEX_OPPONENT_WATCHER_SOP.md)
- [compare_lab/gomoku/watcher_contract.md](/fudan_university_cfs/yj/GenericAgent_dev/compare_lab/gomoku/watcher_contract.md)

每个 request JSON 里都包含：

- `request_path`
- `reply_path`
- `watcher_contract`

推荐方式：

- 一个 watcher subagent 只服务 `generic`
- 一个 watcher subagent 只服务 `lin_daiyu`
- 都持续轮询各自 `requests/`
- 都只写 `{"coord":"H8","summary":"一句短理由"}` 到对应 `replies/`

如果 watcher 仍不稳定，主 Codex 可以退回同步 bridge 模式，逐条处理 request。
