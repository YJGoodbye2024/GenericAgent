# Watcher Contract

`ExternalMailboxGomokuOpponent` 写出的每个 request JSON，都会包含这些供 watcher 使用的字段：

- `request_id`
- `prompt`
- `reply_path`
- `request_path`
- `watcher_contract`

其中 `watcher_contract` 的语义固定为：

- `mode = codex_watcher_loop`
- `side_id`：当前 watcher 只允许处理的 side
- `request_glob`：要轮询的 request 通配路径
- `reply_dir`：reply 输出目录
- `reply_format`：固定为 `{"coord":"H8","summary":"..."}`，由主 bridge 再转成内部结构
- `atomic_write_required = true`
- `poll_seconds = 1.0`
- `process_oldest_first = true`
- `ignore_if_reply_exists = true`

这个 contract 的目的不是给 runner 读取，而是给 watcher subagent 一个机器可见、文件内自解释的约束。
