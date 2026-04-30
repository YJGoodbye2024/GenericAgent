# Compare Lab

`compare_lab/` 是 `GenericAgent/` 与 `GenericAgent_LDY/` 的对比实验框架。

## 设计原则

- 两个 agent 都按各自原生目录运行。
- 每次实验会复制出两个 agent 副本，并在副本内累积 memory。
- 世界探索与五子棋由外部 referee 维护状态。
- 工具探针与狼人杀用原生 prompt probe。
- 报告是质性分析，不做总分。
- 五子棋对手默认走 `mykey.py` 配置的模型后端；若由 Codex 亲自编排，也可切到 `external` 邮箱后端，让两个 subagent 作为对手。

## 目录

- `runner.py`：复制 agent、副本内运行、场景驱动
- `referees/`：世界与狼人杀裁判
- `gomoku/`：五子棋专项代码，含 live runner、对手 client、裁判
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

重生成报告：

```bash
python -m compare_lab report --run-id smoke
```

运行五子棋 live 对比：

```bash
python -m compare_lab gomoku-live --run-id gomoku-001 --agent-llm-no 2 --port 8765
```

若要让对手改走外部邮箱协议（供 Codex 用 2 个 subagent 接管）：

```bash
python -m compare_lab gomoku-live --run-id gomoku-subagent --agent-llm-no 2 --port 8765 --opponent-backend external
```

此时对手请求会写到：

```text
compare_lab/runs/<run_id>/opponent_mailbox/<side_id>/requests/
compare_lab/runs/<run_id>/opponent_mailbox/<side_id>/replies/
```

外部对手只需为每个请求写一个 JSON 回复：

```json
{"row":7,"col":7,"summary":"take central influence first"}
```

比赛进行时打开：

```text
http://127.0.0.1:8765/
```

比赛结束后，静态回放页保存在：

```text
compare_lab/runs/<run_id>/web/index.html
```
