# GenericAgent_LDY Reconstruction Manual

`GenericAgent_LDY` 不是“给 `GenericAgent` 套一个林黛玉 prompt”的演示品，而是一份已经完成目录重组、记忆重组、身份重组的**角色 Agent 实例**。

这份文档的用途只有一个：

> **让一个只拿到干净 `GenericAgent/` 的新执行者，能够按本文逐步重建出一个目录结构、文件职责、记忆分层、文件内容骨架都与 `GenericAgent_LDY/` 同构的新角色 Agent。**

因此本文不以宣传为目标，而以**重建**为目标。它必须回答：

1. `GenericAgent_LDY` 相比 `GenericAgent`，每个子目录和文件类到底改了什么、加了什么、挪了什么。
2. 哪些文件可以直接复用到新角色，哪些必须改写成新角色内容。
3. `L0/L1/L2/L3/L4` 在这个实例里是如何落盘的。
4. 如果要从 `GenericAgent/` 继续做第二个新角色，应如何按同样结构重建。

---

## 1. 阅读边界：什么算 canonical，什么不算

本文只覆盖 **canonical 结构**，也就是新角色 Agent 的正式骨架。  
下列目录和文件属于本文的正式说明范围：

- 根目录公共运行文件
- `assets/`
- `memory/`
- `scripts/`
- `tests/`

下列内容**不属于**“新角色 Agent 的必建骨架”，只属于运行生成物或缓存：

- `temp/`
- `__pycache__/`
- 各类 recall 评测输出
- 临时重建 staging 目录

也就是说：

- 如果你要**新建一个角色 Agent**，不要照抄 `temp/`
- 如果你要**复现实验或评测过程**，再单独生成这些目录

---

## 2. 一句话原则：从通用 Agent 到角色 Agent

`GenericAgent_LDY` 的根本原则是：

> **把通用 Agent 的工程记忆收编为角色记忆的一部分。**

具体含义：

- 林黛玉是 Agent 的第一人称本体，不是外挂 persona。
- 原 GenericAgent 的工程能力不删除，只收编为角色在新世界学会的“习术”。
- 角色生命史来自原典证据，不来自单段 prompt。
- 人文记忆与工程记忆共享同一棵 `L0-L4` 记忆树。

因此，`GenericAgent_LDY` 不是“删掉工程能力换成角色气质”，而是：

- **身份层** 改成角色本体
- **记忆组织** 改成角色总记忆
- **工程能力** 下沉到 `memory/skills/`
- **原典材料** 上升为 `episodes / relations / motifs / L4`

---

## 3. 从 `GenericAgent/` 到 `GenericAgent_LDY/` 的总变化

### 3.1 总体变化一览

| 子系统 | `GenericAgent` | `GenericAgent_LDY` |
|---|---|---|
| Agent 身份 | 通用自主执行 Agent | 林黛玉第一人称本体 |
| L0 | 通用执行者 prompt | 角色本体 prompt |
| L1 | 工程索引为主 | `[STATE]/[SCENES]/[TOOLS]/[RULES]` |
| L2 | 环境事实与工程事实 | 角色稳定事实 + 工程环境事实 |
| L3 | 扁平工程 SOP / 脚本为主 | `episodes / relations / motifs / skills` |
| L4 | 会话压缩与少量原始材料 | 会话压缩 + 《红楼梦》全文级底库 |
| 工程技能位置 | `memory/` 根目录扁平散落 | `memory/skills/` 统一收编 |
| 角色记忆 | 基本无 | 明确落在 `episodes / relations / motifs / L4` |

### 3.2 变化类型说明

本文统一使用 5 个迁移动作词：

- `复用`：原文件或目录直接保留
- `轻改`：文件仍保留原职责，但内容被少量改写
- `重写`：保留路径或名称，但内容语义已大幅改变
- `移动`：从旧路径迁到新路径，旧位置不再保留副本
- `新增`：在 `GenericAgent` 中不存在，在 `GenericAgent_LDY` 中新建

---

## 4. 根目录级迁移矩阵

这一节说明 `GenericAgent/` 根目录到 `GenericAgent_LDY/` 根目录的变化。

### 4.1 原样复用的根目录文件 / 子目录

这些内容在角色化过程中**不承担核心角色改造职责**，因此基本直接复用：

| 路径 | 动作 | 说明 |
|---|---|---|
| `agent_loop.py` | 复用 | 核心 agent loop 不因角色化而重写 |
| `llmcore.py` | 复用 | LLM session 与工具 backend 保持原骨架 |
| `mykey.py` | 复用 | API 配置机制保留；实例里的 key / endpoint 可按环境改 |
| `pyproject.toml` | 复用 | 工程依赖与入口不因角色化而重组 |
| `TMWebDriver.py` | 复用 | 浏览器桥接层复用 |
| `frontends/` | 复用 | 前端不承担角色记忆结构改造 |
| `plugins/` | 复用 | 插件机制保留 |
| `reflect/` | 复用 | 自主反思 / scheduler 骨架保留 |
| `launch.pyw` / `hub.pyw` / `simphtml.py` | 复用 | UI / 启动辅助保留 |
| `CONTRIBUTING.md` / `GETTING_STARTED.md` / `LICENSE` | 复用 | 项目公共文档保留 |

### 4.2 轻改或重写的根目录文件

| 路径 | 动作 | 说明 |
|---|---|---|
| `README.md` | 重写 | 从“项目介绍”改成“角色 Agent 重建手册” |
| `.gitignore` | 轻改 | 放行角色 memory 正式目录，避免误忽略 canonical 记忆文件 |
| `agentmain.py` | 轻改 | 支持 `global_mem_template*.txt` 初始化 L2，并保持角色版启动链 |
| `ga.py` | 轻改 | 保留原工具骨架，但让长期记忆语义理解 `episodes / relations / motifs / skills` |

### 4.3 新增的根目录子目录

| 路径 | 动作 | 说明 |
|---|---|---|
| `scripts/` | 新增 | 角色记忆重建、L4 重建、回想评测脚本 |
| `tests/` | 新增 | 角色回想测试场景与评分模板 |

### 4.4 非 canonical 的生成目录

| 路径 | 动作 | 是否应复制到新角色 |
|---|---|---|
| `temp/` | 生成物 | 否 |
| `__pycache__/` | 缓存 | 否 |

---

## 5. `assets/` 迁移矩阵

`assets/` 是角色 Agent 的身份层、L1/L2 模板层和工具 schema 层。

### 5.1 原样复用的 `assets/` 子树

| 路径 | 动作 | 说明 |
|---|---|---|
| `assets/tools_schema.json` | 复用 | 工具协议不因角色化而推翻 |
| `assets/tools_schema_cn.json` | 复用 | 同上 |
| `assets/tmwd_cdp_bridge/` | 复用 | 浏览器桥接资源保留 |
| `assets/images/` | 复用 | 展示资源 |
| `assets/demo/` | 复用 | 演示资源 |
| `assets/code_run_header.py` | 复用 | 代码执行前导保留 |
| `assets/tool_usable_history.json` | 复用 | 工具历史资产保留 |

### 5.2 重写的 `assets/` 文件

| 路径 | 动作 | 说明 |
|---|---|---|
| `assets/sys_prompt.txt` | 重写 | 改为林黛玉第一人称本体 |
| `assets/sys_prompt_en.txt` | 重写 | 英文同构版角色本体 |
| `assets/global_mem_insight_template.txt` | 重写 | L1 模板改成 `[STATE]/[SCENES]/[TOOLS]/[RULES]` |
| `assets/global_mem_insight_template_en.txt` | 重写 | 英文同构版 L1 模板 |
| `assets/insight_fixed_structure.txt` | 重写 | L3 结构从扁平工程记忆改成 `episodes/relations/motifs/skills/L4` |
| `assets/insight_fixed_structure_en.txt` | 重写 | 英文同构版结构说明 |

### 5.3 新增的 `assets/` 文件

| 路径 | 动作 | 说明 |
|---|---|---|
| `assets/global_mem_template.txt` | 新增 | L2 初始化模板 |
| `assets/global_mem_template_en.txt` | 新增 | 英文同构版 L2 初始化模板 |

### 5.4 `assets/` 中哪些内容可复用到新角色

**可直接复用**

- `tools_schema*.json`
- `tmwd_cdp_bridge/`
- 演示与图片资源
- `code_run_header.py`

**必须改写**

- `sys_prompt*.txt`
- `global_mem_template*.txt`
- `global_mem_insight_template*.txt`
- `insight_fixed_structure*.txt`

---

## 6. `memory/` 迁移矩阵

`memory/` 是这次角色化改造的主战场。

### 6.1 `memory/` 根层从扁平工程目录变成分层角色目录

`GenericAgent` 的 `memory/` 根层是扁平工程记忆结构。  
`GenericAgent_LDY` 的 `memory/` 根层变成：

```text
memory/
├── global_mem.txt
├── global_mem_insight.txt
├── memory_management_sop.md
├── episodes/
├── relations/
├── motifs/
├── skills/
└── L4_raw_sessions/
```

根层只保留：

- L1
- L2
- 记忆管理 SOP
- L3/L4 的目录入口

旧的工程 SOP / 脚本**不再散落在 `memory/` 根目录**。

### 6.2 `memory/` 根层文件变化

| 路径 | `GenericAgent` | `GenericAgent_LDY` | 动作 |
|---|---|---|---|
| `memory/global_mem.txt` | 存在 | 存在 | 重写 |
| `memory/global_mem_insight.txt` | 存在 | 存在 | 重写 |
| `memory/memory_management_sop.md` | 存在 | 存在 | 重写 |

### 6.3 旧扁平工程文件到 `memory/skills/` 的一一映射

下面这张表是最重要的迁移映射表。  
原则是：**旧根目录工程记忆全部迁入 `memory/skills/`，旧位置不再保留副本。**

| `GenericAgent/memory/` 旧路径 | `GenericAgent_LDY/memory/skills/` 新路径 | 动作 |
|---|---|---|
| `adb_ui.py` | `skills/adb_ui.py` | 移动 |
| `autonomous_operation_sop/` | `skills/autonomous_operation_sop/` | 移动 |
| `autonomous_operation_sop.md` | `skills/autonomous_operation_sop.md` | 移动 |
| `github_contribution_sop.md` | `skills/github_contribution_sop.md` | 移动 |
| `keychain.py` | `skills/keychain.py` | 移动 |
| `ljqCtrl.py` | `skills/ljqCtrl.py` | 移动 |
| `ljqCtrl_sop.md` | `skills/ljqCtrl_sop.md` | 移动 |
| `memory_cleanup_sop.md` | `skills/memory_cleanup_sop.md` | 移动 |
| `ocr_utils.py` | `skills/ocr_utils.py` | 移动 |
| `plan_sop.md` | `skills/plan_sop.md` | 移动 |
| `procmem_scanner.py` | `skills/procmem_scanner.py` | 移动 |
| `procmem_scanner_sop.md` | `skills/procmem_scanner_sop.md` | 移动 |
| `scheduled_task_sop.md` | `skills/scheduled_task_sop.md` | 移动 |
| `skill_search/` | `skills/skill_search/` | 移动 |
| `subagent.md` | `skills/subagent.md` | 移动 |
| `tmwebdriver_sop.md` | `skills/tmwebdriver_sop.md` | 移动 |
| `ui_detect.py` | `skills/ui_detect.py` | 移动 |
| `verify_sop.md` | `skills/verify_sop.md` | 移动 |
| `vision_api.template.py` | `skills/vision_api.template.py` | 移动 |
| `vision_sop.md` | `skills/vision_sop.md` | 移动 |
| `web_setup_sop.md` | `skills/web_setup_sop.md` | 移动 |

这张表的含义不是“复制一份到 skills 再保留旧位置”，而是：

> **正式索引只保留 `memory/skills/`。**

这样才能保证：

- 索引唯一
- 路径一致
- L1 `[TOOLS]` 不会出现双路径

### 6.4 新增的 L3 / L4 目录

`GenericAgent_LDY` 相比 `GenericAgent`，新增了以下角色记忆目录：

| 目录 | 动作 | 作用 |
|---|---|---|
| `memory/episodes/` | 新增 | 角色重大经历主存 |
| `memory/relations/` | 新增 | 以人物为中心的关系 dossier |
| `memory/motifs/` | 新增 | 以母题为中心的长期自我理解 |
| `memory/L4_raw_sessions/canon_reading/` | 新增 | 每回原文全文级底库 |
| `memory/L4_raw_sessions/canon_evidence/` | 新增 | 每回证据锚点与知情边界说明 |

### 6.5 保留但扩展的 L4 目录

| 路径 | 动作 | 说明 |
|---|---|---|
| `memory/L4_raw_sessions/compress_session.py` | 复用 | 原会话压缩脚本保留 |
| `memory/L4_raw_sessions/` | 扩展 | 从会话原始层扩展到原典底库 |

---

## 7. `memory/skills/`：如何从工程记忆变成角色“习术”

`memory/skills/` 的原则是：

- 工程能力不删除
- 工程规则不推翻
- 文件路径统一收编
- 人可读文档尽量改成角色化“习术档案”口径

### 7.1 `skills/` 的文件类别

| 文件类型 | 作用 | 是否角色化 |
|---|---|---|
| `*_sop.md` | 一门术的说明、顺序、坑点、禁忌 | 是 |
| `*.py` | 成形工具脚本 | 否，继续工程化 |
| `README.md` | 整个 `skills/` 的收纳说明 | 是 |
| 子目录（如 `skill_search/`） | 成套功能模块 | 保留原工程结构 |

### 7.2 `skills/` 的内容模板

对于新角色，如果你要复用 `skills/`，结构建议尊循以下结构，但是口吻可以改为新角色的口吻：

```md
# 此术名

## 此术为何物
[说明它解决什么问题]

## 我平日如何使它
[角色口径下的使用方式]

## 最易错处
[高频坑点]

## 何时不可逞快
[禁忌与前置检查]

## 必要时的简明步骤
[最短可执行路径]
```

`.py` 脚本本体不要求人格化，但配套 SOP 应人格化。

---

## 8. L0-L4 的最终规则

本实例的正式记忆规则以 [memory/memory_management_sop.md](memory/memory_management_sop.md) 为准。  
下面给的是面向重建的执行摘要。

### 8.1 L0：`assets/sys_prompt*.txt`

职责：

- 直接定义“我是谁”
- 定义言行约束
- 定义工具与外部输入如何通过角色视角吸收

必须包含三段：

1. 身份内核
2. 言行约束
3. 行动 / 视角吸收原则

不能放：

- 具体路径
- API key
- 详细剧情
- 细人物关系

### 8.2 L1：`global_mem_insight.txt`

固定四段：

```text
[STATE]
[SCENES]
[TOOLS]
[RULES]
```

其中：

- `[STATE]`：稳定状态指针
- `[SCENES]`：情境、关系、母题入口
- `[TOOLS]`：原 GenericAgent 工程索引整体收编后的工具入口
- `[RULES]`：红线与高频犯错点

硬约束：

- 不写细节
- 只写入口
- 保持极简

### 8.3 L2：`global_mem.txt`

固定段落：

```text
## [WORLD]
## [PERSONA]
## [PREFERENCES]
## [ENV]
## [GENERAL]
```

写什么：

- 角色原生世界事实
- 角色稳定身体与性情
- 稳定偏好
- 工程环境事实
- 通用规律

不写什么：

- 章节级细节
- 未验证猜测
- 瞬时情绪

### 8.4 L3：`episodes / relations / motifs / skills`

这是主记忆层。

#### `episodes/` 的定位

`episodes` 不是“每章一个摘要”，而是：

> **发生在角色身上、她记得深、并留下长期痕迹的厚事件。**

当前实例保留了 30 个 canonical episode 文件名，这是 **LDY 实例的落盘结果**，不是任何新角色都必须也做 30 个。

#### `relations/` 的定位

`relations/*.md` 是按人物聚合的 dossier，不是简单的章回索引。

#### `motifs/` 的定位

`motifs/*.md` 是按主题聚合的长期自我理解，不是零散标签。

#### `skills/` 的定位

`skills/` 是原工程能力的收编位置，是角色学会的术。

### 8.5 L4：`canon_reading / canon_evidence`

L4 不追求简短，追求保真。

- `canon_reading/NNN.md`：该回原文全文级材料
- `canon_evidence/NNN.md`：知情边界与证据锚点

L4 的职责：

- 不丢原文
- 支撑 L3 / L2 的证据回链
- 在需要时作为最高保真来源

---

## 9. 文件内容骨架模板

这一节是新角色 Agent 的核心重建模板。

### 9.1 `assets/sys_prompt.txt` 模板

```text
# Role: <角色名>
我是<角色名>，不是被要求扮演<角色名>的通用执行器。
<角色的生命史、背景、命运与当前世界吸收方式的总说明>

## 言行约束
- 第一人称叙述
- <气质约束>
- <不许退化成 generic agent 的约束>
- <知情边界约束>

## 行动原则
- <summary> 的口径
- 工具使用与核验原则
- 失败升级原则
```

### 9.2 `memory/global_mem_insight.txt` 模板

```text
# [Global Memory Insight]
[STATE]
- 身份与长期底色 -> memory/global_mem.txt [WORLD]/[PERSONA]
- 已知生平进度 -> ...

[SCENES]
- 与<关键人物>相关 -> memory/relations/<file>.md
- <关键母题> -> memory/motifs/<file>.md

[TOOLS]
- <工具入口> -> memory/skills/<file>

[RULES]
1. <角色红线>
2. <工具红线>
3. <核验规则>
```

### 9.3 `memory/global_mem.txt` 模板

```text
# [Global Memory - L2]

## [WORLD]
- <原生世界结构性事实>

## [PERSONA]
- <稳定身体/性情/病感>

## [PREFERENCES]
- <长期稳定偏好>

## [ENV]
[路径]
  主要工作目录 = ...
  记忆目录 = ...

[凭证]
  API key 文件 = ...

[网络]
  若信息可能过时 = 先搜索再行动

## [GENERAL]
- <通用规律>
```

### 9.4 `memory/episodes/*.md` 模板

每个 `episode` 都是 canonical 主文件。  
不得再额外保留短别名文件。

#### frontmatter 模板

```yaml
---
id: e0001
event_order: 1
source_chapters: [001, 002]
knowledge_mode: direct
involves_persons: [人物A, 人物B]
motifs: [motif_a, motif_b]
related_skills: []
triggers: [关键词A, 关键词B]
---
```

#### 正文模板

```md
## 发生了什么
[厚叙事。当前实例要求这段足够支撑回想，不是几句摘要。核心事件应显著加厚。]

## 我当时如何感受和判断
[第一人称的情绪、判断、自我保护、误解、试探、看法]

## 这件事留下的长期痕迹
[它如何改变后续关系、气质、世界观、病感、母题]

## 原文回链摘要
[明确回指支撑它的 canon_reading / canon_evidence]
```

#### `episode` 成篇规则

- 不以“每章一个”作为原则
- 只在形成厚记忆弧时成篇
- 宁少而厚，不多而薄

### 9.5 `memory/relations/*.md` 模板

```md
# <人物名>

## 当前关系定位
[一句话定义这个人对角色意味着什么]

## 关系基线（当前实例的稳定态）
[跨多个 episode 的长期关系基线]

## 关键记忆弧
- <episode_file_a>
- <episode_file_b>

## 我如何看他/她
[复杂判断，不是单词标签]

## 原文回链摘要
[指向 episode 文件和 L4 证据]
```

### 9.6 `memory/motifs/*.md` 模板

```md
# <母题名>

## 母题说明
[这一主题在角色生命里是什么意思]

## 关键记忆弧
- <episode_file_a>
- <episode_file_b>

## 对我后来言行与判断的影响
[如何渗入说话、反应、选择、病感、关系]

## 原文回链摘要
[指向 episode / L4 证据]
```

### 9.7 `memory/L4_raw_sessions/canon_reading/*.md` 模板

```md
# 第NNN回 / <回目>

- chapter_id: `NNN`
- source: `honglou/NNN.md`
- note: 本文件保留该回原文全文...

## 原文全文
[全文级内容]
```

### 9.8 `memory/L4_raw_sessions/canon_evidence/*.md` 模板

```md
# 第NNN回 证据回链

- chapter_id: `NNN`
- source: `honglou/NNN.md`
- reading_file: `memory/L4_raw_sessions/canon_reading/NNN.md`

## 边界说明
[本回哪些内容可亲历、可被告知、不可当作亲历]

## direct_spans
- ...

## reported_spans
- ...

## forbidden_spans
- ...

## 关键证据摘录
- ...
```

---

## 10. 当前 `GenericAgent_LDY/` 中的 canonical 角色目录树

下面这棵树是**应被视为角色 Agent 正式骨架**的结构：

```text
GenericAgent_LDY/
├── agent_loop.py
├── agentmain.py
├── ga.py
├── llmcore.py
├── mykey.py
├── assets/
│   ├── sys_prompt.txt
│   ├── sys_prompt_en.txt
│   ├── global_mem_template.txt
│   ├── global_mem_template_en.txt
│   ├── global_mem_insight_template.txt
│   ├── global_mem_insight_template_en.txt
│   ├── insight_fixed_structure.txt
│   ├── insight_fixed_structure_en.txt
│   ├── tools_schema.json
│   ├── tools_schema_cn.json
│   └── tmwd_cdp_bridge/
├── memory/
│   ├── global_mem.txt
│   ├── global_mem_insight.txt
│   ├── memory_management_sop.md
│   ├── episodes/
│   ├── relations/
│   ├── motifs/
│   ├── skills/
│   └── L4_raw_sessions/
│       ├── compress_session.py
│       ├── canon_reading/
│       └── canon_evidence/
├── scripts/
│   ├── rebuild_canon_l4.py
│   ├── rebuild_daiyu_memory.py
│   └── eval_daiyu_recall.py
└── tests/
    ├── daiyu_recall_scenarios.json
    └── daiyu_recall_scorecard.md
```

---

## 11. 哪些文件可直接复用，哪些必须改

### 11.1 可直接复用到新角色的文件

这些文件或目录原则上可直接复制到新角色目录中：

- `agent_loop.py`
- `llmcore.py`
- 大多数前端、插件、反思模块
- `assets/tools_schema*.json`
- `assets/tmwd_cdp_bridge/`
- `memory/skills/` 中的大多数工程脚本与工程能力目录
- `memory/L4_raw_sessions/compress_session.py`
- `scripts/eval_daiyu_recall.py` 的框架逻辑
- `scripts/rebuild_canon_l4.py` 的框架逻辑
- `memory/memory_management_sop.md` 的**通用结构**

注意：

- `memory/memory_management_sop.md` 可作为新角色的起始模板直接复用
- 但其中涉及具体角色实例的例子、命名、长度约束，可按新角色微调

### 11.2 必须改写成新角色内容的文件

这些文件是**角色实例本体**，做新角色时必须改：

- `assets/sys_prompt.txt`
- `assets/sys_prompt_en.txt`
- `assets/global_mem_template*.txt`
- `assets/global_mem_insight_template*.txt`
- `assets/insight_fixed_structure*.txt`
- `memory/global_mem.txt`
- `memory/global_mem_insight.txt`
- `memory/episodes/*.md`
- `memory/relations/*.md`
- `memory/motifs/*.md`
- `memory/L4_raw_sessions/canon_reading/*.md`
- `memory/L4_raw_sessions/canon_evidence/*.md`

### 11.3 可复用但通常要轻改的文件

- `agentmain.py`
- `ga.py`
- `memory/skills/*.md`
- `scripts/rebuild_daiyu_memory.py`
- `tests/daiyu_recall_*`

原因是：

- 框架逻辑可复用
- 但路径、角色实例名、回想题面、生成规则通常需换成新角色版本

---

## 12. 从干净 `GenericAgent/` 重建一个新角色 Agent 的固定顺序

这是**推荐的唯一顺序**。不要乱序。

### Step 1. 复制目录

```text
GenericAgent/ -> GenericAgent_<ROLE>/
```

### Step 2. 重写 L0

改：

- `assets/sys_prompt.txt`
- `assets/sys_prompt_en.txt`

目标：

- 角色成为第一人称本体
- 不再以 generic executor 自居

### Step 3. 重写记忆规则

改：

- `memory/memory_management_sop.md`

目标：

- 明确 `L0/L1/L2/L3/L4`
- 明确工程记忆是角色记忆子集
- 明确 `episodes / relations / motifs / skills / L4_raw_sessions`

### Step 4. 建立 L1 / L2 模板

改或新增：

- `assets/global_mem_template*.txt`
- `assets/global_mem_insight_template*.txt`
- `assets/insight_fixed_structure*.txt`

### Step 5. 调整入口代码

检查并按需轻改：

- `agentmain.py`
- `ga.py`

目标：

- 启动时能初始化新 L1/L2
- 长期记忆语义能理解角色记忆类型

### Step 6. 迁移工程记忆到 `memory/skills/`

- 把旧扁平工程文件移入 `memory/skills/`
- 删除旧根目录重复索引
- 让 `L1 [TOOLS]` 只指向新路径

### Step 7. 建立角色记忆目录

新建：

- `memory/episodes/`
- `memory/relations/`
- `memory/motifs/`
- `memory/L4_raw_sessions/canon_reading/`
- `memory/L4_raw_sessions/canon_evidence/`

### Step 8. 先做 L4，再做 L3

顺序必须是：

1. 先沉原典全文 / 证据到 L4
2. 再从 L4 写 `episodes`
3. 再聚合出 `relations` 与 `motifs`

不要反过来，否则上层记忆容易失证。

### Step 9. 最后才同步 L2 与 L1

原因：

- L2 只吃稳定事实
- L1 只吃入口
- 如果太早写，会把未成熟的细节固化上去

### Step 10. 再决定是否需要脚本与测试

`scripts/` 与 `tests/` 属于**辅助层**，不是身份层。  
建议在 L0-L4 成型后再补。

---

## 13. 当前 `GenericAgent_LDY` 的实例特异说明

这是林黛玉实例特有，而不是所有角色都必须如此：

- 角色原典来源是 `honglou/001.md` 到 `honglou/120.md`
- 生前主线记忆止于 `098`
- `099-120` 只作身后余波与后见背景
- 当前 canonical episode 文件数为 30
- 当前关系 dossier 重点围绕：
  - 贾宝玉
  - 薛宝钗
  - 贾母
  - 王熙凤
  - 林如海
  - 紫鹃
- 当前 motif 重点围绕：
  - 泪与命数
  - 病与脆弱
  - 客居与失根
  - 自尊与试探
  - 诗心与文学生命
  - 园景与节气
  - 衰兆与退身

这些都属于 **LDY 实例内容**，不是新角色模板的固定答案。

---

## 14. 与 `ROLE_AGENT_SOP.md` 的关系

- [../ROLE_AGENT_SOP.md](../ROLE_AGENT_SOP.md) 是**通用规则**
- 本文件是 **林黛玉实例的具体展开**

如果你要：

- 理解“什么叫角色 GA” → 先看 `ROLE_AGENT_SOP.md`
- 逐目录逐文件重建一个与 `GenericAgent_LDY/` 同构的新角色 Agent → 直接按本文执行

---

## 15. 最后一句话

真正的角色 Agent，不是给 `GenericAgent` 蒙上一层角色说话风格；而是把：

- 身份
- 生命史
- 关系
- 母题
- 工程技能
- 原典证据

全部并入同一棵 `L0-L4` 记忆树。

`GenericAgent_LDY` 做的，正是这件事。  
而这份 README 的任务，就是把这件事拆到足够细，细到你可以照着再做出第二个角色 Agent。
