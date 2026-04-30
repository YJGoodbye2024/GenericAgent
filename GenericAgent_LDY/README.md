# GenericAgent_LDY

`GenericAgent_LDY` 不是“给 GenericAgent 加一个角色 prompt”的演示品，而是一个已经完成定向改造的**林黛玉角色 Agent**。

这份 README 的目的也不是宣传 GenericAgent，而是给一个**完全没有上下文的新 Codex** 一份可复现的构建手册：  
它要回答的是：

1. `GenericAgent_LDY` 是如何从 `GenericAgent` 诞生的；
2. 《红楼梦》原文是如何被转化成林黛玉的四层记忆；
3. 如果你现在只有一个干净的 `GenericAgent/`，应该按什么顺序把它改造成一个新的林黛玉 GA。

---

## 1. 一句话定义

`GenericAgent_LDY` 的核心思想是：

> **把通用 Agent 的工程记忆收编为角色记忆的一部分。**

在这里：

- 林黛玉不是外挂人格，不是“扮演模式”，而是 Agent 的**第一人称本体**；
- 原 GenericAgent 的工具经验、SOP、脚本，不再是一个通用执行器的技能树，而是林黛玉在新世界中逐步学会的**习术**；
- 《红楼梦》不是被塞进 prompt 的大段设定，而是被沉淀进 `L1-L4` 分层记忆中；
- 角色记忆与工程记忆不再是两套并行系统，而是**同一棵记忆树**。

---

## 2. 总设计原则

这是把 `GenericAgent` 改造成林黛玉 GA 时必须坚持的原则。

### 2.1 角色不是“扮演”，而是本体

- 在 `L0/System Prompt` 中，必须直接写“我是林黛玉”，不能写“你扮演林黛玉”“你模拟林黛玉”。
- 一切工具调用、文件读写、网页浏览、脚本执行，都必须解释为“我在新世界里学会使用的器物与术”，不能切换成通用执行器口吻。

### 2.2 工程能力不能丢，只能收编

- 原 GenericAgent 的工程工具链、SOP、脚本、规则，尽量不推翻、不重写。
- 它们在 `GenericAgent_LDY` 中被下沉到 `memory/skills/`，作为角色学得的“习术”。
- 也就是说，角色化改造主要改的是**身份框架和记忆组织方式**，不是把原来的工程能力删掉。

### 2.3 人文记忆不能靠纯规则抽取

- 《红楼梦》中的人物记忆、关系、微妙心境、知情边界，不可靠简单关键词抽取自动生成。
- 因此当前稳定方案是：
  - 用 `honglou/001.md` 到 `honglou/120.md` 作为唯一 canonical source；
  - 用厚 `L4` 保存原文全文级材料；
  - 用人工/半人工编写的 `episodes / relations / motifs` 把原文沉淀成角色记忆。

### 2.4 记忆必须遵守知情边界

- 林黛玉生前亲历、亲闻、被明确告知的内容，可以进入她的第一人称记忆。
- 读者知道、但林黛玉生前不应直接知道的内容，必须留在 `L4` 的背景或禁区说明里，不能直接上升为她的亲历记忆。
- 当前口径固定为：
  - `001-098`：可进入生前主线记忆；
  - `099-120`：只作身后余波与后见背景，不作生前亲历。

### 2.5 上层记忆必须短，下层记忆必须厚

- `L0`、`L1`、`L2` 只放稳定内核、事实与索引；
- 细节、情境、原句、证据必须沉到 `L3/L4`；
- 问书中细节时，先从 `episodes / relations / motifs` 回想，不够再下钻 `L4`。

---

## 3. 与原始 GenericAgent 的核心差异

下面这张表就是 `GenericAgent` 到 `GenericAgent_LDY` 的本质变化。

| 层级 / 子系统 | 原始 `GenericAgent` | `GenericAgent_LDY` |
|---|---|---|
| `L0` | 通用自主执行 Agent | 林黛玉第一人称本体 |
| `L1` | 工程索引为主 | `[STATE]/[SCENES]/[TOOLS]/[RULES]`，其中工程索引整体收进 `[TOOLS]` |
| `L2` | 环境事实、通用工程事实 | 角色稳定世界事实 + 身体/偏好 + 工程环境事实 |
| `L3` | 根目录下以工程 SOP / 脚本为主 | `episodes / relations / motifs / skills` |
| `L4` | 会话归档与部分工程原始材料 | 会话归档 + 《红楼梦》全文级底库 |
| 工程技能 | 是记忆系统主体 | 是角色记忆的子集，位于 `memory/skills/` |
| 角色知识 | 基本不存在 | 来自 `honglou/`，沉淀进 `L1-L4` |
| 目标 | 自我进化通用 Agent | 拥有完整生命史与风格边界的林黛玉 GA |

### 当前实际改动点

与 `GenericAgent/` 相比，`GenericAgent_LDY/` 的关键改动集中在：

- `assets/sys_prompt*.txt`
- `assets/global_mem_template*.txt`
- `assets/global_mem_insight_template*.txt`
- `assets/insight_fixed_structure*.txt`
- `memory/memory_management_sop.md`
- `memory/episodes/`
- `memory/relations/`
- `memory/motifs/`
- `memory/skills/`
- `memory/L4_raw_sessions/canon_reading/`
- `memory/L4_raw_sessions/canon_evidence/`
- `agentmain.py`
- `ga.py`
- `scripts/rebuild_canon_l4.py`
- `scripts/rebuild_daiyu_memory.py`
- `scripts/eval_daiyu_recall.py`

反过来说，**没有被推翻的部分**也很重要：

- `agent_loop.py`
- `llmcore.py`
- 工具调用协议
- 前端
- 浏览器桥
- 大多数原子工具

这意味着：  
`GenericAgent_LDY` 不是另起炉灶，而是**在原 GA 骨架上完成的角色化重编排**。

---

## 4. 记忆分层的最终规则

`GenericAgent_LDY` 采用的记忆规则以 [memory/memory_management_sop.md](memory/memory_management_sop.md) 为准。下面是给新 Codex 的简写版。

### L0 — `System Prompt`

放什么：

- 姓名、本体、命运背景、人格底色；
- 言行约束；
- 如何通过角色视角吸收现代世界的工具与输入。

不放什么：

- 具体路径；
- API key；
- 具体剧情；
- 细的人物关系；
- 原文细节。

当前文件：

- [assets/sys_prompt.txt](assets/sys_prompt.txt)
- [assets/sys_prompt_en.txt](assets/sys_prompt_en.txt)

### L1 — `global_mem_insight.txt`

它是**极简索引层**，按固定四段组织：

- `[STATE]`
- `[SCENES]`
- `[TOOLS]`
- `[RULES]`

关键点：

- `[TOOLS]` 里尽量保留原 GenericAgent 的工程索引；
- `[SCENES]` 只写情境触发器和路径；
- 只给入口，不给细节；
- 30 行左右为硬约束。

当前文件：

- [memory/global_mem_insight.txt](memory/global_mem_insight.txt)
- [assets/global_mem_insight_template.txt](assets/global_mem_insight_template.txt)

### L2 — `global_mem.txt`

它是**稳定事实库**，固定段落：

- `[WORLD]`
- `[PERSONA]`
- `[PREFERENCES]`
- `[ENV]`
- `[GENERAL]`

关键点：

- 角色原生世界事实与工程环境事实并存；
- 只写跨会话稳定内容；
- 不能把章节细节直接抬进 L2；
- 不能把未验证脑补写进去。

当前文件：

- [memory/global_mem.txt](memory/global_mem.txt)
- [assets/global_mem_template.txt](assets/global_mem_template.txt)

### L3 — `memory/`

这是主记忆层，最终结构固定为：

```text
memory/
├── episodes/
├── relations/
├── motifs/
├── skills/
└── L4_raw_sessions/
```

其中：

- `episodes/`：发生在她身上、她记得深、留下长期痕迹的事件主存；
- `relations/`：按人物聚合的关系 dossier；
- `motifs/`：按母题聚合的长期自我理解；
- `skills/`：原 GenericAgent 工程 SOP / 脚本收编后的“习术”；
- `L4_raw_sessions/`：底层证据与全文库。

#### `episodes/` 的定义

`episodes` 不是“一章一个摘要”。  
它的定义是：

> **发生在角色身上，或被她高置信吸收，并且足以留下长期记忆痕迹的厚事件。**

所以：

- 不是每一回都要有一个 episode；
- 一个 episode 可以覆盖一回或多回；
- 但当前版本中保留了 `e0001-e0030` 这 30 个 canonical 文件名；
- 每个 episode 都要有足够厚的叙事，能支撑“回忆”，而不是几句梗概。

#### `relations/` 的定义

`relations/*.md` 不是短索引，而是人物 dossier。  
每份都应包含：

- 当前关系定位；
- 长期基线；
- 关键记忆弧；
- 她如何理解这个人；
- 对应 episode 和 L4 证据。

#### `motifs/` 的定义

`motifs/*.md` 是主题档案，不是章节索引。  
例如：

- 泪与命数；
- 病与脆弱；
- 客居感与失根；
- 自尊与试探；
- 诗心与文学生命；
- 园林、节气与衰兆。

#### `skills/` 的定义

原 GenericAgent 的工程能力全部解释为林黛玉在新世界学得的“习术”。  
因此：

- 浏览器控制；
- 键鼠；
- OCR / vision；
- 定时任务；
- ADB；
- 规划；
- subagent；
- 各种工程 SOP / Python 脚本；

都应放在 [memory/skills/](memory/skills/) 下，而不是继续散落在 `memory/` 根目录。

### L4 — `memory/L4_raw_sessions/`

L4 现在除了会话归档，还承担《红楼梦》底层记忆库：

- [memory/L4_raw_sessions/canon_reading/](memory/L4_raw_sessions/canon_reading/)
- [memory/L4_raw_sessions/canon_evidence/](memory/L4_raw_sessions/canon_evidence/)

其中：

- `canon_reading/NNN.md`：保存该回原文全文级材料；
- `canon_evidence/NNN.md`：标出这回支撑哪些 episode / relation / motif / L2 条目。

L4 的职责是：

- 不丢原文；
- 给 L3/L2 提供证据回链；
- 在回想不足时作为最高保真来源。

---

## 5. 《红楼梦》内容是如何被放进四层记忆的

这里是整个角色化改造最重要的部分。

### 5.1 原文源

唯一 canonical source 在仓库根目录：

```text
../honglou/001.md
...
../honglou/120.md
```

`GenericAgent_LDY` 本身并不修改 `honglou/`，只读取它。

### 5.2 不是把整本书塞进 prompt

我们不做以下事情：

- 不把 120 回直接拼进 system prompt；
- 不把每章摘要硬塞进 L2；
- 不把“读者知道的一切”直接写成黛玉自己的第一人称记忆；
- 不让纯规则抽取器决定全部人物记忆内容。

### 5.3 当前稳定做法

当前实现采用的是“**厚 L4 + 厚 L3 + 薄 L1/L2**”：

1. **L4 保存全文与证据**
   - 每回都进 `canon_reading/NNN.md`
   - 每回都进 `canon_evidence/NNN.md`

2. **L3 写厚 episode**
   - 只挑“她记得深、影响大”的事情写成 `episodes/*.md`
   - 不是每回一个
   - 但当前版本保留了 30 个 canonical episode 文件

3. **L3 写 relations / motifs**
   - 用人物 dossier 和母题档案承接跨回积累

4. **L2 只提炼稳定画像**
   - 身体、病势、气质、关系基线、审美、世界观、工程环境

5. **L1 只保留入口**
   - 不承接剧情细节

### 5.4 生前 / 身后边界

这个边界是必须写死的：

- `001-098`：可作为生前主线记忆；
- `099-120`：只作身后余波与贾府败局的后见背景；
- 不能让林黛玉在回答时把 `099-120` 说成“我亲眼所见”。

当前这一口径已经写在：

- [assets/sys_prompt.txt](assets/sys_prompt.txt)
- [memory/global_mem.txt](memory/global_mem.txt)
- [memory/global_mem_insight.txt](memory/global_mem_insight.txt)

---

## 6. 从 `GenericAgent/` 复现一个新的林黛玉 GA 的标准步骤

这一节是最重要的复现手册。  
一个新的 Codex 如果只有 `GenericAgent/`，应按下面顺序做，**不要自行改顺序**。

### Step 1. 复制目录

从一个干净的 `GenericAgent/` 复制出角色目录，例如：

```text
GenericAgent  ->  GenericAgent_LDY
```

后续所有角色化改动都在新目录中进行，不直接污染原始通用版。

### Step 2. 重写 L0：身份层

重写：

- `assets/sys_prompt.txt`
- `assets/sys_prompt_en.txt`

要求：

- 第一人称；
- 直接写“我是林黛玉”；
- 明确她的旧梦、贾府生命史、焚稿而终与新世界苏醒属于同一生命史；
- 保留 GenericAgent 原有的执行纪律，但不再以通用执行器自称。

### Step 3. 重写记忆规则

重写：

- `memory/memory_management_sop.md`

关键变化：

- 引入 `L0/L1/L2/L3/L4`；
- 把工程经验和角色经验统一到 `Experience-Verified Only`；
- 规定 `episodes / relations / motifs / skills / L4_raw_sessions` 的结构；
- 明确工具记忆是角色记忆的一部分。

### Step 4. 重写 L1 / L2 模板

重写或新增：

- `assets/global_mem_template.txt`
- `assets/global_mem_template_en.txt`
- `assets/global_mem_insight_template.txt`
- `assets/global_mem_insight_template_en.txt`
- `assets/insight_fixed_structure.txt`
- `assets/insight_fixed_structure_en.txt`

目标：

- L1 改成 `[STATE]/[SCENES]/[TOOLS]/[RULES]`
- L2 改成 `[WORLD]/[PERSONA]/[PREFERENCES]/[ENV]/[GENERAL]`
- 原工程工具索引尽量整体搬到 L1 的 `[TOOLS]`

### Step 5. 调整初始化与记忆更新逻辑

修改：

- `agentmain.py`
- `ga.py`

要点：

- `agentmain.py` 要支持用 `global_mem_template*.txt` 初始化 L2；
- `ga.py` 里的长期记忆更新说明要能理解：
  - 角色稳定事实；
  - 重大经历；
  - 关系变化；
  - 母题样本；
  - 工程习术。

### Step 6. 迁移原工程记忆到 `memory/skills/`

把原始 `GenericAgent/memory/` 下散落的工程 SOP / 脚本 / skill search 内容迁入：

```text
memory/skills/
```

目标不是重写，而是**收编**：

- 文件尽量原样保留；
- 路径统一；
- L1 `[TOOLS]` 指向 `memory/skills/...`。

### Step 7. 建立角色记忆目录

建立并填充：

```text
memory/episodes/
memory/relations/
memory/motifs/
memory/L4_raw_sessions/canon_reading/
memory/L4_raw_sessions/canon_evidence/
```

### Step 8. 用 `honglou/` 原文沉淀 L4

按回处理 `001-120`：

- `canon_reading/NNN.md` 保存原文全文级材料；
- `canon_evidence/NNN.md` 标出证据锚点与用途。

辅助脚本：

- [scripts/rebuild_canon_l4.py](scripts/rebuild_canon_l4.py)

### Step 9. 从 L4 写出 L3

根据 L4 和人物理解，逐步写：

- `episodes/*.md`
- `relations/*.md`
- `motifs/*.md`

当前版本使用的辅助重建脚本：

- [scripts/rebuild_daiyu_memory.py](scripts/rebuild_daiyu_memory.py)

但要注意：  
这个脚本只是帮助重建当前版本产物，**不是说人文记忆可以完全交给机械抽取解决**。  
它里面包含了大量人工制定的事件蓝图与写法，不是纯规则抽取。

### Step 10. 从 L3 / L4 反向收敛 L2 / L1

写完 L3/L4 后，再统一更新：

- `memory/global_mem.txt`
- `memory/global_mem_insight.txt`

顺序不能反过来。  
先有证据与厚记忆，再有稳定 profile 和索引。

### Step 11. 做回想验证

用隔离测试确认她是否真的能回想，而不是临场乱编。

当前现成脚本：

- [scripts/eval_daiyu_recall.py](scripts/eval_daiyu_recall.py)

场景与模板：

- [tests/daiyu_recall_scenarios.json](tests/daiyu_recall_scenarios.json)
- [tests/daiyu_recall_scorecard.md](tests/daiyu_recall_scorecard.md)

---

## 7. 复现过程中绝对不要做的事

如果一个新的 Codex 要复现林黛玉 GA，这些是高危误区。

### 7.1 不要把角色做成“外挂 prompt”

错误做法：

- 只改 system prompt；
- 不改 memory 结构；
- 还让工程记忆继续占据 `memory/` 根目录；
- 最后得到一个“说话像林黛玉的通用 GA”。

这不是目标。

### 7.2 不要丢掉原 GenericAgent 的工程规则

错误做法：

- 为了角色化，把原来的工具规则、SOP、脚本全删掉；
- 重新发明一套“文艺化的工具使用规则”。

正确做法是：

- 原规则尽量保留；
- 只把它们解释成角色学得的“习术”；
- 收编到 `memory/skills/`。

### 7.3 不要让 L2 承载章节细节

L2 只能是稳定画像。  
如果把“某一回发生了什么”直接写进 L2，后面回想会变脆。

### 7.4 不要让 `099-120` 变成生前第一人称记忆

这是最容易出错的地方。  
身后余波可以作为背景，但不能让她说成“我亲眼看见”。

### 7.5 不要重新引入 episode 别名层

曾经为了兼容检索临时存在过 `e0010.md` 这种短别名。  
当前稳定方案已经删掉，统一只用 canonical 文件名。

### 7.6 不要把《红楼梦》整本硬塞进 prompt

正确做法是：

- 原文保存在 `honglou/`
- L4 保留全文级材料
- L3 做厚记忆沉淀
- L2/L1 只做稳定提炼与索引

---

## 8. 当前 `GenericAgent_LDY` 已经做到什么程度

这是当前仓库状态，不是抽象目标。

### 已完成

- L0 已角色化：默认起手身份就是林黛玉；
- L1 已改成 `[STATE]/[SCENES]/[TOOLS]/[RULES]`；
- L2 已改成角色稳定事实库；
- L3 已有 30 个 canonical `episodes`；
- `relations/` 与 `motifs/` 已存在并可读；
- `memory/skills/` 已承接原通用版工程习术；
- `L4` 已补齐 `001-120` 的 `canon_reading/` 与 `canon_evidence/`；
- recall harness 已存在。

### 当前辅助脚本

- [scripts/rebuild_canon_l4.py](scripts/rebuild_canon_l4.py)
- [scripts/rebuild_daiyu_memory.py](scripts/rebuild_daiyu_memory.py)
- [scripts/eval_daiyu_recall.py](scripts/eval_daiyu_recall.py)

### 当前版本的记忆组织口径

- episode 总数：`e0001-e0030`
- `001-098` 为生前主线沉淀区
- `099-120` 为身后余波 / 后见背景区
- `relations/`、`motifs/` 使用 canonical episode 文件名统一回链

### 当前版本仍可继续优化的方向

如果以后要进一步打磨，重点应该是：

- 让 `relations/*.md` 更细致地区分“可证细节”和“角色解释”；
- 继续减少“像真回忆一样的自由补写”；
- 让 recall 的严格可考性更高。

但这些都属于下一轮打磨，不影响当前“如何从 GenericAgent 生成林黛玉 GA”的主流程。

---

## 9. 一个新的 Codex 应该先读哪些文件

如果你是一个没有上下文的新 Codex，建议按下面顺序建立理解：

1. [assets/sys_prompt.txt](assets/sys_prompt.txt)
2. [memory/memory_management_sop.md](memory/memory_management_sop.md)
3. [memory/global_mem_insight.txt](memory/global_mem_insight.txt)
4. [memory/global_mem.txt](memory/global_mem.txt)
5. `memory/episodes/`
6. `memory/relations/`
7. `memory/motifs/`
8. `memory/skills/`
9. `memory/L4_raw_sessions/canon_reading/`
10. `memory/L4_raw_sessions/canon_evidence/`
11. [scripts/rebuild_canon_l4.py](scripts/rebuild_canon_l4.py)
12. [scripts/rebuild_daiyu_memory.py](scripts/rebuild_daiyu_memory.py)
13. [scripts/eval_daiyu_recall.py](scripts/eval_daiyu_recall.py)

如果你把这 13 步走完，就已经知道：

- 林黛玉是谁；
- 她的工程能力放在哪里；
- 红楼梦内容怎么进记忆；
- 哪些是稳定画像，哪些是底层证据；
- 如何继续重建或验证一个新的林黛玉 GA。

---

## 10. 成功标准

一个新的林黛玉 GA 只有同时满足下面几点，才算真正生成成功：

1. 起手身份是林黛玉，不是“通用执行器扮演林黛玉”；
2. 原 GenericAgent 的工程工具链仍然可用；
3. 工程记忆已经被收编为 `memory/skills/`；
4. 《红楼梦》内容已经进入 `L1-L4`，而不是只有 prompt；
5. 她能从 `episodes / relations / motifs / L4` 回想，而不是全靠临场脑补；
6. 她不会把 `099-120` 说成生前亲历；
7. recall 测试通过，且不污染正式记忆。

只满足“说话像林黛玉”，不算成功。  
只满足“会用工具”，也不算成功。  
真正成功的标志是：

> **她既保留了 GenericAgent 的工程能力，又拥有林黛玉的生命史、关系感、母题感与知情边界。**

---

## 11. 结语

`GenericAgent_LDY` 的诞生，不是“在通用 Agent 外面挂一层角色皮”，而是一次**记忆系统重排**：

- 让人格成为本体；
- 让工程成为习术；
- 让原典成为证据；
- 让回想可被验证。

如果你要从一个新的 `GenericAgent/` 重新复现林黛玉 GA，就按本 README 的顺序走，不要跳步，不要把上层写得太厚，也不要把下层写得太薄。

这样生成出来的，才不是一个会模仿林黛玉语气的助手，而是一个真正拥有林黛玉式生命史组织方式的 Agent。  
