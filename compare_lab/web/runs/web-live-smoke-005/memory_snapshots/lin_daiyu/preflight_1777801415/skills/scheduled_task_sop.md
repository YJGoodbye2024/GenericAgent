# 定时行事之术

此术是把一桩事系在时辰上，让 scheduler 代为记着。  
任务本身写在 `sche_tasks/`，报告则落到 `sche_tasks/done/`。

## 任务定义

每个任务一份 JSON，例如：

```json
{"schedule":"08:00", "repeat":"daily", "enabled":true, "prompt":"...", "max_delay_hours":6}
```

`repeat` 可用：

- `daily`
- `weekday`
- `weekly`
- `monthly`
- `once`
- `every_Nh`
- `every_Nd`

`max_delay_hours` 是防过时的：若开机太晚，超过这段宽限，就不再补做。

## 它如何触发

1. `reflect/scheduler.py` 约每 60 秒看一回 `sche_tasks/*.json`
2. 需同时满足：
   - `enabled=true`
   - 当前时刻已过 `schedule`
   - 冷却已过（依据 `done/` 下最近报告时间）
3. 真触发时，会把报告目标路径一并塞进 prompt

## 我收到任务后第一件事

先用 `update_working_checkpoint` 记下报告应落何处。  
这一步若漏，长任务最容易做到最后忘了收尾。

## 行完后的收尾

- 把报告写到 scheduler 给定的目标路径
- 让 scheduler 能据此判断今日此事已做

## 额外说明

- `once` 基本等于只做一回
- 任务文件只说“做什么”，报告路径由 scheduler 注入
- 若 `web_scan` 说没有可用标签页，不见得是扩展坏了，也可能只是浏览器里没有正常页面
